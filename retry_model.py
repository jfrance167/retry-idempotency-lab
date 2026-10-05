"""Scripted synthetic attempts, committed effects and client observations."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import bounded_io as bio

MODEL = "scripted-scoped-records/v1"
MAX_ACTIONS = 128
MAX_REQUESTS = 64
MAX_CALLERS = MAX_OPERATIONS = 8
MAX_TIME = 86400000
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
PROFILES = ("unprotected", "split_record", "atomic_model")
COUNT_KEYS = ("requests", "accepted", "bypass_accepts", "effect_commits", "effect_delta", "responses_generated",
              "responses_delivered", "replay", "conflict", "in_progress", "indeterminate", "expired_records")


def identity(value):
    if type(value) is not str or not ID.fullmatch(value):
        raise bio.InputError("invalid synthetic ID")


def integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise bio.InputError("integer required within declared bounds; booleans rejected")


def validate(raw):
    """Validate every provided action before semantic simulation/output."""
    data = bio.decode(raw)
    bio.fields(data, ("schema_version", "source_kind", "scenario_id", "label", "profile", "retention_ms", "actions"))
    integer(data["schema_version"], 1, 1)
    if data["source_kind"] != "synthetic" or type(data["profile"]) is not str or data["profile"] not in PROFILES:
        raise bio.InputError("unsupported source kind or profile")
    identity(data["scenario_id"])
    if type(data["label"]) is not str or not bio.visible(data["label"]).strip():
        raise bio.InputError("nonempty neutral label required")
    integer(data["retention_ms"], 1, MAX_TIME)
    actions = data["actions"]
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise bio.InputError("action count limit exceeded or invalid list")
    action_ids, attempt_ids, callers, operations = set(), set(), set(), set()
    previous_time = 0
    for action in actions:
        if type(action) is not dict or type(action.get("kind")) is not str:
            raise bio.InputError("invalid action variant")
        if action["kind"] == "request":
            bio.fields(action, ("kind", "action_id", "time_ms", "attempt_id", "intent_id", "caller_id", "operation_id", "key", "delta"))
            for field in ("intent_id", "caller_id", "operation_id"):
                identity(action[field])
            if action["key"] is not None:
                identity(action["key"])
            integer(action["delta"], 1, 1000)
            callers.add(action["caller_id"])
            operations.add(action["operation_id"])
            identity(action["attempt_id"])
            if action["attempt_id"] in attempt_ids:
                raise bio.InputError("duplicate request attempt ID")
            attempt_ids.add(action["attempt_id"])
            if len(attempt_ids) > MAX_REQUESTS or len(callers) > MAX_CALLERS or len(operations) > MAX_OPERATIONS:
                raise bio.InputError("global request/caller/operation limit exceeded")
        elif action["kind"] == "complete":
            bio.fields(action, ("kind", "action_id", "time_ms", "attempt_id", "outcome", "response_delivered"))
            if type(action["outcome"]) is not str or action["outcome"] not in ("success", "abort_before_effect", "effect_without_record"):
                raise bio.InputError("unsupported completion outcome")
            if type(action["response_delivered"]) is not bool:
                raise bio.InputError("response_delivered must be a boolean")
        else:
            raise bio.InputError("unsupported action kind")
        identity(action["attempt_id"])
        identity(action["action_id"])
        integer(action["time_ms"], 0, MAX_TIME)
        if action["time_ms"] < previous_time:
            raise bio.InputError("synthetic action times decrease")
        previous_time = action["time_ms"]
        if action["action_id"] in action_ids:
            raise bio.InputError("duplicate action ID")
        action_ids.add(action["action_id"])
    return data


def simulate(data, digest):
    """Pure validated trace; server decisions never use declared intent metadata."""
    counts = dict.fromkeys(COUNT_KEYS, 0)
    scopes, attempts, records, counters, intents = {}, {}, {}, {}, {}
    effects, trace = [], []
    profile = data["profile"]

    def bump(name, scope, amount=1):
        counts[name] += amount
        scopes[scope][name] += amount

    for action in data["actions"]:
        now = action["time_ms"]
        expired = [scope_key for scope_key, record in records.items()
                   if record["state"] == "completed" and now >= record["completed_at"] + data["retention_ms"]]
        for scope_key in expired:
            del records[scope_key]
            bump("expired_records", scope_key[:2])
        if action["kind"] == "request":
            scope = (action["caller_id"], action["operation_id"])
            scopes.setdefault(scope, dict.fromkeys(COUNT_KEYS, 0))
            counters.setdefault(scope, 0)
            bump("requests", scope)
            intent_key = (*scope, action["intent_id"])
            intent = intents.setdefault(intent_key, {"deltas": set(), "commits": 0, "effect_delta": 0})
            intent["deltas"].add(action["delta"])
            keyed = profile != "unprotected" and action["key"] is not None
            scope_key = (*scope, action["key"]) if keyed else None
            record = records.get(scope_key) if keyed else None
            status, response = "accepted", None
            if record is not None:
                if action["delta"] != record["delta"]:
                    status = "conflict"
                elif record["state"] == "completed":
                    status, response = "replay", dict(record["response"])
                elif record["state"] == "pending":
                    status = "in_progress"
                else:
                    status = "indeterminate"
            if status == "accepted":
                bump("accepted", scope)
                if profile != "unprotected" and action["key"] is None:
                    bump("bypass_accepts", scope)
                if keyed:
                    records[scope_key] = {"state": "pending", "delta": action["delta"], "owner": action["attempt_id"],
                                          "completed_at": None, "response": None}
            else:
                bump(status, scope)
                bump("responses_generated", scope)
                bump("responses_delivered", scope)
                if response is None:
                    response = {"outcome": status}
            attempt = {"attempt_id": action["attempt_id"], "caller_id": scope[0], "operation_id": scope[1],
                       "intent_id": action["intent_id"], "key": action["key"], "delta": action["delta"],
                       "status": status, "active": status == "accepted", "effect_committed": False,
                       "response": response, "response_delivered": status != "accepted",
                       "client_observation": "unknown_application_outcome" if status == "accepted" else status + "_observed"}
            attempts[action["attempt_id"]] = attempt
            trace.append({"action_id": action["action_id"], "kind": "request", "time_ms": now,
                          "attempt_id": action["attempt_id"], "status": status, "response": response,
                          "response_delivered": status != "accepted", "effect_delta": 0,
                          "client_observation": attempt["client_observation"]})
        else:
            attempt = attempts.get(action["attempt_id"])
            if attempt is None or not attempt["active"]:
                raise bio.InputError("complete must target a previously accepted still-active attempt")
            scope = (attempt["caller_id"], attempt["operation_id"])
            keyed = profile != "unprotected" and attempt["key"] is not None
            scope_key = (*scope, attempt["key"]) if keyed else None
            outcome = action["outcome"]
            if outcome == "effect_without_record" and (profile != "split_record" or not keyed or action["response_delivered"]):
                raise bio.InputError("failure cut incompatible with profile/key/delivery")
            response = None
            if outcome != "abort_before_effect":
                counters[scope] += attempt["delta"]
                bump("effect_commits", scope)
                bump("effect_delta", scope, attempt["delta"])
                intent = intents[(*scope, attempt["intent_id"])]
                intent["commits"] += 1
                intent["effect_delta"] += attempt["delta"]
                effects.append({"attempt_id": attempt["attempt_id"], "caller_id": scope[0], "operation_id": scope[1],
                                "intent_id": attempt["intent_id"], "delta": attempt["delta"], "time_ms": now, "counter_after": counters[scope]})
                attempt["effect_committed"] = True
            if outcome == "effect_without_record":
                records[scope_key]["state"] = "indeterminate"
            else:
                response = {"outcome": outcome, "counter": counters[scope], "origin_attempt_id": attempt["attempt_id"]}
                bump("responses_generated", scope)
                if action["response_delivered"]:
                    bump("responses_delivered", scope)
                if keyed:
                    if outcome == "abort_before_effect":
                        del records[scope_key]
                    else:
                        # Pure model joint transition; this is not physical durability.
                        records[scope_key].update(state="completed", completed_at=now, response=dict(response))
            attempt.update(active=False, status=outcome, response=response, response_delivered=action["response_delivered"],
                           client_observation=outcome + "_observed" if action["response_delivered"] else "unknown_application_outcome")
            trace.append({"action_id": action["action_id"], "kind": "complete", "time_ms": now, "attempt_id": attempt["attempt_id"],
                          "status": outcome, "response": response, "response_delivered": action["response_delivered"],
                          "effect_delta": 0 if outcome == "abort_before_effect" else attempt["delta"],
                          "client_observation": attempt["client_observation"]})

    intent_rows = [{"caller_id": key[0], "operation_id": key[1], "intent_id": key[2],
                    "declared_deltas": sorted(value["deltas"]), "payload_consistent": len(value["deltas"]) == 1,
                    "effect_commits": value["commits"], "effect_delta": value["effect_delta"],
                    "repeat_effects": max(0, value["commits"] - 1)} for key, value in sorted(intents.items())]
    final = {"unfinished_attempts": sum(attempt["active"] for attempt in attempts.values()),
             "records_pending": sum(record["state"] == "pending" for record in records.values()),
             "records_indeterminate": sum(record["state"] == "indeterminate" for record in records.values()),
             "records_completed": sum(record["state"] == "completed" for record in records.values())}
    return {"report_version": 1, "model": MODEL, "scenario_id": data["scenario_id"], "source_kind": "synthetic",
            "label": data["label"], "profile": profile, "retention_ms": data["retention_ms"], "input_sha256": digest,
            "counts": counts, "final_state": final, "trace": trace, "effects": effects,
            "attempts": list(attempts.values()), "intents": intent_rows,
            "scopes": [{"caller_id": scope[0], "operation_id": scope[1], "counter": counters[scope], "counts": value} for scope, value in sorted(scopes.items())],
            "records": [{"caller_id": key[0], "operation_id": key[1], "key": key[2], **value} for key, value in sorted(records.items())],
            "actual_delivery_guarantee": "not_established", "assumptions": [
                "Script order and synthetic time are supplied interleavings, not measured concurrency or host time.",
                "Atomic_model assumes joint pure-state effect/outcome commit; it proves no physical durability or exactly-once delivery.",
                "Keys are scoped to caller/operation and exact delta while records exist; keys/intent labels are not authentication.",
                "Intent grouping is analyst metadata only; inconsistent deltas are visible, never a server deduplication decision.",
                "Completed records expire at equality; pending/indeterminate records never expire or recover automatically.",
                "Dropped completion response leaves client outcome unknown even when the model oracle knows an effect or abort.",
                "Replay uses the stored original outcome/counter, not a current-state query or new effect.",
                "Unfinished work remains active, never silently applied or discarded; counters bound effects so far.",
                "Hash identifies input bytes, not truth or authorization to retry an actual operation."],
            "limits": {"input_bytes": bio.MAX_BYTES, "depth": bio.MAX_DEPTH, "numeric_token_chars": bio.MAX_NUMBER,
                       "string_chars": bio.MAX_STRING, "actions": MAX_ACTIONS, "requests_commits": MAX_REQUESTS,
                       "callers": MAX_CALLERS, "operations": MAX_OPERATIONS, "counter_total": 64000, "output_bytes": bio.MAX_OUTPUT}}


def analyze(raw):
    return simulate(validate(raw), hashlib.sha256(raw).hexdigest())


def render(report, format_name):
    if format_name == "json":
        text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    elif format_name == "markdown":
        lines = ["# Synthetic retry/idempotency model", "", "Actual delivery guarantee: **not established**.", "",
                 "Label: " + bio.markdown(report["label"]), "Profile: " + bio.markdown(report["profile"]),
                 "Input SHA-256: " + bio.markdown(report["input_sha256"]), "", "Counts:", "",
                 "```json", json.dumps({"counts": report["counts"], "final_state": report["final_state"]}, sort_keys=True), "```", "",
                 "| Action | Attempt | Status | Effect delta | Response delivered | Client observation |", "|---|---|---|---|---|---|"]
        for row in report["trace"]:
            lines.append("| " + " | ".join(bio.markdown(str(row[key])) for key in ("action_id", "attempt_id", "status", "effect_delta", "response_delivered", "client_observation")) + " |")
        for name in ("attempts", "scopes", "intents", "records"):
            lines.extend(["", "## " + name.title(), "", "```json", json.dumps(report[name], ensure_ascii=True, sort_keys=True), "```"])
        lines.extend(["", "Assumptions and limits:", "", *("- " + item for item in report["assumptions"]), "", *(f"- {key}: {value}" for key, value in report["limits"].items())])
        text = "\n".join(lines) + "\n"
    else:
        raise bio.InputError("unsupported report format")
    result = text.encode("utf-8")
    if len(result) > bio.MAX_OUTPUT:
        raise bio.InputError("output byte limit exceeded")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="exclusive new file only")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as handle:
            raw = handle.read(bio.MAX_BYTES + 1)
        result = render(analyze(raw), args.format)
        if args.output:
            bio.write_new(args.output, result, input_path=args.input)
        else:
            text = result.decode("utf-8")
            if sys.stdout.write(text) != len(text):
                raise OSError("short stdout write")
            sys.stdout.flush()
        return 0
    except bio.OutputCleanupError as exc:
        print("Complete report published; temporary cleanup failed." if exc.published else "Report not published; temporary cleanup failed.", file=sys.stderr)
        return 3 if exc.published else 2
    except UnicodeError:
        print("Rejected: output encoding failure", file=sys.stderr)
        return 2
    except (bio.InputError, OSError) as exc:
        print("Rejected: " + (str(exc) if isinstance(exc, bio.InputError) else type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
