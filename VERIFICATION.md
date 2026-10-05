# Verification — October 5, 2026

Final receipt: verification-runs/20261005T155220300427Z/report.json. Run with installed Python 3.13.7 on Windows, `python verify.py`, exit 0. Full per-command stdout/stderr, commands and child codes are retained beside the receipt. No source changed during mutations. Evidence hashes cover four Python files, three fixtures and frozen ORACLES.md.

| Check | Outcome | Evidence |
|---|---|---|
| Syntax AST parsing | PASS, 4 files | receipt syntax.files |
| `python -W error -m unittest discover -s tests -v` | PASS, 42 tests, exit 0 | normal.stderr.txt |
| `python -O -W error -m unittest discover -s tests -v` | PASS, 42 tests, exit 0 | optimized.stderr.txt |
| Three fixtures, JSON and Markdown CLI | PASS, 6 commands, each exit 0 | fixture-format stdout/stderr |
| Payload-binding mutation | PASS detection: mutant exit 1, target assertion failure | mutation-payload-binding.stderr.txt |
| Scope-binding mutation | PASS detection: mutant exit 1, target assertion failure | mutation-scope-binding.stderr.txt |
| Completed-expiry equality mutation | PASS detection: mutant exit 1, target assertion failure | mutation-expiry-equality.stderr.txt |
| Commit/response conflation mutation | PASS detection: mutant exit 1, target assertion failure | mutation-commit-response.stderr.txt |
| Installed Bandit scan of retry_model.py, bounded_io.py, verify.py | PASS, exit 0, zero findings/errors | bandit.stdout.txt |
| ECC actual-change self-review | Complete, zero actionable defects identified | ECC_REVIEW.md |
| Physical storage/HTTP/concurrency/crash/live retry | NOT APPLICABLE, outside pure-model scope | explicit model assumptions |
| Hosted CI/CodeQL | NOT RUN, Actions disabled pending zero-spend/private eligibility verification | pre-push review in ECC_REVIEW.md |

Tests cover frozen count oracles, false client certainty, scope/body/key rules, abort/pending/gap handling, retention boundaries, immutable replay snapshots, whole-trace errors, exact profile/key/delivery cut matrix, global maximum bounds, duplicate fields/IDs, strict types/Unicode, report escaping, output aliases/competition, fsync/link/cleanup failures and stdout encoding/short-write/flush errors. Mutation success requires an actual AssertionError with no setup/parser ERROR; copies live only in the ignored evidence directory.

Bandit excludes test code from its scan; test subprocesses run fixed local CLI checks. Two narrowly explained suppressions in verify.py cover the subprocess import and fixed no-shell invocation, not analyzer code. Bandit is a local heuristic scan, not a comprehensive audit. No coverage percentage, dependency attestation, cross-platform certification or independent review claimed.

Earlier 41-test normal run passed without final capture. Two verifier execution requests were automatically rejected before running because authorization was not accepted from coordinator retrieval; Jake subsequently said continue here. The actual successful final run replaces NOT RUN status, while rejection history remains in STATE.md. Approval outside the filesystem sandbox enabled synthetic hard-link tests only; no Windows elevation, host audit change or network/real operation was performed.

Subsequent repository review: staged publication contains only this lab, without local operational state or full run output. Three YAML files checked, immutable official Action commits verified, eight original evidence hashes matched and narrow staged credential scan had zero matches. Two new workflow defects were fixed and checks rerun; see ECC_REVIEW.md. No model/source behavior changed. Bandit has no third-party runtime counterpart; its direct development version is pinned, but transitive development dependencies are not hash-locked.
