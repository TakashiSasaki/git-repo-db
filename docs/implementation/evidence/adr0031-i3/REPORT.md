# ADR 0031 I3 author verification

**Author verification complete for bounded typed Parent persistence. Whole-product
acceptance remains NOT READY.** Independent I3 assessment is published separately;
this author report does not approve its own implementation or authorize merge.

- Exact dependency/base: PR #125 `a54e4432b0514ba5a5fe8e73ddcdbc492f99b95e`,
  tree `2006edf82c6cff9ec565d8b78fc828fa5cb97a60`.
- Final executed product HEAD: `61c87ced5245caf3a991592a8eb745eef7126177`;
  tree `6f259f7239d7330bea4d1dd1b6e04c316561728f`. Both final input bindings
  record clean tracked status and unchanged comprehensive executable input hashes.
- Initial live PR searches for I3, Semantic Parent and 0031 found no equivalent
  ADR 0031 I3 implementation. PR #124/#125 heads/base/state remained unchanged.
- Product contract and audit: [implementation record](../../adr0031-i3-parent-reports.md).

## Actual final execution, per measured runtime

| Lane | SQLite 3.51.3 | SQLite 3.53.1 | Exit per runtime |
| --- | ---: | ---: | ---: |
| Ordinary collection | 5,432 nodes | 5,432 nodes | 0 |
| Selected broad execution | 2,891 | 2,891 | 1 |
| Broad success | 2,812 | 2,812 | — |
| Broad call failures | 59 | 59 | — |
| Broad setup errors | 20 | 20 | — |
| Dedicated Parent subset, overlapping broad | 65/65 pass | 65/65 pass | 0 |
| Existing SQL diagnostics, separately grouped and overlapping requirements | 301/301 pass | 301/301 pass | 0 |

No skip, xfail or xpass was added or observed in these cohorts. Selected nodes,
JUnit testcases, journal starts/setup/call/teardown/finish and process exits
reconcile exactly. Every one of Task G's 2,826 selected nodes remains selected;
65 new Parent nodes were added. The remaining **2,541 ordinary nodes were not
executed**, and no assertion after a recorded refusal is credited. Four pytest
warnings remain visible in each full raw log. The two driver wrappers exit 0
when receipt generation completes; their broad child exits are explicitly 1.

The 65 Parent nodes include genuine child-before-Parent registration; no hidden
pending replay after Parent arrival; original report resupply and permission /
selection rechecks even on duplicate; Global scalar/recursive/empty IDs;
PR-scoped and nonleaf Documents; Document children; I7/I8 alternatives; independent
clock/provenance/member reports; missing child/target FK errors 787; every full
nine-column reference component; absent versus NULL versus wrong subtype;
noncanonical/NULL/numeric/bool/oversize/deep inputs; timestamp rebind under seven
conflict verbs; exact no-op replay; UPDATE/DELETE/REPLACE refusal; read-only
projections; INSERT SELECT/RETURNING; multirow, savepoint and transaction rollback;
stored Parent revalidation and required deterministic UDF registration.
Direct SQL cases use actual product DDL and functions, not a validation model.
SQL affinity cannot establish original pre-affinity Python parameter types;
typed admission separately validates those types.

## All 79 inherited staging non-successes remain explicit

The machine [failure classification](failure-classification.json) compares every
baseline node and phase with both actual final executions; sets and phases are
identical, with **zero additional non-successes** and **zero of those 79 resolved
by I3**:

| Remaining owner | Call failures | Setup errors | Meaning |
| --- | ---: | ---: | --- |
| I4 native-I7 SQL / I5 matching Transfer admission and routes | 45 | 20 | The deliberately retained Transfer fences still stop these tests. Parent persistence alone must not unlock them. |
| I6 generalized identification/Wire | 14 | 0 | Existing unsupported wire/identification boundaries remain. |

The prior Task G label grouped Transfer dependency as I3–I5. With I3 now boundedly
implemented, its first refusal still belongs to the intentionally unopened I4/I5
path. No original failing test was deleted, rewritten, skipped or xfailed. The
existing P1 packaging test only adds a new installed I3 probe after its original
assertions. The active SQL diagnostic preserves 301 cases, updating its three
lawful Parent fixture scopes to the newly required I3 scope. Historical Task
E/F/G inputs, archives and results are unchanged.

## Real runtime and distribution bindings

Both libraries were built from official sqlite.org amalgamations with recorded
compiler argv, archive/source/library hashes and build exit 0. Actual SQL reports:

- 3.51.3: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
- 3.53.1: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

The tested interpreter is dynamic CPython 3.13.5. Initial default CPython 3.12's
SQLite was statically built in; setting LD_LIBRARY_PATH did not change its actual
3.53.1 version. That interpreter was not relabeled or counted as 3.51.3. Both
final children/workers and all four installed combinations measured their actual
runtime/source ID. Compile options and required PRAGMAs are retained.

A clean Git archive of the final executed HEAD supplied both direct wheel and
sdist-derived wheel. Both were installed outside checkout on both runtimes:
**four I3 probes exit 0, four I2 probes exit 0, all installed package files match
source hashes**. Original unchanged Access smoke exits **1 in all four
combinations** at Provider Transfer preflight; later assertions remain unexecuted.
The distribution orchestrator intentionally exits **1**. Artifact hashes,
source/archive binding, exact commands, stdout/stderr, imports, schema, UDF,
indexes/FKs and installed manifests are retained; no distribution binary or
catalog is published as evidence. These probes are not release qualification.

## Audit and retained initial failures

Packaged fingerprint/inventory, callsite dependency, Context registration and
implementation boundary audits, full Ruff lint/format, whitespace and existing
prose/report validation pass. The schema audit checks unchanged Resource DDL and
indexes, both Transfer fence bodies, accepted ADR/design inputs, original I2
metadata/identity/stage modules and historical evidence. Context's existing
authority gains five generated projections, two indexes, two FKs and an INSERT
guard; its table count is unchanged. Core/Operational/Search fingerprints and
Coverage DDL remain identical. Source/Coverage acquire no synthetic authority.
Public Schema 21 and Access are unchanged; no I4/I5/I6 implementation is claimed.

The initial frozen attempt at `5abb1140d50f290674758812a99b9b7749e2643d`, tree
`49efc948618fdeb7a073f8406027c78a16434934`, had 2,889 executions per runtime:
2,808 pass, 61 fail, 20 setup errors, with its 63 Parent tests passing. Two extra
failures correctly detected that the new opt-in domain module lacked exact-path
classification in the isolation audit. The final correction registers that
specific module, keeps both tests intact and restores zero additional failures.
It also moves bounded Parent parsing before the general JSON decoder, with new
deep-input and deterministic-registration regressions. Initial results and input
hashes remain separately archived; they are not overwritten by the final run.

The existing `three-store-invariants` reference skill records the verified
projection/null/replay, dynamic-runtime and exact-path isolation lessons. No new
speculative skill or policy is introduced.

## Mandatory handoff and limits

**G-R1 remains open for I7:** direct `Context.candidates()` can return field
evidence despite corrupted Global/Scoped identification without persisting a
Recovery Stop; a later identification read detects it. Task G's failed probes
remain their historical failures, not new reruns or complete Recovery evidence.
I3 adds bounded validation for Parent reads/stored Parent invariants only.

Both Transfer fences remain byte-identical. Lawful I8 Parent reports are stored
as ordinary attributed reports, without any claim that they support E's I7-native
Transfer. I4 G3=A SQL and I5 whole-unit admission, I6 Wire, full I7 recovery and
full I8 Search remain separate. No independent authenticity claim, single Parent
winner, domain table, writable duplicate Parent, durable queue, real catalog,
merge, release, deployment or P8 activation was introduced.
