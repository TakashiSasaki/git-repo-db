# Remaining data-model contract implementation

This change starts from PR #11, `refactor/integrated-data-model`. The six decisions
below were partial at that checkpoint. This document maps the production changes
and their executable checks. The six decisions passed independent regression
review and the final local acceptance below. Exact executed evidence is recorded
in the synthetic report; the submitted commit and hosted CI receipt are recorded
in the new stacked PR body.

All production paths in the table are relative to `src/repo_catalog/`; test paths
are relative to `tests/integration/`. The complete fresh format is schema 13,
composed by `adapters/sqlite/schema.py`. The unreleased application does not
migrate the preceding development schema.

| Decision | Original contract and checkpoint gap | Production implementation | Writer, reader and exchange integration | Executable contract checks | Acceptance |
|---|---|---|---|---|---|
| D29 | Every generated fact directly identifies its immutable parser result. Low-level Git metadata, structure and text still used shared parser projections. | `git_object_payloads` retains verified raw bytes under logical representation `git-object-raw-v1`. `commits`, `commit_parents`, `tree_entries`, `tag_objects`, `root_manifests`, `root_manifest_entries` and `git_text_facts` hold independent result-owned fact UUIDs. `contents` retains byte identity and length rather than decoded text. `parsed_fact_members` includes all these generated facts in publication seals. `git_acquisition_publications` seals exact OID/payload and traversal-root membership. | `adapters/git/importer.py` acquires bytes; `adapters/git/parsing.py` interprets retained bytes for ordinary Git/PR acquisition and offline reparse. `application/query_service.py`, `application/target_queries.py` and `adapters/sqlite/index.py` use eligible or explicitly selected Git facts. `adapters/sqlite/exchange.py` carries result interpretations and complete acquired-byte membership; ordinary backup/restore preserves the same complete schema. | `test_catalog3_git_fact_contracts.py` covers cache-free reparse, alternative metadata/text decoding, verification invalidation, quarantine/repair and conflicting fact UUIDs; `test_catalog3_git_runtime.py`; `test_catalog3_git_readers.py`; installed reparse/fact/exchange/backup checks in `tests/packaging/test_distribution.py`. | Implemented; local acceptance passed |
| D36 | Composite ownership must prevent cross-owner and NULL bypass for every generated fact. Shared Git projections previously lacked result/repository ownership. | Git facts require non-NULL result, repository, acquisition and parent object identity, matching composite result/acquisition/repository-object-source FKs, typed object guards, profile capability and acquisition-input membership. Publication prevents fact mutation/append; `git_acquisition_publications` independently seals exact object/root membership and is required before result publication. Object-format guards reject incompatible parents. | `GitParsing` emits facts under one explicit owner and acquisition. Selection has repository-current and acquisition-specific scopes. Usable-result views suppress quarantined inputs, invalid verification, blocked results and unresolved selection without rewriting history. Exchange retains immutable UUID/content conflicts and follows FK/authored JSON/manifest dependencies into local result barriers. | SQL late/update/delete/replace/NULL/cross-owner probes in `test_catalog3_git_fact_contracts.py`; NULL components, foreign result, object format, late acquired object, omitted raw bytes and disputed acquisition manifests in `test_catalog3_remaining_adversarial.py`; selected profile/result reader checks in `test_catalog3_git_readers.py`; installed owner joins/FK checks. | Implemented; local acceptance passed |
| CAS-3 | Portable authored JSON must use canonical payload and object identity references. The checkpoint validated selected concrete references without an exhaustive registry. | `adapters/sqlite/json_contracts.py` classifies JSON-bearing fields, defines typed reference names and logical payload references, rejects local identity references, malformed canonical UUID/SHA-256 encodings, unknown reference names, duplicate properties and invalid nested structures. `inventory()` discovers JSON CHECK columns and fails on an unclassified field. | `resources/json_contracts.sql` is generated from that registry and composed into production DDL. Writer boundaries and ordinary SQL guards apply authored contracts; `application/catalog_validation.py` checks inventory and, with `--full`, authored records. Provider projections and local operational records have explicit separate classifications. | `test_catalog3_json_contracts.py` covers exhaustive classification/generated-guard equality, nested canonical references, duplicate keys, local IDs, payload representation and exact bytes, and opaque provider fields. Packaging audits a populated installed catalog; the acceptance helper independently inventories the composed schema. | Implemented; local acceptance passed |
| CAS-9 | Meaningful JSON references must identify the real object kind and permitted owner, with valid missing targets staged durably. The checkpoint lacked a general ownership/admission gate. | `reference_dependencies()` extracts typed natural-key dependencies; `validate_record()` checks real targets, repository ownership, Source membership, service bindings and owner-associated logical payloads. Malformed/wrong-kind/foreign references raise contract errors; genuinely absent valid targets produce `MissingJsonDependencies`. Parser definition, input, output and predecessor manifests remain distinct schema categories. | Export validates records and closes typed JSON dependencies. Import and staged promotion validate again after local FK remapping, retain missing dependencies across reopen, and distinguish immutable conflicts. Existing exact 304 request evidence names original observation/result/fetch and payload. SQL guards enforce applicable nested owner/reference constraints without connection callbacks. | Missing multiple targets/duplicate references, wrong object kind/owner, payload ownership, nested verification evidence, reopen/promotion and reversed record order in `test_catalog3_json_contracts.py`; Source membership/nested verification attacks in `test_catalog3_remaining_adversarial.py`; existing 304 runtime/exchange regressions. | Implemented; local acceptance passed |
| CAS-46 | Exchange must select a fetch or collection with exact required context, rather than sending all unrelated repository acquisition history. No selective exporter existed. | `Graph.export()` accepts permanent fetch UUIDs and a catalog-local collection selector. A work queue follows required parent/FK/typed JSON references, whole result input/output publications and applicable DAG dependencies; shared repository/document/collection parents do not pull all sibling acquisitions. Whole-repository export remains the default unit. | `application/exchange_service.py` and `cli/main.py` expose repeated `--fetch FETCH_UUID`, `--collection COLLECTION_LOCAL_ID`, or both for an explicit collection subset. The existing exchange format, immutable identities, local remapping and durable staging are reused. Required physical bytes deduplicate within the unit. Source-wide inventory, local trust/quarantine, operational validators and receiver Source settings retain their established boundary. | F0/F1/F2 receipt orders, reopen, duplicate receipt and full-unit convergence; 304 original closure; multi-input/result publication closure; 500 unrelated sibling acquisitions and unrelated/selected corruption in `test_catalog3_selective_exchange.py`. Installed wheel/sdist CLI exercises both selectors and later full exchange. | Implemented; local acceptance passed |
| CAS-49 | Complete coverage is transportable only with its exact proof. Broad dependency manifests could mistake unrelated present records for completeness evidence. | Completion markers carry permanent UUIDs and immutable exact fetch UUID manifests. `freeze_complete_proof()` binds coverage at construction to exact marker UUIDs; receipt cannot substitute a later receiver-local marker. Complete coverage identifies exact marker/collection or Git acquisition/result dependencies. `Graph.proof_requirements()` derives required records from owned immutable evidence, collection kind and observation boundary; receiver admission checks envelope equality. A fetch subset does not inherit broader completion. Coverage claims still have exactly five columns. | `adapters/github/persistence.py` seals acquired fetch membership; `adapters/github/collector.py` and `adapters/sqlite/coverage.py` freeze applicable proof dependencies. Selective export transports completeness only with the entire selected proof. Immutable proof conflicts derive catalog-local `exchange_blocked_coverage_claims`/result/selection barriers; latest disputed coverage becomes conflict while evidence remains retained. Invalid/missing proof stays unresolved or excluded, without blocking independent records. | Exact collection/subset proof, omitted output publication, unrelated-owner forgery, empty 304 boundary/original evidence, conflicting marker receipt in both orders, unresolved external DAG heads and full convergence in `test_catalog3_selective_exchange.py`; unrelated present proof/truncated manifest attacks in `test_catalog3_remaining_adversarial.py`; coverage v2/latest unknown/conflict smoke checks in the acceptance helper. | Implemented; local acceptance passed |

## Supported selectors and interpretation boundaries

`parser reparse ACQUISITION_UUID [--profile PROFILE_UUID]` accepts retained Git acquisition identity as
well as the existing GitHub fetch UUID. It creates a new result and generated
facts while preserving acquisition identity, observation times and authoritative
bytes. The default keeps the new interpretation as history. Explicit profile
verification/trust/selection and fact selection remain independent operations;
reparse and receipt do not upgrade ordinary current output.

Git profile settings specify metadata/text decoding and the text-size bound.
The installed Git parser implements supported encoding/error settings for its
exact implementation/output schema; a registered unrelated implementation is
not executable merely because it has a profile UUID. Repository-current selection
and a saved acquisition's selection permit recorded/PR contexts to retain their
explicit interpretation independently of a later ref snapshot.

`git_acquisition_publications` records the acquisition's complete immutable
object-format/OID/raw-payload set and traversal roots. SQLite checks exact member
counts and identities, root inclusion and owner matching. Result publication
requires this acquisition publication and all raw bytes. Exchange closes those
members before admitting the seal; receiving an acquisition row without its
objects cannot turn a missing input into an apparently complete empty result.
Late members and disputed acquisition seals do not modify a published input.

Examples, always against a disposable or explicitly selected state directory:

```sh
repo-catalog --state-dir STATE exchange export --repo REPOSITORY_UUID --fetch FETCH_UUID --output fetch.json
repo-catalog --state-dir STATE exchange export --repo REPOSITORY_UUID --collection COLLECTION_LOCAL_ID --output collection.json
repo-catalog --state-dir STATE exchange export --repo REPOSITORY_UUID --collection COLLECTION_LOCAL_ID --fetch FETCH_UUID --output subset.json
repo-catalog --state-dir STATE exchange import --input fetch.json
repo-catalog --state-dir STATE parser reparse GIT_ACQUISITION_UUID
```

The collection selector addresses a local row; transported record identities
remain unchanged. A selected fetch can legitimately bring additional fetches
when an original 304 response or a whole immutable parsed-result manifest
requires them. Required closure never truncates a sealed input/output manifest.

Complete HTTP coverage freezes `completion_marker_uuidv4s` when the claim is
written. Transport validates those exact markers, their owned collection kinds,
sealed fetch sets and observation boundaries, including a 304's original saved
acquisition. Extra later receiver markers do not alter a claim's proof. Conflicting
immutable proof variants propagate through ordinary FKs, authored JSON references
and acquisition publications into catalog-local coverage/result/selection barriers.
The stored first variant remains history; current coverage reports conflict and
affected parsed results lose usability independently of receipt order. These
barriers are recomputed locally and excluded from the portable unit.

Component completeness is validated against the asserted scope. HTTP marker
collections must have the appropriate kind and CR owner; Git component claims
name their published snapshot/result and exact Git input. PR-code completeness
requires one complete sealed code observation for the named result/CR, stable
API head/base evidence, both commit/file listings, all listing fetches among the
result's sealed inputs, and exact role links into published Git roots and acquired
byte manifests. A marker for an unrelated component cannot prove the claim.

Repository aggregate `pr` and `pr-documents` claims freeze the target
`change_request_ids` breadth in their evidence. A complete PR-list proof identifies
the listed CR observations from its exact saved provider pages; every frozen CR
requires its applicable detail/document component collections. The broader `pr`
scope additionally requires timeline/commit/file collections and one named
complete code interpretation per CR, with its listings and Git roles included.
`pr-documents` carries its document scope rather than broadening from later local
CRs or importing unrelated code proof. Aggregate validation uses the frozen target
set and named component publications; it does not reinterpret the claim from the
receiver's current repository inventory.

Ordinary received PR reads derive collection completion from the exact immutable
markers, rather than copying sender job or listing progress. Receipt initializes
only the local partial listing progress required to admit immutable listing
items. A complete code observation must then satisfy its exact sealed commit/file
listing membership; a complete Git root header can precede its entries because
the result's publication seals the final output set. No imported progress row
claims completion.

PR readers compare actual non-operational response/marker observation boundaries,
preserve all equal-boundary candidates, and require every candidate to qualify.
Later partial or unknown markers, disputed proof records and quarantined bytes
prevent an older complete marker from qualifying the collection. Selected thread
reads qualify the exact nested child collection under its saved root, preserving
equal-boundary roots, pages and children. History presentation uses permanent
observation identity and API page ordinal/position rather than receiver-local row
IDs; interpretation selection still uses the explicit immutable DAG.

`test_production_github_complete_proofs_cover_the_asserted_scope` exercises actual
synthetic Git/GitHub production sync, a subsequent 304 sync, and whole-repository
exchange with both one and 101 thread replies. The receiver admits the complete
unit without staging and retains no fabricated complete listing progress. After
explicit receiver-local parser trust, current code UUID/result/state and portable
`pr show`/paginated `pr thread` items and complete statuses equal the sender.
Independent regressions additionally reject a detail-only HTTP marker offered as
complete code or aggregate PR proof, duplicate/truncated listing manifests, stale
or unknown completion boundaries, and later/equal-boundary incomplete markers.

## JSON inventory and acceptance evidence

The registry distinguishes authored evidence; provider projections; decoded Git
headers; local operational configuration; immutable parser definitions and
verification; input, fact and predecessor manifests; Git root manifests; staging
envelopes; and exchange-local key maps. Each category has an explicit shape and
nullability. Reference-bearing authored structures use the central vocabulary;
provider field names alone do not create application references. Typed exchange
envelopes and sealed manifests retain their existing dedicated admission rules
alongside the registry.

The complete field inventory, reference vocabulary and classification of
non-CHECK cursors, diagnostics, outputs and artifacts are recorded in
[`application-json-contracts.md`](application-json-contracts.md). Adding a new
`*_json` column without its JSON constraint or classification fails the inventory
gate rather than silently omitting that field.

`scripts/validate_remaining_contracts.py` runs without test bootstrap and creates
only disposable synthetic databases. It executes the complete packaged DDL,
queries every view, accesses every named index and compiles INSERT/UPDATE/DELETE
for every trigger target. It reports installed trigger DDL and compiled statements
separately from behavioral trigger branches. It checks fresh application
initialization, FK/integrity, canonical repository/service/Source UUID admission,
natural document identity, exact UTF-8 body SHA-256, signed int64/nullable times,
and coverage's five columns/latest unknown/conflict behavior. Its JSON gate runs
schema discovery, registry/generated-guard equality and authored record audit.
It emits actual version/object/check evidence and a failing exit status if a gate
fails; it does not imply that any external test suite ran.

```sh
uv run --no-sync python scripts/validate_remaining_contracts.py --output artifacts/remaining-contracts-ddl.json
uv run --no-sync pytest tests/packaging -q
```

The packaging suite separately builds a wheel and a wheel from the unpacked
sdist, installs each into an isolated environment, removes checkout Python paths
and parser-bootstrap variables, and operates outside the source checkout. Its
local Git and localhost synthetic GitHub fixtures exercise the installed CLI's
new facts, offline reparse/current isolation, registry/audit, selective and full
exchange, repeat receipt, portable UUID retention and backup/restore.

## Final local acceptance

The final ordinary and installed-package checks ran without the test-only parser
bootstrap. Independent counterexample regressions are part of the ordinary suite.
The built-in parser verification artifact was regenerated beforehand from a
successful full bootstrap run and its unchanged implementation/schema snapshot.

| Executed gate | Result |
|---|---|
| Ordinary unit/integration/end-to-end suite | 1,161 passed in 183.17s; zero failures, errors or skips |
| Isolated installed wheel and sdist-derived wheel | 2 passed in 38.19s; zero failures, errors or skips |
| Fresh initialization and complete composed DDL | Schema 13; 102 tables, 45 views, 470 triggers and 100 named indexes; every view queried and trigger-target DML/index access compiled |
| SQLite/established identity contracts | Empty FK check, integrity `ok`; canonical owner UUIDs, natural documents, exact UTF-8 SHA-256, signed int64/unknown times and five-column coverage/latest candidate checks passed |
| JSON inventory | 50 classified fields; packaged guard/registry equality and authored-record audit passed |
| Parser certificate regeneration | 1,161 bootstrap cases passed in 180.37s; exact definition binds 26 implementation modules, schema 13 composed DDL and all 11 capabilities |

The installed fixture's fetch and collection selection retains nine required
fetches from the sealed PR-code result and excludes 22 unrelated fetches. Repeated
partial receipt followed by the full unit preserves every fetch/Git-fact UUID,
leaves no staged records, and passes FK/integrity. Both installed preservation
paths restore schema 13 with 11 acquired-byte publications, 29 retained raw Git
payload mappings and 153 text facts, followed by full maintenance checks.

Exact commands, JUnit hashes, environment, DDL fingerprint/object names,
independent review evidence and final static/report checks are recorded in
[`2026-10-09-complete-model-contracts.json`](validation/synthetic/2026-10-09-complete-model-contracts.json).
The final ordinary JUnit hash is
`4628ec415383fab8ca77d5a28436b30f436b547eadeaff6c9fe4b136ed7c4b68`;
the installed-package JUnit hash is
`18fa07be29608629b5ca268be513f581e301a211d0ef2385346558eedcaff7d8`.
Submitted HEAD and hosted CI evidence belong in the PR body after publication.

Live authenticated acquisition, physical power-loss tests and non-Linux atomic
restore remain unexecuted. D2 remains intentionally absent, CAS-41 unselected,
and CAS-76/CAS-77 deferred.

The initial hosted pagination timeout exposed quadratic publication and scope
lookup work. Exact manifest set comparison, indexed null-safe scope/DAG lookup,
ordered scope deduplication and single-tree JSON duplicate detection preserve
the contracts. The unchanged 101-thread × 101-reply E2E passed in 10.22s in
focused development testing; final full ordinary acceptance includes that same
60-second deadline. The initial failed hosted receipt is retained in the audit
and machine-readable evidence.
