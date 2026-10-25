# ADR 0031 I4 author verification

**Author verification complete for the bounded G3=A SQL implementation. Independent
non-Author review is pending. Whole-product acceptance remains NOT READY.** Both
SQL Transfer fences and application refusals remain enabled in the product.
No merge, release, deployment, P8 or real-catalog/Provider action was performed.

## Exact input and publication binding

- Base: PR #126 HEAD `614ccaac3512a0df4291653fc83901df211f00f6`, tree
  `0e35eccffd996c5b7ed175a53adebf2ac76b16cb`.
- Referenced independently reviewed I3 product tree:
  `6f259f7239d7330bea4d1dd1b6e04c316561728f`.
- **Executed product/tests/runners HEAD:
  `f4d8c3d123552e765ef3f0ddaf4e83deaaa0e9c6`; tree:
  `764414d23797179c6988349ca4a236c6b929a44e`.** Both final regression lanes report
  a clean tracked worktree and identical unchanged input hashes. Distributions
  were built from a clean Git archive of precisely this commit.
- Post-execution evidence-helper correction:
  `27fa4482caad9d146250e0a6701a5fcffc3da390`, tree
  `31b6de0bba1843f63cf2355850e4ebf27e098e74`. It changes only the failure-comparison
  helper and the corresponding repository skill lesson. Product, tests, DDL,
  UDF, dependencies, workflows and packaged inputs are byte-identical to execution.
  The corrected helper was separately executed successfully on both final lanes.
- The last publication commit adds evidence/documentation only. The new Draft
  PR's author-report body binds its **exact final public HEAD/tree** after this
  file is committed; those values cannot be embedded in their own Git tree.
  The final standalone publication report includes that binding too.
- Initial live latest-PR and complete branch searches found no equivalent I4.
  Prepublication rechecks found no new I4 and confirmed #126 still at its exact
  instructed HEAD. Existing PRs were not changed.

## Changes and effective DDL

The [implementation contract](../../adr0031-i4-transfer-sql.md) defines every new
field, FK and I5 obligation. `changed-files.txt`, `effective-ddl.diff`, the complete
executed tree and actual `sqlite_schema` rows are in the indexed raw archive.

| Files | Effective change |
| --- | --- |
| `p1_ddl/context.sql` | Eight generated Event support/type projections; original Event clock projection; full nine-component typed Parent reference; additional native-I7 six-component Resource FK; EventReportKey whole-group UNIQUE; two endpoint reference fields and generated report kind; full seven-component Event report FK; non-NULL predicates and two pre-conflict INSERT guards. |
| `domain/transfer_sql.py`, `p1_context.py`, `p1_schema.py` | Three bounded deterministic row-local UDFs, shared registration and exact arity/flag requirements. No database/external searches in UDFs. |
| `p1_ddl/fingerprints.json`, `p1-disposition.json` | Composed/physical fingerprints and introspected columns, indexes, FKs, CHECKs and triggers refreshed together. |
| `audit_callsite_dependencies.py` | One exact opt-in module path; no prefix exclusion or public-runtime activation. Existing lexical inventory still matches. |
| `test_transfer_sql.py` | 217 new cases through raw composed SQL and the product factory, including isolated positive/negative SQL and normal fenced-product refusal. |
| Existing I2 test and active SQL diagnostic | Poison injection setup adapted to stronger guards; same eight test nodes, original poison values, all downstream assertions and all 301 diagnostic groups retained. |
| New verification/comparison/distribution scripts, contract and repository skill | Reproducible receipts, installed-runtime execution and verified fence/corruption-fixture/archive-selection lessons. |

Context still has 19 tables. ResourceKey triple PK and the entire Resource
identification table definition are unchanged. No Parent-existence FK on children,
new domain/header table, storage surrogate, winner or hidden pending payload.
Six relation roles, Source positives, five-column Coverage, Core/Operational/Search
fingerprints and Schema 21 default are preserved. Both SQL fence definitions are
byte-identical to base; the original application/stored-stage module is unchanged.

Composed Context DDL SHA-256 on both runtimes:
`924cc7557fb3da6211ea070185881f5fcaeff9bf52b6e237a361a238a2ea0c6e`.

## SQL guarantees and limits

The sole original Event support payload generates complete ParentReportKey/type
references and the native-I7 Resource reference. A real lawful I8 Parent report
survives, but its use for this I7 Event fails even after correct I7 support arrives.
Missing I7 Resource/report instead fails the dependency FK; original report
re-supply succeeds after dependency arrival. Arrival alone creates nothing.
Parent and Event original members, scopes, clocks, provenance and observation
times remain independent and immutable. Endpoint time/provenance/clock and full
report references must agree. SQL NULL, UNKNOWN CHECK passage, noncanonical IDs,
wrong types/subtypes/services and BINARY-versus-NOCASE false matches are rejected.

Pre-conflict guards cover INSERT, IGNORE, DO NOTHING, REPLACE and both no-op/update
UPSERT forms; UPDATE/DELETE guards preserve originals. Exact non-mutating replay
keeps old rows. Multirow statement failure, savepoint and transaction rollback
preserve complete prior rowsets. Legitimate multiple Parents and distinct Event
reports with independent genuine evidence coexist. Global/Scoped Document and
ordinary Parent behavior remains covered by the retained I3 cohort.

This proves structural SQL integrity, not Provider authenticity or actual
`transferred` meaning. A nonempty different original event-type string is
structurally representable in the isolated lane, as explicitly tested. I5 must
check event meaning, actual native contract, selection/permission, Provider member
existence, endpoint completeness/truncation, mapping dependencies and original
timestamp types before affinity. It must savepoint the complete unit and
revalidate replay; direct SQL alone cannot ensure all declared endpoints arrived.
Permanent I8 mismatch and resupplyable missing I7 dependencies remain distinct
I5 diagnostic obligations. No clock/time is replaced with SQL-generated time.

## Fenced product versus isolated SQL

New constraint tests compare the entire actual product schema to packaged expected
schema, then drop exactly `i2_transfer_stage_fence` and
`i2_transfer_report_stage_fence` in disposable synthetic DBs. All other integrity
settings, DDL, UDFs, indexes and FKs remain enabled. Both raw composition and
normal product initialize/connect factories are used. The removed definitions,
SQL statements and complete final rowsets are recorded for all 217 focused cases.
These modified DBs are not reopened as supported normal product schemas.

Separate normal configurations reject reports/endpoints through every tested
conflict verb; normal typed Admission still raises `I2_TRANSFER_UNSUPPORTED`.
An additional isolated typed-valid Transfer was injected, exact fences restored,
and the exact product schema/FKs checked: normal Context read then entered
AUTHORITATIVE_CORRUPTION/Recovery Stop. It did not expose the Transfer.

Existing malformed-storage poison controls are a separate corruption lane.
They temporarily disable FK/CHECKs and the relevant I4 INSERT guard solely to
seed the original impossible row, then restore all definitions/settings and
validate the exact schema before the original Context/query/export/Search stop
assertions. They are never credited as supported writes or I4 constraint success.

## Actual runtime execution

Official-source amalgamations were freshly built with recorded compiler argv,
source/archive/library hashes and exit 0. Dynamic CPython **3.13.5** actually
loaded each selected library; no SQLite version was overridden or relabeled.
Measured `sqlite_source_id()` values:

- 3.51.3: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
- 3.53.1: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

Compile options, actual PRAGMAs, functions/flags, full physical DDL and fingerprint
are in each `input-binding.json` and all four installed runtime receipts.
Measured required values: foreign_keys=1, recursive_triggers=1,
ignore_check_constraints=0, defer_foreign_keys=0, trusted_schema=1.
`p1_transfer_event_v1/7`, `p1_transfer_value_v1/2` and
`p1_transfer_endpoint_v1/4` carry deterministic flag 2048. Configuration and
missing/non-deterministic-function controls are tested. Shared factories,
expected-schema and recovery connection paths use the same registration entry.

| Lane per runtime | Executed | Pass | Failure | Error | Skip/xfail | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Broad regression | 3,108 | 3,029 | 59 | 20 | 0/0 | 1 |
| Focused I4, overlapping broad | 217 | 217 | 0 | 0 | 0/0 | 0 |
| Existing I3 subset, overlapping broad | 65 | 65 | 0 | 0 | 0/0 | Broad exit 1 |
| Existing I2 dedicated subset, overlapping broad | 86 | 86 | 0 | 0 | 0/0 | Broad exit 1 |
| Existing SQL diagnostic groups | 301 | 301 | 0 | 0 | 0/0 | 0 |
| Supplemental author SQL groups | 3 | 3 | 0 | 0 | 0/0 | 0 |

I2's 86 are the existing 70 generalized-resource tests, 14 identification unit
cases and two P1 installed cases. Node/JUnit/journal reconciliation verifies
actual execution, no duplicate starts/phases and unchanged inputs. All original
2,891 I3 selected nodes remain; I4 adds 217. Ordinary collection finds 5,651
nodes, with the original two opt-in deselections; 5,649 remain, of which **2,541
ordinary nodes are unexecuted**. There are four pytest warnings per broad lane.
No test deletion, skip, xfail, swallowed failure or narrowed assertion earns PASS.
The 301 groups preserve their original scope: 300 concern product DDL and one
compares the historical composition; they are not 301 new unique pytest tests.

All **79 final I3 non-success node/phase pairs remain identical** on both runtimes:
45 Transfer call failures, 20 Transfer setup errors, 14 I6 Wire call failures.
None is resolved by I4; zero new final non-successes. Every refusal code/text and
trace path/function sequence matches. In 18 trace-frame occurrences only the
`p1_context.py` line number moves by +4 for UDF registration; test failure
positions remain the same. Raw exception messages match exactly for 75/79;
the four installed P5 messages differ in temporary installation paths/pytest
command rendering. All originals and current full messages/frames are retained.
Later assertions beyond the first refusal remain unexecuted.

The comparison explicitly uses I3 archive `final-{version}/regressions.xml` at
2,891 nodes/79 faults. Its earlier `author-*` receipts have 2,889 nodes/81 faults
and are superseded. The initial wrong archive selection and exact-message
comparison failed; the corrected helper preserves raw differences and compares
the actual original refusal and source functions, with a separately verified
successful execution. This correction changes no product or pytest outcome.

## Installed wheel and sdist-derived wheel

A clean archive of executed HEAD produced a direct wheel and sdist; the latter
was unpacked and independently built into a second wheel. Four fresh installations
outside checkout ran both real runtimes. Each ran **217/217 I4 cases, exit 0**,
including actual packaged SQL, UDF, FK, index, fingerprint and fenced-product
controls. All four unchanged I2 and I3 distribution probes also exit 0.
Every installed package `.py`/`.sql`/`.json` hash matches both the wheel and frozen
source package. Import origins are inside each fresh virtual environment.

All four unchanged original Access smokes still exit **1** at Provider Transfer
preflight. Later assertions are unexecuted. Distribution orchestration exits **1**;
no failure is converted to green. Pytest/SQL groups overlap and are not summed.

- Direct and sdist-derived wheels: 758,668 bytes each, SHA-256
  `18038fd72b752767557e03ccc3c06cc94a61ec7a2f0f4fa49a3ef4893517c0f5`.
- Built sdist: 60,398,202 bytes, SHA-256
  `8e8c561797762b77017c381155f4849bb661ce0056c83dbb65a6fc65e699d350`.
- Source Git archive SHA-256:
  `8e1040af61e3b6e4fb301479f44156ad7bb75bb01afbaeb0e63687451a47ffed`.

The indexed evidence includes wheels, exact build/install commands, runtime and
file-hash receipts, copied outside-checkout test/probe inputs and all process
logs/exits. Bulky source archive, sdist, unpacked trees and virtual environments
stay in the execution workspace; their hashes and frozen Git source make them
reproducible. They are not silently represented as included archive payloads.

## Retained development failures and checks

The first dedicated attempt had 15 passes/196 fixture setup errors from a
nonexistent verification API. The next had 205 passes/six malformed-fixture
failures. Corrected dedicated tests pass. Initial frozen `7858615c...` regression
ran 3,108 cases: 3,021 pass, 67 call failures, 20 setup errors. The extra eight
failures were the old poison injector being rejected by new guards, before its
original stop assertions. Setup-only correction retains their node IDs, poison
values and complete downstream coverage. The active SQL diagnostic's initial
poison injection likewise aborted; its corrected final 301 groups pass on both
runtimes. These failed logs/receipts remain separately labeled in the archive.
No original 79-fault refusal was fixed by this fixture adaptation.

Final schema build/fingerprint, full schema inventory, callsite/isolation,
registration and implementation-boundary audits pass on both actual SQLite
versions. Changed-file Ruff lint/format, UTF-8/JSON/prose and whitespace checks
pass. Automatic development CI, if green, is infrastructure evidence and does
not replace these explicit runtime outcomes or constitute release acceptance.

## Frozen independent-review handoff

Review the executed product/tests at the exact HEAD/tree above and the final
publication's separate evidence-helper/skill correction. Verify the indexed
archive hashes, full Parent/native-I7/Event references, original evidence,
pre-conflict paths, normal fences, actual connection setup and all four installed
lanes. Independently execute counterexamples; author tests are not independent
review. This task freezes inputs for a different non-Author agent; no independent
review or approval is claimed here.

I5 must implement the contract's semantic/dependency diagnostics, original input
types, whole-unit completeness, policy and transactional admission before fence
removal and corresponding routing. I6 Wire's 14 failures remain. **Task G G-R1
remains unresolved for I7**, with historical counterexamples untouched; direct
FieldCandidate reads do not prove full Recovery. Paired backup/recovery and full
query/Search acceptance remain separate. No scope beyond this Draft PR is granted.
