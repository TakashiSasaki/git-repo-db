# Task E — ADR 0031 I2 Author implementation and verification

**I2 product code is implemented with its mandatory stage fences. This is Author
verification, not independent product acceptance. Whole-product acceptance is
incomplete: retained Transfer/Exchange/installed Access checks still fail at the
explicit I2/I6 boundaries.** No existing test was deleted, skipped or xfailed.

## Authority, dependencies and exact executed source

The owner directly requested one new Draft implementation PR. Initial and later
live GitHub searches found no equivalent I2 implementation PR/ref. Task F #123 at
`c1b62d216db2b728a4c8cb1821250335fcafc534` gave **READY WITH CONDITIONS**, with
no unresolved design blocker. All five conditions are mapped to product changes
and acceptance tests in the [implementation record](../../adr0031-i2-implementation.md).
Connected publication uses the owner's GitHub account; it supplies no independent
reviewer identity. No subagent or non-author product reviewer was commissioned.

| Input | Exact commit |
| --- | --- |
| I1b #117 | `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` |
| Validation #118 | `9ea69ba8804a368802457950601a5a4027174c52` |
| Sibling independent I1b review #119, read-only reference | `cb49836aa855da8503f02370b9a60dddac5d6113` |
| Basic plan #120 | `9eaa5111c94204c4adf791cd1565b704728493f1` |
| Task D #121 | `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6` |
| C-F1 #122, reviewed design source | `2199a882d79c9c707fffcba3a8327ef96a3fc384` |
| Task F #123, implementation parent | `c1b62d216db2b728a4c8cb1821250335fcafc534` |
| **Final executed implementation/tests** | **`cb1df83afc543d74df8b16327bfb2c418786b3b2`** |

Executed tree: **`9d0130aa3324ff36e4bcda0cfc89258e951a747a`**. The raw full-tree
manifest binds all **3,783 tracked files**. Both final test runners report clean
tracked status, the same executable input hashes and unchanged inputs afterward.
The final full-source check has zero mismatches. Existing frozen evidence,
accepted ADRs, lock/dependencies and workflows remain unchanged. Core,
Operational and Search DDL/physical fingerprints remain exactly unchanged;
Access/default Schema 21 isolation regressions pass.

The publication adds this evidence directory only after the execution freeze.
Its final HEAD/tree and exact unchanged-input comparison are recorded in the new
Draft PR description. This explicitly binds the published implementation/tests
to the executed tree without pretending an evidence-only commit was the original
runtime checkout. Removing only the added evidence directory must reproduce the
exact executed full tree above. Artifact builds below use that executed commit.

## Product changes and limits

The triple PK is unchanged. Explicit immutable non-key identification metadata,
open kinds, canonical SQL predicates, scalar/recursive-array native local IDs,
child-first admission, pre-conflict metadata immutability, BINARY indexes/FKs,
connection registration/configuration, composer/fingerprints, Provider intake,
checked query output and necessary recovery validation are integrated.
`resource_relations` alone owns semantic Parent reports. Resources have no
namespace-existence FK and namespace arrival creates no report.

Both Transfer representations are fenced in packaged SQL: the exact reserved
report name and both endpoint roles. Retained immutable UPDATE guards close
generic-to-reserved UPSERT/update paths. Typed admission/intake refuse before
effects/replay. The real selected import transaction is checked before dependency
rewriting, package binding/replay and either authority's effects. Tests compare
all Core and Context rows on rejection, preserve independent Core-only receive,
and cover mixed order, Provider-only reports and previously bound packages.
V4 rejects unknown nested operation extensions through its real parser; the
normalized nested-operation helper is separately identified, not a new wire parser.

Explicit Transfer reads/exports refuse on empty stores. Impossible reserved rows
in an exact matching schema enter ADR 0026 recovery stop before ordinary Context,
query, export or Search exposure. Diagnostic poison injection restores the exact
schema, preserves all rows and is not a supported write route. Schema mismatch
remains a format refusal. Current wire units that would lose known document
identification raise `I2_IDENTIFICATION_WIRE_UNSUPPORTED`; no shape-based old-wire
translation is introduced. Opaque kinds/reports, ordered members and arbitrary
metadata text remain usable under supported common contracts.

## Actual runtimes and test reconciliation

Both SQLite libraries were freshly downloaded from sqlite.org and compiled in
this Author session. Python 3.13.5 dynamically loaded each library; no SQLite
version constant was overridden. Archive/source/header/library hashes, compiler
argv, compile options and actual runtime PRAGMAs are in the archive.

| Actual runtime | `sqlite_source_id()` |
| --- | --- |
| 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Normal profile: FK=1, recursive triggers=1, ignored CHECKs=0, deferred FKs=0,
trusted schema=1, synchronous=EXTRA, UTF-8. Initialized product catalogs use WAL.
Standalone SQL counterexamples use memory/DELETE journaling and do not establish
WAL crash or host-power-loss qualification. UDF absence and unsupported profiles
are refusal controls, not supported configurations.

| Final lane, per runtime | Collected | Selected / executed | Pass | Fail | Error | Skip / xfail | OS exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full ordinary collection only | 5,369 | 5,367 / 0 | — | — | 0 collection errors | 2 opt-in deselections | 0 |
| Broad regression execution | 2,826 | 2,826 / 2,826 | 2,747 | 59 | 20 | 0 / 0 | **1** |
| Dedicated identification/stage + P1 distribution subset, included above | 86 | 86 / 86 | 86 | 0 | 0 | 0 / 0 | Included in broad exit 1 |
| Task F SQL diagnostics, including unchanged Task D before/after | 301 groups | 301 / 301 | 301 | 0 | 0 | 0 / 0 | **0** |

All original Task A **2,740 selected node IDs** are retained in the final selection,
with zero missing nodes. Collection/start/JUnit duplicate-aware multisets match;
each attempted node has one setup/teardown and one call after successful setup.
Both runtimes have exactly the same node outcomes. The 20 setup errors have no
test-body execution. Four original pytest warnings are retained in raw logs.
There are **2,541 ordinary nodes outside this selected cohort**, plus the two
opt-in nodes; they were not executed. This is not a full release-suite claim.

Every non-success is classified from actual exceptions: **45 call failures plus
20 setup errors at `I2_TRANSFER_UNSUPPORTED`**, and **14 call failures at
`I2_IDENTIFICATION_WIRE_UNSUPPORTED`**. The four P5 wheel/sdist pytest failures
are included in those 14; they are not additional failures. No other final
failure/error category remains.

The 301 SQL groups are adapted from frozen Task F, using actual product
DDL/UDFs. They contain **300 groups involving product DDL and one old-composition
control**; the Task D literal is unchanged. The 42 normalized routing-model
groups are excluded. These SQL groups and pytest overlap requirements and must
not be added as unique acceptance tests. Actual extended errors and complete
pre/post rowsets are retained, including malformed/NULL cases, true collision
replay, all conflict verbs, correct-I7/I8 dependency combinations, UPDATE/UPSERT,
multirow ABORT, caller savepoints, reopened metadata and physical inventories.

## Original Task A four failures: first new boundary

The scalar-only persistence rejection has been removed. Separate positive tests
now persist/reopen recursive local IDs through SQL and through genuine REST and
GraphQL non-Transfer intake, including the original Node-ID namespace. The table
below reports the original nodes' actual first new boundaries, not inferred
success of later assertions.

| Retained node | Actual first position on the executed source | Unreached meaning |
| --- | --- | --- |
| `i2/test_provider_intake.py::test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]` | Test line 376 calls `Context.transfer_event_reports`; `production_context.py:987` refuses after `admit_unit` succeeded | The following repository-relation conjunction and forged-flag promotion assertions do not run in this node |
| `i2/test_provider_intake.py::test_graphql_transfer_parent_namespace_and_original_type` | Test line 408 → `acquisition.py:1519` → `_preflight_units`, line 1471 | Transfer original-type/native Issue namespace, report/support and endpoint semantics are unexecuted |
| `i2/test_provider_intake.py::test_graphql_event_does_not_infer_destination_from_current_issue_repository` | Test line 745 → same preflight at line 1471 | Destination non-inference and one-sided Transfer assertions are unexecuted |
| `i5/test_independent_e2e.py::test_transfer_reports_never_mix_across_observations_or_identifier_namespaces` | **Setup error**: module fixture `assembled_template`, line 271, before the test body; same preflight at line 1471 | Later GraphQL Event, pairing/namespace, selection, onward Exchange/Search/backup checks are unexecuted; this same fixture blocks 20 nodes |

The three Transfer paths now refuse before Resource registration. It would be
incorrect to claim those Transfer nodes exercised a successful Event INSERT or
completed I3–I5 semantics merely because the old storage exception disappeared.

## Installed direct wheel and sdist-derived wheel

Artifacts were built from a clean Git archive of the executed commit using the
prepared interpreter and locked build dependencies. Both wheels were installed
without editable imports into separate venvs for **each** actual runtime and
executed with `-I` outside the checkout. All installed package/resource files
match source hashes; origins are under each venv. Packaged DDL/fingerprints,
function flags, normal PRAGMAs, positive/refusal/reopen Resource behavior and
stored validation pass in **all four I2 smoke attempts**, each OS exit **0**.

- Direct wheel SHA-256: `991bd31ed13cafdcf5d452a80f87270f914f24f105ab998a9631021b7f688c47`.
- Sdist-derived wheel has the same measured hash.
- Source sdist SHA-256: `ac77e951272379b6eef0685b8f9ddf4dd581628817af1def063d3eb8f8f37c06`.

The **unmodified original Access smoke** was also attempted for all four
artifact/runtime combinations. Each exits **1** at installed
`ProviderAcquisition.admit_batch` → `_preflight_units`, lines 1519/1471,
`I2_TRANSFER_UNSUPPORTED`. The first new failure is earlier than the old Event
persistence gate; later Transfer, Exchange, query/Search and paired-backup
assertions remain unexecuted. Its original smoke bytes/hash and all complete
outputs are retained. The distribution orchestrator correctly exits **1**.
Passing the separate I2 probes is not full installed Access acceptance.

## Checks, history and handoff

Changed-file Ruff lint/format, packaged DDL/fingerprints, physical-schema audit,
callsite index, public/target boundary audit, registration audit and report checks
pass. Full-source hash comparisons preserve the freeze. The new explicit target
isolation entries are tested against public-runtime imports. No workflow was
changed to suppress failures.

Initial development attempts and two superseded freezes are retained separately.
They include missing-test command selection, obsolete metadata fixtures, the
missed Provider Core-reference declaration lookup, isolation classification and
the installed receipt's SQLite-Row JSON serialization error. Early pre-freeze
logs have no complete immutable input binding and are not final acceptance
counts. Superseded frozen cohorts retain their own exact commit/tree bindings.
None are relabeled as passing final executions.

Independent product review must freeze the published effective implementation,
inspect the actual product diff and rerun high-risk SQL plus real consumer and
installed artifact checks. Review the updated `three-store-invariants` skill too.
Keep both fences until reviewed I3, I4, I5 and matching routing support replace
them in one coherent effective tree. I4 still needs native-I7/full-report SQL;
I5 still needs actual semantics, original type/time and complete endpoints.
I6 generalized wire and full I7/I8 recovery/Search remain separate work.

No existing PR, merge, release, deployment, P8 activation or real catalog was
changed. [README.md](README.md) and the indexed archive provide reproduction and
raw evidence for the next non-author reviewer.
