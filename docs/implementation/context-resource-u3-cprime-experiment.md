# Context Parent relations without new authority tables: SQLite experiment

**Historical bounded result:** this report remains bound to its original freeze.
The [semantic-coverage follow-up](context-resource-u3-cprime-semantic-gaps.md)
corrects G1/G2 and identifies an unresolved G3 owner question. The current
candidate has a new freeze; this original verdict is not a broader ADR 0031 pass.

**Verdict: DEMONSTRATED for the stated bounded experimental obligations on
SQLite 3.51.3 and 3.53.1**, with the enforcement division below. Independent
review reproduced the corrected result. This is not a claim that SQL alone
establishes event semantics, full-unit admission or Provider authenticity.

The corrected C′ candidate allows a complete Timeline Event Resource before its
Issue, then requires an admitted, exactly identified typed Parent report for a
Transfer. It uses the existing composed Context tables, real composite FKs,
generated projections, row-local CHECKs and immutable-payload triggers. The
mandatory semantic Parent FK is removed from Resources in the experimental copy.

This is feasibility evidence, not product implementation, a migration, release
acceptance or owner approval. [Reproduction/evidence](evidence/context-resource-u3-cprime/README.md)
provides one command. [Design Draft #114](https://github.com/TakashiSasaki/git-repo-db/pull/114)
is a related document, not an imported code dependency. Neither that branch nor
[audit #113](https://github.com/TakashiSasaki/git-repo-db/pull/113) was modified.

## Exact inputs and runtimes

| Input | Identity |
| --- | --- |
| Frozen product baseline and freshly inspected main | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` |
| Product tree | `117d580b31098ecb8287281bd843894fdfad71fc` |
| First experimental freeze | `2f40e5262c6ccdb776b9f82fcba33d42c323a4e8` / tree `ae711e0b6fb24423259f7ddea6760096e84c9376` |
| Corrected executable freeze reviewed independently | `e9aba86f4530b2e683c77e23a4fe58bdf02192c5` / tree `7db7773f4cc2860b3818856b048a5832cdb00d6b` |
| Corrected composed SQL SHA-256 | `c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee` |
| Validator/constructor `cprime.py` SHA-256 | `c0405569a9b878031e34aa3c41ae2239d09d6d715fdec29de9bc4fa62a9c0061` |
| Author harness `run.py` SHA-256 | `12dfaee585ebe67c846e446594ae926f90191a282e22768c876dfa4a78d091b3` |
| Aggregate executable-input manifest SHA-256 | `866c1a521bafac657aba63a6662ea46b3a12f36aa70b5643f4553c99cb837c96` |

[Source bindings](evidence/context-resource-u3-cprime/results/source-bindings.json),
[source/contract map](evidence/context-resource-u3-cprime/contract-and-source-map.md)
and [final input manifest](evidence/context-resource-u3-cprime/results/input-freeze-final.json)
give the full provenance. Main had no difference from the frozen baseline.
The source review verified `MIN_SQLITE = (3, 51, 3)` rather than assuming it.

| Executed lane | Python | Actual SQLite | `sqlite_source_id()` |
| --- | --- | --- | --- |
| Genuine minimum | 3.13.5 | 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| Newer supported | 3.12.14 | 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Full compile options, pragmas and dependency inputs are in the machine receipts.
The minimum library was built from the hash-pinned official SQLite archive
outside the repository; no version check was spoofed. Both production baseline
and experimental factories enable `foreign_keys=1` and `recursive_triggers=1`
before transactions, including reopens. Candidate constraints are immediate.
The supported candidate uses `synchronous=EXTRA`; in-memory cases report journal
mode `memory`, while the actual packaged baseline initializer uses WAL.

The author executed the exact added/modified input bytes before freezing their
commit, so the receipts record the prior Git HEAD plus input hashes. Independent
review executed a detached checkout of the corrected freeze. Later reports and
the procedural skill addition are not represented as another candidate execution.

## What the candidate changes

The [structural comparison](evidence/context-resource-u3-cprime/results/structural-diff-v2.json)
finds the same 19 table names. Only `resources`, `resource_relations`,
`resource_repository_relations`, and the existing typed Resource index differ;
one full-key index and five guards are added. Coverage still has exactly five
columns. Other existing schema objects, including six-role maintenance triggers,
are unchanged. No Parent, Mapping, Witness, Event-header or history table exists.

Resource identification namespace columns are consistency-checked against the
known document identity, but have no FK to a Parent Resource. They preserve
native identification coordinates without asserting a semantic relationship.
The reserved singleton `parent` report stores its full original member list,
provenance, scope and clock in `resource_relations`. Generated columns project
its actual target ResourceKey and typed document contract. Real FKs require both
the target Resource and typed source Document.

The existing `transfer_event_report` group retains the whole report. Its scope
includes the exact Parent members, scope and provenance and the complete endpoint
declaration. Parent and Transfer clocks, provenance and observation times can
remain independent. Endpoint rows reference the complete Parent key and the
complete existing event-report key; generated typed properties require
`timeline_event` and `issue`. No `UNIQUE(event)` or `UNIQUE(event,parent)` removes
attributable alternatives. Full semantic reference width is accepted rather than
replaced by an opaque relation identifier.

The [candidate notes](evidence/context-resource-u3-cprime/candidates/README.md)
describe bounded deterministic predicates and synthetic identity contracts.
No UDF queries the database or looks up external state. Generic SQL does not
decode an arbitrary Provider ID to infer Parent semantics.

## Exact feasibility obligations

| Obligation | Executed result and enforcement boundary |
| --- | --- |
| 1. Complete E9 before I7 | E9 commits without I7. Known native document coordinates remain complete; no Parent row is invented. |
| 2. Typed E9→I7 report waits for actual referents | Real target and typed source FKs reject missing referents. I7 arrival alone creates no report; actual original report re-supply succeeds. |
| 3. Transfer references the appropriate admitted typed report | Real full-key FKs require the exact Parent and event-report groups, including independently attributed support. A bare Issue row is insufficient. |
| 4. Wrong Event/kind/namespace, absent support and incomplete coordinates fail | Direct SQL reaches actual FK or CHECK errors. Explicit non-NULL guards close SQLite composite-NULL bypasses; immutable replay guards run before conflict handling. |
| 5. Actual event semantics remain typed admission | The experimental typed boundary rejects `event_type='closed'`. Deliberately fabricated, internally consistent SQL can pass structurally; no authenticity claim follows. |
| 6. Alternative attributed reports survive | Multiple Parent targets and independent reports for the same target persist, including competing same-Event reports. Each dependent unit names exact support; no winner is inferred. |
| 7. Identity, original clock/provenance and atomic grouping survive | Exact replay preserves rowsets; changed payload is rejected. One-sided groups stay one-sided; selected cuts are withheld. Typed admission savepoints preserve whole-unit atomicity, including second-endpoint FK failure. |
| 8. No new authority/surrogate/hidden Resource Parent | Same 19 tables, no Resource Parent FK, no relation UUID/hash/rowid identity. Identification coordinates and dependent composite references are not independent Parent authorities. |

“Appropriate” in the structural result means the exact supplied typed support
report, not a policy determination that it defeats another report. Which
competing report currently qualifies for an operation remains separate evaluation
work; neither time nor arrival order selects a winner here.

## Required matrix and actual evidence

The corrected author harness executes **15 grouped cases with 163 recorded
steps on each runtime**. Those groups cover T01–T12, with T02/T03 combined,
two groups each for T05, T09, T11 and T12. Collected and executed IDs match exactly.
[Current results](evidence/context-resource-u3-cprime/results/author-current-v4/results.json)
and [minimum results](evidence/context-resource-u3-cprime/results/author-minimum-v4/results.json)
retain SQL traces, exceptions, transaction state, rowsets and checkpoints.

| Family | Demonstrated scope |
| --- | --- |
| T01 | Recursive string arrays; huge decimal strings; exact replay; Unicode/case/whitespace/order distinctions; distinct genuine empty values; numeric/bool/object/null/SQL NULL/malformed/noncanonical rejection; known document checks |
| T02–T03 | Child-before-Parent, withheld relationships/Transfer, descriptive fields absent versus missing Resource, no automatic promotion, original report re-supply and exact deduplication |
| T04 | Missing/wrong Parent, wrong namespace/Event, ordinary Comment, absent exact support; real FK failures distinguished from syntax rejection |
| T05 | Exact endpoint membership, one-sided report, immutable whole-report scope, original nullable time, independent Parent attribution/clock and cross-pair rejection |
| T06 | Four retained competing Parent reports and explicitly linked Transfer alternatives, without broad uniqueness or a derived winner |
| T07 | Partial/all-NULL fields, missing projection, malformed keys, zero/multiple singleton members, wrong JSON/canonicalization; separate raw CHECK(NULL) and partial-NULL FK controls |
| T08 | UPDATE/DELETE/REPLACE/IGNORE and UPSERT actions; immutable Resource/report/endpoint payload comparison before ignored conflicts; unchanged rowsets on rejection |
| T09 | Immediate-FK order, statement failure, transaction rollback/commit, reopens and required pragmas; separate unsupported FK/recursive-trigger disabling controls |
| T10 | Ordered multi-member groups, absent/unknown/empty/partial/complete distinctions, Collection terminals, a nonleaf Document and a generic cycle |
| T11 | Experimental selected reconstruction, missing Parent/support/member withholding, no group shrinking, unknown-kind preservation with unselected resources excluded, original replay and disposable snapshot rowset equality |
| T12 | Direct supported SQL cannot hide missing typed references behind Python validation; actual event semantics remain an explicit typed boundary, without external authentication |

Nine separate baseline controls per runtime first verified the real packaged
19-table schema and current Parent/Transfer constraints. Baseline SQL can admit
a structurally typed endpoint without a whole Transfer report; its application
boundary checks that unit. These baseline controls, prior #113 tests, repeated
driver executions and reviewer tests are not added to the author's distinct
case count. All supported-state FK/integrity checkpoints are clean. Deliberate
misconfiguration produces recorded violations and is not labeled a clean database.

## Enforcement matrix

| Layer | Actual responsibility |
| --- | --- |
| FK | Parent target and typed source existence; exact full Parent support; exact event-report reference; existing Repository endpoint registration |
| CHECK + generated projection | Canonical recursive identity; complete known document coordinates; typed singleton structure; mandatory non-NULL support; endpoint declared in that exact report |
| Trigger | Immutable UPDATE/DELETE/REPLACE protection; original observation time; same EventReportKey whole payload; all added non-key reference/identification fields compared before conflict-ignore |
| Typed admission + savepoint | Actual normalized event type; complete supplied endpoint set; atomic whole-unit writes/rollback; validated exact replay |
| Application selection/dependency checks | General arbitrary-length member referents, explicit selected closure, whole-group withholding without durable staging |
| Evaluation | Current qualification of conflicting attributed reports; no stored winner, authentication or verification-history authority |

Direct SQL can insert a whole-report declaration before all endpoint rows exist;
there is no reverse endpoint-set FK or COMMIT hook. The typed unit boundary must
admit and validate the full unit. General multi-member array referents likewise
retain their application checks. These limits are not relabeled as SQL FKs.
The final typed helper also requires every declared Provider Repository member
to exist and calls the unchanged baseline `validate_observation_us` on the report
and supplied endpoints before equality/replay comparisons. SQLite INTEGER
affinity alone cannot reject the original Python `True`, `100.0` or `"100"` input
after coercion; explicit negative controls demonstrate this division.

## Failures retained and corrected

1. Development 01 retained fixture/expectation errors rather than claiming a
   complete passing run.
2. Development 02 found an actual candidate failure: changed non-key endpoint
   support could be ignored by `ON CONFLICT DO NOTHING` before FK validation.
   A BEFORE INSERT immutable-payload guard fixes it. The exact failed SQL,
   validators and harness remain, and a [fresh replay](evidence/context-resource-u3-cprime/results/failed-replay-check.json)
   reproduces both the actual gap and the separate fixture error-precedence issue.
3. Independent first review found unnecessary Parent/Transfer clock/provenance
   equality and silent Resource non-key metadata ignore. The corrected schema
   carries explicit independent Parent provenance, preserves its original scope
   clock, and compares Resource immutable payload before conflict handling.
4. Independent second review found two application-boundary gaps: declared
   Provider Repository members were not checked for existence by the Transfer
   helper, and coercible original timestamps reached SQLite. The final helper
   withholds missing-member units inside its savepoint and uses the existing
   strict observation validator before comparison/write. Actual member arrival
   does not manufacture a report; the original data must be supplied again.

These final helper corrections do not change candidate SQL or the row-local
validator from the second freeze. The preserved [second review](evidence/context-resource-u3-cprime/independent-review/round2-review.md)
labels that intermediate result PARTIALLY DEMONSTRATED and distinguishes the
application gaps from the already working typed FKs.

The [first review](evidence/context-resource-u3-cprime/independent-review/round1-review.md)
and its receipts remain bound to the first freeze. No failed run is rewritten
as success, and no limited failed candidate is called proof that C′ is impossible.

## Independent review

A separate reviewer, who authored neither candidate nor author/baseline harness,
read the task and accepted constraints, used detached checkouts of each frozen
commit, verified all executable hashes, and reran the full driver on both real
runtimes. The final review covers freeze
`e9aba86f4530b2e683c77e23a4fe58bdf02192c5`.

The reviewer independently wrote and ran **75 checks on each runtime**, including
NULL/complete-key FKs, independent attribution/clocks, cross-pairing, immutable
conflict verbs, general groups, strict original-time types, missing declared
Provider members and late resupply. The actual first-endpoint-success then
second-endpoint-FK-failure case rolled back the report and both endpoints while
retaining the independent Event/Parent facts. All four first/second-round findings
are closed in the corrected experiment; their original receipts remain intact.

[Final review](evidence/context-resource-u3-cprime/independent-review/final-review.md)
records the reviewer's own DEMONSTRATED verdict, exact input binding and limits.
The reviewer's 75 checks overlap the author's 15 grouped scenarios/163 steps;
they are **not summed**. The reviewer also checked the procedural skill addition
as prose outside the executed input freeze. An initial reviewer expectation of
ValueError instead of the baseline validator's TypeError is retained separately
as a reviewer-fixture issue, not relabeled a candidate failure or silently erased.

## Publication scope and remaining work

This experiment does not implement product writers/readers, generic Provider
adapters, product Exchange, integrity validators, or paired backup/recovery for
the candidate. Their unchanged exact-fingerprint gates still expect the baseline.
The T11 harness is explicitly experimental Context-only reconstruction/snapshot
evidence. No live Provider semantics, authenticity, hostile file/DDL replacement,
power-loss durability or production performance claim is made.

No new architectural decision has been demonstrated necessary for the structural
construction. The review corrections were engineering changes within C′. A later
implementation must carry these guarantees across product admission, selection,
validation and recovery, and must not invent a semantic winner among competing
Parent reports. This experiment does not accept proposed ADR 0031 or allocate an
ADR, activate P8, or authorize implementation/merge.

Product `src/`, packaged DDL and fingerprints, dependencies, existing tests,
workflows, accepted ADRs, default runtime, main and real catalogs are unchanged.
No live Provider account data, Provider credentials or real catalogs were used.
Only experimental artifacts and a procedural replay lesson in the existing
[invariants skill](../../.agents/skills/three-store-invariants/SKILL.md#verify-immutable-replay-before-conflict-ignore-handling)
change. The investigation, invariant and lessons-to-skills procedures informed
the work; the skill addition creates no policy or product behavior.
