# Transition plan: Git-only append-only Core + durable Context

**Status:** Implementation planning document for accepted [ADR 0003](../adr/0003-append-only-git-core-and-context-store.md), narrowly extended by [ADR 0004 / GCTX-M01: mandatory metadata-only Core](../adr/0004-metadata-only-git-core.md); no code/DDL is changed by this plan.
**Starting revision:** `b329efacafe612404848dfd26424eec219680e4c` (the implemented Core 21 / Operational 1 / Search 1 format).
**Planning rule:** A complete and consistent final design takes priority over compatibility with unreleased databases or intermediate stacked PR behavior.

**Later binding requirements:** ADR 0004 / GCTX-M01 requires Git Core to catalog commit/parent/tree/blob metadata without bytes or Context. [ADR 0005 / GCTX-M02](../adr/0005-common-oid-identity-with-attributed-metadata.md) selects a common nominal identity keyed by `(object_format, oid)` and separately attributed attributes/relations. Re-audit verified-only assumptions; optional byte verification, current physical health and closure are separate guarantees. Neither the physical registry layout nor verification-result placement is selected.

## 1. Contract first, not a blind table move

The old architecture has **70 Core, 10 Operational, 4 Search** product tables. These numbers are the *source inventory*, not a target estimate. The production SQL entrypoint is `src/repo_catalog/adapters/sqlite/schema.py`; it composes `catalog3.sql`, `git_domain.sql`, `git_facts.sql`, `cas_integrity.sql`, `exchange.sql`, `identity_relations.sql`, `current_resources.sql`, `current_api.sql`, `current_collections.sql` and `json_contracts.sql`.

The implementation agent MUST produce a machine-checkable **full disposition inventory for every current Core table, column, FK, view, trigger, index, writer, reader, Exchange key and validator**. The examples below are not an exhaustive relocation map.

| Incumbent group / examples | Target treatment | Required scrutiny |
| --- | --- | --- |
| `git_objects`, `commits`, `commit_parents`, `tree_objects`, `tree_entries`, `tag_objects`, `git_object_payloads` | Git Core nominal identities, attributed metadata/relations and optional verified representations; concrete separation unresolved | No mandatory bytes/raw headers/offsets for metadata admission; conflicting type/size/relations must not poison OID identity. Retain exact per-object atomic installation for optional byte-verified structure; no late mutable FK or verified-bit update |
| `contents`, `content_digests`, `blob_content_map`, `stored_bytes`, `payloads` | Git Core for admitted canonical raw Git content, optional for metadata-only objects | Do not fabricate bodies/digests for absent payloads or re-introduce HTTP/Provider text; reconcile integrity/quarantine and append-only-safe repair |
| `git_acquisitions`, `snapshots`, `acquisition_roots`, `ref_observations`, `repository_object_sources`, `root_manifests`, `root_manifest_entries` | Split immutable Git metadata/byte acquisition and capture facts from mutable progress/Provider purpose | Metadata observation is not raw-object possession. Inspect `complete`, late FK bindings, `source_id`, endpoint and PR purpose, snapshot promotion/current-selection |
| `root_origins` | Split Git ref provenance (Git Core) from PR/code assessment association (Context) | Current `change_request_id` and `code_assessment_id` FKs point from a Git table to PR domain |
| `git_commit_facts`, `git_text_facts`, `git_name_facts` | Preserve verified-byte decoder facts, and design separately qualified supplied Git metadata where needed | Do not require verified bytes for all message/name metadata. Preserve exact decoder/subject attribution for claims of byte-derived values; no arbitrary winner or silent re-decoding of unrelated Context |
| `repositories`, `repository_bindings`, `repository_endpoints`, `repository_names`, `service_instances`, `sources`, `identity_relations` | Keep **minimal permanent repository identity** and necessary standalone Git metadata provenance in Core; associated service/Source/binding/preference in Context; split identity assertions by real subjects | Preserve permanent `repository_uuidv4`; no Context FK required for Git-only ingestion; cancellation via additional facts rather than rewriting immutable assertions |
| `change_requests`, `documents`, `review_threads`, `issue_resources`, `review_resources`, `change_request_state`, `document_state`, `source_repositories`, `source_inventory_assessments` | Context authoritative resources | Latest-state and field evidence; no fabricated historical edit log; actual transfer and missing/null distinctions |
| `text_bodies` | Context-owned Provider-domain text, exact SHA-256 | Shared across current/context evidence and pending conflict candidates; GC-01/GC-02 apply only here in the future |
| `fetch_collections`, `collection_memberships`, `current_collection_pages`, `completion_markers`, `coverage_scopes`, `coverage_claims`, `thread_collection_*`, `resume_scopes` | Subject-aware split; Provider/Source collection coverage in Context; genuine Git observation/closure facts in Core; retry cursors in Operational | Metadata-scope completeness, byte possession and verified closure are not interchangeable. Preserve five-column Coverage and newest-observation semantics; scope details remain open |
| `code_listings`, `code_listing_progress`, `code_assessments`, `code_acquisitions`, `code_commits`, `code_file_changes`, `change_request_events` | Context owns PR/comparison assessments; standalone modeled Git metadata belongs to Core even before byte verification | Preserve exact head/base/role and matched OID; no false lineage from updated PR head; no whole API replicas or migration of PR semantics into Core |
| `exchange_local_identities`, `exchange_admissions`, `exchange_staging`, `exchange_blocked_coverage_claims`, `coverage_claim_markers`, `identity_relation_staging` | Inspect and split by authoritative domain; processing/deduplication may be disposable only if losing it cannot invalidate facts | First-class metadata-only Exchange, attributed alternatives, no mandatory payload promotion and no sender-verification laundering; no universal Publication authority |
| `preservation_obligations`, `payload_quarantine`, `payload_admission_staging`, `unresolved_payloads`, `database_identity` | Decompose immutable Git truth/diagnostics from **mutable** progress, quarantine resolution, validation/revision bookkeeping | Intentional absence is not corruption, but do not hide real loss. Keep Git-only metadata operation safe without Context; CAS-41, fail-closed byte-dependent work, recovery and backup checks remain |

The target is **not** "move every table whose name starts with `git_`". Conversely, immutable Provider-specific events are Context. Unverified status alone is not a reason to move Git metadata to Context. Core-internal derived indexes may be maintained by SQLite but must not become mutable application-visible tables inside the append-only domain store.

## 2. Critical implementation traps to resolve before coding

1. **Metadata identity and conflicting reports:** Apply the GCTX-M02 common `(object_format, oid)` identity and design unknown attributes, source-attributed relationship observations and optional verified representations before fixing `git_objects.verified` or FK hydration. A wrong early report must not block correct later bytes or overwrite the original observation. Preserve parent ordering and partial tree/list boundaries; do not combine incompatible observations into one canonical graph.
2. **Mutable Git columns:** Inspect all old `UPDATE`/UPSERT/delete statements against Git-owned tables. `snapshots.complete`, `acquisition_roots.complete`, `git_objects.verified`, foreign-key late binding, preservation progress and `local_revision` require a definite append-only-safe model.
3. **Recovery and integrity:** Do not carry in-place CAS repair into Git Core. Provide verified immutable repair-evidence/alternate-instance or restore recovery with adversarial corruption tests and CAS-41. Metadata-only nonacquisition must not be diagnosed as corruption; actual retained-byte loss must not be downgraded to optional absence.
4. **Direction of dependency:** Split `root_origins` PR FKs and `git_acquisitions` context purposes. A local Git metadata catalog must have no Context tables or file; necessary metadata provenance must remain independently interpretable. The source of a modeled Git assertion is not by itself its domain owner.
5. **Cross-DB FK/transactions:** SQLite FKs cannot cross database files. Document crash matrices, typed checks, retry/idempotency, fences and false-completeness prevention. GCTX-M01 does not choose a transaction protocol or place verification results in Context.
6. **Scope claims:** Preserve Coverage's five-column/latest-observation contract. Define metadata inventory, raw-body retention and verified closure separately. Do not relabel an old byte-closure claim or use a mutable generic seal.
7. **Preservation and physical data:** Being unreachable from today's ref never authorizes Core deletion. Raw acquisition is optional, but already admitted required bytes and provenance remain retained. Keep cache GC separate.
8. **Backups:** Test an offline Core-only metadata backup/restore with zero raw payloads, as well as paired Core+Context backups. Label catalog completeness versus raw repository restorability. Preserve identity/hash checks, CAS-41 and atomic no-overwrite restoration.
9. **Search and Exchange:** Normal metadata query/search/traversal/Exchange must not require `available_git_objects`, raw CAS or Context. Separate interfaces requiring verified bytes; preserve unverified/conflict qualification and direct-scan fallback. No fake payloads, hidden fetch or imported local verification authority.
10. **CLI/documentation:** Distinguish installed format, accepted requirement and verified behavior. Do not report intentionally metadata-only catalogs as generally invalid. Do not regenerate the 84-table visualizations from hypothetical DDL and label them implemented.
11. **Independent counterexamples:** Follow ADR 0004's byte-free/context-free tests, partial/conflicting observations and later matching/mismatching bytes, plus ADR 0003's append-only/force-push/cross-store tests. Existing focused checks do not certify the new requirement.

## 3. Suggested Stacked PR dependency graph

Design PRs may stack on the unmerged design baseline without merging it. Implementation integration must respect the accepted design ancestry and separately authorized merge sequence. More than one coding agent may work in parallel where the stated dependency does not exist.

| PR stage | Dependencies | Deliverable and independent verification |
| --- | --- | --- |
| **D0: Four-store boundary design** | Current `main` | Authoritative ADR 0003, status/supersession map and transition intent. **No executable change** |
| **D1: Metadata-only requirement** | D0 / PR #44 | ADR 0004 / GCTX-M01 and scoped supersession. **No executable change**; verification placement, schema and conflict policy remain open |
| **D2: Scoped detailed decisions** | D1 | GCTX-M02 common nominal identity fixed by ADR 0005; next resolve GCTX-M03 observation grouping, then conflict-read/verification contracts and required fences; other scoped designs as needed |
| **I1: Full disposition and invariant probes** | D1, relevant D2 decisions | SQL/call-site/FK matrix for every affected object, counterexamples for metadata-only/append-only/Core-only behavior and remaining decisions |
| **I2: Git Core format and append-only acquisition path** | I1, relevant D2 decisions | First-class metadata-only Core plus optional verified bytes/DAG/captures, immutable completion/revision and safe byte recovery |
| **I3: Durable Context format and current-state path** | I1, I2's typed identity contract | Provider/Source/PR/Issue/review/current text, evidence/conflict and Core links. Independent Context tests; do not assume verification placement |
| **I4: Acquisition + Exchange integration** | I2, I3 | Metadata-only and byte-backed paths, exact provenance, unresolved/contradictory relationships, reverse/repeat/late arrival and crash tests |
| **I5: Backup/restore + Search + Ops/CLI integration** | I2, I3, I4 interfaces | Metadata-only/Git-only/full paired backup, no-overwrite restore, correct search fallback and explicitly qualified CLI guarantees |
| **I6: Complete docs and integrated verification** | I2-I5 | Updated visualization/site/status, exact-tree focused regression and independent review; real workloads only when separately authorized |

Parallel work and merge order must reflect actual dependencies. No acceptance criterion grants merge authorization. The metadata-only requirement is not reopened while deciding how to implement it.

## 4. Explicit acceptance gates

- **Negative requirements:** No Context or raw object bodies required for metadata-only Core; no hidden fetch, fake payload/digest/default attribute, false byte verification, false closure, Git Core UPDATE/DELETE/REPLACE or GC, generic Publication replacement, or retrospective full Provider edit history.
- **Positive requirements:** Normal metadata import/query/traversal/Exchange/backup works with zero raw payloads and absent Context, with truthful unknown/unverified/conflict qualification. Optional verified bytes retain exact identity/structure and physical-integrity guarantees. Force-push observations remain queryable; full Context preservation still needs both authoritative stores.
- **Tests:** ADR 0004's counterexamples plus SQLite mutation/constraint probes, Context omission, stale snapshots, corrupt CAS, retries, Exchange reversal, backup skew, search fallback and packaging/CLI. Apply [ADR 0001](../adr/0001-validation-lifecycle-architecture.md); independent review for material changes.
- **Evidence:** Bind source SHA/tree/DDL fingerprints, test nodes and failure/correction history. Do not claim historical Schema 21 receipts certify the new four-store or metadata-only target. Full release acceptance remains opt-in.

## 5. Owner decisions that are not implicitly reopened

Preserve ADR 0003 except ADR 0004's narrow metadata-admission supersession; unaffected PF-P01-PF-P17, repository UUIDv4 permanence, Q01-B/Q02-B/Q03-B, no independent Publication, Unix microsecond timestamps, exact-byte verification when claimed, retained-byte/CAS-41 guarantees, Source known-positive and existing Coverage semantics, and ADR 0001 validation. No decision to move verification or raw bytes into Context, select a schema/winner policy, allow Core deletion, or change GC-03/GC-04 is implied.

**Design-only boundary:** This plan grants no merge, release, deployment, authenticated collection, retained-data migration, deletion, or implementation authorization beyond separately requested coding tasks.
