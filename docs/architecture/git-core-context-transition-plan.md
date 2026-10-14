# Transition plan: Git-only append-only Core + durable Context

**Status:** Implementation planning document for accepted [ADR 0003](../adr/0003-append-only-git-core-and-context-store.md); no code/DDL is changed by this plan.
**Starting revision:** `b329efacafe612404848dfd26424eec219680e4c` (the implemented Core 21 / Operational 1 / Search 1 format).
**Planning rule:** A complete and consistent final design takes priority over compatibility with unreleased databases or intermediate stacked PR behavior.

## 1. Contract first, not a blind table move

The old architecture has **70 Core, 10 Operational, 4 Search** product tables. These numbers are the *source inventory*, not a target estimate. The production SQL entrypoint is `src/repo_catalog/adapters/sqlite/schema.py`; it composes `catalog3.sql`, `git_domain.sql`, `git_facts.sql`, `cas_integrity.sql`, `exchange.sql`, `identity_relations.sql`, `current_resources.sql`, `current_api.sql`, `current_collections.sql` and `json_contracts.sql`.

The implementation agent MUST produce a machine-checkable **full disposition inventory for every current Core table, column, FK, view, trigger, index, writer, reader, Exchange key and validator**. The examples below are not an exhaustive relocation map.

| Incumbent group / examples | Target treatment | Required scrutiny |
| --- | --- | --- |
| `git_objects`, `commits`, `commit_parents`, `tree_objects`, `tree_entries`, `tag_objects`, `git_object_payloads` | Git Core immutable facts | Canonical bytes/identity, exact per-object atomic installation; no late mutable FK or verified-bit update |
| `contents`, `content_digests`, `blob_content_map`, `stored_bytes`, `payloads` | Git Core for proven canonical raw Git content | Do not re-introduce HTTP/Provider text; reconcile integrity/quarantine and append-only-safe repair |
| `git_acquisitions`, `snapshots`, `acquisition_roots`, `ref_observations`, `repository_object_sources`, `root_manifests`, `root_manifest_entries` | Split immutable Git acquisition/capture facts from mutable progress/Provider purpose | Inspect `complete`, late FK bindings, `source_id`, endpoint and PR purpose, snapshot promotion/current-selection |
| `root_origins` | Split Git ref provenance (Git Core) from PR/code assessment association (Context) | Current `change_request_id` and `code_assessment_id` FKs point from a Git table to PR domain |
| `git_commit_facts`, `git_text_facts`, `git_name_facts` | Git Core immutable decoded candidates only when anchored in verified bytes | Explicit decoder identity; no arbitrary winner or silent re-decoding of unrelated Context |
| `repositories`, `repository_bindings`, `repository_endpoints`, `repository_names`, `service_instances`, `sources`, `identity_relations` | Keep **minimal permanent repository identity** in Git Core; associated service/Source/binding/preference in Context; split identity assertions by real subjects | Preserve permanent `repository_uuidv4`; no Context FK required for Git-only ingestion; cancellation via additional facts rather than rewriting immutable assertions |
| `change_requests`, `documents`, `review_threads`, `issue_resources`, `review_resources`, `change_request_state`, `document_state`, `review_thread_state`, `source_repositories`, `source_inventory_assessments` | Context authoritative resources | Latest-state and field evidence; no fabricated historical edit log; actual transfer and missing/null distinctions |
| `text_bodies` | Context-owned Provider-domain text, exact SHA-256 | Shared across current/context evidence and pending conflict candidates; GC-01/GC-02 apply only here in the future |
| `fetch_collections`, `collection_memberships`, `current_collection_pages`, `completion_markers`, `coverage_scopes`, `coverage_claims`, `thread_collection_*`, `resume_scopes` | Subject-aware split; Provider/Source collection coverage in Context; genuine Git closure/observation facts in Git Core; retry cursors in Operational | Never lose required terminal/child/owner/time evidence; do not graft incomplete acquisition; Coverage remains truthful |
| `code_listings`, `code_listing_progress`, `code_assessments`, `code_acquisitions`, `code_commits`, `code_file_changes`, `change_request_events` | Context owns PR/comparison assessments, real git objects remain Git Core | Preserve exact head/base/role and matched OID; no false lineage from updated PR head |
| `exchange_local_identities`, `exchange_admissions`, `exchange_staging`, `exchange_blocked_coverage_claims`, `coverage_claim_markers`, `identity_relation_staging` | Inspect and split by authoritative domain; processing/deduplication may be disposable only if losing it cannot invalidate facts | Never replace typed owner with universal Publication authority; pending conflict/partial dependency preservation |
| `preservation_obligations`, `payload_quarantine`, `payload_admission_staging`, `unresolved_payloads`, `database_identity` | Decompose immutable Git truth/diagnostics from **mutable** progress, quarantine resolution, validation/revision bookkeeping | Keep Git-only operation safe without Context; CAS-41, fail-closed loss handling, recovery and backup verification must survive |

The target is **not** "move every table whose name starts with `git_`". Conversely, immutable Provider-specific events are Context. Core-internal derived indexes may be maintained by SQLite but must not become mutable application-visible tables inside the append-only domain store.

## 2. Critical implementation traps to resolve before coding

1. **Mutable Git columns:** Inspect all old `UPDATE`/UPSERT/delete statements against Git-owned tables. Current `snapshots.complete` and `acquisition_roots.complete` are examples of mutable completion; `git_objects.verified`, foreign-key late binding, preservation progress and `local_revision` require a definite append-only-safe model.
2. **Recovery and integrity:** Existing CAS repair may update stored bytes after temporarily modifying protective triggers. **Do not carry that approach into Git Core**. Provide a verified immutable repair-evidence/alternate-instance or restore mechanism that still makes valid objects available, with adversarial corruption tests and CAS-41 compatibility.
3. **Direction of dependency:** `root_origins` presently references `change_requests`/`code_assessments`. Replace with independent Git capture evidence and Context-owned PR-to-Git association. A local Git catalog must have no Context tables or Context file.
4. **Cross-DB FK/transactions:** SQLite FKs cannot cross database files. Enumerate and remove cross-store physical FKs while preserving typed checks. Document the exact crash matrices for `Git committed / Context failed` and `Context staged / Git failed`, including retry, idempotency, stale-fence and false-completeness prevention.
5. **Scope claims:** Existing Coverage applies to multiple domains. Preserve five-column claim contract and newest-observation semantics where Coverage continues; new Git-specific completion evidence may be immutable observations, not a mutable generic seal.
6. **Preservation and physical data:** Being unreachable from today's ref never authorizes Git Core deletion. Git-only retention must include required verified bytes and provenance. Keep cache GC safely separate from accepted contents.
7. **Backups:** Implement and test a Git-only backup and a **paired consistent** Git Core+Context backup. Include identities, hashes/manifests, CAS-41, atomic no-overwrite restore and rejected mismatched-pair counterexamples. The legacy single-Core backup is not full Context preservation.
8. **Search and Exchange:** Rework identity fences and query selection over both authoritative sources. Validate source-dependent direct scan fallback; preserve independent Git-only Exchange and Context-linked closure without pretending missing subjects are present.
9. **CLI/documentation:** Distinguish installed format from target ADR in README, developer site and diagrams until each implementation stage is integrated. Do not regenerate the 84-table visualizations from hypothetical DDL and label them implemented.
10. **No context-derived Git fact:** Test offline local Git ingestion, force-push/reobserved ref, incomplete object graph, absent/malformed Context, detached PR references and lack of external credentials.

## 3. Suggested Stacked PR dependency graph

Each implementation PR must start from the accepted ADR PR's merged tree. More than one coding agent may work in parallel where the stated dependency does not exist.

| PR stage | Dependencies | Deliverable and independent verification |
| --- | --- | --- |
| **D0: This design PR** | Current `main` | Authoritative ADR 0003, status/supersession map, complete transition intent. **No executable change** |
| **I1: Full disposition and invariant probes** | D0 | Generated SQL/call-site/FK matrix for **every** affected object, failing counterexample tests for pure append-only and Git-only mode, and an explicit list of unresolved implementation decisions |
| **I2: Git Core format and append-only acquisition path** | I1 | Core DDL, verified Git objects/DAG/captures, immutable completion and revision model, byte/integrity recovery. No mutable Git fact tables; Git-only smoke and focused adversarial tests |
| **I3: Durable Context format and current-state path** | I1, I2's typed identity contract | Provider/Source/PR/Issue/review/current text, current evidence/coverage/conflict and typed Core links. Independent Context CRUD/provenance tests |
| **I4: Acquisition + Exchange integration** | I2, I3 | Local-Git and API/PR capture integration, typed cross-store intake, unresolved dependencies, repeat and reverse delivery, crash-recovery counterexamples |
| **I5: Backup/restore + Search + Ops/CLI integration** | I2, I3, I4 interfaces | Git-only/full paired backup and no-overwrite restore, search two-source fallback/rebuild, explicit operation/monitor behavior |
| **I6: Complete docs and integrated verification** | I2–I5 | Updated schema visualization/website, current ADR/status map, exact-tree focused regression and independent review, real controlled workloads when separately authorized |

I2's Git-only primitives and I3's Context schema can be developed independently after freezing I1's cross-store contract, but *integration and merge order must reflect actual dependencies*. Additional design-only ADRs are appropriate for significant choices such as a new cross-store commit protocol or an append-only-safe physical repair algorithm; do not pretend those were already decided in ADR 0003.

## 4. Explicit acceptance gates

- **Negative requirements:** No Context DB required for local Git; no Git Core fact UPDATE/DELETE/REPLACE; no recovered old ref removal; no unverified object acceptance, fake coverage, fake Source history, generic Publication replacement or new retrospective Provider edit history.
- **Positive requirements:** Current Git object/OID identity and bytes remain exact; retained force-push snapshots remain queryable; real context references verify or remain clearly unresolved; both durable stores have explicit backup roles; Context omission is visibly degraded rather than "full restore".
- **Tests:** Exhaustive SQLite DDL trigger/FK and mutation-shape probes, missing Context, failed partial writes, stale snapshots, corrupt CAS and repeated imports, Exchange reversals, snapshot/restore skew, Search fallback, packaging/CLI. Run focused development checks under [ADR 0001](../adr/0001-validation-lifecycle-architecture.md) and independently recheck material cross-store corrections.
- **Evidence:** Bind source SHA/tree/DDL fingerprints, test nodes and failure/correction history. Do not claim previous Schema 21 test receipts certify the new four-store format. Full release acceptance remains opt-in.

## 5. Owner decisions that are not implicitly reopened

Preserve [ADR 0003](../adr/0003-append-only-git-core-and-context-store.md)'s scoped changes, PF-P01–PF-P17 where not superseded, repository UUIDv4 permanence, explicit Q01-B/Q02-B/Q03-B, no independent Publication, Unix microsecond timestamps, exact bytes, Source known-positive and Coverage semantics, ADR 0001 validation. Document concrete contradictions rather than weakening established guarantees for convenience.

**Design-only boundary:** This plan grants no merge, release, deployment, authenticated collection, retained-data migration, deletion, or implementation authorization beyond separately requested coding tasks.
