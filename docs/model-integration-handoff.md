# Integrated data model handoff

## Current schema 16 handoff

Start from PR #14 HEAD `3f76d4873d14604b918198ac06c1660d0fa9e1b9` on
`fix/current-state-schema-closure`; use `fix/current-state-conflict-boundaries`
for this stacked follow-up. [Boundary corrections](current-state-boundaries.md)
record R1/R2, conservative cross-repository conflict refusal, wire exclusions,
pagination measurements and schema 16 FK cleanup. [The complete inventory](current-state-boundaries-inventory.json) and [retention measurement](validation/synthetic/2026-10-09-current-state-boundaries-retention.json) are reproducible disposable receipts. Fresh schema 16 rejects earlier development catalogs; no migration, merge, release or body GC is included. Exact final local and hosted acceptance are recorded in the follow-up receipt and submitted PR body.

## Historical schema 15 handoff

Start from PR #13 HEAD `db3a5ecfbf95b4c1318198aa308ca6dc749876a1` on
`refactor/latest-state-transport`. The follow-up branch is
`fix/current-state-schema-closure`, stacked on that verified checkpoint.
[Current schema closure](current-state-schema-closure.md) describes per-field
knowledge/evidence, typed staging, original transfer provenance, receiver-local
checks and nonfatal optional recording. [Column liveness](current-state-schema-liveness.md)
and [before/after inventory](current-state-schema-inventory.md) explain retained
columns and actual removals. Schema 15 initializes fresh; earlier unreleased
catalogs/backups are rejected. Final local acceptance is recorded in
[the follow-up receipt](validation/synthetic/2026-10-09-current-state-schema-closure.md);
exact submitted HEAD and hosted acceptance are recorded in the PR body.

## Historical schema 14 handoff

Current work starts from PR #12 `a3a4cb7482d42709f79d137b802f1789e3aa45cb`
on `feat/complete-model-contracts`; the implementation branch is
`refactor/latest-state-transport`. Shared Issue/review current state, optional
transport recording and required CAS-41 counts are described in
[latest-state-transport-implementation.md](latest-state-transport-implementation.md).
The complete table/key/owner/lifecycle inventory is in
[latest-state-table-inventory.md](latest-state-table-inventory.md).
Fresh schema 14 initialization replaces the unreleased development format;
there is no migration or v2 intake. Final local acceptance passed: 1,311 ordinary tests and 2 isolated wheel/sdist cases, without bootstrap and with zero failures/errors/skips. Exact receipts and scope limits are in [the schema 14 implementation report](latest-state-transport-implementation.md). Submitted HEAD and hosted CI are recorded in the new stacked PR body after publication.

## Historical schema 13 handoff

Current work starts from PR #11 `d76ebc776c9e72f565dc3007c878e2002c5f4e8e`, branch `refactor/integrated-data-model`. The implementation branch is `feat/complete-model-contracts`, stacked directly on PR #11. Earlier branches, commits and PR histories remain preserved. Schema 13 completes the remaining Git fact, authored JSON reference and selective exchange paths in the unreleased fresh format; there is no migration of prior development catalogs.

The previous PR #10-to-#11 integration and its schema 12 acceptance remain historical evidence in [`2026-10-09-integrated-model.json`](validation/synthetic/2026-10-09-integrated-model.json). Current implementation mapping is in [`model-contract-completion.md`](model-contract-completion.md), with the complete JSON field/reference inventory in [`application-json-contracts.md`](application-json-contracts.md). Final submitted HEAD and hosted acceptance belong in the new stacked PR body.

## Fresh-catalog workflows

Initialize with `repo-catalog --state-dir PATH init --profile catalog-text-v1 --cache-max-bytes 33554432 --min-free-bytes 0`. Add a Source, discover it, then run `sync git`, `sync pr` or `sync all`. Use `sources configure --source SOURCE_ID --input SETTINGS_JSON` to configure an imported Source locally without changing its registration UUID.

Job plans freeze registration identities, target repositories and non-secret acquisition settings; resume uses those saved values and resolves only credential references from the environment.

Repository list/show responses expose `inventory_observations` as separate Source-owned interpretations with result/observation UUIDs and decoded metadata. Shared repository metadata is local registration data and is not populated from later parsers.

`parser reparse ACQUISITION_UUID [--profile PROFILE_UUID] [--select]` parses retained bytes without creating another remote observation. The positional identity is a Git acquisition ID or GitHub fetch UUID; `--profile` selects a supported Git decoding profile for execution. The default preserves the new result as history. Git bytes, object OIDs, acquisition times and sealed object/root membership remain unchanged. Historical text is retained and interpreted at publication; hydration cannot mutate sealed facts. Git queries and indexing derive from explicitly selected, eligible result-owned facts.

`parser register`, `parser verify`, `parser select-profile` and `parser select-fact` accept JSON keyword arguments for the corresponding `ParserModel` methods using `--input FILE`. `parser trust VERIFICATION_UUID [--revoke]` explicitly changes local trust; `parser invalidate VERIFICATION_UUID --reason TEXT` adds immutable invalidation. `parser status` exposes definitions, evidence, scopes, selections and staging. Profile verification requires evidence for every declared capability and the exact immutable definition. Reparse, receipt and new observations never silently change an established profile selection. Git fact selection can address repository-current output or a saved acquisition's scope using `git_acquisition_id`.

`identity relation --input FILE`, `identity cancellation --input FILE` and `identity status` admit and inspect explicit equivalence evidence. A relation never merges repository rows, facts or coverage; missing cancellation targets remain staged.

`exchange export --repo REPOSITORY_UUID --output FILE` exports the entire repository. Repeated `--fetch FETCH_UUID` selects permanent fetch identities; `--collection COLLECTION_LOCAL_ID` selects one local collection, optionally bounded by explicit `--fetch` members. The collection selector is local syntax; transported identities remain unchanged. Required owner/context, exact bytes, whole parsed-result publications, authored JSON references and applicable DAG dependencies close the selection without pulling unrelated sibling acquisition history. A 304 can require its exact original fetch; a sealed result can require additional inputs. Completeness travels only with its exact scope proof. Missing legitimate dependencies remain staged, and immutable proof conflicts suppress dependent current coverage/results without selecting a receipt-order winner.

`exchange import --input FILE` and `exchange staging` use the existing one-repository exchange unit. Source-wide inventory, local quarantine/trust, derived conflict barriers and validator caches are outside the unit. Received Source settings remain historical provenance and never configure or overwrite receiver-local operational settings. Importing history never makes remote verification locally trusted automatically.

```sh
repo-catalog --state-dir PATH parser reparse GIT_ACQUISITION_UUID
repo-catalog --state-dir PATH parser reparse GIT_ACQUISITION_UUID --profile PROFILE_UUID
repo-catalog --state-dir PATH exchange export --repo REPOSITORY_UUID --fetch FETCH_UUID --output fetch.json
repo-catalog --state-dir PATH exchange export --repo REPOSITORY_UUID --collection COLLECTION_LOCAL_ID --output collection.json
repo-catalog --state-dir PATH exchange export --repo REPOSITORY_UUID --collection COLLECTION_LOCAL_ID --fetch FETCH_UUID --output subset.json
repo-catalog --state-dir RECEIVER_PATH exchange import --input fetch.json
```

`db verify-payloads`, `db repair-payload --sha256 HEX --input FILE`, `db check --full`, `db backup --output FILE` and `db restore --input FILE` expose integrity maintenance. `db check` checks the exhaustive JSON classification gate; `--full` also audits authored references and retained Git object identities. Quarantine suppresses the affected Git interpretation and repair explicitly restores valid bytes without rewriting facts. Restore requires a new explicit state directory; backup requires unused database and companion manifest destinations. Failed restore stages are retained.

## Removed compatibility-only work

The unreleased product no longer ships `adapters/import_v2`, the v2 conversion contract/migrations/workspace, `application/import_service.py`, import-only finalization, `scripts/import_fixture.py`, `scripts/offline_convert.py`, `import-v2` or `db finalize`. Normal text-digest/FK/SQLite validation moved to `application/catalog_validation.py`.

The following suites existed solely for conversion, salvage or old-workspace admission and were retired: `test_import_archive.py`, `test_conversion_git_domain.py`, `test_conversion_pr_domain.py`, `test_runtime_import.py`, `test_catalog3_import_workspace.py`, `test_catalog3_finalization.py`, and `test_catalog3_time_admission.py`. Their obsolete legacy fixture builders were removed. Timestamp unit/range tests, raw object and document integrity tests, current acquisition/resume behavior, Source identity, coverage v2 and ordinary maintenance remain and are adapted to the new model.

Two imported-first-sync scenarios (five parameterized cases) in the GitHub runtime suite were removed with the importer. Ordinary fresh and resumed GitHub tests remain. The two packaging variants now validate the fresh result model and backup/restore instead of an installed salvage importer. This is intentional retirement of unsupported legacy behavior, not a test-count preservation exercise.

## Current-contract test replacements

The former lazy historical text expectation in `tests/e2e/test_text_policy.py`
is replaced by immediate retained historical text and search after publication.
The test preserves exact size, NUL and non-UTF-8 boundaries and verifies hydration
does not mutate published history. Independent profile tests cover alternate
metadata/text decoding, unselected interpretations and index/search isolation.

The removed importer manifest implementation is replaced by the shared
`GitParsing` path. `test_manifest_generation_publishes_bounded_rows_in_new_result`
in `tests/integration/test_git_objects.py` builds a manifest under a new unsealed
result, checks bounded row commits and publication, and verifies the original
result/current snapshot is unchanged. The interrupted bounded staging test in
`test_catalog3_git_fact_contracts.py` additionally checks byte/row transaction
limits, durable staged rows and resumed original fact/result/acquisition UUIDs.
Publication seals immutable facts after staging completes.

`test_related_oid_reuses_published_local_closure` retains its no-transfer guard
for an already published local direct root. The production path still walks the
actual local exact root closure and admits its independent acquisition membership;
retained verified bytes avoid a second object read. Reusing a global OID alone
does not establish repository/acquisition membership.

New contract suites cover JSON registry/SQL/owner admission and delayed receipt,
selective F0/F1/F2 convergence, exact component/aggregate completeness, immutable
Git facts and independent SQL/exchange attacks. The two isolated packaging
variants now also exercise installed Git reparse, new fact ownership, populated
JSON audit, fetch/collection selectors, repeated imports and later full exchange.

Actual production GitHub exchange positives cover initial acquisition and a
subsequent 304 sync with one and 101 thread replies. Complete units admit without
staging while receiver-local listing progress remains partial. Immutable listing
and Git result publication seals establish eligibility; explicit receiver-local
parser trust restores the same current code UUID/result/state and portable
`pr show`/nested `pr thread` output and completeness as the sender. PR readers use
all latest immutable observation candidates, including partial/unknown markers,
and reject disputed or quarantined proof instead of using sender job progress.
Presentation ordering uses permanent observation IDs or saved API page positions,
so remapped receiver row IDs do not reorder historical query output. These
transport and reader contracts are documented in
[`model-contract-completion.md`](model-contract-completion.md).

## Parser verification regeneration

The test-only bootstrap is an explicit synthetic local trust fixture. It is excluded from installed distributions; no production environment-variable bypass exists. A source change requires a new genuine evidence artifact:

```bash
uv run --no-sync python scripts/verify_builtin_parser.py --capture artifacts/parser-definition.json
REPO_CATALOG_TEST_BOOTSTRAP=1 uv run --no-sync pytest tests/unit tests/integration tests/e2e -n 4 --junitxml=artifacts/bootstrap.xml
uv run --no-sync python scripts/verify_builtin_parser.py --snapshot artifacts/parser-definition.json --junit artifacts/bootstrap.xml
uv run --no-sync pytest tests/unit tests/integration tests/e2e -n 4
uv run --no-sync pytest tests/packaging
```

The generator rejects a changed implementation/schema snapshot or failed report. The final two commands deliberately run without the bootstrap flag.

## Historical schema 13 acceptance

Final local acceptance uses the genuine packaged parser artifact without bootstrap.
The machine-readable receipt records commands, JUnit hashes, excluded tests,
DDL inventory, environment and certificate provenance in
[`2026-10-09-complete-model-contracts.json`](validation/synthetic/2026-10-09-complete-model-contracts.json).
Of 1,164 collected available tests, 1,163 ordinary/package tests executed and passed;
the opt-in live test was explicitly excluded. Independent cases overlap the ordinary
suite and are not added to that total.

| Gate | Final evidence |
|---|---|
| Ordinary unit/integration/end-to-end suite | 1,161 passed; 183.162s JUnit duration (183.17s command output); failures/errors/skips 0; no bootstrap. JUnit SHA-256 `4628ec415383fab8ca77d5a28436b30f436b547eadeaff6c9fe4b136ed7c4b68`. |
| Isolated installed wheel and sdist-derived wheel | 2 passed; 37.626s JUnit duration (38.19s command output); failures/errors/skips 0; no bootstrap. JUnit SHA-256 `18fa07be29608629b5ca268be513f581e301a211d0ef2385346558eedcaff7d8`. Both installed variants perform populated Git reparse, JSON full audit, selective/repeated/full exchange and backup/restore outside the source checkout. |
| Fresh initialization/complete packaged DDL | Schema 13; 102 tables, 45 views, 470 triggers, 100 named indexes. All views queried, all named indexes accessed, every trigger target DML compiled. FK check empty; integrity `ok`. DDL SHA-256 `7ce17169bedf10cae7f28decd2fa8239775713d42b515047ee3c6b0ba3a38738`. Installation/compilation is not a claim that every trigger branch was behaviorally exercised. |
| UUID/document/time/coverage and JSON inventory contracts | Acceptance helper passed canonical UUIDv4 including NUL-byte guards, natural document/text identities, signed int64 negative/zero/NULL time and exactly five coverage claim columns with latest unknown/conflict probes. All 50 JSON fields classified; installed generated guards equal the registry. |
| Independent review regressions | R1–R14 reproduced and corrected; final 53-case adversarial run passed without bootstrap, 34.274s JUnit duration; failures/errors/skips 0. SQL/admission/raw-identity/reader/coverage counterexamples and regressions are in `model-integration-audit.md`. |
| Ruff lint/format, whitespace and report validation | `uv run --no-sync ruff check .`, `uv run --no-sync ruff format --check .` (186 Python files), `git diff --check`, and `python scripts/ci_execute.py reports` passed. |
| Parser verification artifact | Exact definition binds 26 implementation modules, explicit decoding settings, complete packaged DDL and all 11 capabilities. Regenerated from a successful 1,161-case bootstrap report (180.37s command output); final ordinary/package acceptance separately passed without bootstrap. Artifact SHA-256 `a6e79d6d7ff5e95e870a1496b13a93adfd2c70859c96d6aedb18a8edb77dda28`; generator snapshot equals the current definition and its report hash matches the successful JUnit. |
| Environment | Python 3.12.14; SQLite 3.53.1; Git 2.52.0; uv 0.12.19; Linux 6.18.44 x86_64, glibc 2.41. |
| Submitted commit/hosted CI | The new stacked PR body records the exact published HEAD, PR #11 base, tested merge/tree, hosted run URL and downloaded acceptance receipt after publication. The accepted commit is not changed to add a self-referential CI record. |

Generate the disposable DDL/baseline/JSON evidence with
`uv run --no-sync python scripts/validate_remaining_contracts.py --output artifacts/remaining-contracts-ddl.json`.
The helper reports trigger installation and DML compilation separately from
behavioral trigger branches; full behavioral acceptance is supplied by the
ordinary suites. Live authenticated acquisition, physical hardware power-loss
testing and non-Linux atomic restore remain unexecuted scopes unless new executed
evidence explicitly establishes them.

The first hosted run exposed a large nested-pagination timeout; its actual
1,156-pass/one-timeout receipt and unexecuted packaging stage remain recorded in
the audit and final JSON. Exact publication set comparison, single-tree duplicate
checks, ordered per-result scope deduplication and indexed exact identity/DAG
queries preserve all constraints and the unchanged 60-second E2E deadline.

## Historical schema 12 acceptance

The previous integration's final unflagged local run passed **1,014 ordinary tests** (96.46s) and **2 packaging tests** (4.71s), with zero failures/errors/skips. Wheel and sdist-derived-wheel tests used isolated installed packages. Its genuine packaged verification artifact bound 21 implementation files, semantic settings and all composed DDL to passing evidence for all 11 declared capabilities. Those historical ordinary/package tests did not use the development bootstrap flag.

Fresh initialization and all composed DDL passed: schema 12, 98 tables, 30 views, 376 triggers and 91 named indexes. `PRAGMA foreign_key_check` returned no rows; `PRAGMA integrity_check` returned `ok`. Coverage claims retain exactly five columns. Ruff lint, format (172 files), whitespace checks and synthetic-report validation passed.

Local environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.23, Linux x86_64. Exact commands, JUnit hashes and DDL/object inventory are in [`2026-10-09-integrated-model.json`](validation/synthetic/2026-10-09-integrated-model.json). The final hosted run, published commit and tree identity are recorded in the submitted PR body after publication. This avoids changing the accepted HEAD merely to add its own CI receipt.

The historical run did not execute live authenticated-source acquisition, physical hardware power-loss testing or non-Linux atomic restore. Synthetic Git/GitHub acquisition and an actual interrupted repair process were tested. This evidence remains a schema 12 checkpoint; it does not establish current schema 13 acceptance.
