# Independent ADR 0031 I3 product review

**Verdict: PASS for the bounded I3 semantic Parent-report contract. Unresolved
I3 findings: 0.** This is an independent non-Author review by agent
`/root/independent_i3_review`; the reviewer did not write the product changes.
Whole-product/release acceptance remains NOT READY. This review grants no merge,
release, deployment, P8 or live-catalog authority.

Reviewed product HEAD: `61c87ced5245caf3a991592a8eb745eef7126177`.
Reviewed tree: `6f259f7239d7330bea4d1dd1b6e04c316561728f`.
Exact base: PR #125 `a54e4432b0514ba5a5fe8e73ddcdbc492f99b95e`.
The checkout remained clean and at that HEAD/tree throughout this review.
No checkout file, branch, existing PR or catalog was edited. All execution used
independently created disposable synthetic databases outside the checkout or
pytest temporary directories. Review scripts and receipts are original review
artifacts under the indexed independent evidence payload.

## Independent execution

| Execution per actual runtime | Executed | Passed | Failed | Errors | Skips | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Focused existing/new pytest cohort | 206 | 206 | 0 | 0 | 0 | 0 |
| Separately authored SQL/API probe groups | 37 | 37 | 0 | 0 | 0 | 0 |

Both SQLite **3.51.3** and **3.53.1** produced those results. The 206 cases
include the author's 65 Parent regressions plus existing schema, Coverage,
generalized Resource, explicit identification and Access isolation tests. Their
successful executions are this reviewer's runs, not inherited author passes.
The 37 independent groups include multiple assertions; nine individually
necessary full-key FK components are one group, not nine extra tests. The
cohorts overlap in requirements and are not a unique total of 243 tests.

Measured SQL source IDs:

- 3.51.3: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`
- 3.53.1: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`

The reviewer reused the prepared official-source local SQLite libraries and
independently measured version/source ID/options/pragmas in fresh processes;
this is not a claim of independently compiling SQLite. Dynamic CPython 3.13.5
actually loads the selected library. No runtime version was overridden or
spoofed. `foreign_keys=1`, `recursive_triggers=1`,
`ignore_check_constraints=0`, `defer_foreign_keys=0` and `trusted_schema=1` were
measured in both probe lanes. The deterministic Parent UDF flag and arity were
also recorded.

The reviewer independently built a direct wheel and an sdist-derived wheel from
a fresh `git archive` of the reviewed commit, installed them into four fresh
outside-checkout environments and executed the independent 37-group probe on
each runtime/artifact combination. All four produced 37/37 successful groups
and exit 0. All **154 installed package files per combination** were independently
hashed and matched the archived source. Both wheel variants have SHA-256
`6a7b792407d6403929b444d8dec5ae1115aa6ccb33484418b36feebae05421d6`.
The sdist SHA-256 is
`b02de0d3ddbc84092fb3e37b8994172420b96d26709c2ba397b36dc6a408f781`.
Source, build commands, artifacts' hashes, installed origins and per-file
manifests are recorded. Distribution binaries and synthetic databases are not
part of the public review payload.

## Contract assessment

- **One authority and independent child identity.** Only `resource_relations`
  owns Parent evidence. The five added columns are virtual generated
  projections, not independently writable facts. The Context table set, Resource
  PK/identification contract and other store fingerprints remain unchanged.
  Independent tests register a child with no Parent, reject its report with
  SQL FK error 787, add the Parent without recreating evidence, then resupply
  the unchanged original report successfully. No queue or hidden payload is
  introduced.
- **Complete reference and null handling.** The existing seven direct report
  PK coordinates preserve whole members/provenance/scope. The nine-component
  typed index adds generated source subtype and Parent kind. Independent
  consumer references reject a change to each individual component with FK
  error 787. Global Document scope explicitly selects `document_kind:null`,
  whose non-NULL `''` projection reaches the real four-column source FK.
  Scoped/global source-type substitution fails. NULL/missing members and
  subtype omission cannot disable a typed reference.
- **Original evidence and conflicts.** Complete original clock/provenance and
  unknown original observation time survive. Distinct Parent, clock or
  provenance alternatives remain separate. Original-time rebinds through
  IGNORE, DO NOTHING, REPLACE and no-op UPSERT fail with trigger error 1811,
  including NULL-to-positive and positive-to-NULL changes. Rejected operations
  preserve complete authoritative rowsets. Statement/multirow, savepoint and
  transaction rollback controls pass.
- **Admission and reads.** `Context.relation()` checks selection, permission,
  complete report shape, stored identifications and dependencies before replay
  shortcuts. Independently repeated admitted reports are idempotent, and a
  changed permission or selection rejects replay without side effects. Reads
  reconstruct all original competing reports and validate their selected
  Parent dependencies. Known scoped Parent-kind restrictions are preserved;
  namespace ID is not a general Parent-ID equality rule.
- **Documents and I8.** Global and PR-scoped Documents, a Document as Parent,
  unknown child kinds and nonleaf graphs succeed. A complete I8 Issue Parent
  report for an Event natively identified under absent I7 is lawful stored
  evidence. The separate Transfer report is still refused. No native-I7
  Transfer eligibility follows from that stored I8 row.
- **Bounds and registration.** The new row-local predicate uses the established
  bounded canonical parser and strict Resource codec. Excessive depth/size,
  raw/noncanonical/decoded identity values, malformed provenance, boolean
  clock values and incomplete or extra scope fail. Typed construction checks
  its Parent input before the generic JSON decoder. Shared factories register
  the deterministic UDF and connection verification requires it. Installed
  execution verifies packaged code/DDL/fingerprint consistency.

## Boundary and evidence audit

Independent byte and schema comparisons confirmed both Transfer fences are
unchanged. There is no I4 native-I7 Transfer SQL or I5 typed Transfer Admission
implementation in this delta. No Parent table, surrogate, mutable winner,
new Source/Coverage claim or cross-store authority was introduced. Core,
Operational, Search, Coverage DDL and Resource identification/identity/stage
modules match the exact base. The Source known-positive/Coverage/schema and
Access isolation tests in the independent cohort pass. The new exact-path
isolated-module registration retains detection of accidental public-runtime
imports; it is not a broad exclusion. The changed reusable skill accurately
records the verified SQL projection, null-reference, conflict, runtime-selection
and isolation-check procedures without granting new authority.

Independent schema/fingerprint/callsite/registration and lint/format commands
all exited 0. The author broad JUnit/selected-node receipts were independently
compared against retained Task G originals: both lanes retain **all 2,826 old
selected nodes**, add exactly 65 Parent tests and retain the same **79 original
non-success node/phase pairs** with zero additional non-successes. No existing
test lines were removed or converted to skip/xfail in this delta. The reviewer
did not rerun the 2,891-node broad cohort; its 2,812 pass / 59 fail / 20 error
counts remain author evidence, with independent receipt comparison only.
Likewise the existing 301-group SQL diagnostic and original Access smoke were
not rerun by this reviewer. The independently authored installed probe and
source/file checks above are separately measured review evidence.

The remaining broad first-boundary failures are 45 call failures plus 20 setup
errors at staged Transfer support (I4/I5), and 14 I6 wire call failures. Later
assertions beyond those refusal/failure points and 2,541 unselected ordinary
nodes remain unexecuted in the author's bounded cohort. I3 resolves zero of
those original staged failures; its separate Parent contract is now implemented.
No aggregate whole-product green result is inferred.

**G-R1 remains an explicit I7 follow-up.** Direct FieldCandidate reads are not
proven to stop on corrupt Global/Scoped identification. Parent-specific reads
and stored Parent checks do not establish full Recovery, salvage, paired
backup/restore or activation guarantees. This reviewer did not retest G-R1 or
claim it fixed. I6 generalized Exchange, full I7 Recovery including G-R1, and
full I8 query/Search remain separate. Caller-provided local selection/permission
checks do not prove I6 wire permission routing or Provider authenticity.

## Reproduction and limits

`run.py` executes the 206-node cohort twice. `probe.py` is the independent SQL/API
probe, and `probe-runner.py` selects/measures both actual libraries. `package.py`
rebuilds from the exact reviewed Git archive and runs that probe in all four
installed combinations. `audit.py` independently checks the source/schema and
retained broad receipts. Command arrays, stdout/stderr, JUnit, detailed errors,
full alternative rows, runtime facts, input hashes and installed-file manifests
are indexed alongside this report. Dependencies come from the unchanged project
lock; no live Provider operation is needed.

This bounded PASS is neither exhaustive SQLite-engine proof nor a full product,
release, hosted-CI or host-power-loss qualification. The reviewer reused the
prepared dependency environment and SQLite binaries, independently executed its
own tests/builds and left all product inputs untouched. No material I3 finding
requires a correction or another product freeze for this review.
