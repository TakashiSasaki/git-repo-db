# Reviewer A — independent database/domain review

Reviewed integrated commit: `178ddbaa8fa06f52aff4993730205c5a38da91f4`.
Exact Git tree: `9740ad1a91f367192bb31ce9777d039c2bb4729b`.
Execution checkout: `/workspace/p7-isolation-audit`, commit `c91321c`;
`git diff --exit-code c91321c 178ddbaa` returned 0 (the entire trees match).

## Independence and scope

This agent authored the replay, existing Context/Core copy stop, missing-required
bytes and explicit P7 audit-module fixes. These changes are **excluded from this
agent's independent approval** and require independent Reviewer C/D coverage.
Implementing-agent runs for those changes are separately recorded; they are not
relabeled as independent acceptance.

Independent scope here covers root-authored source-integrity classification,
forensic source diagnosis/pairing, empty Context handling, enduring stored-domain
guards and the relevant P1/P2/P3 domain/schema compatibility. No outstanding
finding remains within that independent scope after the corrections below.
This is not whole-project approval or authorization to merge.

## Independently reproduced findings and closure

1. **Stored intrinsic evidence could contradict retained bytes.** A disposable
   real P1 commit was admitted normally, then both its scalar/intrinsic size
   values were fault-injected to `["known",999]`, preserving exact trusted DDL,
   foreign keys and native bytes. SQLite integrity_check returned `ok`, FK check
   was empty, and `p1_intrinsic_claim` returned 0, while the old validator accepted
   the retained-byte summary. The corrected enduring-guard validator rejects the
   row. A real backup attempt persists Recovery Stop and rejects publication;
   the source Core file's SHA-256 remains unchanged. See the standalone scripts
   `reviewer-a-intrinsic.py` / `reviewer-a-intrinsic-final.py` and final
   `reviewer-a-intrinsic-c91321c.log` (exit 0). The pre-fix live-tree observation
   is preserved as `reviewer-a-intrinsic-baseline.log`; it is not presented as
   immutable final-revision acceptance.

2. **Temporal admission checks must not reject genuine history.** The root fix
   uses an explicit list of enduring packaged trigger predicates, excluding
   replay-insert and latest-terminal-only predicates. An independently built
   Context store retains two genuine terminal/proof generations, including the
   superseded original proof, and exact empty UTF-8 text. Final domain validation
   accepts that valid history (`reviewer-a-history.py`, final
   `reviewer-a-history-c91321c.log`, exit 0).

3. **New isolated helper modules were omitted from the source-boundary audit.**
   Initial domain runs each produced 611 passed / 1 failed; the genuine failure
   was `test_isolated_target_exclusion_does_not_hide_production_runtime_imports`.
   Raw failures remain in `reviewer-a-domain-1e1b391.*` and
   `reviewer-a-frozen-domain-1e1b391.*`. The correction explicitly identifies
   only recovery_budget.py and recovery_validation.py as optional P7 modules.
   Public baseline imports remain checked. This agent authored that audit fix;
   its independent approval is therefore assigned to C/D, not claimed here.
   The exact final complete domain execution below closes the test failure.

4. **Environmental failure controls.** `reviewer-a-environment.py` constructs a
   disposable healthy Core, independently holds a genuine SQLite exclusive lock
   in a spawned process, and confirms a real backup refuses at its finite lock
   deadline without publishing a corruption stop. A genuine chmod permission
   refusal during forensic source diagnosis raises SourceIntegrityIndeterminateError
   without a stop. A staging-only defect over healthy source likewise does not
   stop authority. Final log: `reviewer-a-environment-c91321c.log`, exit 0.
   An initial counterexample incorrectly expected the diagnosis helper to be
   blocked by the source SQLite lock; it correctly validated its forensic copy.
   That failed harness expectation is retained in `reviewer-a-environment-initial.log`;
   the corrected control tests the actual backup operation under the lock.

## Exact final execution

All commands ran against the immutable c91321c tree, identical to integrated
178ddbaa. Disposable catalogs only; no real recovery or activation occurred.

```
PYTHONPATH=/workspace/p7-isolation-audit/src /workspace/p7/.venv/bin/python /workspace/recovery-evidence-20261016/reviewer-a-intrinsic-final.py
PYTHONPATH=/workspace/p7-isolation-audit/src /workspace/p7/.venv/bin/python /workspace/recovery-evidence-20261016/reviewer-a-history.py
PYTHONPATH=/workspace/p7-isolation-audit/src /workspace/p7/.venv/bin/python /workspace/recovery-evidence-20261016/reviewer-a-environment.py
PYTHONPATH=/workspace/p7-isolation-audit/src /workspace/p7/.venv/bin/python -m pytest tests/integration/p1 tests/integration/p2 tests/integration/p3 tests/integration/p7/test_stored_constraints.py tests/integration/p7/test_source_diagnosis.py -q --junitxml=/workspace/recovery-evidence-20261016/reviewer-a-domain-c91321c.xml
```

The three independent executable controls exited 0. Pytest exited 0:
**612 passed in 40.45 seconds**. JUnit contains exact node IDs; raw log is
`reviewer-a-domain-c91321c.log`. These are concurrent execution durations, not
sequential benchmark claims. This domain selection had no skips or exclusions;
it is not the entire repository suite and makes no claim about the inherited
five Schema 21 failures in the separate all-repository run.

Additional audit-fix checks (author verification, not independent approval):
P1 disposition 22 passed in 0.95 seconds (`reviewer-a-isolation-fix.xml`);
`python scripts/audit_callsite_dependencies.py --check` matched the existing
index; Ruff lint/format passed.

## Limits

This report does not independently approve this agent's authored changes, prove
installed-distribution behavior, hosted CI execution, whole-Context typed salvage
admission, complete Search reconstruction, hostile removal of all durable
accounting evidence, or host power-loss behavior. The platform contract is
cooperating local Linux/POSIX processes with the project's supported SQLite.
The separate filesystem, security, packaging and independent-review receipts
must supply their actual scopes and remaining limitations. No merge is authorized.
