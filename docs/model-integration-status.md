# Design decision implementation status

Baseline: PR #10 (`1c69a868f65b9637a7b8cf00d2c68a4ba05b2faa`).
Integrated status describes the reviewed implementation tree, not a release certification. `implemented` means code and contract evidence exist; `partial` names a remaining contract or supported-flow gap; `unimplemented` names absent behavior. CAS-41 alone is `pending`, because it is deliberately unselected. Final full-suite, packaged-install and GitHub Actions outcomes are recorded separately; they are not implied by these classifications.

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

## D1–D38

| Decision | Contract | Baseline | Integrated status | Evidence / remaining work |
|---|---|---|---|---|
| D1 | Portable independent acquisitions | partial | implemented | Permanent fetch UUIDs survive exchange; independent same-byte acquisitions remain distinct (W, X, A). |
| D2 | Strict evidence for legacy observation identity | partial | unimplemented | Legacy reconciliation was deliberately retired with v2 migration. No old-record identity is inferred; a future legacy intake would need backup+original-record proof before reuse. |
| D3 | Reparse identity separate from acquisition | unimplemented | implemented | Offline reparse creates a new result/facts and retains fetch UUID, time and bytes; explicit selection is required (W, CLI). |
| D4 | Conflicting current choices stay unresolved | unimplemented | implemented | Multiple DAG heads and conflicting immutable variants produce no ordinary current; both arrival orders tested (P, X, A). |
| D5 | No timestamp-only decision ordering | partial | implemented | Current/profile eligibility derives from sealed DAG heads, not time/UUID order; delayed predecessor tests use reversed timestamps (P, A). |
| D6 | Immutable current predecessor DAG | unimplemented | implemented | Immutable decisions, predecessor manifests and publication membership prevent late edge mutation (P, A/A1). |
| D7 | Explicit multi-parent conflict resolution | unimplemented | implemented | Multi-parent decisions explicitly converge heads; late old dependencies do not create a newer winner (P, A). |
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
| D24 | Ordinary reads require verified selected profile | unimplemented | implemented | Ordinary PR/document/code/snapshot readers use eligible results and explicit trusted-profile selections; reparse/receipt never upgrades the selected profile (P, W, R). |
| D25 | Permanent independent parsed-result UUID | unimplemented | implemented | Independent CSPRNG result UUID and immutable input/output publications; reimport preserves UUID (P, W, X). |
| D26 | Exchange nonselected parser interpretations | unimplemented | implemented | Repository exchange carries all repository-owned profile interpretations and their inputs without importing receiver trust (X, W). Source-owned results intentionally excluded from this exchange unit. |
| D27 | Immutable full parser/profile definition | unimplemented | implemented | Definition binds implementation digest, settings, output schema and capability manifest; immutable UUID/content admission (P, A). |
| D28 | Multiple owner-checked input references | unimplemented | implemented | Multiple fetch/Git/source inputs with exact owner FKs and sealed input membership (P, W, A). |
| D29 | Direct parsed-result FK on generated facts | unimplemented | partial | PR/document/review/thread/code/inventory/name/snapshot/ref observations have result ownership and output seals (P, W, A). Low-level commits/tree_entries/contents still store shared Git structural or text projections without per-profile result facts; see residual R1. |
| D30 | Owner/fact-kind profile selection scope | unimplemented | implemented | Repository, CR and Source scopes include fact kind; exact verified-profile and fact-selection DAGs are separate (P, CLI). |
| D31 | Exclusive repository/source result ownership | unimplemented | implemented | Repository/Source result ownership is XOR and matching input/fact ownership is enforced, including Source-derived repository names (P, A). |
| D32 | CR inheritance only without local selection | unimplemented | implemented | CR scope absence permits inheritance; present empty, staged or conflicting CR scope blocks fallback (P, A, R). |
| D33 | Immutable verification and separate trust | unimplemented | implemented | Immutable verification runs and invalidations are separate from mutable catalog-local trust; trust is excluded from exchange (P, X, CLI). |
| D34 | Decision references exact profile verification | unimplemented | implemented | Composite profile+verification FK; invalidating one selected run never substitutes a newer passing run (P, A). |
| D35 | Passed verification covers full profile | unimplemented | implemented | Passed evidence must match the definition digest and every declared capability exactly; partial, duplicate and malformed evidence rejected (P, A). This validates recorded evidence; operator trust is still explicit. |
| D36 | Composite ownership constraints | partial | partial | Composite owner FKs plus XOR/NOT NULL guards cover modeled parsed inputs/facts; direct SQL NULL/cross-owner attacks and generated-name exceptions tested (A). Remaining low-level Git projection split is the same R1 gap as D29. |
| D37 | Separate source-owned acquisition evidence | unimplemented | implemented | Separate Source input UUID/time/context/payload records drive Source-owned inventory results (W, J). |
| D38 | Independent source profile selection | unimplemented | implemented | Source/fact-kind scopes use independent verified profile selection and fact DAGs (P, W, J). |

## CAS-1–CAS-75

| Decision | Contract | Baseline | Integrated status | Evidence / remaining work |
|---|---|---|---|---|
| CAS-1 | Logical payload natural key | implemented | implemented | Logical PRIMARY KEY(representation,sha256), no surrogate payload ID (B). |
| CAS-2 | True digest collision durable staging | partial | implemented | Verified true-collision bytes preserve original and enter durable admission staging; synthetic hash collision test distinguishes bad digest (B, C, W). |
| CAS-3 | Portable self-authored JSON payload references | partial | partial | Portable payload references and 304 original observation/result/fetch references are validated without rewriting provider bytes (B, W, X). No comprehensive schema registry validates every self-authored JSON provenance field; see R2. |
| CAS-4 | Complete bytes in each exchange unit | unimplemented | implemented | Every single-repository unit carries its required bytes; shared bytes repeat across units and deduplicate on receive (X). |
| CAS-5 | SHA-256 without digest aliases | implemented | implemented | Payload CAS uses SHA-256 only, with no alternate digest alias (B). General content candidate digests remain distinct from payload identity. |
| CAS-6 | Canonical external hex/internal BLOB | implemented | implemented | PayloadRef uses canonical lowercase 64-hex JSON and 32-byte BLOB storage; malformed encodings rejected (B, X). |
| CAS-7 | Admission and explicit full hash verification | partial | implemented | Admission recomputes hashes; explicit maintenance full scan added; ordinary reads do not run a full hash scan (B, C, CLI). |
| CAS-8 | Local corruption subgraph quarantine | unimplemented | implemented | Quarantine disables dependent usable results/current facts while unrelated data remains queryable; no destructive data removal (C, P, R). |
| CAS-9 | Schema-aware evidence reference validation | partial | partial | FK-backed portable record envelopes and 304 self-authored references validate types, target identity, payload and owner (X). General JSON provenance schema/ownership coverage remains incomplete (R2). |
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
| CAS-41 | Quarantine count in backup manifest | pending | pending | Unselected by the user. No quarantine-count manifest policy or field introduced. |
| CAS-42 | 304 exchange includes original body evidence | unimplemented | implemented | 304 exchange includes original observation, result, fetch and body dependencies; truncated original stays staged, foreign-owner original rejected (X). |
| CAS-43 | Dedup bytes within each exchange unit | unimplemented | implemented | Each physical byte object occurs once within a unit; separate repository units each include their dependency bytes (X). |
| CAS-44 | Include original acquisition owner context | unimplemented | implemented | 304 dependency closure contains original fetch plus owner/binding/Source context and payload; receiver remaps local IDs (X). |
| CAS-45 | Do not install received validator cache | unimplemented | implemented | Immutable fetch and 304 evidence retain exact response ETag/status, including rejected acquisition staging; unrelated secret-bearing headers are excluded. Received validator-cache rows are never installed (W, X). |
| CAS-46 | Partial collection dependency closure | unimplemented | partial | Importer supports incomplete units, portable collection context and delayed dependencies. Public exporter only exports whole repositories; no F1-only collection/fetch selector yet (R4). |
| CAS-47 | One repository per exchange unit | unimplemented | implemented | Exchange unit root is one repository UUID; references cannot expand to unrelated repository acquisitions (X). |
| CAS-48 | Shared source context without other repositories | unimplemented | implemented | Referenced Source/service context included with target repository relation only; receiving operational settings remain independent (X, A). |
| CAS-49 | No unsupported completeness in partial exchange | unimplemented | partial | Complete claims require acquisition proof and explicit dependency closure; truncated completion markers remain staged (X). Selective collection export and minimal completeness closure remain unfinished with CAS46 (R4). |
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

## Remaining work and explicit limits

1. **R1 — Low-level Git interpretations (D29/D36).** Snapshot/ref/code selections are result-owned, but shared `commits.metadata`, structural commit/tree rows and `contents` text projections are not separate per-profile observations. The next implementation must split parser-dependent projections from immutable Git identity/raw bytes, attach owner/result keys and output membership, then route all readers through the selected interpretation. Shared rows must never be overwritten to simulate that split.
2. **R2 — General self-authored JSON references (CAS3/CAS9).** Payload references and 304 evidence have concrete validation. Add registered schemas for the remaining application-authored provenance/derivation documents, validate embedded references and owners on writer and import paths, and add malformed/cross-owner negative tests. Provider JSON stays untouched.
3. **R4 — Selective collection exchange (CAS46/CAS49).** Add a fetch/collection subset exporter with exact dependency closure. Omit global completion markers/complete claims unless their full proof is included; test F1-only export from F0/F1/F2, both arrival orders and later full-unit promotion. Current full-repository export and dependency-aware intake do not provide that selector.
4. **R5 — Retired legacy intake (D2).** No old catalog reconciliation or migration remains. This is intentional for a pre-release incompatible format. If legacy intake is later reintroduced, require strict original backup/record proof; digest or names alone cannot establish observation identity.
5. **R6 — Platform and operational limits.** Atomic restore publication currently depends on Linux `renameat2`; another platform requires an equivalent no-replace primitive, not a check-then-rename fallback. Repair does not automatically replay retained rejected acquisitions; an explicit later import/retry is needed. OS-kill tests cover interrupted SQLite repair, not hardware power loss or every filesystem durability failure.
6. **R7 — Acceptance gate.** Final ordinary/package tests must use genuine packaged verification evidence bound to the final implementation. Synthetic development bootstrap runs are useful regression evidence but are not that acceptance gate. The final validation record contains local results; the submitted PR body records its exact published HEAD and hosted CI result.

No new choice was made for CAS-41, CAS-76 or CAS-77. Source-wide inventory exclusion is an implemented single-repository exchange boundary, not an unfinished export dependency. Coverage model v2 retains its five-column claim table and existing state derivation; these changes integrate selection and admission without replacing that model.
