# SEP34 independent FAIL and author corrections

Original reviewed source38dbef32/treee6664c3d remains history with scoped FAIL. Its green CI is not rewritten as approval. failed-review.json preserves both findings. Both old counterexamples were reproduced using disposable fixtures: metadata symlink overwrote its outside sentinel; uncommitted executed helper altered IR under unchanged source pin. Raw red logs are retained. New regression XML records394 product passes+69 subtests and75 documentation passes, no failures/errors/skips.

| Private sink | Guard/publication after correction |
| --- | --- |
| build_docs_site documentation-inputs.json | Preflight exact sink before input record/freshness; shared atomic private writer |
| schema_inventory inventory.json and producer.json | Both sinks preflighted before execution; inputs-only namespace; no-follow atomic writes, manifest published last |
| verify_documentation attempt/logs/JUnit/copies/receipt | Unique0700 private attempt; all child sinks preflighted; exclusive no-follow log descriptors; atomic copies and receipt; no existing attempt overwritten |
| provenance CLI | Read-only validation and stdout; no private file writer |
| renderer/staging/MkDocs outputs | Existing dedicated output/source/link/containment checks retained; no new private sink or public allowlist expansion |

Private writers reject linked parents/leaves, hard-link aliases, catalog headers, reserved/source-overlap paths; directory walking and publication use no-follow descriptors. Atomic replacement does not dereference a leaf link. Tests use disposable state only.

Producer closure is conservative and shared, covering every committed product source and Python script/control plus root config/lock. Required audit_publication_free and verification_outputs controls cannot disappear. Unknown executed repository modules or modules loaded outside selected checkout fail closed; selected bytes are rechecked after validation and before output. Tests cover helper drift, control side effects during validation, unbound executed helper and missing receipt closure/hash evidence. No source-byte hashes or changed IR are silently relabeled as the old pin.

All product SQL/contracts/machine inputs/Transfer fences and cache identity remain unchanged. Fresh exact-head CI and independent re-review are separate gates. No main merge, deployment/settings change or complete-release claim. The earlier Azure403 artifact route is not retried or bypassed.
