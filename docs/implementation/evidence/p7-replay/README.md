# P7 replay implementation checkpoint

Base: `e0c6fd85bc233412c0b4dbfb32d63d69ffd26893`.
This is implementing-agent regression evidence, not independent acceptance.

The baseline run used an unmodified `git archive e0c6fd85 src` extracted outside
this checkout, with the new 31-node replay regression test file. Command:

```
uv run pytest -o pythonpath=/workspace/recovery-evidence-20261016/replay-baseline-source/src tests/integration/p7/test_exact_replay.py -q --junitxml=/workspace/recovery-evidence-20261016/replay-baseline.xml
```

Exit 1: 18 failed, 13 passed, 1.58 seconds. The failures reproduced digest-only
replay (wrong metadata type/size, wrong Notes role/Capture/body attributes),
repository rebinding, missing-copy misclassification, partial Capture admission,
ignored duplicate Capture coordinates, original repository replacement and empty
metadata refusal. Raw failures and node IDs remain in `baseline.log`/`.xml`.
Three additional focused nodes were added after that baseline run; it must not be
reported as a baseline execution of all final nodes.

The corrected implementation always invokes typed production admission before
counting replay. Core's immutable-row equality checks apply to the complete
physical copy and role evidence. `admit_note` installs Capture, role and body in
one transaction; no earlier independent Capture mutation remains. New physical
copies count as admissions, missing original copy identity remains an observation.
Extracted Notes include original repository/source/ref; destination identity is
never substituted for original Capture repository. Top-level/payload Capture
coordinates must agree. Context text uses the exact UTF-8 check including replay.
Unsupported Context resources are explicitly qualified observations, not typed
authoritative recovery or replay. Their dependency reconciliation remains an
acceptance limitation.

Final command for the executable changes in this checkpoint:

```
uv run pytest tests/integration/p7 -q --junitxml=/workspace/recovery-evidence-20261016/replay-p7-final.xml
uv run ruff check src/repo_catalog/adapters/sqlite/recovery.py tests/integration/p7/test_exact_replay.py
uv run ruff format --check src/repo_catalog/adapters/sqlite/recovery.py tests/integration/p7/test_exact_replay.py
```

Exit 0: 80 passed in 3.77 seconds, comprising all 46 pre-existing P7 tests and
34 new replay tests. Raw results are `p7.log`/`.xml`. Ruff passed. An earlier new
test-helper attempt incorrectly assumed rowid on WITHOUT ROWID tables (27 helper
failures); the helper was corrected to compare every table's actual rows. A Ruff
local-import ordering failure was also corrected before final checks. Neither
was reclassified as a production defect.

This checkpoint does not verify the integrated budget/input fixes, installed
distributions, hosted CI, independent reviews or power-loss behavior. Those
require exact-revision integration acceptance.
