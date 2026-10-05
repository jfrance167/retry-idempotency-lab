# Retry / idempotency lab

An offline Python learning tool showing why a lost response does not tell a client whether an operation committed. It separates request attempts, accepted work, committed synthetic counter increments, generated responses and delivered responses. All inputs and effects are invented; the tool makes no HTTP calls or actual retries.

## Try it

Python 3.13.7 was verified on Windows; runtime uses only the standard library. From this directory, with your installed Python:

```powershell
python retry_model.py fixtures/unprotected-loss.json --format markdown
python retry_model.py fixtures/atomic-loss.json --format markdown
python retry_model.py fixtures/split-gap.json --output fresh-report.json
```

`--output` requires a new filename in an existing trusted directory. It refuses overwriting existing files, including the input. Default format is JSON; stdout is the default destination. Outputs include exact input SHA-256, assumptions, limits, per-action trace, attempts, scope counts/counters, declared intents and retained records.

The supplied demos produce these hand-calculated outcomes:

| Fixture / profile | Requests | Accepted | Effects | Responses generated / delivered | Retry result |
|---|---:|---:|---:|---:|---|
| unprotected-loss | 2 | 2 | 2 | 2 / 1 | Second attempt commits again |
| atomic-loss | 2 | 1 | 1 | 2 / 1 | Stored outcome replay, no second commit |
| split-gap | 2 | 1 | 1 | 1 / 1 | Indeterminate status; original outcome unknown to client |

In each example the first completion response is absent. The model oracle knows the effect count; the original client observation stays `unknown_application_outcome`. That observation also applies after a dropped zero-effect abort. A retained replay can communicate the stored result, but this does not establish universal exactly-once delivery or physical durability.

## Model and architecture

```text
Bounded UTF-8 JSON → strict complete schema → fresh serial state transitions
                  → whole-trace semantic validation → bounded JSON/Markdown
```

- `unprotected`: keys are ignored; each accepted attempt can commit.
- `split_record`: a scoped key reserves pending work. `effect_without_record` commits the effect but leaves an indeterminate record without a completed outcome.
- `atomic_model`: effect and completed outcome enter pure model state together. This is an explicit assumption, not evidence about a real database or crash boundary.

Records are keyed by `(caller_id, operation_id, key)` and bound to exact integer `delta`. A changed delta conflicts before any pending/completed/indeterminate status reuse. Completed same-payload requests replay the original outcome/counter snapshot; this may differ from the current counter after other work. Pending requests return `in_progress`; indeterminate requests stay indeterminate. Those immediate responses are delivered in this model and create no active work.

Completed records expire before each action when `time_ms >= completed_at + retention_ms`. Expiry removes the binding/outcome, so key reuse can commit again; prior effects remain. Pending and indeterminate records never expire or recover automatically. Equal timestamps retain input order, with no actual concurrent scheduling. An unfinished accepted attempt remains active at trace end with zero effect so far.

An explicit null key bypasses deduplication in protected profiles and creates no record. `intent_id` groups analyst-declared logical intent within caller/operation; server decisions never use it. Changed declared deltas are permitted and flagged inconsistent. Changing keys can repeat an intent; identifiers are case-sensitive invented labels, not authentication or proof of identity.

## Input contract

Root fields are all required and exact: `schema_version` (integer 1), `source_kind` (`synthetic`), `scenario_id`, `label`, `profile`, `retention_ms`, `actions`. No extra fields.

| Variant | Required exact fields |
|---|---|
| request | kind, action_id, time_ms, attempt_id, intent_id, caller_id, operation_id, key, delta |
| complete | kind, action_id, time_ms, attempt_id, outcome, response_delivered |

Request acceptance applies no effect yet. Completion must refer to a previously accepted, still-active attempt, once only. `success` commits delta and generates an outcome; `abort_before_effect` commits nothing, generates an outcome and releases any pending reservation. Response delivery is a separate required boolean. `effect_without_record` is valid only for a non-null keyed `split_record` attempt with `response_delivered=false`; it consumes the active attempt and leaves an indeterminate record. Completion of replayed/blocked/unknown/finished attempts is invalid.

IDs match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. Action IDs and request attempt IDs are unique. `label` must contain visible text. Time is synthetic nondecreasing integer milliseconds from 0 through 86,400,000; retention is 1 through 86,400,000. Delta is integer 1–1000; booleans are rejected as integers. All provided actions are structurally validated, then simulated into fresh state before rendering. Any late semantic error rejects the entire report.

Limits: 65,536 input bytes, nesting depth 12, numeric tokens 20 characters, strings 256 Unicode scalars, 128 actions, 64 requests/commits, 8 caller IDs and 8 operation IDs globally. Total committed delta is bounded by 64,000. Output is limited to 1 MiB. Duplicate JSON fields (including escaped aliases), floats/nonfinite numbers, invalid UTF-8/surrogates, missing/extra fields and bound violations reject rather than truncate. These are admission bounds, not measured hard memory/time guarantees.

## Outputs and failure behavior

`counts` includes global and per-scope requests/accepted/bypass accepts, effect commits/delta, responses generated/delivered, replay/conflict/in-progress/indeterminate responses and expired records. `final_state` counts unfinished attempts and pending/indeterminate/completed records. Per-intent repeat effects are `max(0, commits-1)`; they depend on supplied analyst metadata. JSON preserves the label with escaping; Markdown neutralizes controls, bidi/formatting characters and markup.

Complete serialization happens before publication. The output helper flushes a sibling temporary file, then uses an exclusive hard link and removes the temporary name. Hard-link support is required; there is no weaker overwrite fallback. File flushing does not prove crash/power-loss durability or protect against hostile directory changes. Use trusted local regular files/directories and inspect [SECURITY.md](SECURITY.md).

Exit 0 means completion; exit 2 means rejected input or failed output. Exit 3 explicitly means a complete report was published but temporary cleanup failed. A pre-publication cleanup failure returns 2 and can leave a temporary file. Preserve/inspect evidence; never assume nonzero exit proves no file exists. Stdout is not transactional and may contain partial output on write/encoding/flush failure. CLI paths are explicit local operator inputs; no real data should be supplied.

Reusable entry point: `retry_model.analyze(raw_bytes)` validates and returns the deterministic report dictionary, raising `bounded_io.InputError` for invalid input. `render(report, "json"|"markdown")` consumes a trusted analyzer report and returns bounded UTF-8 bytes. Internal `simulate()` expects validated data. See fixtures and [ORACLES.md](ORACLES.md) for the independent expected outcomes.

## Verification and learning

```powershell
python -W error -m unittest discover -s tests -v
python -O -W error -m unittest discover -s tests -v
python verify.py
```

October 5, 2026: **42 tests passed in each interpreter mode**, four Python files parsed, six JSON/Markdown demos passed, and four isolated mutations were detected by assertion failures. Installed Bandit reported zero findings/errors for the model, helper and verifier. `verify.py` additionally requires installed Bandit; it does not install packages or use networking. It saves commands, child exit codes, full output, original/mutant hashes and eight source/fixture/oracle hashes under ignored `verification-runs/`. It uses host UTC only for evidence-directory naming; the model uses supplied synthetic time only. Final receipt: `verification-runs/20261005T155220300427Z/report.json`.

See [VERIFICATION.md](VERIFICATION.md), [ECC_REVIEW.md](ECC_REVIEW.md), [DECISIONS.md](DECISIONS.md) and [LEARNING.md](LEARNING.md). ECC was an implementing-agent self-review, not an independent audit. No persistent service/database, real HTTP/concurrency/crash test, automatic retry/backoff, authentication, business payload canonicalization or pending-owner recovery is implemented.

## Repository checks

Jake authorized a separate private GitHub repository after local review. Pinned workflows provide tests/Bandit and a weekly/manual/push/PR CodeQL configuration. Repository Actions is disabled because included usage and private CodeQL eligibility could not be verified; **hosted checks have not run**. Nothing activates billing or purchased security features. Enable only after zero additional spending and licensing are verified. `requirements-dev.txt` pins the direct scanner version; transitive development dependencies are not hash-locked. Dependabot proposes updates for development requirements and Actions. Local operational STATE and full verification-run output remain ignored; the verification summary and frozen oracles are committed.

## Sources and attribution

[RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) defines idempotency around intended effect. The [IETF Idempotency-Key draft 07](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) was expired/archived when reviewed October 5, 2026; it is background, not an RFC or conformance target. This lab's record rules are explicit model conventions. [RESEARCH.md](RESEARCH.md) records the source inspection and upstream candidate license discrepancy. No candidate source or test vectors were adopted. Bounded I/O and verification patterns reuse our own reviewed timeline lab.

MIT license. AI assistance: Codex drafted, reviewed and verified the implementation/docs. A bounded local Ollama idea draft was truncated and overstated timeout/atomicity guarantees; rejected output was preserved separately. No remote worker output was used, no paid fallback or new spending. Test results support this bounded model only.
