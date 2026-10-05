"""Fixed local checks and isolated mutations; never changes original model source."""
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
# Only reviewed local interpreter/module/script commands; no shell or input code.
import subprocess  # nosec B404
import sys

ROOT = Path(__file__).resolve().parent


def execute(command, directory, stem):
    """Capture bounded fixed checks; preserve output and child exit code."""
    result = subprocess.run(command, cwd=directory, capture_output=True, timeout=60, shell=False)  # nosec B603
    stem.with_suffix(".stdout.txt").write_bytes(result.stdout)
    stem.with_suffix(".stderr.txt").write_bytes(result.stderr)
    return result


def main():
    run = ROOT / "verification-runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, exist_ok=False)
    sources = sorted([*ROOT.glob("*.py"), *ROOT.glob("tests/*.py"), *ROOT.glob("fixtures/*.json"), ROOT / "ORACLES.md"])
    hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    syntax = []
    for source in sources:
        if source.suffix == ".py":
            ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            syntax.append(source.relative_to(ROOT).as_posix())
    checks = []
    for name, mode in (("normal", []), ("optimized", ["-O"])):
        command = [sys.executable, *mode, "-W", "error", "-m", "unittest", "discover", "-s", "tests", "-v"]
        result = execute(command, ROOT, run / name)
        checks.append({"name": name, "command": command, "exit_code": result.returncode})
    demos = []
    for fixture in sorted(ROOT.glob("fixtures/*.json")):
        for format_name in ("json", "markdown"):
            command = [sys.executable, "retry_model.py", str(fixture.relative_to(ROOT)), "--format", format_name]
            result = execute(command, ROOT, run / (fixture.stem + "-" + format_name))
            demos.append({"command": command, "exit_code": result.returncode})
    mutations = []
    original = (ROOT / "retry_model.py").read_text(encoding="utf-8")
    for name, before, after, target in (
        ("payload-binding", 'if action["delta"] != record["delta"]:', 'if False:', "test_body_binding_conflict_and_intent_inconsistency"),
        ("scope-binding", 'scope_key = (*scope, action["key"]) if keyed else None', 'scope_key = ("global", "global", action["key"]) if keyed else None', "test_pending_scope_isolation_without_completion"),
        ("expiry-equality", 'now >= record["completed_at"] + data["retention_ms"]', 'now > record["completed_at"] + data["retention_ms"]', "test_before_exact_after_completed_expiry"),
        ("commit-response", 'if outcome != "abort_before_effect":', 'if outcome != "abort_before_effect" and action["response_delivered"]:', "test_atomic_loss_hand_oracle"),
    ):
        if original.count(before) != 1:
            raise RuntimeError("mutation anchor must be unique")
        directory = run / ("mutation-" + name)
        (directory / "tests").mkdir(parents=True, exist_ok=False)
        mutant = directory / "retry_model.py"
        mutant.write_text(original.replace(before, after, 1), encoding="utf-8")
        (directory / "bounded_io.py").write_bytes((ROOT / "bounded_io.py").read_bytes())
        (directory / "tests/test_retry.py").write_bytes((ROOT / "tests/test_retry.py").read_bytes())
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-k", target, "-v"]
        result = execute(command, directory, run / ("mutation-" + name))
        output = result.stderr.decode(errors="replace")
        detected = result.returncode == 1 and "FAIL: " + target in output and "AssertionError" in output and "ERROR:" not in output
        mutations.append({"name": name, "command": command, "exit_code": result.returncode,
                          "detected_assertion_failure": detected, "mutant_sha256": hashlib.sha256(mutant.read_bytes()).hexdigest()})
    sast_command = [sys.executable, "-m", "bandit", "-r", "retry_model.py", "bounded_io.py", "verify.py", "-f", "json"]
    sast = execute(sast_command, ROOT, run / "bandit")
    current = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in hashes}
    unchanged = hashes == current
    record = {"python": sys.version, "executable": sys.executable, "syntax": {"status": "PASS", "files": syntax},
              "tests": checks, "demos": demos, "mutations": mutations,
              "bandit": {"command": sast_command, "exit_code": sast.returncode},
              "source_sha256": hashes, "source_unchanged_after_mutations": unchanged,
              "limits": {"physical_atomicity_crash_recovery": "NOT APPLICABLE: pure model assumptions only",
                         "network_actual_retries": "NOT APPLICABLE: offline scope",
                         "CodeQL_hosted_CI": "NOT RUN: no standalone owned repository/publication"}}
    (run / "report.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(run / "report.json")
    print(json.dumps({"test_exit_codes": [c["exit_code"] for c in checks], "demo_count": len(demos),
                      "mutations_detected": [m["detected_assertion_failure"] for m in mutations],
                      "bandit_exit": sast.returncode, "source_unchanged": unchanged}))
    return 0 if all(c["exit_code"] == 0 for c in checks + demos) and all(m["detected_assertion_failure"] for m in mutations) and sast.returncode == 0 and unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
