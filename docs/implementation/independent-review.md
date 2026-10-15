# Independent read-only review

Two subagents reviewed source and executed evidence independently of authors.
Neither edited source/docs nor committed changes. The `review_prototypes` role
reviewed A/B/C; `review_audit` independently executed production composed DDL and
reviewed the table/call-site audit, P1–P8 DAG, skills and AGENTS instructions.
Author review alone was not treated as independent approval. Both reviewers rebound their review to frozen commit
`db5775f792a30e259ba9e742c12635d34b5a098c`, tree
`5b3f0b04b10ead94bbb80bf1920f45aac2c74f65`. Prototype source/test hashes matched
independent execution; both checkers and four audit tests were independently
rerun after the generator whitespace normalization. Later documentation-only follow-ups retain executable input hashes and may
expand verified CI retrieval procedures in an existing skill. Frozen source/skill
hashes remain identified as source-commit hashes in
`execution-evidence.json`.

## Findings and disposition

| Severity | Finding / source | Reproduction and correction | Independent resolution |
| --- | --- | --- | --- |
| Major | B manifest could precede repository/FK/integrity checks; `consistency.py` backup/validate_pair | Change Context repository identity, call backup: original code wrote manifest despite invalid pair. Shared `validate_pair` now runs before manifest and after transfer; three defect fixtures assert no manifest. | Reviewer independently ran corrected B: 14 passed. |
| Major | A derived conflict ignored closed-list negative slots; `core.py` parents | Known-empty versus partial parent slot0, or complete `[p0]` versus partial slot1, incorrectly returned no conflict. Four new cases failed before correction. Compare actual asserted slots against every applicable complete/known-empty group, preserving compatible/unknown controls. | Reviewer independently ran corrected A: 43 passed. |
| Minor | B backup concurrency test relied on child scheduling; `test_consistency.py` between-copy callback | Starting a child did not prove lock entry before copy2. A real child `LOCK_EX|LOCK_NB` probe must report blocked at the cut; removing gate reports UNFENCED without scheduler dependence. | Reviewer rechecked source and reran complete B: 14 passed. |
| Minor | C format-negative failed at OID width rather than adapter format guard; `test_notes.py` native identity test | Give full syntactically valid opposite-format root/target/note OIDs and assert `object-format mismatch`. | Reviewer reran 8 affected nodes: passed, 59 deselected. |
| Minor | Generated link referenced nonexistent dependency-map.md; `audit_implementation_boundary.py` rendered prose | Corrected to callsite-dependencies.md; regenerated exact artifacts. | Both checkers pass. |
| Minor | Audit script import ordering | Ruff I001 corrected. | Independent Ruff check/format passed. |
| Minor | Coverage physical-five-column wording could be mistaken for a view workaround; audit-notes | Explicitly require physical authoritative relation; no 5-col view over 6-col authority, extra observation UUID or surrogate scope key. | Independent source/contract recheck passed. |
| Minor | AGENTS retained obsolete proposed/unadopted #52 text | Correct scoped adoption statements; later explicit owner steering additionally authorizes skill guidelines. | Reviewer rechecked accepted policy and expanded authorization scope. |

**Blocking 0; all 2 Major and 6 Minor findings reconciled; open material findings 0.**
The source line anchors below identify final reviewed locations, avoiding references
to changing development line numbers:

- A: `tests/integration/architecture_spikes/core.py:494` `Core.parents`; `test_core.py` `test_closed_parent_group_conflicts_with_partial_extra_slot` and compatible controls.
- B: `tests/integration/architecture_spikes/consistency.py:143` `backup`, `:192` `validate_pair`; `test_consistency.py` `test_invalid_pair_never_receives_full_backup_manifest`, `test_pair_backup_fence_blocks_writer_and_rejects_mismatch`.
- C: `tests/integration/architecture_spikes/test_notes.py:333` `test_exact_native_identity_and_supplied_size_digest_required`.
- Audit: `scripts/audit_implementation_boundary.py` generated dependency references; `audit-notes.md` Coverage section; `AGENTS.md` decision/skill sections.

## Independent execution

`review_prototypes` ran all integrated spike/checker tests:

```sh
uv run --no-sync pytest tests/integration/architecture_spikes -q \
  -o junit_family=xunit1 --junitxml=/tmp/independent-all-prototypes.xml
```

Result: **128 passed, 0 failed/skipped** (A43/B14/C67/audit4). The reviewer also
ran manual SQLite/Python counterexamples, corrected A/B full suites and C's 8
changed nodes. Evidence is review execution, not an author's relabeled result.

`review_audit` ran both audit `--check` commands, 4 checker tests and script Ruff
checks. Separately executed composed production DDL directly with SQLite, rather
than trusting the shared schema visualization collector: Core 70 tables/512
triggers/20 views/46 explicit indexes; Operational 10/20/0/5; Search 4/8/0/1.
It independently injected missing/duplicate/empty classification cases and
confirmed fail-closed checking. All current product columns have explicit routes.

## Informational limits and readiness

No production-readiness or release approval follows this review. Literal references
are not a complete Python data-flow proof; manually traced dynamic integration
paths supplement them. Prototype A's narrow verifier and supported connection
boundary do not protect against privileged file/schema manipulation. B proves
process-death behavior, not power-loss or final installation. C documents its
post-I/O Operational-accounting kill gap: production needs conservative reservations
before work and safe reconciliation. Full corruption stop/salvage/fresh restore/
validated merge, wire evolution, scale, installed target schema and four-store
runtime integration remain future implementation tasks. None is a newly unresolved
owner architectural choice.
