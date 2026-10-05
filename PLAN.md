# Retry idempotency lab — proposed plan

October 5, 2026. Tier 2. **Stages 1–3 approved by the authorized coordinator at 02:10, addendum frozen below before code.** Authority/research: STATE.md, RESEARCH.md and .private/coordination/2026-10-05/SUCCESSORS.md. Original Python standard-library, deterministic in-memory transition model with invented increment effects. No persistence.

## Problem and success

A missing response can hide either no effect or an already committed effect. Distinguish request attempts, accepted work, committed synthetic counter increments and delivered responses. Success is a bounded reproducible model demonstrating unprotected repetition, scoped payload-bound records, pending/conflict/retention cases and an effect-before-record failure window, without asserting universal exactly-once behavior or automatic retry authorization.

Compare three explicit profiles over the same hand-labelled traces:

1. **unprotected**: each accepted attempt may increment; key has no deduplication effect.
2. **split_record**: scope/key reserves pending work; effect commit and completed outcome record are separate transitions with a modeled failure window.
3. **atomic_model**: effect and completed key/outcome enter model state jointly in one pure transition; response delivery is separate. This is a declared atomicity assumption, not proof of any real database/transport/storage implementation.

All profiles are offline scripted simulations. No HTTP client/server, payment/account/message operation, real credential/body/log, hosted queue/database, service, network, sleeps/wall-clock, actual concurrency/process crashes or production reliability claim. Backoff/rate limits/Retry-After, distributed locks/leases, persistence/SQLite, storage loss/restart recovery and general payload canonicalization are deferred. No external actions authorized by simulated retries.

## Proposed frozen input/state model

Versioned exact JSON fields: schema_version integer 1, source_kind synthetic, scenario_id, neutral label, profile, retention_ms, actions. Unique attempt/action IDs; visible ASCII identifier allowlist [A-Za-z0-9][A-Za-z0-9_.-]{0,63}. Payload is only positive integer delta 1–1000; booleans/floats rejected. This deliberately avoids nested-body/hash/canonicalization ambiguity. Scope is `(caller_id, operation_id, key)`; caller/operation are invented labels, not authentication. The only effect is an invented counter per `(caller_id, operation_id)`.

Every request also carries an `intent_id`: declared analyst oracle for counting repeat effects for an intended logical operation, **not** a server deduplication lookup or proof of intent. Report intent separately; different keys for the same intent can produce repeat effects. A key is bound to exact delta inside its scope while a record exists; key itself grants no identity/authorization.

Actions are explicit serial interleavings with nondecreasing synthetic integer time_ms 0–86,400,000, never host time. Equal times retain input order and do not model actual simultaneous scheduling. Proposed exact variants:

- **request**: action_id, time_ms, attempt_id, intent_id, caller_id, operation_id, key (ID or explicit null), delta. New accepted work becomes an active attempt. No effect is applied at acceptance. Duplicate/conflict/replay requests create no active work and cannot later be completed. Their generated synthetic status response is delivered in this initial model; response-loss injection is confined to completion.
- **complete**: action_id, time_ms, attempt_id, outcome, response_delivered (true boolean). Only an accepted active attempt can complete once. Outcomes: success, abort_before_effect, effect_without_record. Impossible references/recompletion/profile-cut combinations invalidate the entire scenario before output.

Whole input is structurally validated before simulation; semantic trace validation runs into fresh model state before any output. Reject malformed later actions even if an earlier retry was blocked. Fixed schema/action fields and precise profile/cut compatibility are stage-1 gate requirements before coding; no silent extra fields or bypasses.

Keys may be null: protected profiles explicitly report deduplication bypass and behave as unprotected for that attempt. Unprotected records are not used. Track separate attempt count, accepted count, committed effect count/delta, generated/delivered status responses, completed key records, pending/indeterminate records and per-intent repeat effects. Replay returns the **stored original outcome/counter snapshot**, not the current counter after other operations.

## Transition and failure semantics

### Approval addendum: exact counting and compatibility

Action objects include required `kind` equal to request or complete, in addition to the variant fields listed above. IDs are case-sensitive. Unfinished accepted attempts are valid at trace end: preserved as active/awaiting-response with zero committed effect so far and unknown client application outcome; never completed/dropped automatically. An effect_without_record completion consumes the active attempt but leaves its keyed record indeterminate; no modeled recovery can complete it again.

Per-intent grouping is `(caller_id, operation_id, intent_id)` and uses only analyst metadata. Changed deltas under the same declared intent are allowed, explicitly flagged payload_consistent=false with sorted declared deltas; this preserves body-conflict examples rather than masking them with schema rejection. No server decision uses intent metadata. Limits (128 actions/64 requests/64 commits/8 callers/8 operations) are global, not per scope; counters/count views are both global and per caller/operation. Effects bounded by 64*1000 delta.

Generated responses: each immediate replay/conflict/in_progress/indeterminate request generates one and delivers one, creating no active work. Newly accepted request generates no response yet. Success/abort completion generates one even when dropped; delivered count increases only for response_delivered=true. Effect_without_record generates/delivers zero and requires false. Client observation is unknown_application_outcome after any dropped completion, including zero-effect abort, and for unfinished work; replay observes a stored outcome, not a new commit. Generated/delivered count is distinct from model oracle effect counts.

Success/abort are valid for every accepted attempt. Effect_without_record is valid **only** for split_record, non-null key and response_delivered=false. Under unprotected or null-key bypass there is no keyed phase, so this cut is invalid; under atomic_model it is invalid by the declared joint-transition assumption. Only previously accepted still-active attempts can complete; repeat/block/replay requests never become completable. Entire invalid trace rejects output rather than continuing partially.

Completed records expire globally before each action at time>=completed_at+retention; count each removal, preserve prior effects, and do not expire pending/indeterminate records. Final records reflect the last action's synthetic time, without a future clock read. Same-time actions remain input-order interleavings. Replay retains the original counter snapshot even when current counters changed.

For protected keyed requests, expire only completed records at `now >= completed_at + retention_ms`, then look up scope/key. Expiry removes binding and cached outcome, not the prior committed effect. Reuse after expiry is a fresh attempt and can duplicate declared intent, even with the same payload. Different caller/operation scope does not collide.

Existing unexpired record with changed delta returns **conflict**, with no effect. Same delta completed record returns **replay**, with no new effect. Same delta pending returns **in_progress**, with no new effect. Same delta indeterminate returns **indeterminate**, no guessed response/effect. Scope/binding check precedes status reuse while a record exists.

Pending and indeterminate records have **no automatic lease expiry** in the initial model. This prevents pretending that a timed-out owner cannot later commit. It also explicitly limits liveness: no recovery/abandonment protocol is provided. Completed retention is not an in-flight lease. No shared operation/intent counter deduplication substitutes for a key.

`abort_before_effect` releases the keyed pending reservation and applies no counter effect. A delivered rejection states this modeled attempt applied nothing; a dropped rejection gives the client no such observation. `success` commits delta and records a fixed outcome (for keyed protected profiles), then delivery true/false determines client observation. Lost success response leaves committed state unchanged; a protected retained retry replays.

`effect_without_record` is a deliberate split_record failure window: increment effect, retain the key as **indeterminate**, produce no completed outcome. Require response_delivered false for this cut. Do not auto-rollback the effect, synthesize success or automatically retry it. Reject this cut under atomic_model because its declared joint transition has no such internal point. For unprotected attempts, use success with response_delivered false to demonstrate commit/response loss; no fake record phase.

Client observation after response loss is **unknown application outcome**, whether the model oracle shows zero or one commit. Report oracle state separately from client knowledge. Never upgrade timeout to failure/no effect. Conditional retained-key replay can avoid another modeled effect, but that is not universal exactly-once processing/delivery or physical crash durability.

Independently fixed scenarios: lost response after commit without key => two effects; retained scoped key => one effect/two generated outcomes; abort before effect then retry => one effect; body mismatch => conflict/no new effect; cross-caller or cross-operation same key => independent work; pending retry => in_progress; split gap => effect exists/client unknown/indeterminate block; exact retention boundary => new effect allowed; changed keys for same intent => repeat intent; replay counter snapshot differs from later current counter. Frozen expected counts must be hand-calculated before implementation.

## Architecture/tradeoffs

Bounded bytes/strict schema -> validate action shapes -> pure fresh-state transition simulation -> analyst/oracle/client views -> bounded deterministic JSON/Markdown -> stdout or exclusive new report. Exact input hash/model version/limits/assumptions retained. No global compliance score or recommendation to retry real operations. Input hash identifies bytes, not truth/authorization.

Standard dict/dataclass/int/json/unittest are sufficient; no external dependency or source copy. Reuse reviewed local bounded decoding/output/evidence patterns after approval, adapted to this schema. Candidate ASGI middleware is coupled to HTTP/backend dependencies, bare key reuse and unresolved BSD metadata conflict; do not adopt/fork it for this scope. Rate-limit accounting is a later distinct model; persistence would require separate transaction/crash evidence and explicit resource scope before implementation.

## Threat model and limits

Hostile inputs may exploit duplicate identity, bool-as-integer, malformed late actions, giant counters/trace expansion, report injection, output clobbering or optimistic retry conclusions. Predecode byte cap 65,536, nesting 12, numeric token 20; strings <=256 Unicode scalars, IDs <=64 ASCII chars, <=128 actions, <=64 requests/commits, <=8 callers and <=8 operations. Retention 1–86,400,000 ms. Bounded delta/count limits bound counters; no unbounded retry/backoff loop. Enumerate every admitted action; limit violations reject, never truncate into apparent success. These are admission/model bounds, not a hard RSS/time guarantee.

Reject duplicate JSON fields/action IDs/attempt IDs, unknown versions/fields, invalid references/order/time/profile cuts, nonfinite/floating numbers and invalid Unicode. Null key is explicit; missing key invalid. All supplied actions validated before rendering. Escape structured output, sanitize control/bidi/formatting in Markdown presentation, no HTML execution/raw terminal content. Output <=1 MiB, complete serialization before exclusive new-file publication; refuse existing input/output aliases and document pre/post-publication/cleanup/stdout failure limits. Trusted local regular input/directories/runtime/source; hostile directory races/special devices/power-loss and unauthenticated assumptions remain outside the model. No real data or external execution.

## Stages and verification

1. **Freeze contract and independent oracles**: exact schema/time/status/profile-cut rules, hand-calculated fixture counts, bounded parser and pure transitions. Done when complete provided/trace validation, pending/conflict/scope/expiry boundaries and oracle/client separation pass. No persistence/dependencies.
2. **Reports/CLI and scenario matrix**: all three profiles, bounded complete traces/counts/intent outcomes, deterministic JSON/Markdown and safe outputs. Done when missing responses never imply no application, stored replay snapshots stay distinct from current counter, and malformed late input emits no semantic partial report.
3. **Evidence/ECC/docs**: normal/optimized tests, focused key/body/scope/expiry/commit-response mutations with isolated copies and unchanged originals, available SAST, actual ECC self-review/fixes, full command/exit/hash/output capture, README/security/DECISIONS/LEARNING/license/AI disclosure/STATE and vault milestone. Done when approved local checks pass with explicit conditional/durability/hosted limits. No publication/repository creation under this plan.

Tests must cover every independent scenario above; new/bypass/replay/conflict/pending/indeterminate and stale snapshots; before/exact/after retention; in-progress never treated as expired completion; impossible/double complete and unknown reference; mixed scopes/changed keys/changed delta; response delivered versus model commit; abort versus split gap; equal times/script order; max limits/counters/output, duplicates/type/resource bounds, markup/control/privacy diagnostics, input immutability/determinism, exclusive aliases/competition/failure states and normal/-O guard behavior. Mutations should remove body/scope binding, use wrong expiry equality or conflate commit with delivery; count assertion failure, not setup/parser exceptions, as detection.

All three local stages approved with the frozen addendum above. Continue implementation/tests/review/docs within that scope. Single writer/new directory, preserve parent/shared tools/completed labs. No real HTTP/payments/accounts/messages/credentials, hosted queue/database/service, persistence/new repository, clock changes, new chats/schedulers, publication/merge or external messages. No new dispatch beyond 08:00 Eastern October 6.
