# Transition plan: Git history, structure and notes catalog without file archival

**Accepted target scope:** [ADR 0014 / GCTX-S01](../adr/0014-history-and-notes-catalog-without-file-archive.md), refined for notes-ref discovery by [ADR 0015 / B01-R01](../adr/0015-automatic-git-notes-ref-discovery.md) and immutable capture-scoped notes-ref observation identity by [ADR 0016 / B01-R02](../adr/0016-immutable-notes-ref-capture-observations.md).
**Design base:** PR #54, `0301fcc8aeef427e2b9e2a3197a4ed993dcdf657`.
**Repository-wide key rule:** [ADR 0017 / KEY-P01](../adr/0017-domain-keys-without-storage-surrogates.md) prohibits storage-only surrogate PKs: use natural/domain composites and preserve already-fixed permanent repository, genuine capture and physical-instance identities. [ADR 0018 / B01-R03](../adr/0018-notes-capture-uuidv4-composite-identity.md) fixes direct `(capture_origin_uuidv4,capture_uuidv4)` capture PK/FK; [ADR 0019 / B01-R04](../adr/0019-monotonic-notes-capture-fact-admission.md) fixes monotonic compatible immutable fact/group admission and exact replay, while [ADR 0020 / B01-R05](../adr/0020-immutable-competing-notes-member-claims.md) now fixes immutable competing notes member reports and derived conflicts; B01-R06 semantic claim keys and physical instance identity encoding remain open.
**Implemented source format:** Three-Store Core 21 / Operational 1 / Search 1. No implementation, schema version or runtime change is made by this plan.

## 1. Product boundary before physical tables

Retain repository identity, Git object metadata, commit history, tree structure, tags, ref observations and Git notes. Preserve actually acquired commit/tree/tag representations and note content so exact metadata can be checked and reanalyzed. Ordinary repository-file blob bodies are outside the product, not an optional archival mode.

Git Core must still work with no original bytes and no Context, as required by GCTX-M01. The retained-type capability does not require every source to supply raw commit/tree/tag data or complete notes. Missing evidence is not replaced by fake values or implicit fetching. A no-body file entry is normal and outside physical quarantine, not a corrupted CAS instance.

Notes are a role of Git blobs, not a native `note` object type. Native type checks and retention-purpose checks are separate. The retained-body admission boundary permits commit/tree/tag data and evidenced note content, not every object reachable from them. Annotated tag targets, annotated note targets and normal tree blob children do not inherit body retention permission.

## 2. Logical model (not approved DDL or final table names)

| Component | Durable meaning | Body/verification rule |
| --- | --- | --- |
| Nominal object registry | One `(object_format, oid)` subject across repositories | No inherent type, size, body or verified status |
| Field claims | Actual supplied type/size/message/author/time claims with source and scope | Keep unknown and contradictory values; do not fabricate raw-content digests |
| Commit relations | Ordered parents and tree target with observation grouping | Verified structure may use exact retained commit bytes; referenced ordinary blobs are not required |
| Tree relation groups | Names, modes, child OIDs, known order/partial/complete scope | Do not union incompatible captures; gitlinks remain distinct from ordinary blobs |
| Tag objects and observations | Annotated-tag attributes/body; lightweight tag refs as observations | No fabricated tag object for a lightweight ref; no target-blob hydration |
| Notes captures | Repository, full notes ref, observed root kind/OID if known, target OID, note OID, observed path and provenance | Independent from target object presence; keep old captures when ref changes |
| Notes bodies | Annotation content and exact source bytes where available, plus explicit decoding provenance | Native object type remains blob; retain by notes role. Reported text is not fabricated raw serialization |
| Retained metadata representations | Actual locally validated commit/tree/tag/notes bytes and intrinsic linkage | Existing M05–M09 integrity/instance rules apply; no generic file-object archive |
| Context | Provider/Source/PR/Issue/review state, associations, text and conflicts | Independently durable and mutable where already permitted; not a file archive escape hatch |
| Operational / Search | Retry/cache state and rebuildable metadata/notes indices | Deletion cannot erase canonical evidence; excluded ordinary file text is not retained in either |

ADR 0016 / B01-R02 fixes a **distinct immutable capture-scoped identity per genuine notes-ref observation**, even when repository/ref/root and member reports match another capture; associated notes member groups must reference their original observation. A replay of the same genuine capture is idempotent. Repository/ref/root/annotated OID are **not** a sufficient natural key for the observation. ADR 0017 forbids a separate receiver-local storage surrogate; ADR 0018 / B01-R03 fixes the direct origin UUIDv4 plus capture UUIDv4 composite PK/FK and new-observation issuance. ADR 0019 / B01-R04 fixes compatible same-capture incremental immutable facts/groups and idempotent exact replay; untrusted source/replay authentication, ADR 0020 / B01-R05 fixes competing immutable member report preservation and derived conflicts; exact semantic key and further evidence remain B01-R06 and related contracts; table names/FKs, member grammar, path evidence and completeness remain later design work. A notes ref may point directly to a tree, and source-reported captures may lack a verified root; do not invent a notes commit or call an unverified association intrinsic.

Same-OID file/note reuse shares nominal identity, while the retention-purpose relation remains explicit. It is legitimate to store bytes in their evidenced annotation role without reintroducing a general API for restoring repository files. Untrusted strings such as `is_note=true` are not a substitute for the typed notes ingestion contract.

## 3. Source-schema and call-site impact audit

The existing inventory is **70 Core, 10 Operational, 4 Search product tables**, not a target count. Each final table's genuine domain PK and every child FK must be audited under ADR 0017; legacy `*_id INTEGER PRIMARY KEY` storage-only surrogates are not grandfathered. Typed immutable occurrence/physical-instance identity must be justified, not invented for convenient joins. `src/repo_catalog/adapters/sqlite/schema.py` composes production SQL. Implementation MUST inventory every source table, column, FK, view, trigger, index, writer, reader, validator and Exchange key; this grouped map is a starting point, not a completed exhaustive audit.

| Existing group | Redesign action | Required counterexample |
| --- | --- | --- |
| `git_objects` | Common nominal OID plus attributed metadata; do not restore mandatory body or mutable verified-bit gates | Metadata-only blob with unknown size is usable |
| `commits`, `commit_parents`, `tree_objects`, `tree_entries`, `tag_objects` | Preserve typed metadata and allowed exact representations; keep late references by actual OID, not UPDATE hydration | Parent/child missing, lightweight tag and tag-to-blob work without file content |
| `git_object_payloads`, `stored_bytes`, `payloads` | Scope admission to retained metadata and notes; physical-instance redesign remains under M08/M09 | A generic ordinary blob admission is refused even when correctly hashed |
| `contents`, `content_digests`, `blob_content_map` | Remove ordinary file body ownership/preservation dependency. Retain useful supplied digest metadata as attributed claims, not false local computation | SHA-1 Git OID must not become a raw-body SHA-256 |
| `git_commit_facts`, `git_name_facts`, `git_text_facts` | Retain commit/name and notes decoding; remove ordinary file `raw_text` storage and file-content FTS feed | Excluded file cannot reappear in a text fact or Search after rebuild |
| `git_acquisitions`, `ref_observations`, `snapshots`, `repository_object_sources`, roots/manifests | Capture metadata and allowed metadata-body acquisition separately from full Git object closure | Complete requested tree inventory with intentionally omitted file bodies is not a full repository backup |
| `preservation_obligations` | Remove future obligations to retrieve/preserve ordinary file bodies; keep explicitly scoped retained-metadata obligations/evidence | No job hydrates every referenced file blob |
| `payload_admission_staging`, `unresolved_payloads`, `payload_quarantine` | Do not admit excluded ordinary file bodies through failed/pending paths. Retained metadata faults still use durable diagnosis/CAS-41 | Missing never-retained file is not a quarantine; lost retained note is not normal omission |
| `root_origins`, `git_acquisitions` Source/Provider/PR fields | Continue the Core/Context split; notes provenance must work without Context | Core-only local-Git/notes catalog needs no Source registration |
| Provider resources, `text_bodies`, collection/coverage and identity tables | Preserve prior domain placement and semantics; not removed because Git file bodies are excluded | PR text remains durable Context data |
| Exchange staging/admissions and local identity mappings | Validate type and retained role before byte admission; independent partial metadata remains useful | Older sender carrying arbitrary file bytes cannot silently reinstate archive mode |
| Operational job/cache paths | Reclassify acquisition/resume work to metadata and notes; no durable hidden clones or excluded-body cache feature | Cancel/restart does not leave ordinary file content as authoritative pending data |
| Search/CLI/backup packaging | Metadata/name/message/notes/Context search only, scope-aware export/restore | A restored catalog does not claim checkout capability |

Do not blindly delete a table solely because its name contains `blob`, `payload` or `bytes`: notes use blobs and retained metadata still needs byte integrity. Do not promise a new table count before the complete audit.

## 4. Acquisition and retention enforcement

Acquisition planning separates ref discovery, commit/tree/tag metadata, notes associations and allowed content. Ordinary blob identity/attributes can be ingested without content. Current importer assumptions rejecting filtered/promisor/incomplete repositories require a scoped redesign: intentionally missing ordinary file bodies are supported, while missing retained metadata remains truthfully unknown/partial/unavailable.

Read source metadata without content filters that manufacture different object bytes when claiming exact identity. Do not use displayed or normalized Git output as byte-exact canonical evidence. Retain exact parent order, tree names/modes and explicitly chosen decoder provenance. Recompute actual OIDs before claiming byte-backed facts; neither a Provider `verified` label nor child availability is proof of parent-list completeness.

Transport may make it impossible to avoid every incidental input byte; this decision excludes **durable product archival**, not all transient network buffers. Any incidental ordinary body must not be committed to authoritative tables, replay logs, long-lived caches, failed-admission storage or a user-visible retrieval service. The concrete acquisition adapter must expose and bound such behavior. A new transient file-body verifier is not selected or necessary here.

Notes import uses the **accepted B01-R01 selector**: enumerate all observable `refs/notes/*` names (including nested suffixes), and add explicitly nominated additional notes ref names. Scope enumeration to the actual repository/source observation; absent local refs do not prove absent remote refs, and selecting a ref is not proof of a notes mapping or permission to archive arbitrary blobs. ADR 0016 / B01-R02 fixes capture-per-genuine-observation identity and ADR 0018 / B01-R03 fixes its UUIDv4 composite key. ADR 0019 / B01-R04 fixes compatible fact/group append under the same capture and exact replay; ADR 0020 / B01-R05 fixes competing member report admission; B01-R06 semantic claim keys, origin authentication, root/capture provenance details, fanout-path interpretation, binary-safe content and resource limits remain open. A notes-tree entry qualifies as annotation only through the accepted notes mapping semantics, not because a filename or ref contains the word `notes`. Arbitrary files in a notes-like tree, malformed names and unsupported modes cannot automatically authorize blob archival. API-reported notes remain attributed reports when the exact Git association is not verified.

A source may supply an empty note, a binary note, a huge note, a note about an unavailable target, or the same note OID under multiple namespaces. Keep these distinctions; do not silently strip whitespace, decode destructively, truncate or coalesce targets. Hard resource limits and namespace defaults remain an explicit design question, not guessed acceptance conditions.

## 5. Scope, integrity, backup and search

Separate metadata inventory coverage, notes inventory coverage, retained metadata-body presence and whole-repository file-content restorability. Existing Coverage five-column/latest-observation semantics remain fixed. New product-specific scope labels must not weaken old complete claims. Logical terminal absence is not an empty observation without evidence.

M05–M09 still protect retained commit/tree/tag/notes bodies. Original metadata admission remains immutable; verified byte returns check the bytes actually delivered; physical diagnosis/replacement and deterministic candidate selection apply to that retained domain. GCTX-M10 quarantine disposition and the exact CAS-41 physical-count predicate remain unresolved. No count is reduced just because ordinary file body archival is now excluded.

Backup/restore preserves the catalog, retained metadata/notes, required integrity metadata and both Core/Context where Context is included. It does not promise source-file restoration, clone completeness, `git checkout` or byte-complete `git bundle` output. Old admitted content is not silently purged: a future explicitly authorized fresh-catalog extraction must identify excluded legacy content and leave source catalogs/backups intact unless separately authorized otherwise.

Search remains reproducible from appropriate canonical stores. Index commit/tag messages, tree names, notes and Context text as supported; stop storing/indexing whole ordinary file text. Vector/search results depending on discarded file bodies cannot masquerade as fully rebuildable catalog-only Search. This does not remove existing legitimate Provider descriptions/review evidence or invent a new full API edit history.

## 6. Implementation stack, only after authorization

| Stage | Dependencies | Deliverable |
| --- | --- | --- |
| D-Scope | Existing design stack through PR #54 | ADR 0014 and this scope/transition map, documentation only |
| D-Notes | D-Scope, ADR 0015 / B01-R01, ADR 0016 / B01-R02, ADR 0018 / B01-R03, ADR 0019 / B01-R04, ADR 0020 / B01-R05 | B01-R06 semantic claim/group PKs and replay equality, notes body admission, origin trust, resources, retained representation and B03 completeness; do not reopen Capture identity, ref discovery, monotonic admission or competing claim retention |
| I-Boundary | D-Scope, relevant D-Notes choices | Complete table/call-site audit and tests prohibiting ordinary blob archival; no real-data migration |
| I-Core | I-Boundary | Nominal OIDs, claims, ordered relations, refs, commit/tree/tag and notes; append-only checks and allowed-body integrity |
| I-Context | Core identity contract | Existing durable Context separation and known-positive Source semantics; may proceed in parallel where independent |
| I-Ingest/Exchange | Core and Context contracts | Body-selection enforcement across direct import, reverse/repeat Exchange, staging, retries and failure paths |
| I-Backup/Search/CLI | Prior interfaces | Catalog-scope manifests, retained-metadata integrity, correct direct-scan fallback and no file restoration promises |
| I-Review | Relevant implementation stages | Exact-tree independent review, focused development tests, packaging/installed schema validation; full release qualification only if explicitly requested |

No stage is begun by this design PR. Unreleased single-developer status permits coherent fresh formats instead of compatibility scaffolding. Parent PRs are historical design ancestry, not an instruction to implement their superseded ordinary-body paths first.

## 7. Required future tests and actual checks

Required product counterexamples: ordinary file import without body; raw ordinary-file submission refused; note-content exception; no tag/note target-blob hydration; same-OID file/note roles; binary and empty notes; direct-tree notes roots; multiple namespaces and repeated observations; ref deletion/force-push retaining old facts; unverified API note reports; no fake raw serialization; resource-limit/partial reporting; no hidden body storage in text/Exchange/cache/Search; metadata-only Context-free operation; exact retained-byte validation; retained-note corruption and CAS-41; truthful catalog backup and unavailable checkout; safe old-to-new extraction without source deletion.

Actual check performed for this design: a disposable Git 2.47.3 fixture confirmed native commit/tree/tag types, note blobs, binary note round-trip, direct-tree notes refs and the same blob used as file and annotation. This was an upstream object-model check, not a `git-repo-db` implementation test. No runtime/DDL/restore/Exchange suite, full build, hosted-CI acceptance or independent production review is claimed.

All unchanged Source, identity, time, Coverage, Publication, Core/Context dependency, byte-integrity and ADR 0001 rules remain binding under ADR 0014's explicit scope. GCTX-M10, cross-store fences/transactions, exact backup pairing and Context GC-03/GC-04 are not selected here. No merge, release, deployment, publication-allowlist change, authenticated collection or retained-catalog mutation is authorized.
