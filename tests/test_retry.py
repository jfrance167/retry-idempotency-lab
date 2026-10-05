"""Independent count/transition oracles and strict input/output boundaries."""
import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bounded_io as bio
import retry_model as lab

ROOT = Path(__file__).resolve().parents[1]


def request(attempt="A", time=0, *, caller="lab", operation="increment", intent="intent", key="K", delta=1):
    return {"kind": "request", "action_id": "r" + attempt, "time_ms": time, "attempt_id": attempt,
            "intent_id": intent, "caller_id": caller, "operation_id": operation, "key": key, "delta": delta}


def complete(attempt="A", time=1, *, outcome="success", delivered=True):
    return {"kind": "complete", "action_id": "c" + attempt, "time_ms": time, "attempt_id": attempt,
            "outcome": outcome, "response_delivered": delivered}


def scenario(*actions, profile="atomic_model", retention=10):
    return {"schema_version": 1, "source_kind": "synthetic", "scenario_id": "test", "label": "Invented retry model",
            "profile": profile, "retention_ms": retention, "actions": list(actions)}


def encoded(data):
    return json.dumps(data).encode()


def analyze(data):
    return lab.analyze(encoded(data))


class ContractTests(unittest.TestCase):
    def reject(self, data):
        with self.assertRaises(bio.InputError):
            analyze(data)

    def test_root_version_source_and_profile(self):
        for key, values in (("schema_version", (True, 1.0, "1", 2)), ("source_kind", ("live", None)), ("profile", ("once", None, [])), ("retention_ms", (True, 0, 86400001))):
            for value in values:
                data = scenario()
                data[key] = value
                with self.subTest(key=key, value=value):
                    self.reject(data)

    def test_unknown_missing_fields_and_blank_label(self):
        data = scenario()
        data["hostname"] = "private"
        self.reject(data)
        del data["hostname"], data["profile"]
        self.reject(data)
        data = scenario()
        data["label"] = "\x1b\u202e"
        self.reject(data)

    def test_invalid_ids_and_null_missing_key(self):
        for field in ("action_id", "attempt_id", "intent_id", "caller_id", "operation_id", "key"):
            for value in ("bad|id", "a" * 65, 1, "\u0430"):
                action = request()
                action[field] = value
                self.reject(scenario(action))
        action = request()
        del action["key"]
        self.reject(scenario(action))
        self.assertEqual(analyze(scenario(request(key=None)))["counts"]["accepted"], 1)

    def test_delta_and_time_true_integer_bounds(self):
        for field, values in (("delta", (True, 0, 1001, "1")), ("time_ms", (True, -1, 86400001, "1"))):
            for value in values:
                action = request()
                action[field] = value
                self.reject(scenario(action))

    def test_variant_outcome_and_delivery(self):
        for value in ("invent", None, []):
            action = request()
            action["kind"] = value
            self.reject(scenario(action))
        for value in (1, "true", None):
            self.reject(scenario(request(), complete(delivered=value)))
        self.reject(scenario(request(), complete(outcome="timeout")))

    def test_duplicate_json_keys_and_escaped_alias(self):
        for raw in (b'{"a":1,"a":2}', br'{"a":1,"\u0061":2}', b'{"a":{"b":1,"b":2}}'):
            with self.assertRaises(bio.InputError):
                lab.analyze(raw)

    def test_duplicate_action_attempt_and_case_sensitive_ids(self):
        self.reject(scenario(request(), request(time=1)))
        action = request("B")
        action["action_id"] = "rA"
        self.reject(scenario(request(), action))
        self.assertEqual(analyze(scenario(request("A"), request("a", key="k")))["counts"]["accepted"], 2)

    def test_decreasing_time_rejected_equal_time_scripted(self):
        self.reject(scenario(request(time=2), complete(time=1)))
        result = analyze(scenario(request(time=0), complete(time=0), request("B", time=0)))
        self.assertEqual([row["status"] for row in result["trace"]], ["accepted", "success", "replay"])

    def test_global_request_caller_operation_and_action_limits(self):
        self.reject(scenario(*(request(f"A{i}", key=f"K{i}") for i in range(65))))
        self.reject(scenario(*(request(f"A{i}", caller=f"C{i}") for i in range(9))))
        self.reject(scenario(*(request(f"A{i}", operation=f"O{i}") for i in range(9))))
        data = scenario()
        data["actions"] = [{}] * 129
        self.reject(data)
        data["actions"] = None
        self.reject(data)

    def test_bytes_depth_tokens_nonfinite_and_bad_json(self):
        for raw in (b" " * 65537, b"[" * 13 + b"0" + b"]" * 13, b"\xff", b"\xef\xbb\xbf{}", b"{", b"{} {}", b"null", b'{"x":"\x01"}'):
            with self.assertRaises(bio.InputError):
                lab.analyze(raw)
        for number in ("1" * 21, "1.0", "1e999", "NaN", "Infinity", "-Infinity"):
            with self.assertRaises(bio.InputError):
                lab.analyze(('{"schema_version":' + number + '}').encode())

    def test_string_bounds_surrogates_and_quoted_scanner(self):
        data = scenario()
        for value in ("x" * 257, "\ud800"):
            data["label"] = value
            self.reject(data)
        data["label"] = "[" * 20 + "9" * 40 + '\\"' + "]" * 20
        self.assertEqual(analyze(data)["label"], data["label"])

    def test_invalid_complete_reference_recompletion_or_blocked(self):
        self.reject(scenario(complete()))
        second = complete(time=2)
        second["action_id"] = "second"
        self.reject(scenario(request(), complete(), second))
        self.reject(scenario(request(), complete(), request("B", time=2), complete("B", time=3)))
        self.reject(scenario(request(), request("B", time=1), complete("B", time=2)))
        self.reject(scenario(request(), complete(outcome="effect_without_record", delivered=False), request("B", time=2), complete("B", time=3), profile="split_record"))

    def test_exact_cut_profile_key_delivery_matrix(self):
        for profile in lab.PROFILES:
            for key in ("K", None):
                for delivered in (True, False):
                    data = scenario(request(key=key), complete(outcome="effect_without_record", delivered=delivered), profile=profile)
                    valid = profile == "split_record" and key is not None and not delivered
                    if valid:
                        self.assertEqual(analyze(data)["final_state"]["records_indeterminate"], 1)
                    else:
                        self.reject(data)

    def test_malformed_late_action_not_masked_by_early_block(self):
        action = request("C", time=3)
        action["delta"] = True
        self.reject(scenario(request(), request("B", time=2), action))
        self.reject(scenario(request(), request("B", time=2), complete("B", time=3)))


class ModelTests(unittest.TestCase):
    def check_counts(self, result, expected):
        for name, count in expected.items():
            self.assertEqual(result["counts"][name], count, name)

    def test_unprotected_loss_hand_oracle(self):
        result = analyze(scenario(request(), complete(delivered=False), request("B", time=2), complete("B", time=3), profile="unprotected"))
        self.check_counts(result, {"requests": 2, "accepted": 2, "effect_commits": 2, "effect_delta": 2, "responses_generated": 2, "responses_delivered": 1})
        self.assertEqual(result["intents"][0]["repeat_effects"], 1)
        self.assertEqual(result["attempts"][0]["client_observation"], "unknown_application_outcome")
        self.assertEqual(result["records"], [])

    def test_atomic_loss_hand_oracle(self):
        result = analyze(scenario(request(), complete(delivered=False), request("B", time=2)))
        self.check_counts(result, {"requests": 2, "accepted": 1, "effect_commits": 1, "responses_generated": 2, "responses_delivered": 1, "replay": 1})
        self.assertFalse(result["attempts"][1]["effect_committed"])
        self.assertEqual(result["trace"][-1]["response"]["counter"], 1)

    def test_abort_loss_client_unknown_but_oracle_zero(self):
        result = analyze(scenario(request(), complete(outcome="abort_before_effect", delivered=False), request("B", time=2), complete("B", time=3)))
        self.check_counts(result, {"requests": 2, "accepted": 2, "effect_commits": 1, "responses_generated": 2, "responses_delivered": 1})
        self.assertFalse(result["attempts"][0]["effect_committed"])
        self.assertEqual(result["attempts"][0]["client_observation"], "unknown_application_outcome")

    def test_body_binding_conflict_and_intent_inconsistency(self):
        result = analyze(scenario(request(), complete(), request("B", time=2, delta=2)))
        self.check_counts(result, {"requests": 2, "accepted": 1, "effect_commits": 1, "conflict": 1, "responses_generated": 2, "responses_delivered": 2})
        self.assertFalse(result["intents"][0]["payload_consistent"])
        self.assertEqual(result["intents"][0]["declared_deltas"], [1, 2])

    def test_pending_unfinished_no_retention_expiry(self):
        result = analyze(scenario(request(), request("B", time=20)))
        self.check_counts(result, {"requests": 2, "accepted": 1, "effect_commits": 0, "responses_generated": 1, "responses_delivered": 1, "in_progress": 1, "expired_records": 0})
        self.assertEqual(result["final_state"]["unfinished_attempts"], 1)
        self.assertEqual(result["final_state"]["records_pending"], 1)
        self.assertTrue(result["attempts"][0]["active"])

    def test_split_gap_indeterminate_not_completion(self):
        result = analyze(scenario(request(), complete(outcome="effect_without_record", delivered=False), request("B", time=20), profile="split_record"))
        self.check_counts(result, {"requests": 2, "accepted": 1, "effect_commits": 1, "responses_generated": 1, "responses_delivered": 1, "indeterminate": 1, "expired_records": 0})
        self.assertEqual(result["final_state"], {"unfinished_attempts": 0, "records_pending": 0, "records_indeterminate": 1, "records_completed": 0})
        self.assertIsNone(result["records"][0]["response"])

    def test_before_exact_after_completed_expiry(self):
        for now, status, expired in ((10, "replay", 0), (11, "accepted", 1), (12, "accepted", 1)):
            result = analyze(scenario(request(), complete(), request("B", time=now)))
            self.assertEqual(result["trace"][-1]["status"], status)
            self.assertEqual(result["counts"]["expired_records"], expired)
        result = analyze(scenario(request(), complete(), request("B", time=11), complete("B", time=12)))
        self.check_counts(result, {"requests": 2, "accepted": 2, "effect_commits": 2, "responses_generated": 2, "responses_delivered": 2, "expired_records": 1})

    def test_caller_and_operation_scope_isolation(self):
        result = analyze(scenario(request(caller="C1", operation="O1"), complete(), request("B", time=2, caller="C2", operation="O1"), complete("B", time=3), request("C", time=4, caller="C1", operation="O2"), complete("C", time=5)))
        self.check_counts(result, {"requests": 3, "accepted": 3, "effect_commits": 3, "responses_generated": 3, "responses_delivered": 3})
        self.assertEqual([row["counter"] for row in result["scopes"]], [1, 1, 1])
        self.assertEqual(len(result["intents"]), 3)

    def test_pending_scope_isolation_without_completion(self):
        result = analyze(scenario(request(caller="C1", operation="O1"), request("B", caller="C2", operation="O1"), request("C", caller="C1", operation="O2")))
        self.check_counts(result, {"requests": 3, "accepted": 3, "effect_commits": 0, "in_progress": 0})
        self.assertEqual(result["final_state"]["records_pending"], 3)

    def test_changed_key_same_intent_repeats_effect(self):
        result = analyze(scenario(request(), complete(), request("B", time=2, key="J"), complete("B", time=3)))
        self.assertEqual(result["counts"]["effect_commits"], 2)
        self.assertEqual(result["intents"][0]["repeat_effects"], 1)

    def test_replay_original_snapshot_not_current_counter(self):
        result = analyze(scenario(request(), complete(), request("B", time=2, key="J", delta=2), complete("B", time=3), request("C", time=4)))
        self.check_counts(result, {"requests": 3, "accepted": 2, "effect_commits": 2, "responses_generated": 3, "responses_delivered": 3})
        self.assertEqual(result["trace"][-1]["response"]["counter"], 1)
        self.assertEqual(result["scopes"][0]["counter"], 3)

    def test_null_key_bypass_hand_oracle(self):
        result = analyze(scenario(request(key=None), complete(delivered=False), request("B", time=2, key=None), complete("B", time=3)))
        self.check_counts(result, {"requests": 2, "accepted": 2, "bypass_accepts": 2, "effect_commits": 2, "responses_generated": 2, "responses_delivered": 1})
        self.assertEqual(result["records"], [])

    def test_intent_never_server_lookup(self):
        result = analyze(scenario(request(intent="one"), complete(), request("B", time=2, intent="different")))
        self.assertEqual(result["counts"]["replay"], 1)
        self.assertEqual(result["intents"][1]["effect_commits"], 1)  # sorted one after different

    def test_conflict_precedes_pending_indeterminate_status(self):
        result = analyze(scenario(request(), request("B", time=2, delta=2)))
        self.assertEqual(result["trace"][-1]["status"], "conflict")
        result = analyze(scenario(request(), complete(outcome="effect_without_record", delivered=False), request("B", time=2, delta=2), profile="split_record"))
        self.assertEqual(result["trace"][-1]["status"], "conflict")

    def test_expiry_global_before_other_scope_action(self):
        result = analyze(scenario(request(), complete(), request("B", time=11, caller="other")))
        self.assertEqual(result["counts"]["expired_records"], 1)
        self.assertEqual(result["scopes"][0]["counts"]["expired_records"], 1)

    def test_max_counts_and_scope_sums(self):
        actions = []
        for i in range(64):
            actions.extend([request(str(i), time=0, key=f"K{i}", delta=1000), complete(str(i), time=0)])
        result = analyze(scenario(*actions))
        self.assertEqual(len(result["trace"]), 128)
        self.check_counts(result, {"requests": 64, "accepted": 64, "effect_commits": 64, "effect_delta": 64000, "responses_generated": 64, "responses_delivered": 64})
        for key in lab.COUNT_KEYS:
            self.assertEqual(sum(row["counts"][key] for row in result["scopes"]), result["counts"][key])
        self.assertLessEqual(len(lab.render(result, "json")), bio.MAX_OUTPUT)

    def test_empty_and_unprotected_unfinished(self):
        result = analyze(scenario())
        self.assertEqual(set(result["counts"].values()), {0})
        result = analyze(scenario(request(), profile="unprotected"))
        self.assertEqual(result["final_state"]["unfinished_attempts"], 1)
        self.assertEqual(result["records"], [])

    def test_deterministic_input_immutability_and_hash(self):
        data = scenario(request(), complete(), request("B", time=2))
        before = copy.deepcopy(data)
        first = analyze(data)
        self.assertEqual(first, analyze(data))
        self.assertEqual(data, before)
        self.assertEqual(first["input_sha256"], hashlib.sha256(encoded(data)).hexdigest())
        self.assertEqual(first["actual_delivery_guarantee"], "not_established")

    def test_report_markup_controls_preservation_and_bounds(self):
        data = scenario()
        data["label"] = '<script>x</script>\n| [x](https://bad.example)\x1b\u202e'
        result = analyze(data)
        self.assertEqual(json.loads(lab.render(result, "json"))["label"], data["label"])
        text = lab.render(result, "markdown").decode()
        self.assertNotIn("<script>", text)
        self.assertNotIn("[x](", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\u202e", text)
        with patch.object(bio, "MAX_OUTPUT", 10), self.assertRaises(bio.InputError):
            lab.render(result, "json")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".test-retry-", dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "input.json"
        self.source.write_bytes(encoded(scenario(request(), complete())))
        self.target = self.root / "report.json"

    def test_exclusive_complete_file_and_alias(self):
        original = self.source.read_bytes()
        with self.assertRaises(bio.InputError):
            bio.write_new(self.source, b"bad", input_path=self.source)
        os.link(self.source, self.target)
        with self.assertRaises(bio.InputError):
            bio.write_new(self.target, b"bad", input_path=self.source)
        self.assertEqual(self.source.read_bytes(), original)
        other = self.root / "new.json"
        bio.write_new(other, b"complete")
        with self.assertRaises(bio.InputError):
            bio.write_new(other, b"bad")
        self.assertEqual(other.read_bytes(), b"complete")

    def test_competing_output_preserved(self):
        link = os.link
        def competitor(source, target):
            Path(target).write_bytes(b"other")
            return link(source, target)
        with patch.object(bio.os, "link", side_effect=competitor), self.assertRaises(FileExistsError):
            bio.write_new(self.target, b"ours")
        self.assertEqual(self.target.read_bytes(), b"other")

    def test_link_flush_failure_and_output_limits(self):
        for method in ("link", "fsync"):
            with patch.object(bio.os, method, side_effect=OSError("synthetic")), self.assertRaises(OSError):
                bio.write_new(self.target, b"complete")
            self.assertFalse(self.target.exists())
            self.assertEqual(list(self.root.glob("*.tmp")), [])
        with self.assertRaises(bio.InputError):
            bio.write_new(self.target, b"x" * 1048577)
        with self.assertRaises(OSError):
            bio.write_new(self.root / "missing" / "report", b"bytes")

    def test_post_publication_cleanup_warning(self):
        errors = io.StringIO()
        with patch.object(bio.Path, "unlink", side_effect=PermissionError("synthetic")), contextlib.redirect_stderr(errors):
            code = lab.main([str(self.source), "--output", str(self.target)])
        self.assertEqual(code, 3)
        self.assertIn("Complete report published", errors.getvalue())
        self.assertEqual(json.loads(self.target.read_bytes())["counts"]["effect_commits"], 1)

    def test_pre_publication_cleanup_state(self):
        with patch.object(bio.os, "link", side_effect=OSError("synthetic")), patch.object(bio.Path, "unlink", side_effect=PermissionError("synthetic")), self.assertRaises(bio.OutputCleanupError) as caught:
            bio.write_new(self.target, b"complete")
        self.assertFalse(caught.exception.published)
        self.assertFalse(self.target.exists())

    def test_late_semantic_invalid_trace_no_output(self):
        self.source.write_bytes(encoded(scenario(request(), complete(), request("B", time=2), complete("B", time=3))))
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = lab.main([str(self.source), "--output", str(self.target)])
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(self.target.exists())
        self.assertNotIn(str(self.source), errors.getvalue())

    def test_cli_normal_or_optimized_and_overwrite_refusal(self):
        command = [sys.executable, *(["-O"] if sys.flags.optimize else []), str(ROOT / "retry_model.py"), str(self.source), "--output", str(self.target)]
        first = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.target.read_bytes()
        self.assertEqual(subprocess.run(command, capture_output=True, timeout=10).returncode, 2)
        self.assertEqual(self.target.read_bytes(), before)

    def test_missing_or_oversized_input_redaction(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(lab.main([str(self.root / "private-name")]), 2)
        self.assertNotIn("private-name", errors.getvalue())
        self.source.write_bytes(b" " * 65537)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(lab.main([str(self.source)]), 2)

    def test_ascii_encoding_short_stdout_and_flush_errors(self):
        data = scenario()
        data["label"] = "安全"
        self.source.write_bytes(encoded(data))
        output = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        self.addCleanup(output.close)
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(lab.main([str(self.source), "--format", "markdown"]), 2)
        self.assertEqual(errors.getvalue(), "Rejected: output encoding failure\n")
        class ShortWriter(io.StringIO):
            def write(self, text):
                return super().write(text[:-1])
        class BadFlush(io.StringIO):
            def flush(self):
                raise OSError("private detail")
        for output in (ShortWriter(), BadFlush()):
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                self.assertEqual(lab.main([str(self.source)]), 2)
            self.assertEqual(errors.getvalue(), "Rejected: OSError\n")


if __name__ == "__main__":
    unittest.main()
