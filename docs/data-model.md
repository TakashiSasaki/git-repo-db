# Data model — Catalog3 Schema 20

The [composed packaged DDL](../src/repo_catalog/adapters/sqlite/schema.py) is authoritative. The [schema map](phase2/publication-free-schema-map.json) records all current columns/PKs/FKs/views/triggers/indexes and the preserved Schema 19 delta. The [implementation handoff](phase2/publication-free-implementation.md) explains keys, consumers, lifetimes and pending acceptance. Historical inventory reports are earlier checkpoints, not active format contracts.

## Identity and direct ownership

Services, repositories and Source registrations use portable canonical UUIDv4 identities; local Source IDs are distinct. Binding identity is scoped to service/provider repository ID. Names and URLs are selectors, never automatic identity mergers. Explicit aliases/equivalence/cancellation remain separate assertions.

A PR has its typed repository/binding identity. A document uses `(change_request_id, kind, provider_change_request_document_id)`; a thread uses `(change_request_id, provider_resource_id)`. Current values attach directly to these owners. PR title/body are document values, with no second authority on PR metadata. Ordinary Issue identity is `(service, kind, provider_resource_id)`, allowing membership transfer independently of its original capture. Reviews retain `(PR, kind, provider document ID)`.

## Shared latest-state resources

`change_request_state`, `document_state`, `review_thread_state`, `issue_resources`, `review_resources` and Source association fields preserve accepted current values, presence and seven-key per-field origins: provider clock/time, observation time, parsing time, actual parser module/version and capture scope. Missing fields retain the original value/evidence. Explicit null is observed. Older responses may fill unknown values without replacing newer known values. Provider clocks are scoped evidence, not a universal total order.

Real equal/incomparable-clock alternatives are normalized conflict candidates. Receipt order, parser version and parsing timestamps cannot decide them. `last_checked_at_us` is receiver-local, advancing only through accepted authoritative live admission with pre-request revision/scope fences. Import does not copy sender checks. Capture and current membership remain separate for transferred resources; detached capture IDs are preserved and existing relationships are validated when available.

Source `(Source, repository)` rows mean known positive association and current modeled attributes. Partial R1 after known R1/R2 leaves R2 known. No absence deletion policy is selected. Local explicit aliases are not an append-only provider-name history.

Exact UTF-8 body SHA-256 identifies shared `text_bodies`. Current updates do not append full normalized API state/history. Unreferenced old shared text may remain physically present; no GC or supported retrospective edit-history query is implied. Closed metadata vocabularies retain named modeled domain fields, not provider response replicas.

## Enumeration, targets and Coverage

A fetch collection owns an actual repository/PR/request scope. Its pages record stable typed members and their captured digests, page order and has-next outcome. Completeness markers assess that scope's terminal/member and required-child outcomes. A terminal empty enumeration differs from having no terminal evidence. Valid individual resources do not require completion of the larger enumeration.

Thread requirements bind exact parent capture/time, provider thread and head/base to required child collections. Code listings/entries and assessments bind exact comparison/head/base/role targets; current PR changes do not retag old evidence. Actual provider events are domain occurrences, separate from mutable PR edit snapshots.

`coverage_claims` has exactly `coverage_claim_id`, `coverage_scope_id`, `coverage_state`, `observed_at_us`, `details_json`. States are complete/partial/unknown/not_applicable. The complete set at the latest observation determines current state/conflict, including latest unknown; there is no fallback to an older successful claim. Details remain advisory. Current-only member attestations do not require today's values to equal yesterday's superseded digest. Sender digest consistency is not provider authenticity.

## Git and physical content

Git identity is `(object_format, oid)` verified from canonical header/type/size and bytes. Complete intrinsic commit/parent/tree/entry/tag structures install atomically per object. Required target OIDs survive when actual target objects are missing, with nullable links; no fake object is created. Genuine acquisitions, ref captures, snapshots, roots/origins and repository object associations retain their own subjects. Proven capture predecessor relationships preserve ambiguity instead of clock/generation ranking.

Decoder-specific commit/blob/name facts have direct object/entry owners, explicit settings and actual producer module/version. Disagreement is a conflict unless an actual decoder key is explicitly requested. Git-only reanalysis does not create another capture. Raw Git payloads use only `git-object-raw-v1`; `decoded_api` is rejected. Contents/digests and manifests retain exact domain identity/closure without a generic member seal.

Shared physical bytes retain hash/length integrity, quarantine and canonical real-Git repair authorization. CAS-41 backup manifests record the verified copied database's active physical quarantine count. Restore checks that count before diagnosis, validates in a fresh retained stage and installs atomically without overwrite. Positive matching counts preserve quarantined bytes and diagnostics; unexplained corruption or mismatch rejects restore.

## Local operations and Exchange

`database_identity.local_revision` is one receiver-local counter for snapshots, paging and live fences, with no history ledger. Job/attempt, cursor/continuation, credential-reference and cache states are operational; domain validity does not depend on their existence. No write transaction spans network work. Search/index generations are derived infrastructure.

Exchange carries actual typed domain closure from one snapshot, with portable FK/key resolution and independently validated required bytes. It retains normalized missing/conflicting candidates and key/digest mappings for repeat delivery, rather than archived accepted current bodies. Transport envelopes/checksums and processing receipts do not own admitted resources. Full Source inventory, local credentials/quarantine/cache and optional transport archives are excluded.

No new broad deletion, retention/GC, cache/checkpoint lifetime, stronger sender trust or decoder/ref policy is selected. Exact review/acceptance evidence is required before claiming the redesign complete.
