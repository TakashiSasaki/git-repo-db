# P1 executed development validation

**Verdict: READY FOR P2/P3 PARALLEL IMPLEMENTATION**, subject to owner review of
P1 and its PR #70 dependency. This establishes isolated physical schemas, stable
typed interfaces and executable reference behavior. It does not switch Catalog3
Schema 21, implement complete P2–P8 behavior or qualify a release.

## Exact source and evidence binding

Final tested and independently reviewed executable source:
`f56cf3f2adddaf18e3d5cc5052ad92440a8abc33`, tree
`fd61dca21c8e34c4729e3cf9b43d226a83b95a94`.
Dependency/base: PR #70, `feat/implementation-boundary-spikes`, HEAD/merge-base
`eb84be9b2061b026ad82b780cc95e062928f838a`. Main remained
`57de60b65c2ef29420a885b0c2102dc90e11fa75`; PR #70 remained open/unmerged.

The [machine-readable receipt](p1-execution-evidence.json) records actual selected
and executed node IDs, setup/call/teardown outcomes, exact command outputs, raw
JUnit/journal byte counts and SHA-256, and executable source hashes. Selected
collection IDs, journal starts/phases and JUnit cases reconcile exactly once.
No node or success is synthesized from a proposed requirement. Later evidence-only
commits cannot contain their own hash; the PR binds the final feature SHA/tree,
unchanged input hashes, final direct checks and development CI. Temporary GitHub
merge commits are reported separately from feature commits.

Environment: Python 3.12.14, SQLite 3.53.1, uv 0.12.19, pytest 9.1.1, Ruff 0.16.10.
Dependencies prepared with `uv sync --locked --group dev`, without lock changes.

## Commands and results

```sh
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync pytest tests/integration/p1 tests/integration/architecture_spikes tests/packaging/test_p1_distribution.py --collect-only -q
uv run --no-sync pytest tests/integration/p1 tests/integration/architecture_spikes tests/packaging/test_p1_distribution.py -q -o junit_family=xunit1 --junitxml=<output>/f56cf3f.xml --journal=<output>/f56cf3f.jsonl
uv run --no-sync pytest tests/unit/test_schema_viz.py tests/integration/test_catalog3_schema.py -q -o junit_family=xunit1 --junitxml=<output>/f56cf3f-baseline.xml --journal=<output>/f56cf3f-baseline.jsonl
git diff --cached --check
```

Static lint and format pass (247 Python files formatted). All schema builders and
three audit checks pass. The focused integrated run returned **380 passed in
25.78s**, zero failures/errors/skips. It comprises 250 new P1 tests, 128 existing
spike/audit regressions and two installed-package variants (wheel and sdist-derived
wheel, built and installed offline outside the checkout). This is focused packaging
verification, not the complete released CLI packaging suite.

The separate unchanged baseline pair returned **35 passed, 1 failed in 10.48s**.
The complete nonoverlapping selected categories are:

| Category | Selected | Executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| Four-store DDL and dispositions | 25 | 25 | 25 | 0 | 0 |
| Core contracts (including Core Coverage) | 74 | 74 | 74 | 0 | 0 |
| Context contracts | 24 | 24 | 24 | 0 | 0 |
| Coverage/identity (Context scope suite) | 39 | 39 | 39 | 0 | 0 |
| Cross-store coordination | 46 | 46 | 46 | 0 | 0 |
| Notes/retention contracts | 30 | 30 | 30 | 0 | 0 |
| Other affected tests | 178 | 178 | 177 | 1 | 0 |
| **Total** | **416** | **416** | **415** | **1** | **0** |

Other affected tests are 12 derivative/work-accounting tests, 128 existing
architecture spikes/audit tests, 2 focused distribution tests and 36 unchanged
Schema 21/visualization tests. No new P1 test failed. These categories do not
claim selection or execution of the full application suite.

## Existing failure and separate repair

`tests/integration/test_catalog3_schema.py::test_committed_resource_does_not_need_collection_or_operation_success`
queries Operational `jobs` through its Core-only fixture and fails at line 244:

```text
sqlite3.OperationalError: no such table: jobs
1 failed, 35 passed
```

Reproduced independently in a disposable detached worktree of unchanged main
`57de60b...` with the same interpreter and direct pytest: **1 failed**, same
exception/location. P1 does not delete, skip, xfail, hide or cherry-pick a repair.
Independent [PR #71](https://github.com/TakashiSasaki/git-repo-db/pull/71), based on
main, corrects only the stale store-boundary assertion while preserving resource
eligibility behavior. Its commit `155645c03417905fcb1a6485e916c10aef371318`, tree
`e0ff950e755bc5b9fed18cecc83f26625434ffcc`, passed all 36 affected tests. Root
independently reviewed its source and journal. Its ordinary
[development CI](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38801923418)
passed with zero hosted pytest execution; it remains open/unmerged.

Direct pytest uses the existing journal registration once. The profiling wrapper
was not invoked in P1; PR #70's known duplicate `--journal` registration is not
claimed fixed or successfully executed here.

## Iteration and independent review evidence

Early dirty-tree integration encountered unfinished fixture imports, stale
fingerprints/disposition evidence and APIs being changed concurrently (one such
run: 110 passed, 12 failed, 25 setup errors). These were development failures,
not acceptance evidence. Formatting initially exposed one changing Core file;
final lint and format both pass. Required fingerprints and ledger were regenerated
only after authored semantics/constraints were corrected.

Exact clean source runs progressed from 310 passed at `8b6db0c`, to 359 at
`18bb00e`, 370 at `924fb20`, and 380 at final `f56cf3f`. Independent reviewers
found real cases absent from those passing suites, including scope/negative
conflicts, malformed proof certification and stop timing. Corrections retain
regressions. [Independent review](p1-independent-review.md) records severities,
original locations, counterexamples, correction commits and rechecks. All three
reviewers report zero remaining material findings in their assigned P1 scope.

Applied repository skills: `three-store-invariants`, `ci-final-tree-verification`
and `lessons-to-skills`. The invariant skill now records cursor capability escape,
mirrored multi-SELECT snapshot tests, actual generated-column behavior and
stop-before-unwind/completion-fence testing. No accepted ADR or Pages publication
allowlist changed.

## Proven boundary and remaining implementation

All four databases construct independently from packaged DDL; all 46 tables are
STRICT/WITHOUT ROWID with explicit semantic PKs. Core is application INSERT-only;
Coverage has exactly five actual columns in each authority. The complete
84-table/625-column successor ledger has zero unclassified entries.

Subprocess tests demonstrate SQLite process-loss cuts, Core-first partial durable
success, atomic Context rollback, identity-preserving retries, real gate exclusion,
pinned snapshots, incomplete backup candidates and persistent stop across restart
and derivative loss. They do not prove host power failure, filesystem/journal
preservation, fresh restore/salvage/activation or Windows/network-filesystem support.
Those are explicit P7/platform work, not implemented claims.

Core's narrow native/proof grammar is an executable contract reference, not the
full P2/P4 parser or P5 acquisition/Exchange implementation. P6 can optimize the
conservative snapshot-content hashing/direct authority validation. P8 integrates
the coherent public runtime after P2–P7. No real user catalog, source backup,
release, deployment, merge or auto-merge was modified/performed.

**P2: READY WITH EXPLICIT DEPENDENCIES. P3: READY WITH EXPLICIT DEPENDENCIES.** Both
depend on owner acceptance of P1/#70; neither depends on the other's implementation.
Their [P2](p2-git-core-handoff.md) and [P3](p3-context-handoff.md) briefs define exact
ports, DDL, focused commands and separate file ownership. Shared schema/Coverage/
coordination contracts are frozen by P1 and require coordinated dependency edits.
Genuine unresolved architectural owner decisions: **0**. No demonstrated accepted
requirement contradiction remains.
