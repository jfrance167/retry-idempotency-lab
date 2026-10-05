# Learning

- A missing response gives the client an unknown application outcome. The simulator can know zero effects after a dropped abort or one after dropped success; that oracle knowledge was not delivered to the client.
- Idempotency concerns intended effects, not identical responses or absence of logs. A replayed counter snapshot can be 1 while the current counter is 3.
- Key identity and logical intent differ. Different keys or expired records can repeat declared intent; shared raw keys across different callers/operations must not collide in this model.
- Completed retention cannot safely substitute for an in-flight owner's lease. Expiring a pending owner without a validated recovery/fencing protocol would allow another effect while the original owner remains capable of committing. Recovery is deliberately deferred.
- Atomicity must name its boundary. A Python state transition assumption proves no physical crash/storage guarantee. Split effect-before-record exposes why an outcome can become indeterminate.
- Hand-calculated ORACLES.md preceded code. Four mutation checks show assertions detect removed payload/scope binding, wrong expiry equality and effect/delivery conflation; they do not prove every possible defect absent.
- Static review, unit tests, SAST and source research have different evidence limits. The local worker's truncated timeout/atomicity assertions were rejected, not upgraded into facts. Context handoffs must name current project, phase and next step so completed projects do not displace unfinished work.

Optional exercise: set atomic-loss retention to 1 ms and observe which retry becomes fresh work. Predict accepted/effect counts before adding a completion for the newly accepted attempt.
