# Final integration review F186-01/P2: MemAvailable precedence

Independent final review of PR186 HEAD
`af32cf593060beecb1689e4b37d27473bfb9edaf`, tree
`4a55d1e9e000a40633e3c987db5d6b1147ca4537`, returned **FAIL / HOLD MAIN MERGE**
for F186-01/P2. Normal /proc/meminfo ordering puts MemTotal first; the parser
returned total RAM before reaching MemAvailable. With 16 GiB total, 1 GiB
available, 8 CPUs and 200 nodes, it selected 8 workers rather than 2 at 350 MiB
per worker. The finding and old green CI are preserved separately in
historical-f186-01.json. Neither old CI nor earlier repair PASS approves this fix.

## Narrow correction

Code commit `7dd1e984cdad0ff7a4d318a97f8669ad7924e47a`, tree
`f4e3729c168949486da3a9127dd125ef1407be77`.

`available_memory_mb` now searches for valid MemAvailable independently of field
order and retains MemTotal only as a fallback after the search. Each malformed
record is ignored independently so it cannot hide a later valid value. Values
must be finite, nonnegative kB; zero availability is retained and therefore
reaches the existing one-worker floor. Positive total-memory, sysconf and default
fallback policies remain. No worker cap, memory-per-worker default, override,
CPU/affinity/cgroup quota or host-reservation implementation is changed.
AST comparison confirms that available_memory_mb is the only changed scheduler
function. Existing scheduler/quiet-runner/receipt/collector/reservation tests and
an explicit CPU-quota plus low-memory minimum test preserve the existing caps.

## Red/green verification

- Old parser plus the first 29-node cohort: **13 failed / 16 passed**. Both
  MemTotal/MemAvailable orders, malformed records and low-memory repros are
  retained in red.log.gz. This is an old-source regression control, not a full
  old-tree suite.
- First corrected parser cohort: **29 passed**.
- Final focused cohort: **86 passed**, including **33 scheduler nodes**, xdist
  2 workers, exit 0, 1.15s. Cases cover both field orders; missing/malformed/
  negative/nonfinite/wrong-unit data; zero and low availability; later valid
  records; total and sysconf fallbacks; and unchanged CPU/cgroup caps.
- Full Ruff lint/format (474 files) and whitespace checks passed.

Command on the unchanged verified Python 3.12.15 / actual SQLite 3.53.1:

```sh
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q -n 2 \
  tests/unit/test_resource_scheduler.py tests/unit/test_quiet_runner.py \
  tests/unit/test_ci_collector.py tests/unit/test_ci_receipt_verification.py \
  tests/unit/test_test_efficiency.py \
  --junitxml=artifacts/pr186-final/f186-01-focused.xml
```

Exact Python input hashes and compressed raw JUnit/logs are in summary.json.
The code/test working bytes match the code commit; the later evidence commit is
not another test run. The reused skill records why replacing the high-level
memory result in a test could not expose this real parser defect.

ADR0034 adoption, prior repair/review ancestry, prior FAIL history, product source,
both Transfer fences and the 43 known non-successes are preserved. No new product
scope, release, deployment or SQLite change. The final candidate SHA/tree belongs
in PR186 metadata; new exact-head Development/Access CI and the same independent
reviewer's final re-review must pass before main merge.
