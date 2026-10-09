# Transport-independent core implementation boundary

The accepted [ADR](transport-independent-core-adr.md) is implemented incrementally from PR #16 (`7829a6addb05d73ab4f303eb48ba19cd9957aba7`). Schema 17 is incompatible with schema 16; initialize disposable fresh catalogs. No migration, merge or release is included.

## Current Issue/review resources

TP-01, TP-02 and TP-05–TP-08 apply to current ordinary Issues/comments and reviews/comments: exact domain text, typed identity/parents, field evidence, transfer capture, unresolved alternatives and established normalized collection receipts remain durable without original response bytes. Acquisition, queries/search, full/selective exchange and backup/restore work with no `fetch_occurrences`, `decoded_api` CAS or optional archive. A review requires a typed `change_requests` owner, not a retained parent PR response. Whole PR synchronization still uses the historical paths below.

TP-04 replaces `parser_profile_uuidv4` with nonempty NUL-free `parser_module` and `parser_version` on `issue_resources`, `review_resources` and `current_collection_pages`. `current_parser` stamps its own module/version, overriding caller attribution. Page attribution identifies the resource normalizer that produced the digested current members; the historical thread interpretation remains separately owned by the legacy parser. Every retained mutable field's seven-key evidence includes its actual producer, clock, observed/parsed times and capture scope. Missing fields retain their original evidence; explicit null remains an observed value. Module/version are excluded from semantic fingerprints and owner comparisons. Versions do not rank conflicting values. Current admission and views require no profile registration, capabilities, certificates, trust or selection; built-in historical profile capabilities no longer include these current families.

The current acquisition JSON guards reject transport-original, profile, parsed-result and selection references and contain no unreachable queries to their legacy stores, while preserving typed owner checks and detached Issue-transfer snapshots. Current selective exchange no longer exports profile selection closure. Issue-only queries reject obsolete profile selectors; explicit historical profile filters on PR document queries select historical documents. Current queries expose module/version and field evidence. Existing incremental baseline behavior conservatively starts a full scan after a producer change; this is an operational baseline, not a new provider-ordering or completeness policy.

Changed schema objects: the three current tables, their capability FKs/generated capability columns, current eligibility views, current-page capability guard, and generated capture/field-evidence guards. The five coverage claim columns and existing terminal/member/page proof semantics are unchanged. Existing normalized provider projections are preserved; this change does not choose a new provider-field retention policy or content GC.

## Remaining baseline and exact blockers

| Remaining objects and paths | Contract required before removal |
| --- | --- |
| `source_input_observations`, `repository_inventory_observations`; `collector.inventory_request/inventory_result`, `CollectionService.discover` | Normalized inventory publication/ownership and retained provider-field inventory. The existing query exposes opaque provider metadata. |
| `fetch_occurrences`, `change_request_observations`, `document_observations`, `change_request_events`, `review_thread_observations`, `code_observations`, `code_commits`, `code_file_changes`; `ApiFacts.page/result/ownership/publish`, PR/detail/document/thread/code acquisition | Domain batch/publication identity and atomic completion, historical lifecycle/resolution and retained fields. Saved fetch inputs currently protect sealed immutable output membership. |
| Historical `completion_markers`, `collection_memberships`, code listings and exchange aggregate proof | Normalized historical member/terminal proof and exchange validation. PR-list exchange rereads saved JSON to check exact member closure; dropping this would weaken correctness. |
| `validators` and PR detail 304 replay; legacy HTTP CAS `payloads`/`stored_bytes`, unresolved/quarantine records | Conditional HTTP cache/restart contract and raw-content retention/GC. Preserve current behavior until that contract is decided. Domain Git objects and exact text remain required. |
| `parser_profiles`, capabilities, verification/invalidation/local trust; `parsed_results`, inputs/publications; five profile-selection and five fact-selection tables; exchange blocked-result/selection state | Replacement historical publication and unordered fact-resolution contracts for PR/thread/inventory/Git. Existing ordinary historical readers still use these objects; removing them would choose a current winner or admit partial output. |

Owner decisions remain the ADR's deferred lifecycle/resolution, publication boundary, historical completeness/exchange validation, provider-field inventory, operational cache/restart and content-retention contracts. Current-resource changes preserve existing behavior as an implementation baseline and do not declare these deferred policies accepted.

## Validation contracts

Independent `test_transport_independent_guards.py` additionally checks valid current admission/conflicts after physically dropping nine empty legacy stores, and rejects malformed transport/profile references and false capture owners under FK enforcement.

Independent `test_transport_independent_core.py` uses fresh synthetic catalogs with no profiles/originals and checks acquisition, actual producer attribution, inherited fields, missing/null, out-of-order and equal-clock conflicts, incomplete pagination, recorder failures, archive deletion, queries/search, exchange and backup/restore. PR #14/#15 adversarial ownership, JSON-type, clock, transfer and completeness assertions remain. Only their current parser-profile eligibility/capability expectations are superseded with module/version and gate-free behavior tests. Wheel/sdist tests retain Git content verification and historical parser checks and add current module/version assertions.

Each implementation PR reports its executed focused/full/package results and base/head SHAs. Historical validation reports are untouched. The remaining legacy parser certificate is regenerated only from successful relevant tests, followed by acceptance without bootstrap overrides.
