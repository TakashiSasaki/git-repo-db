# Design decision implementation status

Baseline: PR #10 (`1c69a868f65b9637a7b8cf00d2c68a4ba05b2faa`).
Current implementation: schema **16**, branch `fix/current-state-conflict-boundaries`,
stacked on PR #14 HEAD `3f76d4873d14604b918198ac06c1660d0fa9e1b9`.
[Boundary corrections](current-state-boundaries.md) and the [schema 16 inventory](current-state-boundaries-inventory.json) record incumbent proof retention, transferred conflict exchange, receiver-local wire exclusions and duplicate FK cleanup. The schema 15 receipts below remain historical evidence.
`implemented` describes code and scoped evidence, not release certification.
The prior schema 14 checkpoint passed 1,311 ordinary and two installed tests;
that is historical evidence for its exact tree, not schema 15 acceptance.

Final schema 16 local acceptance passed 1,509 ordinary cases and both isolated
installed variants without bootstrap, failures, errors or skips; independent
review passed 59 overlapping cases. The [exact boundary receipt](validation/synthetic/2026-10-09-current-state-boundaries.md)
separates local evidence from the submitted HEAD's hosted acceptance.

The earlier schema 15 boundary corrections and evidence are in
[current-state-schema-closure.md](current-state-schema-closure.md), with
[column liveness](current-state-schema-liveness.md) and
[before/after inventory](current-state-schema-inventory.md).
Optional recording is specified in [latest-state-transport.md](latest-state-transport.md).
The 113 older identifiers below retain their baseline traceability; unchanged
historical receipts are preserved. Final schema 15 local acceptance passed
1,452 ordinary cases and both isolated installed variants without bootstrap,
failures, errors or skips. [The exact local receipt](validation/synthetic/2026-10-09-current-state-schema-closure.md)
and the submitted PR body distinguish local and hosted evidence.

## Later decisions and current implementation scope

| Scope | User decision | Implementation | Verification status |
|---|---|---|---|
| Ordinary Issues/comments | Latest accepted state per resource; one shared physical store; Issue identity independent of repository membership | `issue_resources`, common admission, standard `sync issue/all`, offline `issue list/show/comments`, `search issue` | Focused evidence is tracked in the implementation report; Schema 14 checkpoint: 1,311 + 2, no bootstrap; schema 15 evidence is linked above. |
| Reviews/comments | Latest accepted state per resource in one shared store | `review_resources`; redundant marker/history paths removed; independent review/reply/thread and stable code references retained | Focused current/review/query regressions; Schema 14 checkpoint: 1,311 + 2, no bootstrap; schema 15 evidence is linked above. |
| Supplementary HTTP archives | Recording supported but not required for ordinary current-state use | Transport recorder/reader ports; `github.record_messages=false`; visible expected recording failures; bounded read-only inspect/reparse | `tests/unit/test_transport_recording.py`; Schema 14 checkpoint: 1,311 + 2, no bootstrap; schema 15 evidence is linked above. |
| Collection/exchange | Required scope/member/terminal evidence independent of optional archives | Immutable current-resource page receipts; full/selective single-repository exchange; shared update/conflict/dependency admission | Current collection/exchange tests; Schema 14 checkpoint: 1,311 + 2, no bootstrap; schema 15 evidence is linked above. |
| CAS-41 | Required active physical quarantine count in backup manifests | Copied verified count; strict nonnegative int64 JSON integer; compare before restore diagnostic scan; full-byte checks retained | 39 focused maintenance/CAS/e2e checks passed on Python 3.12.14 / SQLite 3.53.1 without bootstrap; Schema 14 checkpoint: 1,311 + 2, no bootstrap; schema 15 evidence is linked above. |
| D2 | `not_applicable / retired` | No legacy importer or identity fabrication | Retirement is deliberate; historical receipts preserved. |
| LFS/attachments | Pointer bytes / source text and embedded URLs only | No object-body download or automatic URL fetching | Existing Git/text preservation scope; body acquisition deferred. |

## Evidence index

All code paths below are relative to `src/repo_catalog/`; tests are relative to `tests/integration/`.

| Key | Production evidence | Contract tests |
|---|---|---|
| P | `resources/catalog3.sql`; `adapters/sqlite/parser_model.py` | `test_catalog3_parser_model.py`; `test_catalog3_adversarial_model.py` |
| W | `adapters/github/persistence.py`; `adapters/github/collector.py`; `adapters/git/importer.py`; `application/parsing_service.py` | `test_catalog3_parsing_runtime.py`; `test_catalog3_github_runtime.py`; `test_catalog3_git_runtime.py` |
| R | `application/pr_queries.py`; `application/query_service.py`; `application/target_queries.py` | `test_catalog3_pr_scope_coverage.py`; `test_catalog3_coverage_queries.py`; query/e2e suites |
| X | `resources/exchange.sql`; `adapters/sqlite/exchange.py`; `application/exchange_service.py` | `test_catalog3_exchange.py`; `test_catalog3_exchange_integrity_audit.py` |
| C | `resources/cas_integrity.sql`; `adapters/sqlite/cas_integrity.py`; `application/maintenance_service.py` | `test_catalog3_cas_integrity.py`; adversarial repair tests |
| B | `domain/payload.py`; `adapters/sqlite/payloads.py`; payload tables in `catalog3.sql` | `test_catalog3_payload_cas.py` |
| I | `resources/identity_relations.sql`; `adapters/sqlite/identity_relations.py`; `application/repository_identity.py` | `test_catalog3_identity_relations.py`; `test_catalog3_portable_identity.py` |
| J | `application/job_plans.py`; `application/collection_service.py`; `application/source_service.py`; Job plan tables in `catalog3.sql` | `test_catalog3_job_plans.py`; `test_catalog3_portable_identity.py` |
| CLI | `application/parser_service.py`; `application/identity_service.py`; `cli/main.py` | `test_catalog3_model_cli.py` |
| A | Independent SQL/admission attacks; detailed counterexamples in `model-integration-audit.md` | `test_catalog3_adversarial_model.py` (33 focused cases at review checkpoint) |
| G | `resources/git_facts.sql`; `adapters/git/parsing.py`; `application/git_query_context.py` | `test_catalog3_git_fact_contracts.py`; `test_catalog3_git_readers.py`; `test_catalog3_pr_git_readers.py` |
| Q | `adapters/sqlite/json_contracts.py`; generated `resources/json_contracts.sql`; `application/catalog_validation.py` | `test_catalog3_json_contracts.py`; `test_catalog3_maintenance_contracts.py` |
| S | `adapters/sqlite/exchange.py`; `adapters/sqlite/coverage.py`; completion markers and acquisition publications | `test_catalog3_selective_exchange.py`; installed wheel/sdist acceptance |
| N | Independent remaining-contract review; R1–R14 in `model-integration-audit.md` | `test_catalog3_remaining_adversarial.py` (53 cases at the schema13 checkpoint) |
| LS | `resources/current_resources.sql`; `domain/current_state.py`; `adapters/sqlite/current_resources.py`; `adapters/github/current_parser.py`; `application/issue_queries.py` | `test_current_resources.py`; `test_current_state_independent_review.py`; `test_catalog3_current_queries.py` |
| LC | `resources/current_collections.sql`; `adapters/sqlite/current_collections.py`; current collection/exchange integration | `test_catalog3_current_collection.py`; `test_catalog3_current_exchange.py` |
| T | Recorder/reader protocols and adapters in `adapters/recording.py`; `adapters/github/transport.py`; message actions in `application/parser_service.py` | `tests/unit/test_transport_recording.py` |

## D1–D38

| Decision | Contract | Baseline | Integrated status | Evidence / remaining work |
|---|---|---|---|---|
| D1 | Portable independent acquisitions | partial | implemented | Permanent fetch UUIDs survive exchange; independent same-byte acquisitions remain distinct (W, X, A). |
| D2 | Strict evidence for legacy observation identity | partial | not_applicable / retired | Legacy reconciliation was deliberately retired with v2 migration. No old-record identity is inferred; identity fabrication remains prohibited. Historical receipts are retained. |
| D3 | Reparse identity separate from acquisition | unimplemented | implemented | Historical offline reparse creates a new result/facts and retains fetch UUID/time/bytes; explicit selection is required (W, CLI). Supplementary message reparse returns a bounded read-only projection retaining source time, without admission (T). |
| D4 | Conflicting current choices stay unresolved | unimplemented | implemented | Multiple DAG heads and conflicting immutable variants produce no ordinary current; both arrival orders tested (P, X, A). |
| D5 | No timestamp-only decision ordering | partial | implemented | Historical fact/profile decisions derive from sealed DAG heads, not time/UUID order (P, A). Current provider rows use proven comparable clocks or an explicit live revision/scope fence; receipt/parsing time alone cannot pick a winner (LS). |
| D6 | Immutable current predecessor DAG | unimplemented | implemented | Immutable historical/profile decisions, predecessor manifests and publication membership prevent late edge mutation (P, A/A1). Mutable Issue/review states are outside sealed result membership (LS). |
| D7 | Explicit multi-parent conflict resolution | unimplemented | implemented | Historical selection decisions explicitly converge heads; late old dependencies do not create a newer winner (P, A). Current-resource conflicts use scoped admission, with no fabricated selection DAG (LS). |
| D8 | Missing dependencies block integrated current | unimplemented | implemented | Durable parser/exchange staging and dependency blocks suppress integrated current while dependencies are absent (P, X, A). |
| D9 | Dependency arrival promotes without new identity | unimplemented | implemented | Dependency admission retries staged decisions/records using the same UUIDs, including reopening the database (P, X, CLI). |
| D10 | Issuer-independent qualified admission | unimplemented | implemented | Admission validates definition, evidence, ownership and DAG independently of issuer; receiving trust remains explicit and local (P, X). |
| D11 | Explicit service equivalence only | partial | implemented | Explicit immutable service/repository relations; URL matching never merges namespaces (I, portable-identity tests). |
| D12 | Permanent repository UUID identity | partial | implemented | CSPRNG UUIDv4 repository identity and canonical byte-length guards; all ordinary FKs use repository_uuidv4 (I, A, portable-identity tests). |
| D13 | Conflicting repository binding staging | partial | implemented | Conflicting provider-binding insertion is held by generic exchange staging; independent records can still be admitted (X; binding UNIQUE constraints in catalog3.sql). |
| D14 | Equivalence does not rewrite identities | partial | implemented | Equivalence closure preserves independent repository rows, IDs, facts and coverage; no merge/rekey operation (I). |
| D15 | Conflicting provider binding staging | partial | implemented | Conflicting provider ID for an existing repository/service binding cannot replace its immutable row and is staged (X; repository_bindings constraints). |
| D16 | Derived equivalence transitive closure | unimplemented | implemented | Recursive equivalence views retain direct assertions separately from transitive derivation (I). |
| D17 | Immutable equivalence cancellation | unimplemented | implemented | Separate immutable cancellation records invalidate relations without editing their assertions (I, CLI). |
| D18 | Historical name set without scalar current | partial | implemented | Immutable name observations and DISTINCT historical name view; generated names require published usable selected-profile results, while manual names remain independent (I, P, A). |
| D19 | Cancellation-first atomic arrival | unimplemented | implemented | Cancellation-first staging promotes relation and cancellation in one savepoint, without intermediate active relation (I, CLI). |
| D20 | Names resolve only when unambiguous | partial | implemented | Historical name selection requires a unique repository UUID; ambiguity is an error (I). |
| D21 | Permanent name-observation UUID | unimplemented | implemented | Each name observation has independent permanent UUID; identical displayed names are deduplicated only by the view (I, A). |
| D22 | Immutable UID collisions stage dependencies | unimplemented | implemented | Immutable-content conflicts retain original data, stage incoming variants and block affected results/scopes independent of receipt order (X, A). |
| D23 | Payload byte sharing is not observation identity | implemented | implemented | Exact payload bytes and representation sharing remain separate from permanent fetch identity (B, W). |
| D24 | Ordinary reads require verified selected profile | unimplemented | implemented | Historical readers use eligible results and explicit trusted profiles; current rows carry exact parser/profile attribution and eligibility independently of archive/result membership (P, W, R, LS). Reparse/receipt never upgrades the selected profile. |
| D25 | Permanent independent parsed-result UUID | unimplemented | implemented | Immutable interpretations retain independent result UUID/input/output publications and reimport identity (P, W, X). Mutable current rows are not result-owned immutable facts and do not create a result for every refresh (LS). |
| D26 | Exchange nonselected parser interpretations | unimplemented | implemented | Unaffected repository interpretations and inputs remain exchangeable without receiver trust; Source-owned results are excluded (X, W). Current-state rows/profile attribution/required proofs exchange without mandatory historical transcripts (LS, LC). |
| D27 | Immutable full parser/profile definition | unimplemented | implemented | Definition binds implementation digest, settings, output schema and capability manifest; immutable UUID/content admission (P, A). |
| D28 | Multiple owner-checked input references | unimplemented | implemented | Immutable results retain multiple fetch/Git/source inputs and sealed membership (P, W, A). Current rows preserve typed owner/acquisition scope and minimum collection proof without a mandatory HTTP-body input (LS, LC). |
| D29 | Direct parsed-result FK on generated facts | unimplemented | implemented | Immutable Git/history facts retain result ownership, publications, acquisition seals and selected eligibility (G, W, R, N). Scoped Issue/review current rows are mutable and have parser/profile attribution rather than sealed output membership (LS). |
| D30 | Owner/fact-kind profile selection scope | unimplemented | implemented | Repository, CR and Source scopes include fact kind; exact verified-profile and fact-selection DAGs are separate (P, CLI). |
| D31 | Exclusive repository/source result ownership | unimplemented | implemented | Immutable result ownership remains XOR with matching inputs/facts, including Source-derived names (P, A). Current rows independently enforce repository/binding/service/parent ownership (LS). |
| D32 | CR inheritance only without local selection | unimplemented | implemented | CR scope absence permits inheritance; present empty, staged or conflicting CR scope blocks fallback (P, A, R). |
| D33 | Immutable verification and separate trust | unimplemented | implemented | Immutable verification runs and invalidations are separate from mutable catalog-local trust; trust is excluded from exchange (P, X, CLI). |
| D34 | Decision references exact profile verification | unimplemented | implemented | Composite profile+verification FK; invalidating one selected run never substitutes a newer passing run (P, A). |
| D35 | Passed verification covers full profile | unimplemented | implemented | Passed evidence must match the definition digest and every declared capability exactly; partial, duplicate and malformed evidence rejected (P, A). This validates recorded evidence; operator trust is still explicit. |
| D36 | Composite ownership constraints | partial | implemented | Immutable generated Git facts retain non-NULL result/repository/acquisition ownership, input guards and sealed membership (G, P, N). Current stores add direct canonical-ID, kind/owner/parent/reply/thread/scope constraints; missing valid parents stage, malformed owners reject (LS, LC). |
| D37 | Separate source-owned acquisition evidence | unimplemented | implemented | Separate Source input UUID/time/context/payload records drive Source-owned inventory results (W, J). |
| D38 | Independent source profile selection | unimplemented | implemented | Source/fact-kind scopes use independent verified profile selection and fact DAGs (P, W, J). |

## CAS-1–CAS-75

| Decision | Contract | Baseline | Integrated status | Evidence / remaining work |
|---|---|---|---|---|
| CAS-1 | Logical payload natural key | implemented | implemented | Logical PRIMARY KEY(representation,sha256), no surrogate payload ID (B). |
| CAS-2 | True digest collision durable staging | partial | implemented | Verified true-collision bytes preserve original and enter durable admission staging; synthetic hash collision test distinguishes bad digest (B, C, W). |
| CAS-3 | Portable self-authored JSON payload references | partial | implemented | The central JSON registry distinguishes authored/provider/operational/native-manifest fields and includes new current-scope/member/proof shapes. Typed references, unknown/local references and duplicates are checked at writer, SQL, exchange/promotion and audit boundaries; provider bytes remain opaque (Q, N, LS, LC). |
| CAS-4 | Complete bytes in each exchange unit | unimplemented | implemented | Every single-repository unit carries its required bytes; shared bytes repeat across units and deduplicate on receive (X). |
| CAS-5 | SHA-256 without digest aliases | implemented | implemented | Payload CAS uses SHA-256 only, with no alternate digest alias (B). General content candidate digests remain distinct from payload identity. |
| CAS-6 | Canonical external hex/internal BLOB | implemented | implemented | PayloadRef uses canonical lowercase 64-hex JSON and 32-byte BLOB storage; malformed encodings rejected (B, X). |
| CAS-7 | Admission and explicit full hash verification | partial | implemented | Admission recomputes hashes; explicit maintenance full scan added; ordinary reads do not run a full hash scan (B, C, CLI). |
| CAS-8 | Local corruption subgraph quarantine | unimplemented | implemented | Quarantine disables dependent usable results/current facts while unrelated data remains queryable; no destructive data removal (C, P, R). |
| CAS-9 | Schema-aware evidence reference validation | partial | implemented | Typed references validate actual target kind, repository/Source/service ownership and payload association. Missing valid dependencies stage durably across reopen and promote with original identities; malformed/wrong-kind/foreign references reject. Consumed request, code, root and marker structures have explicit schemas (Q, X, N). |
| CAS-10 | Immutable physical corruption diagnostics | unimplemented | implemented | Immutable physical corruption rows in unresolved_payloads (C). |
| CAS-11 | Cross-representation physical sharing | implemented | implemented | Representations share exact physical stored_bytes, tested independently of logical keys (B). |
| CAS-12 | Physical digest key without surrogate | implemented | implemented | Physical PRIMARY KEY(sha256), no integer physical surrogate (B). |
| CAS-13 | One diagnosis per physical object | unimplemented | implemented | One diagnostic per physical digest during continuous quarantine; shared representations derive impact (C). |
| CAS-14 | Repair only by explicit maintenance | partial | implemented | Reacquisition preserves corrupt original and stages valid incoming evidence; only explicit repair changes bytes (C, W, X). |
| CAS-15 | Atomic physical/logical admission | implemented | implemented | Stored bytes and logical payload admit under one transaction; failure rollback tested (B). |
| CAS-16 | Stage acquisitions blocked by corrupt bytes | unimplemented | implemented | Rejected acquisition retains original UUID/time/raw bytes/context in durable payload staging without repair (C, W). |
| CAS-17 | No permanent successful hash-scan history | partial | implemented | Full-scan success/progress is returned, never persisted; failed diagnostics remain (C). |
| CAS-18 | Separate local active quarantine | unimplemented | implemented | Separate payload_quarantine operational table and immutable unresolved_payloads history (C). |
| CAS-19 | Reject declared digest mismatches without bytes | implemented | implemented | Bad declared hash rejects bytes and dependent closure; bytes do not enter normal or staging storage (B, C, X, A). |
| CAS-20 | Atomic repair and quarantine release | unimplemented | implemented | Preverified replacement, transactional protection-trigger suspension/restoration, post-write hash check and quarantine removal; injected failure/process death rollback tests (C, A). |
| CAS-21 | Local-only physical corruption state | unimplemented | implemented | Physical diagnosis/quarantine is catalog-local and rejected/excluded in ordinary exchange (C, X). |
| CAS-22 | Absence of quarantine means usable | unimplemented | implemented | Quarantine table contains only active quarantine; explicit repair removes row while keeping diagnostic history (C, P). |
| CAS-23 | Exclude local diagnostics from exchange | unimplemented | implemented | Exchange allowlist excludes local diagnostics/quarantine/staging; backup retains them (X, C). |
| CAS-24 | Restore full hash scan retaining quarantine | unimplemented | implemented | Restore stage receives full physical hash scan and preserves known quarantine before publication (C). |
| CAS-25 | Interrupted scan restarts from beginning | unimplemented | implemented | Interrupted scans retain diagnostics, save no success cursor, and restart from the first digest (C). |
| CAS-26 | Atomic diagnostic plus quarantine | unimplemented | implemented | First diagnosis plus quarantine and reader publication revision commit in one savepoint (C, A). |
| CAS-27 | One diagnosis during continuous quarantine | unimplemented | implemented | Repeated continuous diagnosis reuses one record; repair then recurrence creates a new record (C). |
| CAS-28 | SQLite serializes diagnostics | unimplemented | implemented | SQLite PK and write transaction serialize quarantine admission under the common writer lock (C). |
| CAS-29 | Freeze physical bytes during full scan | unimplemented | implemented | Full maintenance scan holds catalog writer.lock so acquisition/repair cannot change target bytes (C). |
| CAS-30 | Stop payload writes during full scan | unimplemented | implemented | Normal payload writers use the same lock, while scan diagnosis uses short transactions (C, W). |
| CAS-31 | OS lock with short diagnosis transactions | unimplemented | implemented | OS FileLock encloses scan; verify_all rejects an existing long write transaction and commits each diagnosis separately (C). |
| CAS-32 | Nonblocking common writer lock | partial | implemented | Existing locks/writer.lock is nonblocking and returns WRITER_BUSY; lock regression test (C). |
| CAS-33 | Verified staged atomic restore publication | partial | implemented | Restore copies into a fresh stage, verifies file/schema/physical bytes, then atomically publishes; failed stage retained (C). |
| CAS-34 | Preserve failed stages; fresh retry stage | unimplemented | implemented | Failure/retry keeps distinct stage directories and repeats validation from backup (C). |
| CAS-35 | Never overwrite restore destination | partial | implemented | Existing restore destination rejected without mutation (C). |
| CAS-36 | Atomic no-replace restore race handling | unimplemented | implemented | Atomic no-replace publication handles competing winner; losing stage retained. Current OS support is Linux renameat2 (C; R6). |
| CAS-37 | Back up quarantined bytes and diagnostics | unimplemented | implemented | Backup retains corrupt physical bytes with their diagnosis/quarantine, allowing healthy independent data to remain usable after restore (C). |
| CAS-38 | Backup DB plus required adjacent manifest | partial | implemented | Nonoverwriting adjacent DB+manifest pair; incomplete pair is invalid and preserved (C). |
| CAS-39 | Full source hash scan before backup | unimplemented | implemented | Backup scans source first and records newly detected quarantine before copying (C). |
| CAS-40 | Full copy hash scan before publication | unimplemented | implemented | Backup copy scans all bytes and rejects unexplained new corruption before manifest publication (C). |
| CAS-41 | Quarantine count in backup manifest | pending | implemented | Required `quarantined_payload_count`, strict JSON int 0..2^63-1 excluding bool. Count verified-copy active physical rows; compare after checksum/identity before diagnosis. Positive counts allowed; mismatches/unexplained corruption reject and retain stage (C). Focused 39 checks passed; Schema 14 checkpoint: 1,311 + 2, no bootstrap; schema 15 evidence is linked above. |
| CAS-42 | 304 exchange includes original body evidence | unimplemented | implemented | 304 exchange includes original observation, result, fetch and body dependencies; truncated original stays staged, foreign-owner original rejected (X). |
| CAS-43 | Dedup bytes within each exchange unit | unimplemented | implemented | Each physical byte object occurs once within a unit; separate repository units each include their dependency bytes (X). |
| CAS-44 | Include original acquisition owner context | unimplemented | implemented | 304 dependency closure contains original fetch plus owner/binding/Source context and payload; receiver remaps local IDs (X). |
| CAS-45 | Do not install received validator cache | unimplemented | implemented | Immutable fetch and 304 evidence retain exact response ETag/status, including rejected acquisition staging; unrelated secret-bearing headers are excluded. Received validator-cache rows are never installed (W, X). |
| CAS-46 | Partial collection dependency closure | unimplemented | implemented | Historical fetch/collection selectors retain required FK/JSON/304/DAG/result/acquisition closure (S, X, N). Current collection selection adds required current rows/parents/bodies/proofs without pulling optional archive history (LS, LC); schema 14 installed checkpoint passed; current evidence is linked above. |
| CAS-47 | One repository per exchange unit | unimplemented | implemented | Exchange unit root is one repository UUID; references cannot expand to unrelated repository acquisitions (X). |
| CAS-48 | Shared source context without other repositories | unimplemented | implemented | Referenced Source/service context included with target repository relation only; receiving operational settings remain independent (X, A). |
| CAS-49 | No unsupported completeness in partial exchange | unimplemented | implemented | Historical completion retains exact markers/fetch membership/code/Git inputs/publications (S, R, N). Current completion uses immutable scoped page/member/terminal receipts independent of supplemental bytes; missing proof cannot become complete. Receiver conflicts remain unresolved and latest partial/unknown/conflict never falls back to older complete claims (LC, R). |
| CAS-50 | Exclude source-wide completeness evidence | unimplemented | implemented | Source-wide inventory complete evidence excluded from repository units (X). |
| CAS-51 | Separate historical request and current settings | partial | implemented | Saved fetch/request context and frozen job plans are separate from mutable local Source settings; exchange retains sender provenance variants (W, X, J, A). |
| CAS-52 | Map colliding local source IDs independently | unimplemented | implemented | Source registration UUID maps to a distinct receiver-local source ID; collision round-trip tests (X). |
| CAS-53 | Exclude all source-wide inventory from exchange | unimplemented | implemented | All Source-owned evidence/results and Source-derived names excluded, independent of completeness state (X). |
| CAS-54 | Persist source registration/local mapping | partial | implemented | Durable exchange identity mappings reused for repeated imports and forwarding; original intake catalog retained in delayed staging (X, A). |
| CAS-55 | Nonunique service display name | implemented | implemented | Service display name is nonunique; service UUID remains identity (portable-identity tests). |
| CAS-56 | Reject ambiguous service selection | implemented | implemented | Ambiguous named/implicit service selection rejects and requires UUID (portable-identity tests). |
| CAS-57 | Permanent source registration UUID | implemented | implemented | Immutable canonical Source registration UUID distinct from local source_id, preserved by backup/exchange (portable-identity tests, X). |
| CAS-58 | Immutable source service membership | partial | implemented | Service membership immutable; conflicting incoming Source identity stages dependents (X, portable-identity tests). |
| CAS-59 | Local settings not overwritten by exchange | unimplemented | implemented | Incoming operational settings stored as provenance; receiver settings unchanged, including changed sender settings under same identity (X, A). |
| CAS-60 | Immutable source discovery kind | partial | implemented | Source discovery kind immutable; differing incoming definition cannot overwrite it (X, portable-identity tests). |
| CAS-61 | Imported source initially unconfigured | unimplemented | implemented | First received Source has settings=NULL until explicit local configuration; original settings retained separately (X, CLI). |
| CAS-62 | Local source display names retained | unimplemented | implemented | Receiver Source display name stays local across repeated provenance variants (X, A). |
| CAS-63 | Nullable configuration and preflight validation | implemented | implemented | NULL means unconfigured; non-NULL JSON validated further before acquisition and explicit configuration (J, CLI, portable-identity tests). |
| CAS-64 | Select sources by IDs only | implemented | implemented | Source display names are not selectors; local ID or registration UUID only (portable-identity tests). |
| CAS-65 | Bulk unconfigured skip without remote evidence | implemented | implemented | Bulk unconfigured Source skipped with persisted reason; no fake remote observation or coverage (J, portable-identity tests). |
| CAS-66 | Explicit source selector namespaces | implemented | implemented | Cross-namespace ambiguity rejects; local:/registration: prefixes resolve explicitly (portable-identity tests). |
| CAS-67 | Missing preflight credentials skip source | partial | implemented | Missing credential preflight skips only that bulk Source without remote evidence (J). |
| CAS-68 | Mixed success/skip terminal partial result | partial | implemented | Mixed acquired/skipped Sources finish attempt complete with persisted Result.status partial (J). |
| CAS-69 | Explicit source credential failure before job | partial | implemented | Explicit Source credential failure rejects before Job or remote evidence creation (J). |
| CAS-70 | Persist per-source attempt outcomes | partial | implemented | Per-Source attempt outcomes/diagnostics and final response status persisted (J). |
| CAS-71 | No usable sources means no job | partial | implemented | Zero usable bulk Sources returns aggregated reasons without creating Job (J). |
| CAS-72 | Atomic terminal state and result | partial | implemented | Terminal Job state, Source outcomes and Result status commit atomically (J, portable-identity tests). |
| CAS-73 | Postcreation all-source skips terminal partial | partial | implemented | Postcreation credential loss for all Sources yields complete attempt, partial result and no fabricated evidence (J). |
| CAS-74 | Freeze job target registration UUIDs | unimplemented | implemented | Job captures target Source registration UUID set; resume ignores subsequently added Sources (J). |
| CAS-75 | Freeze nonsecret acquisition settings | unimplemented | implemented | Immutable nonsecret source plan/settings retained across resume; secret values rejected and credentials resolved at use (J). |

## Completed checkpoint gaps and explicit limits

Within the older 113-identifier mapping: **112 implemented, 0 partial, 1 not_applicable / retired (D2)**, with scoped supersessions above. This is a decision/implementation classification, not a test count or proof that all later boundaries passed. Prior checkpoint receipts remain in [`2026-10-09-complete-model-contracts.json`](validation/synthetic/2026-10-09-complete-model-contracts.json). Current implementation mapping and final verification belong in [latest-state-transport-implementation.md](latest-state-transport-implementation.md), the integration handoff and submitted PR body.

1. **R1 — Low-level Git interpretations (D29/D36), completed.** Schema 13 splits retained raw Git bytes from result-owned metadata, structure, traversal and text. Offline reparse retains acquisition identity, and ordinary/explicit readers, search, exchange and maintenance consume the owner-checked interpretations. Independent review covers sealed publication, ownership, identity conflicts and raw Git OID validation.
2. **R2 — General self-authored JSON references (CAS-3/CAS-9), prior checkpoint completed.** The schema13 50-field registry introduced callback-free SQL guards and typed ownership checks at writer/exchange/full-audit boundaries. Schema14 extends the registry for current resource scopes, page members and proofs; the authoritative inventory is generated from the current registry. Valid missing dependencies remain staged; provider projections keep their separate classification.
3. **R4 — Selective collection exchange (CAS-46/CAS-49), completed.** Fetch/collection selectors preserve exact required dependency and publication closure. Complete evidence is frozen and scope-specific; incomplete subsets, missing/conflicting proof and latest unknown/partial observations stay unresolved. Receipt ordering, repeat receipt, reopening, later full convergence and real synthetic GitHub/304 transport are exercised.
4. **R5 — Retired legacy intake (D2).** No old catalog reconciliation or migration remains. This is intentional for a pre-release incompatible format. If legacy intake is later reintroduced, require strict original backup/record proof; digest or names alone cannot establish observation identity.
5. **R6 — Platform and operational limits.** Atomic restore publication currently depends on Linux `renameat2`; another platform requires an equivalent no-replace primitive, not a check-then-rename fallback. Repair does not automatically replay retained rejected acquisitions; an explicit later import/retry is needed. OS-kill tests cover interrupted SQLite repair, not hardware power loss or every filesystem durability failure.
6. **R7 — Prior checkpoint and current local acceptance.** The schema13 checkpoint passed unflagged ordinary and installed-package acceptance (1,161 + 2, one opt-in live exclusion). That receipt and its artifact remain historical. Schema14 verification was regenerated from the successful 1,311-case exact-definition bootstrap report; final ordinary 1,311 and isolated-package 2 cases passed without bootstrap. Exact submitted HEAD/tree and hosted CI receipt belong in the implementation report and PR body.

CAS-41 is selected and implemented. CAS-76/CAS-77 remain deferred; no content or implementation is invented for them. Archive retention/deletion, comprehensive deletion propagation, LFS/attachment body acquisition, global PR/Git history removal, non-Linux restore and broader provider collection remain outside this task. Source-wide inventory exclusion remains the single-repository exchange boundary. Coverage v2 retains exactly five claim columns and latest-observation-time set derivation, including unknown/conflict; optional recording does not redefine completeness.
