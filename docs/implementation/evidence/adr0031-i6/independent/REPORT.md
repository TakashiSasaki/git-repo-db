# Independent design review — ADR 0031 I6 / PR #134

**設計PASS：I6-A実装へ進行可能。** The design provides implementable,
counterexample-testable closure for I5-A1/B1/C1. New design findings: **Critical 0,
High 0, Medium 0, Low 1** (nonblocking test-plan specificity). This verdict is
about the frozen design, not permission to implement under this review task.
I6 implementation still needs its separately authorized task.

The three I5 Medium findings remain **open in the product**. No I6 product
implementation, normal Transfer activation, I7/I8 acceptance, release validation,
merge, release or deployment is claimed. Both packaged Transfer fences remain.

## Frozen scope and independence

Review date: 2026-10-23 UTC. Separate reviewer execution from the Design Author;
two read-only subsidiary reviews independently checked wire and SQL/stage scope.
The verdict incorporates fresh source inspection and our own disposable probes,
not the Author's evaluation. Subsidiary analysis is supporting input, not a claim
of independent distribution acceptance.

| Reference | Commit | Tree / branch |
| --- | --- | --- |
| Reviewed #134 Author | `418ee68046fdfd03a0e84cc840e5d52fce176b81` | `476d32923c9be5e3b60e4e17c8828e3646611c43` |
| #134 actual parent #133 | `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `6bfa580baafa9f6a117b7a0b610c4e65cd031b86` |
| Review PR base | same Author commit | `docs/adr0031-i6-boundary-contract-20261022` |
| Review branch | new branch from Author | `review/adr0031-i6-design-independent-20261023` |
| Historical #130 I5 review | `b4ede5d8a87f3ce7b1f6df8fda5b3051c3865ba2` | inherited report/findings read in full |

Live GitHub API confirmed open Draft #134, exact assigned HEAD, exact sole
parent, no published reviews, no issue/review comments, and successful `offline`
and `sqlite-policy` development checks. All remote heads were explicitly fetched;
initial all-state PR search for the requested base returned `[]`. The assignment
HEAD did not move, so there is no retarget delta to review. GitHub test-merge
`3ca6ec4dd2358c0434c7a33ad47095af338b2999` has the exact #133/Author
parents and the same tree as Author (`raw/author-test-merge.json`). API snapshots and
remote refs are in [raw](raw/). The publication commit/tree and the final live
recheck are recorded externally in the new PR body; a file cannot contain its own
Git tree hash. Development badges are not complete runtime acceptance.

Read scope includes all three I6 documents, the full original Resource handoff,
#130 report/findings, Accepted ADRs 0027–0032, the schema contract, and current
Resource identity/identification, Parent, Transfer, Exchange, acquisition,
Provider normalization, Context facade/store, SQL DDL/UDF/fingerprints,
Recovery and Query/Search sources. [MATRIX.md](MATRIX.md) records all R01–R19,
normal/adversarial cases, owners, V/T mapping and residual test obligations.

## Findings and design closure of I5 boundaries

### I5-A1 — caller authorization

**Closed at design level, open at product level.** R10 binds the facade/store to
its trusted local policy service and authenticated invocation principal; callers
cannot select a different allow-all implementation. Resource, Repository, Source,
claim and replacement permissions differ from selection. R11 checks the full
DependencySet before duplicate success, including locally existing rows. R14 also
puts cached package success behind current checks. R11's lease and writer-lock
recheck explicitly cover revocation between check and commit; actual work on
bounded restart is charged. This requires a real policy transaction/lease adapter,
not just a boolean permission callback.

The independent B-A1 probe shows the current store still has no `admission`
parameter, inserts a complete report without any local policy and returns
`duplicate` on replay. That is baseline reproduction, not a new bypass through
normal product fences. T07–09/14/26 supply the main future negative controls.
The nonblocking finding I6-L1 below makes policy-handle/principal forgery explicit.

### I5-B1 — independent original Parent evidence

**Closed at design level, open at product level.** R08 requires the exact seven
SQL key coordinates and genuine independent original time; a complete Parent row
can come from the package or authorized validated local storage. It never borrows
Event clock/provenance/time or chooses another Parent. Missing coordinates and
missing exact rows have different outcomes. Child identity remains independently
admissible. R01/R08/R15 retain the additional native-I7 typed constraint without
turning namespace coordinates into a Parent report. Lawful I8 reports survive,
but never qualify an I7-native Transfer. T02–04/15/16 cover alternatives/resupply.

B-B1 independently registers the child before I7, stores Parent 50/P/51 and Event
100/E/101, reproduces the old constructor's false missing-dependency failure,
and then admits with the explicit original Parent key. The independent Parent
time remains 51. Current constructors still synthesize defaults; future mandatory
carriers must make that construction impossible and compare original time.

### I5-C1 — original Provider endpoint declaration

**Closed at design level, open at product level.** R09 requires declaration before
filtering and exact received endpoint comparison, using the existing nine-key
scope rather than a duplicate authority. Genuine `not_reported`, explicit NULL,
Provider-only unresolved, resolved, missing and filtered states remain distinct.
Full declarations cannot be rescued by previously stored endpoint rows. R14
preserves immutable Event keys across reverse/onward/repeat delivery; later mapping
arrival cannot amend the old unresolved report or fabricate a new observation.
A coherently forged first unsigned report remains unauthenticated, as ADRs
0027/0028/0030 require; checksum correction cannot authenticate it.

B-C1 constructs an original two-sided synthetic report, drops a role before old
constructor invocation and confirms the baseline admits the surviving one-sided
report. R09/V05/T05 must reject that loss when the original declaration is carried.
This test deliberately uses a separate disposable fixture; it is not replay of a
changed payload under an already admitted original key.

### I6-L1 — enumerate local policy-handle and principal substitution tests

Severity **Low**, nonblocking test-plan gap; R10 contract itself is sufficient.
Targets R10/R11, V08 (sender permission is not local authority), T07/T08/T26.
See [findings.json](findings.json) for complete machine-readable fields.

R10 lines 296–305 requires service-bound policy handles and locally established
principals. T07 tests denied dependencies and T26 injects a deny-all trusted
policy, but neither explicitly calls the API with a context from another policy
service or a caller-chosen privileged principal. A buggy future implementation
could pass those tests while trusting `admission.authorizer` or `principal` from
the caller. Add both negative cases to T07/T26: foreign allow-all policy handle
and forged principal must fail before lookup/write, on initial admission and
exact replay; instrument the trusted service to show the substituted service
was not used. The wire sender field case is separate from direct API injection.
No production counterexample is claimed: AdmissionContext does not exist yet.

Required change: enumerate those cases in the implementation's R10 test mapping;
no accepted ADR or substantive contract change is needed. Re-review at frozen
I6-A with actual typed refusal, zero row delta, no existence leakage and exact
replay denial. This can be delivered in A; it does not require modifying #134.

## Wire, identity, finite closure and evidence semantics

R02 names exact v5 and inherits a pinned finite grammar, changing only seven
Resource columns and the two endpoint report references. R03 explicitly preserves
the existing ASCII Context JSON profile versus UTF-8 outer digest profile.
`resource_identity.encode_identity`/`parse_identity` remain the only identity
codec; there is no second wire implementation authority. R05 matches the current
four-column `ResourceIdentification` validator, including global Document repeated
ID, canonical namespace-TEXT and explicit known-contract dispatch. Known malformed
input cannot retry as opaque; unknown kinds have bounded common semantics.

R06 preserves ordered whole relation and Collection reports, not sorted/unioned
members. R07 correctly distinguishes sorted Source inventory, positive association
retention, real terminal alternatives and the existing five Coverage columns.
A late partial or withheld terminal cannot borrow prior completeness. R13 handles
finite node/edge/depth/byte/work bounds and visited sets; lawful generic cycles
register identities first and reports second. There is no native Parent walk or
Provider-wide permission expansion. R14 fixes current import's Parent-first
resource loop and Transfer-before-Parent order while preserving explicit resupply.

Our 15 wire/domain checks exercise existing canonical identity, identification,
ordered relations, terminal distinctions and sorted inventory. **No v5 codec,
new closure planner, new authorization adapter or future T01–T27 suite was run.**

## SQL, transaction and Recovery review

Current `p1_ddl/context.sql:134` retains two distinct references: full original
Parent report and native-I7 Resource/typed uniqueness. `context.sql:372` ties each
endpoint to the complete Event report. Existing immutable/pre-conflict guards and
row-local deterministic UDFs must remain; SQL does not authenticate callers or
prove whole endpoint receipt by itself.

R15/T17–18 correctly separate preflight, in-flight second INSERT and deferred
COMMIT failure. B-D1's injected second-endpoint trigger observes **one Event and
one endpoint already present**, then fails with `SQLITE_CONSTRAINT_TRIGGER`;
trace shows `ROLLBACK TO p1_transfer_event`, resulting counts **0/0** and unchanged
Parent original. This confirms the existing SAVEPOINT behavior, not future policy
rollback. The independent raw SQL deferred-FK probe shows why explicit outer
rollback matters: COMMIT returns `SQLITE_CONSTRAINT_FOREIGNKEY` while transaction
and pending counts **1/1** remain; explicit ROLLBACK restores **0/0**. Merely catching
the COMMIT exception is insufficient. R15 already requires this rollback.

Five fence-state probes reproduce the asymmetric current `has_transfer_fence`;
exact composed schema comparison detects each modified definition/missing fence.
The current facade even accepts the exact two-fence-removed synthetic schema
shape (`production_context.py:350`); this is **not** evidence that normal reopen
is already safe. R16/T19 explicitly require normal reopen refusal and trusted
fixture separation. Both packaged fence definitions remain byte-identical here.
The B-STAGE probe confirms normal store refusal with both present and zero writes.

R17/T20–22 properly require trusted reconstruction, all original endpoint refs,
native support, real terminals, Source/Coverage, source Stop and fresh paired
restore; clean FK checks alone do not qualify recovery. Current-policy revocation
alone is not stored corruption. IO/lock/budget uncertainty must not become a
fabricated corruption verdict. G-R1 remains I7 work. R18 keeps namespace filters
separate from semantic Parent and effective qualified Transfer/Search; R19 holds
both fences until reviewed C/I7/I8 and final integrated/distribution acceptance.

## Implementation entry and acceptance conditions

- **I6-A may start** from this reviewed design with existing I4/I5 ancestry.
  Introduce immutable mandatory originals/declaration and trusted AdmissionContext
  at store/facade; make every external callsite lacking context refuse before
  writes. Preserve both fences and native/full-report SQL; extend T07/T26 for
  I6-L1. Accept A only after independent A1/B1/C1 negative probes, revocation races,
  replay, real SQL rollback/COMMIT, complete fence states and installed-artifact
  checks. Normal route positives remain staged. Do not create temporary permissive
  contexts to keep old application callsites working.
- **I6-B starts after frozen non-Author A review.** Reuse existing identity codec,
  add pure exact bounded v5 codec/planner and whole terminal/Source/Coverage rules;
  normal unwired routes and Transfer remain refused. Independently test malformed
  versions/keys/duplicates, cap boundaries, cycles, seven-column roundtrips and
  full originals. A pure codec is not a permission grant.
- **I6-C starts after frozen non-Author B review.** Carry genuine Provider originals
  and declarations before filtering; connect all external routes/composition roots
  to the same guarded API, remove the legacy native-Parent registration loop and
  re-evaluate cached package replay. Demonstrate explicit isolated sender→wire→
  receiver roundtrips and normal Transfer refusal; audit every callsite.
- **I7** depends on reviewed durable A/B/C forms, trusted decoding, G-R1, Stop,
  pairing, untrusted authorized salvage and fresh activation. **I8** basic generic
  reads can follow B; Transfer interpretation waits for C/I7 and scan/Search parity.
  A later separately authorized integrated retirement must reconcile all inherited
  failure nodes and both installed distribution forms, then change both fences
  and application guards together. This review authorizes none of that retirement.

## Actual execution, omissions and remaining blockers

Environment: selected CPython **3.12.14**, actual SQLite **3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No added SQLite engine, replacement binding or version spoofing. Locked dev/docs
dependencies were installed into a disposable venv using that same Python.
The initial uv default-cache attempt failed on a read-only home; using writable
`/tmp` cache/venv completed dependency setup. This was an environment setup error.

| Newly executed check | Result / limit |
| --- | --- |
| Existing I5 typed admission + I4 SQL pytest | **246 passed**, exit 0; exact JUnit/journal/node reconciliation, 738 successful phases |
| Reviewer baseline A1/B1/C1/D1/normal stage probes | **5/5**, exit 0; intentional old boundary deficiencies reproduced |
| Reviewer existing wire/domain checks | **15/15**, exit 0; existing codec/types only |
| SQL fence-state / deferred-COMMIT diagnostics | **5 states + 1 transaction scenario**, exit 0; disposable raw SQL |
| Evidence/probe lint, format, UTF-8/links/fences/JSON and scope | actual receipts in `raw/validation.json` |

[README.md](README.md) contains commands and evidence provenance. Initial reviewer
fixture errors are preserved in `raw/harness-corrections.txt`; successful final
runs do not relabel those setup failures. Full product suite, inherited all-79
failure reconciliation, future v5 routes, policy lease implementation, normal
Transfer end-to-end, real Provider/catalog operations, I7 recovery, I8 Search and
new wheel/sdist-derived-wheel executions were **not run**. Historical #130 counts
are context only. No assertion of those paths is earned by 246 focused successes.

Remaining execution/publication blockers: **none at review completion**. No new
owner-level policy blocker found. Product carryovers I5-A1/B1/C1 and F1, G-R1,
I4-E1 remain explicitly assigned; this design review closes none in product.
Existing investigation/final-tree/lessons-to-skills procedures were used. The
COMMIT diagnostic reinforces the existing transaction guidance; no new skill is
created from one task, and no speculative implementation recipe is added.
