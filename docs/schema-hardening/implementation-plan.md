# Current catalog3 implementation state

Catalog3 is the sole ordinary runtime; the packaged DDL and runtime identity module are authoritative. [Runtime handoff](runtime-handoff.md) records runnable commands, validation, preservation and limits. Earlier phase plans and design/export schemas are historical snapshots.

The naming stride starts from main `2566522c79c41aad9b410c2a3db6e699e2acdf65` on the new branch `refactor/catalog3-schema-names`, after merged PR #1. It advances runtime schema identity 3 → 4 while retaining `repo-catalog/catalog3`.

Implemented scope:

1. Audit all 74 runtime tables and 148 FK components; rename 135 columns using semantic entity identifiers, aligned neutral/owner FKs and explicit role prefixes. No table or logical relationship changes.
2. Update SQLite/Git/GitHub writers, readers, query projections, indexing, finalization, maintenance, backup/restore, CLI row output and current fixtures/tests. Explicit target INSERTs and positional audit SELECTs name their columns.
3. Keep v2 source schemas/names unchanged; target recipes and saved identity contexts translate to current catalog3 names while preserving exact acquired evidence. No old-catalog3 migration/view/alias or dual path.
4. Replace the v2-era data-model description with the current catalog3 model and update current README/identity/architecture/operations guidance.
5. Narrow CI classification to explicit runtime/CI contracts and named historical report inputs. Unknown inputs still expand testing; no change-aware CI redesign.
6. Complete focused subsystem checks and the affected integration closure (242 passed). Final substantive revision `2399248c3cc5a49c56231a94b084d15fe3ce1852` passes 339 current acceptance tests, both isolated installed wheel/sdist checks, lint/format and schema/doctor checks. The existing collection/profile reconciliation confirms all 341 selected tests executed once on that clean revision. Exact results are recorded in the handoff.

Museum-portal Git/API and retained-v2 discovery reports retain their original pre-refactor commits and scope. They are not repeated for identifier changes. Semantic redesign, product features, exchange work, real-data activation and release publication are outside this stride.
