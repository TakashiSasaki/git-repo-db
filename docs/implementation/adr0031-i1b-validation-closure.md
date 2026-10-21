# ADR 0031 I1b validation closure — Task A

**Validation fixtures repaired; product and distribution acceptance remains blocked.**
[Draft PR #118](https://github.com/TakashiSasaki/git-repo-db/pull/118) is stacked on
[Draft #117](https://github.com/TakashiSasaki/git-repo-db/pull/117). Neither was merged.
No production code, DDL/fingerprint, dependency, workflow or accepted identity
contract changes belong to this PR. No release, deployment, P8, real-catalog
mutation or live Provider acquisition was performed.

## Frozen coordinates and stack reconciliation

| Coordinate | Value |
| --- | --- |
| Main after merged #116 | `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` |
| Main / I1a effective tree | `318ad07874ab436206e6a61f231b308a421cfc54` |
| I1a head, ancestor of both main and I1b | `d92377599a50f192f534836fc12402a5fe87ca83` |
| Exact I1b branch base and unchanged #117 head | `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` |
| I1b tree | `708c860cd4badd4d787d4d8140b9626c80813be6` |
| Tested executable freeze | `d77acad2c2d97538479d7fa5489ecebfd5ad8f67` |
| Tested executable tree | `9e6a0d9db602446d4ce7e93d98f12533202e4b5e` |

Live GitHub state matched the supplied baseline before edits. #117 was retargeted
from the I1a branch to main without rewriting its head. Both three-dot merge
bases are I1a `d923775…`; the effective diff SHA-256 before and after is
`e2c6f75518c8c97d848ef3582b008770b8accb1054bf9cf613405b3794c826a0`.
The validation branch began at the exact I1b head. A prospective merge with main
has the executable tree above; this calculation performs no merge. Initial live
PR snapshots, ancestry/tree observations and source setup are in the receipts.
Later publication adds only report/evidence/skill files; its final SHA/tree and
checks are bound in #118's description, separately from the executable freeze.

Read contracts: repository AGENTS, [ADR 0001](../adr/0001-validation-lifecycle-architecture.md),
[ADR 0031](../adr/0031-generalized-context-resources.md), its
[schema contract](../architecture/context-resource-schema.md),
[implementation handoff](context-resource-design-handoff.md), and the
[I1 implementation/review evidence](adr0031-i1-canonical-resource-identity.md).
The prior I1 report and historical execution records remain unchanged.

## Changes and identity boundaries

The [active AST inventory](evidence/adr0031-i1b-validation/active-boundary-audit.json)
records 216 constructor/factory calls, including parseable embedded Python in
distribution scripts. Its structural scope is explicit; it is not a whole-program
data-flow proof. Native fixture literals and reviewed native helper arguments now
use `ResourceKey.from_native`. Serialized database rows and canonical GitHub
helper results retain strict `ResourceKey(...)` reconstruction. Deliberate invalid
serialized inputs in identity tests remain refusal tests.

Repairs cover module-level P3/P2–P3 fixtures; SQL Core-reference IDs; nested
Provider role scopes; canonical query predicates; Search projection identifiers;
accessor string overloads; CLI `--id`; and installed-distribution inputs. Known
scoped Document/Timeline factories keep native local values and canonical namespace
TEXT. The ordinary-comment negative test now supplies a valid scoped comment so
the intended Transfer-filter guard actually runs. Public Schema 21 metadata using
different identity contracts was not mechanically quoted.

The Access smoke now obtains its decimal Repository key through the canonical
GitHub helper, retains the separate Node namespace, and uses a native factory for
its Issue key. Its original mapping evidence text, clocks and provenance remain.
The genuine GraphQL Event local array is preserved. Both artifacts are attempted,
with runtime/origin/fingerprint/hash/error receipts, and either failure keeps the
script exit nonzero. No composite ID is stringified to satisfy old DDL.

The shared packaging fixture explicitly binds both checkout and unpacked-sdist
builds to `sys.executable`; P3's installed venv is similarly bound. This removes
ambient interpreter selection without changing dependencies or isolation checks.
The living generated call-site index was refreshed: its only addition describes
the codec already introduced by I1a. No historical execution evidence was edited.
The repository skill reference records the verified fixture/interpreter lessons.
No tests were deleted, skipped or xfailed; existing semantic assertions, exact
text, clocks, provenance and Exchange digest validation were preserved.

## Executed verification

Final runs are bound to the executable freeze above. All **429** source, test,
script, dependency and workflow input hashes match before/after both sequential
runs and between runtimes. The raw [receipt bundle and index](evidence/adr0031-i1b-validation/README.md)
retain exact argv/environment overrides, input hashes, Git state, source IDs,
compile options, SQL pragmas, selected IDs, journals, JUnit, full failure traces,
process exits and artifact hashes. These are local agent-asserted development
receipts, not independent release attestation.

| Actual SQLite / interpreter | Collected | Selected | Executed | Passed | Failed | Errored | Skipped | Xfailed | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.51.3 / Python 3.13.5, full ordinary collection | 5,283 | 5,281 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.53.1 / Python 3.12.14, full ordinary collection | 5,283 | 5,281 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.51.3 / Python 3.13.5, broad cohort | 2,740 | 2,740 | 2,740 | 2,736 | 4 | 0 | 0 | 0 | 1 |
| 3.53.1 / Python 3.12.14, broad cohort | 2,740 | 2,740 | 2,740 | 2,736 | 4 | 0 | 0 | 0 | 1 |

Each ordinary collection deselected exactly two opt-in live/benchmark cases and
had **zero collection errors**. No affected module was excluded. The cohort has
zero deselections. Its explicit paths are in archived `cohort.json`; **2,541**
ordinary nodes outside that cohort were not executed on the final freeze and are
enumerated in `ordinary-not-executed-on-final-freeze.txt`.

Within each cohort: Access **483/483**, P1–P7 **1,226/1,226**, P2/P3 and P5/P6
compatibility **49/49**, relevant unit tests **766/766**, and P1–P7 installed
packaging **22/22** pass. I23/I3/I4 pass **34/34**, **66/66**, **26/26**;
Provider intake passes **45/48**, and I5 passes **19/20**. These partitions sum
to the cohort; focused I1 and SQL counts overlap and are not added again.
All **37** disposable SQL identity cases pass with their actual runtime/pragmas.
The separate packaging/Search preflight passes **23/23** on each runtime and also
overlaps the cohort.

Duplicate-aware selected/start/finish/JUnit multisets agree, with exactly one
setup/call/teardown phase per executed node. The original work runner's raw
`selected_equals_junit=false` is preserved: it incorrectly split four parameter
IDs containing literal `::` in IPv6/`ext::` values. Separate reconciliation uses
the repository's existing `junit_key` rule, preserves parameter text, and proves
exact equality. This was an evidence-parser error, not missing test execution.

Actual SQLite source IDs:

- 3.51.3: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
- 3.53.1: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

The minimum amalgamation was verified against official sqlite3.c SHA3-256
`32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e`.
Archive SHA-256, compiler, exact shared-library build command/hash and dynamic
interpreter selection are in `stack-and-runtime-setup.json`. No version constants
were mocked. Setup used `uv sync --frozen --group docs` and the locked all-group
export for the separate minimum venv, plus independently prepared locked wheelhouses.
The final broad cohorts each had a separate collect-only invocation with
`-m 'not live and not benchmark'`.

Ruff lint/format passed across `src tests scripts` (394 Python files). Call-site,
composed P1 DDL/fingerprint, schema, implementation-boundary and Context-registration
audits passed. No workflow was changed or release validation dispatched.

## Installed Access distribution results

`python scripts/verify_access_distribution.py` was executed with each actual
runtime. Each built and independently installed a direct wheel and an
sdist-derived wheel outside the checkout, using `-I` and asserted installed
origins. **Both variants on both runtimes fail, each smoke process exit 1; each
script invocation exits 1.** They reach the genuine composite-local Event storage
gate after the corrected inputs. Their later Transfer Exchange/Search/backup
assertions are unexecuted. Passing P1–P7 packaging tests do not override this.

All four installed wheels have SHA-256
`47d1f5cc4af32eca2552ebf91bd5fa8641001eeab58dd050ba5aa86f6fc724ff`.
The source sdist SHA-256 is
`12107f35fe68be4d79f44311d8ad30ebe0e05f3805a7cc67873d8673f17558da`.
Context DDL fingerprints agree:
`fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`.
These artifacts were built at the executable freeze, before this evidence-only
publication. Equality of bytes/fingerprints is not domain acceptance.

## Failure disposition and precise remaining dependencies

The [per-node CSV](evidence/adr0031-i1b-validation/failure-disposition.csv) includes
the corrected and remaining diagnostic failures. The summary retains every
earlier failed/interrupted invocation with its original outcome.

| Finding | Classification and disposition |
| --- | --- |
| P3 `ResourceKey(SERVICE, "pull_request", "pr-7")` and P2/P3 module-level native key | Obsolete native-versus-serialized fixtures; repaired. Both modules collect and execute fully. |
| Original installed smoke plain decimal key | Obsolete scripted input; repaired without encoding canonical Node IDs again. Both variants now reach the distinct I2 gate. |
| SQL references, nested scopes, role/projection expectations, predicates, accessor/CLI inputs | Obsolete representation boundaries; corrected with semantic assertions retained. Final affected cases pass on both runtimes. |
| Unpacked-sdist build: missing Hatchling, 22 setup errors in an earlier cohort | Pre-existing interpreter-selection ambiguity exposed by this workspace; fixture now pins the prepared interpreter. All 22 cases pass on both final runtimes. |
| Missing PyYAML during first raw collection | Workspace setup: declared docs dependency group was absent. Installed that group; no dependency change. |
| First minimum attempt actually loaded SQLite 3.49.1, 48 failures | Invalid supported-runtime attempt, retained and not counted as minimum validation. Corrected by explicit dynamic `/usr/bin/python3.13` binding and actual SQL version/source-ID checks. |
| Generated call-site index missing the already-added I1a codec | Inherited active-index drift; regenerated and reviewed, production source unchanged. Hosted audit now passes. |
| Three recorded Provider-intake cases and one additional I5 case | Genuine native composite Event persistence needs I2; four failures retained on both runtimes. Exact nodes below. |
| I1b production defect | None identified by these executions. No production correction was made; unexecuted scope is explicit. |

Remaining failing test nodes, **all first failing at
`ContextStore.resource()`'s explicit nonempty-scalar-local storage guard**:

1. `tests/integration/i2/test_provider_intake.py::test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]`
2. `tests/integration/i2/test_provider_intake.py::test_graphql_transfer_parent_namespace_and_original_type`
3. `tests/integration/i2/test_provider_intake.py::test_graphql_event_does_not_infer_destination_from_current_issue_repository`
4. `tests/integration/i5/test_independent_e2e.py::test_transfer_reports_never_mix_across_observations_or_identifier_namespaces`

The installed Access smoke's `EV_installed` is the same capability dependency.
For the I5 counterexample the key contains native local
`["github:node_id","EV_node"]` under Issue `501`, not a string containing that
array's JSON. The accepted key is complete; current packaged persistence rejects
the local array. Namespace preservation is correct. Later semantic assertions,
including non-Transfer and report-pairing checks, are blocked rather than proved.

I2 must integrate generalized Resource identifying metadata and native
scalar/recursive-array local persistence, bounded SQL functions, packaged DDL,
composer/indexes and fingerprints coherently. Durable global/scoped contract
metadata and meaningful empty/composite local IDs remain unsupported capabilities;
merely removing the Python guard is insufficient. Preserve the key triple,
canonical BINARY equality and genuine namespace distinctions.

I3's sole Parent-report authority, I4's G3=A native-I7 typed Transfer SQL, I5's
whole-unit semantic admission, I6 generic relations/Collections/Exchange, I7 stored
validation/paired recovery and I8 query/Search integration remain separately
scoped stages from the accepted handoff. The four first-reached I2 failures do
not demonstrate execution or correctness of those later obligations.

An intentionally interrupted earlier diagnostic selected 4,993 and started 2,090
cases after completing the relevant integration portion: 2,046 passed, 43 failed,
one incomplete. The raw runner defaulted that incomplete case to `skipped=1`;
the supplementary summary corrects its classification without rewriting the raw
receipt. A subsequent complete candidate had 2,713 passed, five failed and 22
setup errors; the later assertion/interpreter repairs and final reruns supersede
that candidate. The work orchestration process completing successfully is not
the pytest result: both final cohort subprocesses exit 1.

## Hosted CI and reviewer handoff

At executable freeze `d77acad…`, [Development CI 39596753789](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39596753789)
passed. [Access 39596753781](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39596753781)
failed on actual SQLite 3.51.3: **2,388 passed, the same four failed**, test exit 1.
Both installed smoke variants fail. Module-ownership/schema/registration and
formatting steps pass; the acceptance ledger refuses the failed receipt.
The fetched hosted test-merge `b63c59749b18d5dab2cca0b4c4ec88ec8d61b556`
has exact parents I1b `32e5d4de…` and executable freeze `d77acad…`, and the
identical effective tree `9e6a0d9db602446d4ce7e93d98f12533202e4b5e`.
The actual job log and metadata are archived. Final publication-head checks are
reported separately in #118. Green Development CI does not imply full pytest,
product, distribution or release acceptance.

A separate reviewer should inspect the frozen executable commit read-only, then
the evidence/skill-only publication delta. No new non-author review or approval
is claimed here. Review all native conversions against their supplying contracts;
check retained serialized row/helper calls, the namespace-TEXT Document profile,
Node/decimal inequality, original mapping evidence, SQL references, negative-test
reachability and unchanged Exchange digest rules. Inspect the raw four failures
and four installed smoke failures without replacing their native arrays.

Reproduce collection and the archived cohort on actual 3.51.3 and 3.53.1; verify
source IDs and all 429 hashes, then reconcile selected IDs, starts, every phase
and JUnit using duplicate-aware parameter-preserving normalization. Review the
raw instrumentation limitations and their supplementary corrections. Confirm
the final publication has no diff in the frozen runtime/test/script/dependency/
workflow inputs. The [complete changed-file list](evidence/adr0031-i1b-validation/changed-files.txt)
includes tests, script, generated index, skill and all new reporting paths.

Applied repository procedures: efficient-repository-investigation,
ci-final-tree-verification, three-store-invariants and lessons-to-skills, plus
managed cloud-runtime setup guidance. The existing Context registration/Exchange
skill reference was updated with verified procedures; it grants no new execution
or acceptance authority. No merge is requested or authorized by this report.
