# ADR 0031 I2 product implementation — Task E

This is an owner-authorized **Author implementation**, based on Task F #123
`c1b62d216db2b728a4c8cb1821250335fcafc534`, tree
`9e970f71b27d8d1c8cec3971cbca8690edb27da1`. Task F's verdict is
**READY WITH CONDITIONS** for implementation, not product acceptance. The
reviewed C-F1 design is #122 `2199a882d79c9c707fffcba3a8327ef96a3fc384`.
The dependency stack includes #120, #121, #118 and #117; #119's sibling independent
I1b review is a read-only reference, not a missing product dependency.

## Implemented contract

`ResourceKey` and its three-component equality/PK remain unchanged. The new
immutable `ResourceIdentification` binds four non-key columns to that same key.
Document/review/thread/comment admission requires an explicit declaration even
on replay. Unscoped kinds use the all-NULL contract. Factories take actual native
coordinates; stored decoding validates every column. Global/scoped declarations
are never inferred from key shape, factory flags, arrival or equal-key retention.

Packaged Resources now admit open service-scoped kind names and strict canonical
scalar/recursive-array identities. The existing I1 codec supplies bounded SQL
predicates. Native local IDs are stored as canonical identity TEXT; complete
children need neither a namespace Resource nor a Parent report. There is no
Resource self-FK. `resource_relations` remains the sole semantic Parent authority.
The generated non-NULL subtype projection and exact BINARY 4/5/6-column UNIQUE
targets are packaged with both Transfer fences and regenerated fingerprints.

All normal factory/expected-schema connections use the required deterministic
UDFs and verified FK/recursive-trigger/CHECK/defer/trusted-schema profile. Recovery
validation connections register/configure the same trusted contract before
evaluating packaged checks. No recovered SQL is executed by these changes.

Provider observations carry actual adapter declarations; Resource hierarchy
registration no longer parses keys to manufacture namespace Resources. Query
returns `identification` and `identifier_namespace`; the old semantic `parent`
filter explicitly refuses pending I3. Search continues to use exact Resource
triples and checks staged authority before extracting projections.

## Task F conditions mapped to implementation and tests

| Required condition | Product implementation | Acceptance evidence |
| --- | --- | --- |
| Coherent DDL/UDF/index/fingerprint/configuration unit | `p1_ddl/context.sql`, `p1_schema.py`, `resource_identification.py`; active schema/callsite inventories regenerated | `test_generalized_resources.py`; `verify_i2_sql_counterexamples.py`; installed `verify_i2_distribution.py` |
| Typed/generic Transfer refusal before writes/replay | Reference/production Context, normalized Provider units and batch preflight; exact reserved names | Empty-store typed queries, SQL conflict/no-op/poison controls and real Provider residual nodes |
| Selected atomic import preflight | Real decoded receiver selection is checked before dependency rewriting, package replay/binding or Core/Context admission; direct Context import also checks | Rechecksummed mixed-order endpoint/Provider-only imports, primed package replay, independent Core-only selection |
| Explicit consumer refusal and Stored Invariant stop | Typed Transfer query/export refuse even on empty catalogs; matching-schema impossible report/endpoints enter ADR 0026 stop before ordinary Context/Query/Search/export exposure | Poisoned matching-schema fixtures, retained rowsets, recovery validator and absence of input-caused stop |
| Preserve fences until coherent reviewed replacement | Both report and endpoint INSERT fences plus immutable UPDATE/DELETE guards remain unconditional | Task D literal and Task F's 301 SQL groups against product DDL; no routing-model cases counted as product SQL |

Known document declarations cannot travel through the current Exchange v4 wire.
Selected affected Context units explicitly raise
`I2_IDENTIFICATION_WIRE_UNSUPPORTED` before authority effects. No old-wire
translation or metadata guessing is added. Independent Core-only selections
remain supported. Exact reserved Transfer names raise `I2_TRANSFER_UNSUPPORTED`;
case/whitespace/NUL variants remain opaque BINARY names. Metadata text containing
a reserved word has no operation semantics.

Supported Context units retain savepoint rollback. Tests include a late real FK
error and a real SQLite COMMIT authorization refusal, alongside direct SQL caller
savepoint/statement controls. These do not establish crash/power-loss behavior.

## Existing test preservation and mechanism mapping

No existing test is deleted, skipped or xfailed. Existing Transfer-success and
dependent Exchange tests retain their assertions and can fail at the explicit
I2/I6 boundary; they are not reclassified as passes. The four Task A Event nodes
are included in the unchanged broad selection and their first exceptions must be
reported separately from the new persistence/refusal tests.

The following accepted mechanism replacements retain their original nodes:

- P1 `test_children_have_real_parent_and_document_kind_coordinates` and its P3
  port reuse retain PR/subtype/local disjointness and malformed-row rejection;
  the old Resource Parent-existence assertion becomes complete child-first
  admission with zero inferred reports. The new generalized tests exercise this
  for global and recursive native IDs too.
  The old Parent-FK suffix of `test_counterexample_4_invalid_roles_and_targets`
  receives the same replacement; its closed-role/target refusal assertions stay.
- Existing genuine scoped fixtures explicitly supply the same namespace/subtype/
  native-local values already used by their ResourceKey factories. No fixture
  introduces a key-shape decoder. Typed ownership/evidence assertions remain.
- P6 native namespace output/filter assertions move from the misleading `parent`
  name to `identifier_namespace`. Semantic Parent query remains unavailable.
- P3's unknown-kind refusal becomes open nominal kind admission plus explicit
  rejection of an undeclared Document; ordinary file-body storage remains absent.
  Empty Transfer queries now assert the required unsupported error and no stop.
- The P3 swallowed-SQLite-fault adapter permits the new trusted schema/stage
  validation SELECTs during binding, retaining the actual read-fault assertions.

The first broad execution found a missed stored-declaration lookup on Provider
Core-reference registration and missing explicit isolation classifications for
the two new domain modules. Both are corrected; existing Provider and default
runtime isolation regressions cover the fixes. Initial failed receipts are kept.

## Review boundary and reproduction

I3 typed semantic Parent reports, I4 G3=A native-I7/full-report support SQL, I5
actual event semantics/completeness/whole-unit Transfer Admission, I6 complete
generalized wire/selection, and full I7/I8 recovery/Search remain separate work.
General I8 Parent storage is lawful common storage, not eligible Transfer support.
Missing native I7 support and permanently wrong I8 support are not conflated with
the unconditional temporary I2 rejection. Parent arrival cannot replay a unit.

For new executions, follow [ADR 0032](../adr/0032-environment-sqlite-validation.md)
and the [current testing guide](../testing.md). Historical results above remain
unchanged. Use the current helper interfaces:

```sh
python scripts/verify_i2.py --output /absolute/new-evidence-directory
python scripts/verify_i2_sql_counterexamples.py /absolute/repository /absolute/new-sql-directory
```

Use only the selected environment Python's SQLite. Do not repeat across versions
or obtain another library. The broad runner retains ordinary/selected node
inventories, actual OS exits, JUnit/phase journals, source hashes and runtime facts.
`verify_i2_distribution.py` is copied outside the checkout and run using both
isolated installed artifacts with that environment's binding. Original Access
distribution smoke remains intact. Historical archived commands are not a new
exception approval or a current requirement to recreate their two engines.

Author execution receipts and final publication binding are supplied separately
with the Draft PR. A non-author frozen-tree product review is still required.
No merge, release, deployment, P8 or real-catalog operation is performed.
