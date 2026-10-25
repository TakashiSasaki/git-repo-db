# ADR 0031 I4 independent product review

**限定I4独立レビューPASS — bounded I4 SQL implementation only.** No Critical,
High or Medium I4 issue remains. Product implementation findings: **0**.
One **Low** evidence-scope finding, **I4-E1**, remains: complete sdist inputs are
not identical between the Author execution and publication trees. Runtime code,
DDL, UDFs, tests, build configuration and resulting wheels are identical. The
literal whole-sdist-input equivalence check is **FAIL**; installed runtime checks
are **PASS**. This qualification is part of this verdict, not an implied claim
that every requested identity check passed.

This review does not accept ADR 0031 as a whole, enable Transfer, accept I5–I8,
resolve G-R1, or authorize merge, publication, release or deployment.

## Fixed references and independence

Reviewed on 2026-10-22 UTC by an agent separate from the implementation Author.
GitHub was checked before runtime testing and checked again at completion.
PR #127 and base PR #126 remained open, Draft and unmerged at the requested heads.

| Reference | Commit | Tree |
| --- | --- | --- |
| Base #126 | `614ccaac3512a0df4291653fc83901df211f00f6` | `0e35eccffd996c5b7ed175a53adebf2ac76b16cb` |
| Author execution | `f4d8c3d123552e765ef3f0ddaf4e83deaaa0e9c6` | `764414d23797179c6988349ca4a236c6b929a44e` |
| Evidence correction | `27fa4482caad9d146250e0a6701a5fcffc3da390` | `31b6de0bba1843f63cf2355850e4ebf27e098e74` |
| Public HEAD and independent product execution | `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e` | `3dd1e39e06d347883a6fb493e7b9b06fb6dbfb62` |

Execution used a clean, detached worktree at public HEAD. No reviewed product,
test, branch or PR was modified. Reviewer probes and observers live outside the
checkout and have their own SHA-256 inventory in the bundle. The pre-existing
workspace checkout was not used as the review target. There was no real Provider,
catalog, merge, release or deployment operation and no GitHub write.

The accepted ADR, detailed schema contract, I4 contract, Author report/index,
actual `context.sql`, composed schema, generated columns, indexes, FK/CHECKs,
triggers, UDFs and registration/connection code were read. Evidence files were
treated as claims to check, not acceptance authority.

`blob-comparison.json` records actual Git blob equality for 409 product/test/
workflow/build-configuration paths. `all-execution-input-blobs.json` covers all
445 execution inputs: the sole difference is the explicitly corrected evidence
comparator, `scripts/compare_i4_failures.py`; the other 444 are equal. All eight
tree differences are enumerated. Full sdist membership is separately audited
under I4-E1 below; it must not be conflated with wheel inputs.

## Author evidence independently checked

The published ZIP has exactly **5,431,376 bytes**, SHA-256
`e452d2b86f99fff8f44993204d7e72df925b69b34086a6399d791aeb39c75948`.
Its 840 distinct payload names exactly match the index, and every indexed size
and hash verifies. Both archived runtime bindings and the distribution binding
name the requested Author execution HEAD/tree. Each runtime's 445 recorded input
hashes was recomputed from that exact Git tree. Both archived wheels' 153 package
source/SQL/JSON files were compared byte-for-byte with the frozen source.

Required final regression, focused execution, JUnit, phase journal, build/install,
runtime and process-exit receipts were inspected. Archived final broad receipts
have 3,108 starts, 3,029 passes, 59 failures, 20 errors and exit 1; focused receipts
have 217 starts/passes and exit 0. Earlier failed development runs remain earlier
failed runs. The ZIP excludes bulky source/sdist/environment directories as
declared; their presence was not inferred. See `author-content-audit.json` and
`author-receipts-audit.json`.

These checks establish archive consistency. The following executions were newly
performed by this reviewer and are the runtime basis of this verdict. Reused
repository runners retain their hard-coded `author_verification` metadata field;
that label does not turn these new executions into historical Author runs.

## Actual engines and newly executed cohorts

Both SQLite amalgamations were independently downloaded from sqlite.org and
compiled as shared libraries. CPython 3.13.5 actually loaded each selected library.
The executing SQL returned:

| SQLite | `sqlite_source_id()` |
| --- | --- |
| 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Compile options, compiler command/source/archive/library hashes, actual schema,
FK/index column order, column types/collations, deterministic-function flags and
PRAGMAs are retained in `runtime-builds.json`, both independent `runtime.json`
files and all four installed runtime receipts. Compilation uses `-O2`, FTS5,
RTREE, math functions and column metadata; options were measured rather than
assumed to equal the Author's compiler profile.

Every supported connection had foreign_keys=1, recursive_triggers=1,
ignore_check_constraints=0, defer_foreign_keys=0, trusted_schema=1.
`p1_transfer_event_v1/7`, `p1_transfer_value_v1/2` and
`p1_transfer_endpoint_v1/4` have deterministic flag 2048. Composed Context DDL
SHA-256 on both engines and all four installations is
`924cc7557fb3da6211ea070185881f5fcaeff9bf52b6e237a361a238a2ea0c6e`;
declared composed/physical fingerprints and inventory checks also pass.

| Newly executed, per engine | 3.51.3 | 3.53.1 | Exit |
| --- | ---: | ---: | ---: |
| Reviewer-designed SQL/API cases | 153/153 | 153/153 | 0 |
| Original I4 focused pytest cases | 217/217 | 217/217 | 0 |
| Original I3 cases, within broad cohort | 65/65 | 65/65 | Broad exit 1 |
| Broad product regression | 3,029 pass / 59 call fail / 20 setup error | Same | 1 |
| Original SQL diagnostic groups | 301/301 | 301/301 | 0 |
| Original eight poison nodes with restoration observer | 8/8 | 8/8 | 0 |
| Schema, inventory, callsite, registration and implementation-boundary audits | Pass | Pass | 0 |

The broad cohort has 3,108 distinct starts and exactly the expected phases;
it contains all original 2,891 I3-selected nodes plus 217 I4 nodes. No skip,
xfail, xpass or early termination changes those results. The focused and I3
cohorts overlap broad execution; the table is not an additive unique-test count.
Ordinary collection selects 5,649 nodes after the original two opt-in deselections;
**2,541 ordinary nodes were not executed**. Four broad warnings per engine are
retained in the logs. Later assertions behind the 79 refusals were not executed.

## Independently designed counterexamples and observed failure positions

`independent_sql.py` imports product APIs only; it imports no Author test helpers.
Each positive database is constructed from actual product composition or its
initialize/connect factory, then the complete schema is compared with packaged
expected DDL. The only positive-lane mutations are:

```sql
DROP TRIGGER i2_transfer_stage_fence;
DROP TRIGGER i2_transfer_report_stage_fence;
```

All remaining schema rows and required connection settings are checked. Normal
fenced connections, including factory connections, are tested separately.
An explicit unsupported-deferred-configuration negative control is labelled as
such: `verify_connection` refuses it, COMMIT fails its unresolved FK, and rollback
removes the pending row. It is not credited as a positive I4 configuration.

All 153 cases record expected versus actual acceptance, SQL and parameter values,
exception class/code/text and unchanged-rowset results. Expanded SQL traces are
retained. Representative actual results on both engines:

| Minimal attempted counterexample | Expected | Observed position/result |
| --- | --- | --- |
| Child Resource, missing native I7 Resource | Child accepted; dependent report withheld | Child accepted; Event INSERT fails FK, code 787 |
| I7 Resource present, correct Parent report absent | Dependency refusal | Event INSERT fails FK, code 787 |
| I8 Resource and lawful Parent report present, with I7 report also present | Retain I8, permanently reject I8 support | I8 Parent INSERT succeeds; Event INSERT using I8 fails native FK, code 787; correct I7 Event succeeds |
| Another Event under the same I7 borrows the first Event's Parent payload | Reject complete-key borrowing | Event INSERT fails FK, code 787 |
| Change only quoted Parent provenance | Reject evidence borrowing | Event INSERT fails FK, code 787 |
| Uppercase native-ID lookalike that compares equal under NOCASE | Reject BINARY false match | Native FK rejects, code 787 |
| NULL `parent_members_json`, omitted support field | Reject NULL/UNKNOWN route | `i4_event_report_admit`, `invalid typed Event report`, code 1811 |
| IGNORE or UPSERT with same Event clock/provenance but changed observation time | Reject before conflict no-op/update | `immutable original Event report rebind`, code 1811 |
| DO NOTHING endpoint using changed full Event scope | Reject pre-conflict rebind | `endpoint original Event payload rebind`, code 1811 |
| Second endpoint has a different original time | Reject | `rrr_event_report_time`, code 1811; explicit unit rollback restores the prior complete rowset |
| Multirow INSERT, first valid and second contradictory original group | Entire statement fails | Code 1811; no first row survives |

FK failures share SQLite's generic error code 787. SQL structurally distinguishes
the invalid native-Issue binding from absent dependencies; it does **not** provide
distinct permanent-versus-resupplyable application diagnostic codes. I5 must do
that classification before admission.

The remaining cases cover wrong service/subtype, all required support fields,
noncanonical IDs and malformed/duplicate JSON, SQL NULL and wrong SQL types,
32/33 array depth, 262,144/262,145 identity bytes, 4,096/4,097 identity nodes,
aggregate scope limits, zero/negative/float/bool/string/overflow clocks, NULL/1/
int64-max observation times, full endpoint members/scope/provenance/clock/time,
INSERT/IGNORE/REPLACE/DO NOTHING/UPSERT and UPDATE/DELETE guards, exact legitimate
replay, savepoint/transaction rollback, child-first resupply, competing I7/I8
Parent reports and Event reports with distinct genuine clocks or provenance.

Boundary controls deliberately demonstrate that isolated SQL can store a nonempty
event type other than `transferred`, a report before all its endpoints, and
INTEGER-affinity conversions of original bool/string/integral-float observation
inputs. The strict original-type API rejects the latter original inputs. These
are documented I5 duties, not SQL authenticity/completeness guarantees.

Two reviewer-harness assumptions were corrected with original failed logs kept:
explicit NULL Provider endpoint IDs are valid in the selected contract; and the
journal correctly labels a fully finished nonzero cohort `failed`, not
`completed`. Neither correction changed product code, original tests or actual
test outcomes. Final probes/comparison use the corrected explicit expectations.

## Accepted ADR invariant audit

| # | Invariant | Mechanism and execution evidence |
| --- | --- | --- |
| 1 | U3=C′, one semantic Parent authority | Only `resource_relations` owns Parent facts; support projections are generated and full-key constrained. No new table or writable Parent authority. |
| 2 | B3, native identity differs from semantic Parent report | Resource namespace metadata alone creates no report. Lawful I8 Parent coexists with native I7; native metadata is used only for Transfer's additional FK. |
| 3 | U4=B, child-first admission | Independently inserted Event succeeds before I7 exists; I3 global/scoped child-first cases also execute successfully. |
| 4 | No fabricated Parent/report/queue | Failed dependent INSERT leaves the full rowset unchanged. Parent arrival alone leaves no Event report; no pending domain storage was added. |
| 5 | Original resupply/time/provenance | Explicit original-report resupply succeeds only after dependencies; no arrival-time substitution. Parent 101/109 clock/time and Event 211/223 clock/time remain independently supplied. |
| 6 | Competing Parents, no winner | Multiple I7/I8 Parent rows remain; Event support cites one complete original report rather than selecting a global winner. |
| 7 | I3 global/scoped/nonleaf Documents | `test_global_child_first_late_parent_original_resupply` and `test_scoped_alternatives_i8_document_children_and_nonleaf`, plus the full 65-case I3 cohort, pass on both engines. |
| 8 | G3=A correct I7 support | Additional six-column native-I7 FK and complete typed Parent FK both enforced. Correct I7 support succeeds in the isolated lane. |
| 9 | I8 retained but permanently ineligible | Real I8 Parent stored; I8 Event support rejected even with I7 present. No deletion, correction or winner. |
| 10 | Missing I7 is a dependency | Missing Resource/report fail actual dependency FKs; original resupply succeeds after arrival. I5 owns useful diagnosis. |
| 11 | Full keys and original group | Typed Parent reference has all seven PK components plus subtype/kind; endpoint reference has all seven Event PK components. Whole-group Event UNIQUE and pre-conflict guards retain original members/scope/clock/provenance/time. |
| 12 | Existing PK/roles/Source/Coverage/store boundaries | Resource CREATE TABLE unchanged with triple PK; 19 Context tables; native FK's six TEXT/BINARY columns inspected in order. Six-role CHECK, Source positive tables, Coverage tables/shared DDL and Core/Operational/Search DDL remain unchanged; original regression and schema audits pass. |

The native FK targets exactly `(service_instance_uuidv4, resource_kind,
provider_resource_id, reference_document_kind, identifier_namespace_kind,
identifier_namespace_id)`, in that order. Its UNIQUE index key slots are BINARY.
Generated required values and the Event predicate block partial-NULL FK exemption;
explicit non-NULL endpoint references block CHECK UNKNOWN. UDFs are deterministic,
bounded, row-local predicates/projections with no storage/external lookup. The
complete FK/CHECK/trigger combination, not an isolated UDF result, is the guarantee.

## Existing poison fixtures and 301 diagnostic groups

AST comparisons with exact base #126 establish that the original poison INSERTs,
both parameter decorators (eight nodes), and every downstream Context/query/
export/Search refusal, Recovery Stop and unchanged-rowset assertion are identical.
The 301-group script is AST-identical outside `inject`; no assertion/group was
removed or weakened. Its original named groups are all present and executed.

The additional bypass belongs only to deliberately impossible-storage injection.
Read-only observers verify the exact normal schema, all required PRAGMAs and UDF
registrations after injection and before downstream exposure. Both engines
execute all eight unchanged nodes. Each engine records 24 poisoned-state schema
validation observations across the eight nodes, and 105 restored `inject` returns
in the 301-group diagnostic. The eight-node observers do not replace assertions
or suppress exceptions. The 301 groups all pass with unique group names.

No positive I4 SQL result uses disabled FK/CHECKs or a removed integrity guard.
Both stage fences and the application Transfer refusal remain enabled in ordinary
product use. Normal typed Admission still refuses; injected matching-schema
Transfer storage still drives corruption/Recovery Stop rather than exposure.

## All 79 inherited first failures

`independent-failure-comparison.json` compares the I3 ZIP's **final-{version}**
2,891-node/79-fault receipts with this review's newly executed 3,108-node receipts.
The archived earlier **author-{version}** 2,889-node/81-fault receipts are explicitly
superseded and were not used as baseline.

On each engine, exactly the same node/phase pairs and first semantic refusals remain:

- 45 call failures: `I2_TRANSFER_UNSUPPORTED`.
- 20 setup errors: `I2_TRANSFER_UNSUPPORTED`.
- 14 call failures: `I2_IDENTIFICATION_WIRE_UNSUPPORTED`, owned by I6.

New non-successes: **0**. Resolved non-successes: **0**. Test file/line positions
and source path/function sequences agree for all 79. Eighteen trace-frame
occurrences move by exactly +4 in `p1_context.py`, matching the added UDF
registration lines; test failure lines do not move. Raw messages match for 75.
The four installed P5 raw messages differ only in temporary directories and
pytest's truncated `-c` argument rendering. Exact fragments and the narrowly
applied normalization are retained in `raw-message-differences.json`; normalized
messages are equal. All original and new raw messages remain in the bundle.

The 79 remain genuine failures/errors. No downstream assertion or unexecuted
ordinary test is promoted to PASS. The existing 79 therefore do not establish
whole-product acceptance, and they are not new I4 regressions.

## Independent distribution execution

Clean `git archive` of public HEAD was used to build a direct wheel and sdist;
the sdist was unpacked and independently built into another wheel. Fresh virtual
environments outside the checkout were used for each artifact, each exercised
with both real SQLite libraries. Import origins are inside the installation,
and all 153 installed `.py`/`.sql`/`.json` files match the wheel and source.

| Installed combination | I4 pytest | Reviewer cases | Original I2/I3 probes | Original Access smoke |
| --- | ---: | ---: | --- | --- |
| Direct wheel / 3.51.3 | 217/217 | 153/153 | Exit 0 / 0 | Exit 1, Transfer preflight |
| Direct wheel / 3.53.1 | 217/217 | 153/153 | Exit 0 / 0 | Exit 1, Transfer preflight |
| Sdist-derived wheel / 3.51.3 | 217/217 | 153/153 | Exit 0 / 0 | Exit 1, Transfer preflight |
| Sdist-derived wheel / 3.53.1 | 217/217 | 153/153 | Exit 0 / 0 | Exit 1, Transfer preflight |

All four I4 and independent probe processes exit 0. Distribution orchestration
exits **1**, preserving the four original Access failures. The review orchestration
wrapper only records child exits; its own completion is not interpreted as a
green test result. Per-process commands, cwd, runtime measurements, logs, XML and
exit codes are retained and independently reconciled.

Both newly built wheels are 758,668 bytes, SHA-256
`18038fd72b752767557e03ccc3c06cc94a61ec7a2f0f4fa49a3ef4893517c0f5`,
identical to the Author's wheel artifacts. Public source archive SHA-256 is
`b9cf056225da357437c2d83d459d7e79a299fc9510a9d8265440a6bd0daed685`.

### I4-E1 Low complete sdist equivalence claim is too broad

**Expected:** if “distribution inputs are completely identical” includes the full
sdist, no changed input should enter that archive. **Actual:** all eight
post-execution differences enter the public sdist: the skill, evidence README,
new REPORT/index/ZIP/classification/summary, and corrected comparison helper.
The Author report's broad “packaged inputs are byte-identical” wording therefore
needs a runtime/wheel scope qualification.

Minimal reproduction: `git ls-tree f4d8c3d123552e765ef3f0ddaf4e83deaaa0e9c6 --
docs/implementation/evidence/adr0031-i4/REPORT.md` returns no entry; the same query
at public HEAD returns blob `0543869133cd56f1b1832099395cd954d249a419`. The public
sdist contains `repo_catalog-0.2.0/docs/implementation/evidence/adr0031-i4/REPORT.md`.
See `I4-E1-reproduction.json` and `sdist-input-scope.json` for exact operations.

The newly built public sdist is **65,541,415 bytes**, SHA-256
`6aa8bd0f1625cc7e353c10a6302a6336611aa021b21a5a045b81e6e5afdae09a`;
the Author-execution sdist receipt reports **60,398,202 bytes**, SHA-256
`8e8c561797762b77017c381155f4849bb661ce0056c83dbb65a6fc65e699d350`.
The actual failure boundary is archive-input equivalence, not SQL admission or
wheel behavior. Public sdist-derived runtime is independently tested above.

**Required correction boundary:** Author/evidence documentation should name
runtime/wheel inputs explicitly and retain separate public source/sdist bindings.
No product-code fix is indicated. The reviewed tree was not edited. This Low
finding remains open; there are zero unresolved I4 product defects or significant
I4 findings. It does not invalidate the bounded SQL verdict.

## I5 entry conditions and later mandatory work

I5 may proceed with the reviewed SQL contract and both fences retained. Its own
independent acceptance must demonstrate:

1. Actual Provider `transferred` semantics and the correct native contract;
   validation of original timestamp/input types before SQLite affinity.
2. Selection/permission, Provider members, mapping/referent dependencies and
   canonical complete Parent/Event references before any duplicate shortcut.
3. Permanent native-Issue mismatch versus resupplyable missing-I7 diagnostics;
   no fabricated Parent, evidence or original-bearing waiting queue, and no
   replay merely because a Parent later arrives.
4. Endpoint completeness, missing versus explicitly NULL versus truncated input,
   original independent clocks/provenance/time, and per-Transfer savepoint rollback
   on a later endpoint failure. Replays must revalidate eligibility.
5. All corresponding routing paths and tests completed and independently reviewed
   before safely replacing **both** Transfer fences. These I4 results alone do
   not authorize removing either fence or claim endpoint-set atomic admission.

Resolve I4-E1's evidence wording when maintaining the acceptance packet; do not
reuse the complete-sdist equality claim. I6 Wire remains separate with its 14
retained failures. **Task G Medium G-R1 is explicitly carried forward unresolved
and mandatory for I7:** direct `Context.candidates()` field reads can expose
Global/Scoped identification corruption before `identification()` detects it and
persists Recovery Stop. I4 does not fix or newly accept that path. Full I7 stored
validation/recovery/paired backup and activation need their own evidence. I8
Query/Search and final V1/V2 remain separate acceptance gates.

## Evidence and reproduction

The bundle contains reviewer scripts, per-case SQL/expected/actual/errors,
runtime/DDL/UDF inventories, both regression and focused logs/XML/journals,
all-79 comparisons, 301 diagnostic outputs, restoration observations, distribution
logs/measurements, wheels, build hashes and an entry-by-entry SHA-256 index.
Bulk source/sdist/unpacked trees and virtual environments remain in the workspace
and are omitted from the portable ZIP with explicit hashes/commands retained.
No omitted artifact is represented as a ZIP payload.

Use CPython 3.13, unchanged `uv.lock`, `uv sync --frozen --group dev --group docs`
and `scripts/prepare_wheelhouse.py` to prepare dependencies. Runtime compilation
argv and source URLs are in `evidence/runtime-builds.json`. Set `LD_LIBRARY_PATH`
to the selected recorded library directory for every Python process/child.

```sh
python scripts/verify_i4.py --sqlite 3.51.3 --output /absolute/new-broad-3513
python /absolute/reviewer/independent_sql.py --output /absolute/new-probes-3513
python /absolute/reviewer/run_diagnostic_observed.py /absolute/repo 3.51.3 /absolute/new-sql301-3513
python scripts/verify_i4_distribution.py --output /absolute/new-distributions --minimum-library /absolute/sqlite3513 --newer-library /absolute/sqlite3531
```

Repeat the runtime-specific commands with actual 3.53.1. For installed independent
probes, use the installed environment's Python from a cwd outside checkout with
empty PYTHONPATH. The exact executed commands are in the process receipts and
`remaining_runs.py`. The observed eight-node pytest command is likewise recorded;
its plugin only observes restoration and preserves the original test bodies.

Repository `three-store-invariants` and `lessons-to-skills` were consulted. The
reviewed skill/tree was not edited. Suggested reusable lesson: compare wheel
runtime inputs separately from the complete sdist membership whenever publication
adds evidence/documents after an execution freeze; retain both archive bindings.
This report supplies the verified counterexample and correction boundary for a
future authorized skill/documentation update.
