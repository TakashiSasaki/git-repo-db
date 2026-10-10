# Phase 1 implementation: API-original capability retirement

This implements the owner's [Phase 1 decision](phase1-api-original-retirement.md).
Fresh Catalog3 advances from schema 17 to 18 because the physical diagnostic and
rejected-admission contracts change. Retained catalogs are neither migrated nor
cleaned up. This architecture report does not choose a retention policy or
replacement domain-publication design. The current owner instruction separately
authorizes merging PRs #19 and #20 after their review and acceptance gates pass.

This is a scoped retirement, not a repository-wide zero-original guarantee.
Successful historical publication, accepted partial GraphQL roots, coherent live
restart/304 reuse and historical domain-exchange proof still retain originals.
Their precise boundaries are below. The existing opaque provider JSON projections
also remain pending a field-inventory decision.

## A. Stack and baseline

Fetched starting main: `47fd5b88355b98019c0c04408449081e16ab4505`, tree
`e7a41038e26eb93c89b921a9a9d0bf1d2c54a310`. It contains merged PRs #14–#18.
Fresh metadata confirmed PRs #19 and #20 open and mergeable in the intended
dependency order, with no unrelated changes included. The stale clean checkout
at `7a35962` was not used as the implementation base.

1. [Decision PR #19](https://github.com/TakashiSasaki/git-repo-db/pull/19), branch
   `docs/phase1-api-original-retirement-20261010`, based on fetched main. Head:
   `65e80cf5eac5bc7aa99415c9a09517fdc6017d92`; tree:
   `ea88c2178eb6c75437926219931a6801f3fa2406`; opened ready for review.
2. Integrated implementation branch
   `impl/phase1-api-original-retirement-20261010`, based on the decision commit.
   Its actual submitted PR URL, base/head/tree SHAs, draft status and final hosted
   CI receipts are recorded in the implementation PR and the owner handoff.

The decision commit precedes implementation. Its
[passing documentation CI](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38018631631)
does not certify this runtime change. Final acceptance must identify the feature
HEAD and tested tree; a PR merge checkout may have a different commit SHA with
the same tree. This report records the implementation scope and does not itself
grant merge authority; the current owner instruction authorizes the two scoped
merges after their gates pass.

## B. R1–R7 disposition

| Target | Implemented disposition and evidence | Remaining shared boundary |
| --- | --- | --- |
| R1: saved API reparse | The core HTTP dispatch was already absent on main and remains verified absent. Removed `reparse-message`, `--context`, archive-to-domain projection, parser imports and service branch. Unsupported actions fail before reading files/catalogs or acquiring a writer lock. Existing HTTP fetch UUIDs cannot invoke `ParsingService.reparse`. | Genuine Git reparse retains Git acquisition identity and bytes. Bounded `inspect-message` displays capture metadata/body availability without a domain parser. |
| R2: future-field extraction | Removed the only saved-message projection/extraction surface and its success tests. No alternate extraction service, store, flag or JSON projection was introduced. | Existing provider-shaped fields are retained by historical and current metadata contracts; their inventory is undecided. Their existence is not a speculative extraction API. |
| R3: offline API ingestion replay | Core API ingestion replay was already absent and remains verified. Removed `source='replay'` from current-resource admission; only actual `live` and domain `import` remain. Imports never create a receiver-local live check. | Accepted original reads for live restart and conditional validation remain C; they do not expose offline API-to-domain publication. |
| R4: original archive/CAS management | Removed original-only exchange registration/encoding/admission routes and API rejected-byte bookkeeping. The logical unresolved-payload columns/FK/index are gone. There is no supported standalone original archive command. | `ApiFacts.payload`, `intern_payload`, `payloads` and `stored_bytes` still register bytes through successful historical publication/proof and real Git content. Byte hash/deduplication is shared B/C, not fully retired. |
| R5: maintenance for later original reuse | API-only explicit repair is rejected without modifying the catalog. A representation label cannot authorize repair: replacement bytes must verify every mapped Git object's format, typed OID, type and size. Diagnostics contain physical hashes/lengths/time only. | Full verification, quarantine, copied-backup verification, restore and CAS-41 still protect every physical byte, including API-only proof bytes and digests shared with Git. This shared integrity boundary remains; it is not claimed removed. |
| R6: rejected-original retention | Deleted `ApiFacts.rejected_fetch/stage_rejected` and `failed_graphql_page`, failed fetch/payload/diagnostic inserts and saved rejected-response promotion. SQL and Python raw admission staging are Git-only. Fully rejected REST/GraphQL/inventory/parser/CAS responses leave no raw, hex, Base64 or substitute provider object. Safe retry URLs/cursors, reason and actual partial-observation clocks remain; retries fetch remotely. API-only corrupt incoming exchange bodies are discarded before staging and during late promotion. | Successful committed prefixes and accepted partial GraphQL roots retain their exact historical publication/restart inputs, including response envelopes containing errors. That portion is C pending normalized restart/publication proof; it is not described as removed. Valid domain exchange missing-dependency staging also remains C. |
| R7: original distribution | Original-only units, disconnected original fetch selectors, direct encoders/admission and pending promotion cannot distribute or admit archive records. `requires` hints, empty publications and malformed typed-reference carriers cannot authorize original retention. Full/selective export omits disconnected originals. | Wire records `fetch_occurrences/payloads/stored_bytes` remain only in actual retained domain/Git/proof closure. Accepted historical collection/304 proofs still require their originals. Their complete removal requires a new domain proof contract, so R7 has a remaining shared portion. |

Absence tests exercise public CLI/help, direct service/admission calls, production
exchange encoding/intake/promotion and direct SQL. HTTP synthetic fixtures remain
tests, not a production replay entry point. No alias, compatibility shell or
replacement archive was added.

## C. Reproducible inventory and classification

Run from the checkout, against fresh in-memory databases only:

```sh
uv run --no-sync python scripts/audit_api_original_retirement.py --output artifacts/phase1-inventory.json --summary docs/phase1-api-original-retirement-inventory.json
uv run --no-sync python scripts/validate_remaining_contracts.py --output artifacts/phase1-contracts.json
```

The first command reads exact baseline resources with `git show`, composes the
current production resources, executes both DDLs, records `sqlite_schema`, full
`table_xinfo`, composite FK clauses/components, indexes/`index_xinfo`, generated
columns, views, triggers and JSON registries, then compiles views and triggered
INSERT/UPDATE/DELETE statements. It also inventories repository-wide Python
imports, function ASTs and relevant call sites. Static references support the
investigation; they do not prove dynamic reachability or legitimate retention.
The second command adds behavioral identity/text/time/JSON/DDL probes and full
checks. Installation, compilation and exercised behavior are reported separately.

The compact [executed inventory](phase1-api-original-retirement-inventory.json)
records exact fingerprints and deltas. Product tables exclude FTS virtual/shadow
tables and SQLite metadata/internal tables; neither fresh composed catalog has
materialized FTS/internal tables. An ordinary deployed search index is separate
from this production catalog DDL. An FK clause is one constraint, while components
are its individual columns. Explicit indexes have SQL; implicit indexes have null
SQL. Counts overlap and must not be summed.

| Executed product object | Before (17) | After (18) | Explanation |
| --- | ---: | ---: | --- |
| Tables | 103 | 103 | Every remaining table has a retained consumer; no artificial DROP target. |
| Columns | 667 | 665 | Removed unresolved logical representation/digest columns. |
| FK clauses / components | 227 / 360 | 226 / 358 | Removed the two-column unresolved logical-payload FK. |
| Views | 48 | 48 | Shared eligibility/publication/coverage readers remain. |
| Triggers | 497 | 498 | Four generated JSON triggers narrow; one Git-object identity guard is added; other integrity guards stay. |
| Explicit / implicit indexes | 107 / 144 | 106 / 144 | Removed `unresolved_payloads_fk_1`. |
| Classified application JSON fields | 57 | 57 | Diagnostic field becomes required physical evidence; no new JSON store. |

| Touched object/closure | Class and action | Concrete retained consumer or deletion reason |
| --- | --- | --- |
| CLI `reparse-message`, `--context`; `ParserService._message` projection; `test_message_reparse.py` | A: delete | Their only production responsibility was saved API interpretation. Replaced success tests with bounded viewer and absence/no-side-effect tests. |
| Current-resource `replay` admission branch | A: delete | Offline interpretation cannot earn admission or local confirmation. Existing live/import and field-ordering regressions remain. |
| `stage_rejected`, rejected-fetch cache, `failed_graphql_page`, raw failure writes | A: delete | No accepted domain publication owns these rejected bytes. Retry context does not need the body. |
| `unresolved_payloads.payload_representation/payload_sha256`, composite FK, `unresolved_payloads_fk_1` | A: delete | Retired rejected logical inputs were their consumer. |
| Remaining five-column `unresolved_payloads`; its immutability/retain/no-replace guards and physical FK | B: narrow/retain | `diagnose_corruption/verify_all`, active physical quarantine and CAS-41 read them. Digest, actual/declared lengths, diagnosis clock and reason identify physical corruption without retaining incoming bytes. |
| `payload_admission_staging` and `cas_integrity.sql` | B: narrow | Only rejected raw Git acquisition remains. SQL CHECKs validate descriptor shape and a fail-closed Git-object identity trigger verifies the raw object hash and physical SHA-256; the writer also validates before INSERT. API and legacy-normalized originals are rejected. |
| `repair_payload` and maintenance CLI | B: narrow | Genuine retained Git objects, including SHA-1/SHA-256 and digests shared with API. All mapped Git identities are checked before atomic repair/quarantine mutation. |
| `diagnose_admission_failure` | B: preserve shared diagnosis | Only a canonical `PAYLOAD_CORRUPTION` digest of actual incumbent content is accepted after rollback. It accepts no incoming response/body/context. Shared Git eligibility cannot silently continue after corruption detection. |
| `database_identity.schema_version`, `SCHEMA_VERSION` | B: advance to 18 | Actual structural contracts changed; no compatibility/migration branch. |
| `json_fetch_occurrences_request_*`, `json_completion_markers_evidence_*`, JSON generator | B: narrow | Removed dead `operational_only` typed flags and guards. Genuine live/proof reference vocabulary and owner checks remain. `diagnostic_json` is nonnullable. Generated SQL equals its generator. |
| `Graph.record/export/receive/_admit/promote`, shared exchange staging/receipts | B/C: narrow | Typed domain/Git/proof roots authorize only their derived original closure. Advisory manifests cannot authorize disconnected originals. Domain missing dependencies/conflicts and late valid proof bytes remain supported. |
| `completion_markers`, progress/cursors, coverage queries | B/C: narrow | Rejected actual resource responses use existing reason-only partial markers with true clocks, without fabricated fetches/members/terminal claims. Error-only operational failures have no semantic observation. Completion uses accepted receipts, preserving later partial candidates and equal-clock conflicts. |
| `ApiFacts.page/source_input/result/ownership/publish`, typed immutable facts/results, successful originals | C: retain | Exact chains in the next section; deletion would break atomic publication, live recovery or honest proof. |

No exclusive wire type can simply be deleted: all three original-bearing record
types also encode retained Git/historical proof dependencies. Their allowed
encoders/intake/promotion are narrowed rather than replaced by a new format.
The obsolete `payload_repairs` exchange-exclusion name was removed; no such
production table existed and it is not counted as a dropped table. The 18
historical parser/publication/selection tables are still consumer-owned C, not
dead schema retained for compatibility.

## D. Superseded rules and preserved objectives

The [decision's checked rule-by-rule table](phase1-api-original-retirement.md#scoped-supersession-of-older-contracts)
reconciles D3/D23/D25/D28/D29/D31/D36/D37 and
CAS-3/4/9/16/42/44/46/49 against their actual documented definitions. Mechanism
retirement does not erase the independent domain invariant:

- D3/D25/D28/D29: API re-execution and projection retire; Git acquisition/result
  separation, immutable result UUIDs, typed owned inputs and sealed fact output
  publication remain. Historical domain batch/publication identity is undecided.
- D23/D31/D36/D37: archive-only byte management and rejected Source input retention
  retire; independent observation/identity, owner XOR, composite domain ownership
  and accepted live inventory publication remain. Inventory ownership/fields and
  historical lifecycle replacement remain undecided.
- CAS-3/4/9: original-only references/distribution/validators retire; typed JSON,
  complete required domain bytes and schema-aware ownership validation remain.
  Historical normalized exchange proof remains undecided.
- CAS-16: rejected API body staging retires; actual Git rejected content and
  incumbent physical diagnosis remain. No alternate API retry archive replaces it.
- CAS-42/44/46/49: standalone replay distribution retires; exact 304 origin,
  capture/owner context, partial domain dependency closure and truthful completeness
  remain. Normalized completeness/cache/restart decisions are still required.

Earlier statements that an external nonpublishing `reparse-message` projection
was outside retirement, or that failed API originals must be saved for retry,
are superseded. The earlier boundary report also understated exceptional wire
retention: bare CAS bytes and malformed staged carriers could survive independently
of admitted domain facts. The new exchange regressions expose and retire those
routes. Historical reports are preserved as historical evidence, not rewritten.

## E. Remaining original-dependency map

Paths below are actual retained callers, not hypothetical future usefulness.
Source references name functions so this map survives line movement.
The referenced implementations are
[CollectionService](../src/repo_catalog/application/collection_service.py),
[GitHubCollector](../src/repo_catalog/adapters/github/collector.py),
[ApiFacts](../src/repo_catalog/adapters/github/persistence.py),
[Graph](../src/repo_catalog/adapters/sqlite/exchange.py),
[historical PR readers](../src/repo_catalog/application/pr_queries.py),
[maintenance](../src/repo_catalog/application/maintenance_service.py),
[physical integrity](../src/repo_catalog/adapters/sqlite/cas_integrity.py) and
[recording adapters](../src/repo_catalog/adapters/recording.py).

| Public caller and implementation chain | Reads/writes and consumer | Why deletion changes retained behavior | Minimum next-phase decision |
| --- | --- | --- | --- |
| `sync pr/all`, `jobs resume` → `CollectionService._sync` → `GitHubCollector.collection/detail/threads/code_check` → `ApiFacts.page/result/ownership/publish` | Writes `fetch_occurrences`, `payloads(decoded_api)`, `stored_bytes`; owned `parsed_results/parsed_result_inputs/parsed_result_publications`; direct immutable PR/document/event/thread/code facts. Eligibility/current historical readers and portable manifests read those identities. | Removing input records violates owned/sealed output membership or makes incomplete historical interpretations eligible. Current Issue/review rows themselves remain independent. | Domain publication/batch identity, historical observation lifecycle/resolution, exact field inventory. |
| `source discover`, planned discovery/resume → `CollectionService._discover` → `GitHubCollector.inventory/inventory_input/inventory_result` → `_publish_inventory` | Accepted user/org/repository pages write Source-owned `source_input_observations`, logical/physical bytes, inventory results/publications, `repository_inventory_observations` and inventory coverage. Accepted prefix inputs can remain when a later page fails. | Accepted input ownership and immutable inventory publication currently require the originals; merely removing writes breaks inventory eligibility. Malformed/out-of-scope/unsupported-owner inputs are rejected before this store. | Normalized inventory evidence, Source publication/ownership, inventory completeness and retained provider fields. |
| Live `sync pr`, detail retry → `GitHubCollector.detail` 304 branch | `validators` binds scope/etag to composite payload identity. Reuse reads saved bytes, compares exact provider object with the selected PR observation and seals a `completion_marker` referencing that original fetch/result/observation. | Dropping bytes or anchor checks can falsely attach cached A to newer B, or invent a new remote observation. Operational validators are not exchanged. | Conditional cache/revalidation policy and a domain proof that preserves exact origin. |
| Live `jobs resume` → `GitHubCollector.threads/_thread_children` | Reads accepted root fetch bytes/GraphQL structure and original response clock to reconstruct actual child cursors; committed roots/prefixes and child page receipts remain. Completed roots also supply merge role expectations. | Removing accepted root inputs loses child continuation and can report premature completeness or change the original time. Partially accepted responses with errors remain shared here. | Normalized thread continuation/target evidence and atomic publication/restart contract. |
| `sync pr`, Git code collection → `saved_thread_code_input`, `completed_pr`, existing code input assembly | Reads last accepted thread-root JSON for observed merge/test-merge OIDs; combines PR/listing/Git acquisition inputs into a separately owned code interpretation and target coverage. | Removing it forgets observed roles or makes a missing/unobserved target look complete. Raw Git objects remain domain content. | Durable normalized review/code targets and restart/publication ownership. |
| `exchange export/import`, `--fetch/--collection`, delayed promotion → `Graph.aggregate_proof/proof_requirements/code_proof` | Historical PR-list proof rereads required original objects to compare exact listed PRs with `change_request_observations.payload`; result/owner/publication/member/304/root identities join required originals. Allowed original records have derived typed closure, not envelope hints. | Dropping this read weakens missing-member, scoped-list, partial-collection or 304 proof. Removing the whole function would retire surviving domain exchange. | Historical normalized member/terminal proof and publication closure; preserve existing trust/ownership objectives. |
| Existing historical/current queries and exchange → provider-shaped projections | `change_request_observations.payload`, document metadata, event payload, code commit/file payload, review-thread payload, inventory metadata and current resource metadata retain provider-shaped/unknown fields. A synthetic transport marker can survive inside an accepted projected field. | Deleting opaque fields chooses an unapproved field inventory and changes existing query/export values. They must not be advertised as wholly normalized or original-free. | Explicit retained field inventory, exact null/missing/empty meaning and lifecycle for each field. |
| `db check --full`, `db verify-payloads`, `backup/restore` → `verify_all/diagnose_corruption` and copied database scan | Reads all `stored_bytes`, writes physical-only `unresolved_payloads/payload_quarantine`, records/checks CAS-41 active quarantine count. Explicit repair additionally requires real `git_object_payloads` and validates Git identity. | Selectively ignoring API-labelled digests would allow broken shared Git bytes or corrupt historical proof to pass verification/backup. API-only corruption remains quarantined; original repair is retired. | Separation/lifecycle of historical proof content and recovery policy after API-only quarantine; no decision made here. |
| Optional `github.record_messages`, `parser inspect-message` → recording adapters | Supplementary filesystem archive, bounded `LocalArchiveReader`, sanitized bounded nonfatal diagnostics. Core current acquisition/queries/exchange do not require it; inspection invokes no domain parser. | This explicitly allowed diagnostic responsibility differs from replay. It may record otherwise rejected transport data when the user enables it. No core rejection test enables recording. | Optional archive retention/deletion policy; outside this retirement's core store claim. |

Manual Git discovery additionally stores `legacy_normalized` configuration proof;
it is user-authored source configuration, not an API response. Git objects and
exact UTF-8 `text_bodies` are required domain content. All historical profile,
verification/invalidation/trust and profile/fact-selection readers stay until
their publication/resolution replacement is decided; current resources do not
acquire those dependencies.

## F. Verification and independent findings

Environment: Python 3.12.14, SQLite 3.53.1, uv 0.12.19 on the managed Linux
workspace, with offline synthetic fixtures and fresh disposable catalogs. The
initial baseline invocation could not collect because pytest dependencies were
not installed (exit 2); `uv sync --locked --group dev` resolved that setup issue.
The subsequent baseline selection passed 60 tests without bootstrap in 13.33s.

Independent workstreams changed disjoint entry-point, CAS/schema, exchange and
test/document files; the lead integrated shared DDL/generator/collector changes.
They tested actual diffs, not solely this report. Concrete independent findings:

1. **Medium — collection boundary:** A malformed observed GraphQL child at 200 after accepted root 100 originally
   lost its newer partial boundary when the body was discarded. Existing
   reason-only partial markers now retain 200; raw-invalid JSON without a resource
   keeps 100 rather than fabricating a resource observation.
2. **Medium — observation clock:** An older terminal retry at 150 after partial 200 originally failed the current
   page completeness trigger, and copying 200 into completion would fabricate its
   clock. Completion uses accepted page receipts; partial 200 remains the latest
   candidate. Equal-time retry 200 leaves a conflict, while a later 300 can complete.
3. **Medium — Source inventory admission:** A valid-looking `/users/owner` response for an unsupported nonauthenticated
   User was saved before `SCOPE_UNSUPPORTED`. Its intake now follows accepted
   Organization scope validation; the earlier accepted `/user` input is C.
4. **High — Exchange root validation (`Graph.original_root`, `required_original_keys`, `receive`, `_promote`):** Standalone byte/payload exchange originally admitted originals with no domain
   facts. Malformed direct-SQL staged reference carriers and advisory `requires`
   could also authorize originals. Typed closure validation and attack regressions
   cover export/intake/direct admission/promote, not just the normal encoder.
5. **Medium — CAS diagnosis (`stage_verified_payload`, `diagnose_admission_failure`):** Removing raw failure staging also removed its incumbent-corruption diagnosis.
   A physical-only post-rollback helper restores shared diagnosis without saving
   replacement bytes. Canonical wrong-OID Git mappings cannot authorize API repair.
6. **Medium — CAS staging (`stage_verified_payload`, `payload_admission_staging`):** The Python staging helper rejected a forged Git descriptor, but direct SQL could
   still insert an API body with a syntactically valid false OID. A deterministic
   SQLite UDF and fail-closed INSERT trigger now verify Git format/type/size/OID
   and the physical SHA-256 in the database itself. Direct-SQL positive and forged
   SHA-1/SHA-256 probes cover both paths; an unregistered SQLite writer fails closed.
7. **High — Exchange preflight (`original_root`, `_admit`, `receive`, `_promote`):** Exchange preflight treated malformed complete markers, inconsistent publication
   manifests, and SQL-invalid domain facts as original roots. Minimal receive and
   delayed-promotion reproducers showed rejected API bytes persisted. The corrected
   preflight evaluates ordinary admission and proof closure over incoming dependencies
   before authorizing raw bytes; invalid evidence is discarded while justified
   missing-dependency staging remains. Independent retest passed 53 Exchange cases.
8. **Medium — Exchange scalability (`local_original_context`, `original_intake_context`, `_promote`):** A selected-repository export scanned unrelated Git mappings and every exchange
   receipt; promotion repeated an unindexed staging scan per repository. Scoped
   root discovery, receipt lookups, and one grouped pending snapshot remove those
   repeated scans. On the same harness, an empty export with 1,000 / 5,000 unrelated
   Git objects fell from 0.635s / 3.119s, 10,224 / 50,224 statements, and 9.1 / 44.9
   MiB peak to 0.018s / 0.010s, 224 statements, and 0.6 / 0.2 MiB. A 50,000 unrelated
   receipt context fell from 0.324s and 24.2 MiB to 0.0006s and 0.016 MiB.
9. **Medium — Source inventory input (`GitHubCollector.inventory`):** Empty Source login and nonnumeric repository IDs passed structural validation
   and were retained before rejection. Collector now validates nonempty login and
   positive decimal provider IDs before input admission. The six targeted inventory
   cases passed, including the unsupported owner and malformed-ID reproducers.

Development runs are overlapping evidence, never summed as acceptance totals.
The earlier collector selections had 90 passes/4 failures, then 92/2 while old
raw assertions and concurrent parser-definition changes were being corrected.
The GitHub runtime selection had 68 passes/1 failure; its unchanged 304 race
test passed an exact rerun and disposable reproduction. Initial exchange checks
had 87 passes/3 failures while fixtures/gate integration were in progress.
These failing reports do not certify the final endpoint. Focused independent
retirement/CAS/entry/exchange receipts and exact final results are included in the
implementation PR's verification ledger.

The frozen-source independent retirement selection passed 32 cases in 15.32s
with zero failures/errors/skips; its bootstrap flag is explicitly development
evidence. The initial new exchange gate selection passed 20 cases without
bootstrap in 8.30s. The existing exchange rerun passed 75 cases in 59.30s;
two packaging setup errors in that invocation meant no package runtime executed
because the locked wheelhouse had not yet been prepared. That setup is required
before final isolated package acceptance. Additional exceptional-owner/Git and
aggregate-clock findings are included in the final regression/receipt ledger.

The final expanded original-exchange gate selection passed 31 cases without
bootstrap in 13.19s. This includes valid late Git delivery, malformed public and
pending owner/reference carriers, forged Git OIDs and forged local repair
exemptions, plus rejected API envelopes already marked invalid/conflicting.
The integrated exchange selection had 104 passes and two fixture setup failures;
all 75 existing exchange cases passed. Those two fixtures failed the preserved
Git raw-length guard before reaching the intended wrong-OID check. Matching the
synthetic corrupt body's length fixed the fixture only; the 31-case rerun passed
without further production changes. No surviving guard was removed.

A later read-only review found that a missing Git object descriptor could let a
forged portable OID authorize an original before the descriptor arrived. The
instrumented prior-method reproduction retained one body plus one Base64 receipt
through both public intake and pending promotion; the corrected method retained
neither. Known portable format/OID and candidate bytes are now verified even
without the descriptor; actual matching Git content keeps its ordinary missing
parent dependency. The 33 retirement cases plus ten integrity cases passed
without bootstrap in 24.23s. The first full development run had already selected
1,702 cases when its captured definition became obsolete; it was interrupted
(exit 130), produced no complete JUnit receipt, and is not accepted evidence or
a passed-case total. A fresh snapshot and full execution are required afterward.

The coordinated final exchange focus passed 45 cases in 19.10s without bootstrap:
35 retirement regressions and ten surviving integrity cases. It also proves
SHA-1/SHA-256 genuine Git content can keep rejected-byte staging when its object
metadata arrives later; a real format/OID/body match does not fabricate that
missing metadata or prematurely admit the mapping. The final exchange source
fingerprint is included in the compact executed inventory.

The final expanded independent selection passed 35 cases in 19.44s, with zero
failures/errors/skips and all 27 scoped source/test fingerprints unchanged. It
includes actual full-sync/resume clocks 150/200/300, not only isolated child calls.
The older 150 result is ignored by coverage admission; it cannot emit a counterfeit
complete candidate at 200. Its actual completion receipts remain 150. An earlier
development assertion incorrectly expected stale coverage insertion and failed
one of three new cases; the assertion was corrected to preserve the existing
stale-admission contract. No production ordering rule was weakened.

Before the database-level Git identity guard was added, a fresh definition
snapshot and the complete non-packaging bootstrap suite passed 1,714 cases in
168.49s with zero failures, errors or skips. That run is historical development
evidence and does not cover the later SQL guard. Its nine parser certificates were
regenerated from the successful receipt. A fresh snapshot/bootstrap and clean-tree
ordinary and installed-package acceptance are required for the final feature tree.

After the database-level guard and final regression additions, a new pre-run
definition snapshot and complete non-packaging bootstrap execution passed 1,715
cases in 166.27s with zero failures, errors or skips. The nine retained parser
capability certificates were regenerated from that exact successful receipt.
This is certificate-generation evidence; ordinary and installed-package final
acceptance runs separately without the bootstrap environment variable.

Final acceptance workflow:

```sh
uv run --no-sync python scripts/verify_builtin_parser.py --capture artifacts/parser-definition.json
REPO_CATALOG_TEST_BOOTSTRAP=1 uv run --no-sync pytest tests --ignore=tests/packaging -m 'not live and not benchmark' -n 4 --junitxml=artifacts/bootstrap.xml
uv run --no-sync python scripts/verify_builtin_parser.py --snapshot artifacts/parser-definition.json --junit artifacts/bootstrap.xml
python scripts/ci_profile.py run --name planning -- python scripts/ci_plan.py --full
python scripts/ci_profile.py run --name report-validation -- python scripts/ci_execute.py reports
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python scripts/ci_execute.py collect
uv run --no-sync python scripts/ci_execute.py run --lane tests
uv run --no-sync python scripts/ci_execute.py run --lane packaging
python scripts/ci_execute.py gate
```

The bootstrap report is development evidence only: a pre-run exact definition
snapshot and zero failed cases are required to regenerate the nine remaining
historical capability certificates. Final ordinary and isolated installed
wheel/sdist checks run without bootstrap; packaged tests run outside the checkout
with locked offline wheels. Ruff lint/format, fresh DDL/JSON equality/FK/integrity,
FTS/doctor and report validation also run. CI reconciles selected/executed node
IDs, skips/failures/exclusions and unexecuted lanes, and records clean-tree and
feature/tested-tree identity. Final counts and hosted artifacts belong to the
submitted PR's actual receipt, not an old count floor or this development ledger.
No live provider, old-schema migration, retained-data cleanup or deployment is
exercised.

## G. Prioritized remaining decisions

1. Define domain batch/publication and ownership identity for historical PR,
   thread, code and Source inventory outputs without acquisition-byte inputs.
2. Define normalized member/terminal/304 and cross-catalog completeness proof,
   preserving missing dependencies, equal-time conflicts and exact scope.
3. Define accepted thread continuation and merge/review-target evidence, and
   conditional HTTP reuse/recovery semantics, without saved original reads.
4. Inventory retained provider fields and choose historical/current resource
   lifecycle and selection policy before deleting opaque JSON or histories.
5. Decide physical-content separation, API-only quarantine recovery, retention/GC
   and optional archive lifecycle. No duration or automatic deletion is selected.
