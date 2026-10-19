# Independent I2 + I3 review: initial findings

Reviewer: independent read-only subagent `/root/independent_i23_review`; no production/test authorship and no repository changes. Review and counterexamples are outside the repository. This is the initial rejected tree, not final acceptance.

- HEAD: `6b595ca69d2bcadb7a4643ec7c14191512b20086`
- tree: `25613415f2a96edaa07138492d795003d20ddf58`
- preserved merge: `6dccd3c3bc4919975117a9cea80818936f2b9a5e`
- I2 parent: `9b8a6ad9b761bf23b45eda9f84d639569cee56ef`
- I3 parent: `5c5b816998f7051703ca400e8cfeab377254c435`
- merge-base: `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7`

## Executed checks

Initial exact-tree focused run:

```
.venv/bin/python -m pytest -q tests/integration/i2 tests/integration/i3 tests/integration/i23 tests/integration/p5 --junitxml=/workspace/i23-review/focused.xml
```

173 passed, 0 failed/errors/skips: I2 48, I3 66, I23 11, P5 48. Runtime SQLite 3.53.1. This passing suite missed all findings below.

Additional executions use an unchanged `git archive 6b595ca...` extracted outside the repository, with PYTHONPATH pointing at its src and tests. Confirmed module origin `/workspace/i23-review/old/src/repo_catalog/__init__.py`; SQLite 3.53.1. No committed branches/working source were edited by the reviewer.

## Findings requiring correction

### R1 — High: I2 typed Provider role validation occurs after binding and Core commit

`validate_context()` constructs generic `ResourceRelation` but omits `validate_provider_repository_scope()`, which is called only at production Context admission. Three valid-checksum mutations of a real I2 export reproduced binding + Core registration followed by `AdmissionFailure(core_committed=True, context_committed=False)`:

- replace current role with Transfer role;
- role `observed_at_us` differs from original relation observation;
- remove declared Provider members.

Counterexample: `test_provider_preflight.py`, 3 reproduced controls (`provider-preflight.xml`, `provider-preflight.log`). These are invalid inputs and should be rejected before Package Binding, including when receiver selection disables Context.

### R2 — High: further Context writer-only checks miss preflight; primitive values can change through affinity

`reported_core_reference` with empty value, malformed OID or empty role passes generic FieldCandidate validation and fails after binding + Core commit (IndexError, CoreFailure, or REFERENCE_VALUE). Empty provider_kind passes preflight and fails a SQL CHECK at that same late boundary. Integer provider_kind and integer generic relation_kind are accepted and silently stored as text `"7"`.

Counterexample: `test_writer_preflight.py`, 6 reproduced controls (`writer-preflight.xml`, `writer-preflight.log`). Reconcile all v4 row primitives with exact types and share special reference semantics with the actual writer; STRICT affinity does not preserve original input types.

### R3 — High: legitimate collection-owned Coverage fails, and Source permission cuts abort otherwise admissible Context

A genuine collection, its collection-owned CoverageScope, and a partial CoverageClaim exported from a valid Context fail reception: the importer inserts the Coverage scope before the collection FK referent. A missing collection scope is also retained rather than classified as a missing dependency. A genuine Source coverage scope for R2 survives a receiver permission cut to R1 because scope filters check only Source identity, then violates the source/repository membership FK. All three reproduced `FOREIGN KEY constraint failed` after binding + Core commit, with Context wholly rolled back. The permission-cut case does not auto-register R2, but it prevents independent Context admission.

Counterexample: `test_coverage_dependencies.py`, 3 reproduced controls (`coverage-dependencies.xml`, `coverage-dependencies.log`). Dependencies must include the exact Source/Repository positive pair or complete collection key, with correct collection-before-scope admission order.

## Static scope

Read AGENTS, accepted ADR 0029/0030 and ledgers, I1/I2/I3/I23 handoffs, both architecture contracts, design evidence handoff, changed integration test/workflow/distribution files, inherited I2/I3 domain/adapters/application changes, and relevant repository skills. Reviewed original Provider IDs/Node namespaces, current provider roles versus stale Core rows, exact ClaimKey/Disposition/EventReportKey preservation, independent R/O/C selection, permission closure, Operational digest binding and loss, checkpoints/crash facts, Access exclusion, Notes/Capture/Core scope, whole Transfer/Coverage units and P7 Stop.

No final acceptance is issued for this initial tree. Hosted CI, packaging and full extension evidence belong to the implementing agent and remain pending independent reconciliation against the corrected pushed tree.
