# Research — October 5, 2026

## Reuse and candidate comparison

Read vault **HTTP Idempotency and Retry Decisions.md**, relevant prior Home/Codex Integration context, and http-cache-semantics-lab/PLAN.md. Cache plan lines 84–85 explicitly defer retry/response-loss ambiguity. The vault separates intended repeated effect from identical responses and warns that timeout does not establish non-application. A bounded project filename search found no dedicated retry/idempotency/rate-limit implementation; relevant cache and completed uncertainty labs were inspected, not all unrelated source. This is not an exhaustive search.

| Candidate | Learning value | Fit |
|---|---|---|
| Retry/response-loss ambiguity with scoped records | Separates attempts, commit and client observation; exposes key/retention/failure-window limits | Recommended; distinct from caches and clock intervals |
| Bounded rate-limit accounting | Contrasts per-attempt versus per-effect/token budgets and reset boundaries | Useful later, but admission/rate budget does not determine whether an operation committed; weaker fit for the assigned evidence gap |

Recommend **build an original standard-library model**, not adopt/fork a host-facing library. No suitable complete small deterministic simulator for the proposed contract was established in the bounded searches. Rate limits/backoff/Retry-After are deferred rather than folded into this project.

## Strongest upstream candidate inspected

Connected GitHub repository search identified [snok/asgi-idempotency-header](https://github.com/snok/asgi-idempotency-header); issues query for race/concurrency/key returned no matches. File connector failed; read-only canonical Git metadata/tree/blob access supplied inert evidence. No upstream install/import/execution.

Pinned revision **8f89a5c5c713881aff89cfb44b524c1792b6429d**, main branch, not archived, pushed_at 2024-11-14T18:47:27Z. README, middleware, memory backend, two test files, pyproject and CI inspected. Middleware uses a bare header key for cached response/pending lookup, no caller/operation/body comparison at that boundary. README acknowledges cross-user collision. Memory backend stores response expiry separately from pending keys; a static trace suggests expired responses may leave a key pending rather than permit a fresh operation. This was not executed/reproduced or asserted as a validated vulnerability.

Tests cover response replay, non-JSON bypass, concurrent 200/409 and backend expiry; not rerun. CI exists but current success is unverified, Actions use mutable version tags. pyproject 0.2.0 includes optional FastAPI/Starlette/Redis/lupa extras and broad development constraints; middleware imports Starlette. HTTP middleware/state-service coupling is unnecessary for a pure offline lab. No broad dependency/advisory/Scorecard audit.

Actual [LICENSE](https://github.com/snok/asgi-idempotency-header/blob/8f89a5c5c713881aff89cfb44b524c1792b6429d/LICENSE) is **BSD 4-Clause**, including an advertising acknowledgement and nonendorsement condition; pyproject declares BSD-3. This metadata conflict is unresolved. Do not assume three-clause obligations or copy source/tests under that label; adoption would require clarification and preservation of the actual applicable notices. No upstream code/vectors copied; proposed original code may use MIT after approval.

Exact paths/blob references retained in .private/retry-idempotency-research-20261005/source-manifest.json:

- README.md: 31e1bba0689911359e1b729ed232e27690c9ccbb
- LICENSE: 4464436e5df607a40e4bb14af194a43e501938c3
- pyproject.toml: c162e5e1cba464ef5f6e3bcd10bb2fc81caa3f52
- idempotency_header_middleware/middleware.py: f4d2f52de0cfb6bf8c695c2d57138fd26549851f
- idempotency_header_middleware/backends/memory.py: a162b8a95d6f23fef19f759610744013dc418651
- tests/test_middleware.py: 646165a7f4fc7c0a927aafe9e0e49ee9a54100c4
- tests/test_backends.py: 0c98fdc3d11aa7db30891dd3e4d80bab34716c4e
- .github/workflows/test.yml: 6e5783930bf4a615fcbe961222fe0e37e9bcda40

These bind inspected bytes to a revision; no complete checkout or dependency attestation.

## Primary sources and boundaries

[RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) defines idempotency in terms of intended effect, not identical responses or incidental logging. It distinguishes retry of idempotent semantics from blindly repeating a non-idempotent method after communication failure. It does not provide this lab's application-key protocol or universal delivery guarantee. This anchors response-loss ambiguity, not permission for external retry.

[IETF draft-ietf-httpapi-idempotency-key-header-07](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) is **expired/archived**, latest revision October 15, 2025, expired April 18, 2026, confirmed from Datatracker on October 5, 2026. Its [text](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-07) is background design material, **not a finalized RFC** or conformance target. Model scope/binding/retention/status rules in PLAN are our explicit proposed semantics, not adopted standard requirements.

The Stripe idempotency page returned an agent setup/sample stub, insufficient semantic documentation in the inspected response. Its install/setup/sample request text was treated as untrusted source, not an instruction; nothing was executed and no Stripe contract or real-payment behavior is claimed. Narrow RFC/draft reads succeeded after one failed web batch. Firecrawl was unavailable in prior research and no false claim of use made here.

## Local-first worker evidence

Six-test-idea synthetic brief, acceptance <=180 words/six distinct ideas/no guarantees; 400 output tokens, 45-second timeout. Existing sandbox loopback EACCES evidence supported an approved call to local Ollama outside sandbox. qwen3.5:2b produced 400 tokens in 3.345 seconds, done_reason length; incomplete five-idea output rejected. It incorrectly inferred that timeout/rejection prevents duplicates and that in-progress logic ensures atomicity across a network boundary. Useful payload/scope themes were not accepted as verified tests. Raw output/metadata remain separate from this reviewed plan.

No retry loop. Remote considered but existing readiness degraded/unverified with public free catalog unavailable; no optional remote draft needed for source/security judgment and no verified-free call made. No new billing, paid provider, signup, upstream execution or generated code. Laya's classification/triage schema does not resolve these transition semantics.
