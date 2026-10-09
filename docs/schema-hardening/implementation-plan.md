# Current catalog3 implementation state

Catalog3 is the sole ordinary runtime. Packaged DDL and the runtime identity module are authoritative; [runtime handoff](runtime-handoff.md) records commands, validation and limits. Historical phase plans and design/export schemas remain snapshots.

## Identity foundation (schema 10)

PR #7 at `d6ee309a6845cf915f821aa1f1910b46b536a614` is the base for branch
`refactor/identity-foundation`. This stride changes repository key naming,
introduces portable Source registration UUIDs, removes service-name uniqueness,
and adds explicit Source/service selection and unconfigured-source handling.
DDL, ordinary callers, guarded salvage, queries and tests are updated together.
There is no earlier-catalog3 compatibility migration.

Remaining implementation proceeds through CAS physical/logical storage,
acquisition/parsed-result/fact separation, verified profile and current-selection
DAGs, staged single-repository exchange, frozen Source/Job inputs and crash-safe
quarantine/backup/restore. The existing five-column coverage contract and signed
64-bit epoch-microsecond timestamps remain acceptance requirements. Intermediate
strides do not imply that the entire design is implemented.

## Design-review corrections

The correction work started from reviewed PR #6 `cd900e252f1320e0cc304fc200317d7190af0143` and includes the subsequent PR #5 timestamp guard at `9abfdc0eb439a823246e306e7773b775cfaa75e7`. Initial work branch: `fix/coverage-review-findings`. Read-only verification subsequently found that PR #7, `refactor/coverage-model-v2` at `304ea4acc5ea224ead8e7e9774aca7851035b553`, superseded closed PR #6. Branch `fix/coverage-review-pr7` reconciles both implementations without rewriting either history. The nine findings and related rate-limit, 304 replay and explicit-null corrections are implemented at substantive commit `604de8db0e957da28ea33f1e74110bc609d4cf63`. Completed local acceptance is **819 ordinary + 2 packaging**, with all 821 selected checks executed exactly once; the recovered results and their independent reconciliation are linked from the runtime handoff. Existing PR #5 and PR #7 track publication and separately attributed hosted CI.

| Order | Review findings | Implementation and acceptance criteria |
| --- | --- | --- |
| 1 | 1, 2 | Finalize code observations only after resolving required roles and checking stored acquisitions. A stable API head with mismatched Git refs, or incomplete merge-role enumeration, cannot assert code completeness. Actual observed gaps propagate to PR and repository coverage; an unobserved request failure alone does not create a claim. |
| 2 | 4, 8 | Preserve original authorization time and identity when reusing imported listings; repeated JobService resume creates no duplicate marker. Require valid GraphQL connection nodes, pagination flags and continuing cursors before claiming terminal completeness. |
| 3 | 5, 6 | Share document/code scope classification, and evaluate requested PR coverage independently of page size, byte cutoff and cursor position in the same read snapshot. Document-only queries exclude code-only gaps. |
| 4 | 3, 7, 9 | Reject fractional UTC offsets across supported parser spellings, retaining raw imported evidence and NULL plus a diagnostic. Make repository/PR coverage ownership explicit. Permit negative local claim IDs without disrupting automatic allocation or weakening immutable admission. |
| 5 | All | Preserve focused failure evidence, review the integrated changes, and run coherent current-runtime, guarded salvage and installed-distribution acceptance with collection/execution reconciliation. Record exact revisions and results in the runtime handoff and synthetic validation report. |

Use only disposable synthetic catalogs, Git remotes and HTTP responses. Existing raw evidence, import protection and immutable coverage semantics remain part of acceptance. Multi-catalog transport, schema compatibility and release/main publication are outside this correction milestone.

## Coverage derivation (schema 9)

Starting from current PR #5 at `9abfdc0eb439a823246e306e7773b775cfaa75e7`, PR #7 branch `refactor/coverage-model-v2` replaces mutable coverage selection with immutable scope/time/state claims and a derived `current_coverage` view. The latest time is chosen before unknown is weakened; same-time determinate disagreement becomes derived conflict. Admission ignores stale and semantic duplicate inputs without changing details. Export selection preserves every latest claim; a multi-catalog exchange protocol remains deferred.

All coverage producers preserve actual saved observation times across resume. Repository Git scopes exclude PR-only acquisition; failures without observed incomplete evidence remain operational job state. PR-code completeness also requires every role named by the observed API state to have a persisted Git acquisition. Reuse of imported sealed listings is tied to the authorizing observation rather than replay time. Ordinary and diagnostic queries use the same view; document-only queries exclude code-only scopes, and pagination does not change coverage evaluation. Schema 9 retains 65 ordinary tables and workspace schema 2. Local and hosted acceptance are separately attributed in the runtime handoff.

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
