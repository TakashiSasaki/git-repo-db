# G3=A: bounded native-Issue Transfer SQL proof

This is a disposable experiment for the owner's explicit **2026-10-21 G3=A**
decision. It is not production implementation or acceptance of ADR 0031.
The ADR remains proposed, its acceptance date null, and PR #114 Draft.
The native Issue I7 is the semantic Issue of the reserved Q-S10 Timeline Event.
An attributed I8 Parent report remains valid retained evidence; a Transfer using
it for this Event is permanently ineligible. Missing original I7 support is a
retryable dependency and requires resupply of the original report after arrival.

## Inputs and provenance

`candidates/` and the helpers in `harness.py` derive from the externally inspected
F2 freeze **9eeacb28f7e4a426114a9ce40e2324b4da302817** in PR #115.
`run.py` contains only the new focused GA01–GA11 cases. No old F2 result is reused
as a result of this experiment, and no old experiment/review/receipt is edited.
The original F2 SQL hash is
`2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f`.
The new receipts bind their own composed SQL, executable file hashes, input
commit/tree and unchanged product `src` Git tree separately.

The F2 `QualificationRequired` boundary is historical. This experiment replaces
it with typed `Qs10Violation` and `DependencyMissing` outcomes. It does not change
the historical F2 files or reinterpret their structural-I8 SQL success as failure.
`build-minimum.sh` is a byte-identical copy of F2's reproducible build procedure;
the newly recorded execution is fresh, using its pinned archive hash, rather than
reusing an old runtime receipt. It changes no repository dependency setting.

## SQL construction and connection contract

The schema is composed over the unchanged packaged Context DDL. The experiment
changes only its disposable Resources and Relations sections and existing
Transfer projections/constraints. The actual composed table count is measured
as **19**, not promoted to an absolute future invariant.

- `resources_native_event_fk` is a BINARY/default-collation UNIQUE index on
  `(ResourceKey, reference_document_kind, identifier_namespace_kind,
  identifier_namespace_id)`. `cp_resource` necessarily executes as a SQL CHECK
  and establishes that namespace metadata agrees with the canonical Identity.
- Event reports derive quoted Parent service/kind/Canonical ID solely from their
  existing `parent_members_json` support payload. The mandatory SQL predicate
  requires that kind to be `issue`. All required FK projections are
  explicitly non-NULL; projected service must equal the Event's service.
- The new composite FK links the same Event's `timeline_event` subtype and
  `issue` namespace/native ID to that quoted Parent. The existing complete
  ParentReport FK remains. Endpoint FKs still quote a complete Event report.
  The wider index is not another independent Parent source of truth.
- General Parent reports have NULL Transfer projections, so no universal native
  namespace equality is imposed. Resources still have no Parent-existence FK.
- Generated columns cannot be written independently. BEFORE INSERT rebind guards
  run before IGNORE/DO NOTHING uniqueness shortcuts; immutable UPDATE/DELETE and
  recursive-trigger REPLACE guards retain original Resources/reports/endpoints.
  Genuine normal replay validates first and deduplicates exact original bytes.
- Parent reports and Event reports preserve independent original provenance,
  clocks and `observed_at_us`. Endpoints must retain the clock, provenance and
  observation time of their own complete EventReportKey.

Every normal connection must register baseline `p1_schema` UDFs and the bounded,
deterministic `cp_identity`, `cp_resource`, `cp_relation`, `cp_endpoint`, `cp_get`
functions, then set/verify `foreign_keys=ON`, `recursive_triggers=ON`,
`ignore_check_constraints=OFF`, `defer_foreign_keys=OFF`, and `trusted_schema=ON`.
The last is required because Python UDFs are not tagged SQLITE_INNOCUOUS.
`synchronous=EXTRA` is selected too. Receipts record actual PRAGMAs, compile
options, source ID, version and Python. No UDF searches another table or performs
an external lookup. Predicate UDFs return 0 on malformed input, so CHECK's NULL
pass-through does not make malformed canonical values valid. Those mandatory SQL
UDFs differ from `admit()`, which direct-SQL cases never call.

## Enforcement and case map

| Cases | Executed boundary |
| --- | --- |
| GA01 | E before I7; retain/read I8; actual direct-SQL FK error; permanent Admission rejection; qualified I7 succeeds without deleting I8 |
| GA02 | Missing I7 row/report is dependency; arrival performs no automatic replay; original resupply and exact replay |
| GA03 | Complete-key mixing across Event/service/real report elements rejected; explicitly quoted whole alternative report succeeds; independent Parent/Event origins, clocks and times retained |
| GA04 | NULL/missing/malformed Canonical support and Identity, wrong kind/subtype/native namespace, metadata inconsistency, independently written generated projection rejected |
| GA05 | UPDATE/DELETE/IGNORE/DO NOTHING/REPLACE/UPSERT cannot invalidate or rebind Resources, Parent reports, Event reports or endpoints; normal replay is idempotent |
| GA06 | Admission rejects actual non-Transfer event, missing declared Provider member, wrong original time type/range, truncated endpoints; second endpoint FK failure rolls back its entire unit while E/Parent remain |
| GA07 | Explicit SQL limitation controls: stored structurally valid rows do not authenticate actual Provider event type, and INTEGER affinity does not prove original input type; Admission revalidates stored replay |
| GA08 | General namespace differs from Parent; independent Documents and children; unknown kind; genuine empty Identity; single G2 Parent-ID TEXT profile; known PR no-fallback |
| GA09 | Disposable reconstruction/snapshot/reopen controls keep dependency/resupply and permanent-I8 validation; no stored row or validated flag grants Admission success |
| GA11 | Genuine complete one-sided report and explicitly reported NULL endpoint remain admissible with independent NULL observation time; no absent role is invented |
| GA10 | Eligible direct SQL report/endpoints COMMIT; raw caller can commit partial multi-statement work after one endpoint fails, explicitly demonstrating absence of arbitrary-SQL whole-unit guarantees |

SQL proves these structural contracts under the stated connection configuration.
It does not authenticate Provider information or prove actual external event type,
original input time types, arbitrary-length declared-member existence, necessary
endpoint completeness, or whole-unit atomicity. Typed Admission checks those
conditions and wraps report/endpoint writes in one savepoint. The GA06 second
endpoint failure demonstrates its rollback; GA10 deliberately distinguishes raw
SQL's statement-level guarantees. A fake structurally coherent `closed` event
can be persisted by direct SQL in GA07 but never accepted by normal Admission.

## Reproduction and limits

Provision an external genuine minimum runtime if needed:

```sh
sh docs/implementation/evidence/context-resource-design/g3-a/build-minimum.sh /tmp/g3-sqlite-runtime
```

Then run both interpreters against the same frozen files, using a new output:

```sh
G3_MIN_SQLITE_LIB=/tmp/g3-sqlite-runtime/minimum/lib \
  sh docs/implementation/evidence/context-resource-design/g3-a/reproduce.sh /tmp/g3-rerun
```

Each receipt includes case IDs, real SQLite error name/extended numeric code,
executed SQL trace, pre/post rowsets and transaction state; explicit BEGIN,
COMMIT and ROLLBACK steps remain visible. Final integrity/FK checks supplement,
rather than substitute for, actual rejection statements. The two runtimes run
sequentially; no benchmark comparison is claimed.

I6 production generic Relation/Collection/Selective Exchange and I7 production
stored-data validation/paired Backup/Recovery were not implemented or executed.
They must validate original typed units on replay/import/recovery and refuse
ineligible Transfers despite retained rows or sender/local checked flags. I8
query/Search Transfer consumption, integrated runtime, default-runtime behavior,
isolated wheel and sdist-derived wheel/fingerprint validation remain future
implementation acceptance. This Context-only harness/snapshot is not a substitute.

## Frozen execution results

Author input freeze: `4c07cb8ecc4d744ddfb8c3908deb91d8ad72f6f9`, tree
`e171de9f2459b0ade409bebb40787b850d88ff5e`.
Composed SQL SHA-256:
`ee8618874d061b8fc71bf83be94a10b1d009d7d1859ddd145e560c7755c41cd0`.
The [author summary](author/summary.json) and [receipt guide](author/README.md)
record **11/11 groups, 292 steps and zero failed groups per runtime** on genuine
SQLite 3.51.3 / Python 3.13.5 and SQLite 3.53.1 / Python 3.12.14. Counts overlap
and are not summed. Each recorded 77 actual SQL errors, including the I8 direct
SQL `SQLITE_CONSTRAINT_FOREIGNKEY` extended code **787**, with unchanged
pre/post rowsets and explicit rollback. SQL constraints and Admission outcomes
remain separate in the per-step receipts.

These receipts bind the frozen inputs; later evidence/status-only publication
is not represented as another executable revision. Independent final review
and its own major-counterexample executions are recorded separately below.

## Independent review and readiness

**READY FOR OWNER DESIGN ACCEPTANCE.** A separate non-author performed
[SQL/Admission review and independent execution](independent-review/final-review.md),
authored 99 observations on both actual runtimes, and separately repeated the
11 author groups / 292 steps. The same I8 fixture commits through F2's exact
structural SQL but fails through the new native-I7 FK with extended code 787.
Composite and genuinely empty native Issue positives retain the scoped rule.
A second non-author performed [documentation and evidence-pin review](independent-docs/review.md).
No blocking/substantive finding remains. Counts overlap and are not summed.

The exact executable/design freeze is stated above. Later status, links and
receipt-only additions are separately reviewed and bound to unchanged input
hashes. This recommendation asks for the owner's decision on the entire ADR;
it does not change proposed/date-null status or authorize implementation.

Final factual/status/transport delta was independently rechecked at publication
candidate `6bc9525ab853344fba309b28aee343250f575738`, tree
`97efebce12fcf1ff45ddd336e60d59c14d5e8dfb`: [SQL reviewer recheck](independent-review/final-delta-review.md)
and [documentation reviewer recheck](independent-docs/post-freeze-review.md).
The resolved intermediate review-file manifest hash issue is recorded explicitly;
all current stored/raw hashes match. Original executable inputs remain unchanged.
Subsequent additions contain only these review/check receipts and factual links,
not another executed or materially revised design.
