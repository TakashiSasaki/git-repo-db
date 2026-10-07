# Current catalog3 implementation state

Catalog3 is the sole ordinary runtime. Packaged DDL and the runtime identity module are authoritative; [runtime handoff](runtime-handoff.md) records commands, validation and limits. Historical phase plans and design/export schemas remain snapshots.

## Coverage derivation (schema 9)

Starting from published PR #5 at `fee685db14e8052d2e9decd5f4b3470d4da80517`, branch `refactor/coverage-model` replaces mutable coverage selection with immutable scope/time/state claims and a derived `current_coverage` view. The latest time is chosen before unknown is weakened; same-time determinate disagreement becomes derived conflict. Admission ignores stale and semantic duplicate inputs without changing details. Export selection preserves every latest claim; a multi-catalog exchange protocol remains deferred.

All coverage producers preserve actual saved observation times across resume. Repository Git scopes exclude PR-only acquisition; failures without observed incomplete evidence remain operational job state. Ordinary and diagnostic queries use the same view and return separate advisory details. Schema 9 retains 65 ordinary tables and workspace schema 2. Final synthetic acceptance and installed distribution checks are attributed in the runtime handoff.

## Timestamp normalization (schema 8)

Starting from PR #4 at `307ab6a8df3bc05a99670495676ef25b7c613289`, branch `refactor/unix-microsecond-timestamps` normalizes all catalog/workspace absolute times to signed 64-bit Unix epoch microseconds with `_us` names. Integer ordering applies to source membership, observations, finalization, retry deadlines and cache TTL; provider requests format dates at the boundary. Preserved source bytes and legacy source schemas remain unchanged. Workspace identity advances to 2. The subsequent coverage stride uses this timestamp contract.

## Prior identity and observation stride

This stride starts at main `1ce7fccdb63ab7de74daf6694d2c7187fcddd835` on `refactor/portable-document-observations`. It advances schema identity **4 -> 6**, retaining `repo-catalog/catalog3`, and implements the user's agreed identity/observation decisions rather than another purely mechanical rename.

Implemented scope:

1. Rename service namespace to `service_instance_uuidv4` and kind to `service_kind`; require canonical UUIDv4 and retain CSPRNG generation. Preserve provider-originated identifiers and namespace separation; do not merge by URLs.
2. Replace local document IDs with `(change_request_id, kind, provider_change_request_document_id)` across DDL, collectors, references, queries and diagnostics. Remove the review extension's redundant document-ID alias as well.
3. Make exact-UTF-8 SHA-256 the unique text-body content identity, rejecting inconsistent digests and conflicting body reuse.
4. Remove document versions. Store each observation's direct text-body SHA-256; use a same-document `current_document_observation_id`, preserving actual A->A->B->A history and replay fencing.
5. Adapt guarded v2 salvage to the new target without altering source schema or bytes. Archive old IDs/version facts; map documents to composite keys and current-version assertions only to suitable real observations.
6. Rebuild PR search inputs by content identity while returning distinct observations. Replace obsolete CLI version selectors with explicit observation selectors. Validate normal runtime, preservation, recovery and packaging on disposable synthetic sources.

7. Use explicit change-request kind/provider-number names, remove secondary normalized Node-ID aliases and replace local thread IDs with parent-scoped provider resource keys. Retain failed canonical-ID response evidence and resume without admitting Node-keyed documents.

No v4/v5 migration/compatibility views, separate portable schema, multi-catalog exchange, open-ended providers, real-data activation or release publication is included. Existing real-world reports retain their original commits and scopes. Prior schema-5 clean substantive revision `b6cca875b9a303989bc8947dc56dddb04d7b9ec2` passes 358 current tests and both installed distribution checks (360 reconciled), recorded in the runtime handoff.

## Import-workspace storage boundary

The schema-7 runtime keeps only ordinary catalog entities. The eight conversion/archive/mapping/diagnostic tables belong to a durable but disposable workspace DB through finalization. Same-transaction attached writes preserve resume integrity; normal finalized operation and backups are independent of workspace. See the current runtime handoff and data model; historical phase contracts are not expanded or rerun.
