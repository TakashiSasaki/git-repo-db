# Independent shared time, DDL and typed-snapshot review

Reviewer owned no production or repository tests. Work was read-only against
separate detached clean worktree `/workspace/work/review-shared-tree`; executable
counterexamples and evidence were written only under reviewer scratch directory.

## Reviewed identities and outcome

Final executable review: commit `f17dd2154f22f965883d8a1943c140f9cc439ae8`,
tree `952c18132b11f393715e67baad33b730e3404e12`, acceptance input hash
`e3c7e35f6202f8b3e5c9a33a48866e9f24916062fb6ac7a77c09582f2d6faeaf`.
The final committed focused selection passed **119** nodes, and independent
reviewer counterexamples passed **74** nodes. Both reconcile collected IDs,
exactly-once journal starts, three passed phases per node, JUnit identities and
one successful journal finish; zero failures/skips.

Earlier independent impact rerun on corrected commit
`2d4f5d4e30903a4ddd9f1f7977560b47cfe29e6b`, tree
`5829799cb8ab0da0dad5306f74df82ff9f84cd31`, passed **816** nodes, including
P1/P2/P3/P4, the existing **20** P2/P3 compatibility nodes and snapshot helpers.
Its acceptance input hash is
`e3b960c328cce008497c4d3e1c5893ec80d0b1f5a1fb9d4593418a82a40df0e6`.
The 119 final focused nodes overlap that selection and must not be summed as
additional unique committed coverage. Final metrics instrumentation changes the
input hash; the 816 result is explicitly bound to its earlier corrected commit.

## Material finding SHARED-R1, fixed and independently rechecked

Reproduced on clean `3e8280250185b9b894da98b994dc2c384b400f50`:
`GitCore.for_snapshot(valid_A_snapshot, directory_B)` accepted a reader for A
while storing B as its corruption-stop owner. A real synthetic retained-tree
byte mismatch raised authoritative corruption but left A without its persistent
stop and stopped unrelated B. The original two independent counterexamples failed
and their JUnit/journal remain in `binding-impact.*`. This was a supported public
helper call, not an injected private capability.

Root cause: the new helper checked live snapshot/store role but trusted an
unrelated caller directory and dropped the owner's corruption callback. The fix
in `2d4f5d4` binds coordinator-issued `ReadSnapshot` to its actual catalog
directory, refuses mismatched/unbound readers, retains the owner's corruption
callback, and applies the matching Context snapshot-owner check.

Production regression:
`tests/integration/test_snapshot_read_limits.py::test_snapshot_cannot_redirect_catalog_corruption_stop`.
Independent final regressions:
`test_snapshot_binding.py::test_typed_core_reader_refuses_foreign_catalog_directory`
and
`test_snapshot_binding.py::test_foreign_directory_cannot_redirect_detected_source_corruption_stop`.
The latter first requires safe foreign-directory refusal, then reads real corrupted
retained bytes using the correct directory and verifies only the actual source is
persistently stopped. Both pass on exact final `f17dd21`.

## Shared time/DDL review

The generic signed-int64 converter remains unchanged. Observation/Provider values
are positive-or-NULL with strict pre-storage Python validation; required Coverage,
Collection and SourceInventory coordinates stay positive/nonnull. Git observation
JSON and repository observation claims do not gain native signed status merely
because they are stored in Core. JSON original types are checked before SQLite's
generated-column affinity. NULL is not converted into fabricated chronology or a
receipt-order winner; field replay preserves original observation coordinates.

Independent counterexamples exercise NULL, -1, 0, 1, both signed endpoints,
out-of-range values, bool, floats, numeric strings, original JSON types, generated
clock storage and small-magnitude microsecond preservation. Both native Git formats
retain exact negative/zero author/committer commit bytes and tagger tag bytes
through admission, close and reopen. Ordinary observation/Provider counterparts
reject zero/negative values. No arbitrary native-time bypass flag was added.

Opt-in Core and Context fingerprints change, while Operational/Search fingerprints
remain identical to #79. `verify_declared()` passes. Coverage retains five columns
and original required composite PK/FK meanings; nullable fields do not participate
in formerly required terminal proof coordinates. Public schema source diff is empty;
its initializer reports Schema **21**, whose composed public DDL SHA-256 is
`8ee2631fe083e26cd0346bc71a8a5d1f4d7dab4bf661958d6406c885bc553ff0`.

Final additive timing instrumentation measures authority validation and snapshot
digest generation in disjoint `perf_counter_ns` intervals. It is diagnostic output,
not a freshness authority or a claim of index acceleration. Metadata-only fences
exclude retained payload/proof bytes, preserving explicit verified byte readers.
Finite read-limit refusal is separately tested as noncorruption; capability expiry
and correct stop ownership are exercised independently.

## Commands and environment

Environment: Python 3.12.14; SQLite 3.53.1. A separate `uv sync --locked --group dev`
was performed for the review worktree; imported `repo_catalog` resolves to that
worktree, not another agent's editable checkout. `git status --porcelain` was clean
at both reviewed revisions. Versions are environment observations, not host-power-loss
or release qualification.

Committed final collection and execution:

```sh
uv run --no-sync pytest tests/integration/p1/test_time_policy.py tests/integration/p1/test_schema.py tests/integration/p1/test_validation_stop.py tests/integration/p1/test_coordination.py tests/integration/test_snapshot_read_limits.py --collect-only -q
uv run --no-sync pytest tests/integration/p1/test_time_policy.py tests/integration/p1/test_schema.py tests/integration/p1/test_validation_stop.py tests/integration/p1/test_coordination.py tests/integration/test_snapshot_read_limits.py -q -o junit_family=xunit1 --junitxml /workspace/work/review-shared-scratch/committed-f17.xml --journal /workspace/work/review-shared-scratch/committed-f17-journal.jsonl
```

Independent final collection and execution (external scratch files):

```sh
uv run --no-sync python -m pytest /workspace/work/review-shared-scratch/test_independent_classified_times.py /workspace/work/review-shared-scratch/test_snapshot_binding.py /workspace/work/review-shared-scratch/test_native_tagger.py --collect-only -q
uv run --no-sync python -m pytest /workspace/work/review-shared-scratch/test_independent_classified_times.py /workspace/work/review-shared-scratch/test_snapshot_binding.py /workspace/work/review-shared-scratch/test_native_tagger.py -q -p scripts.ci_journal -o junit_family=xunit1 --junitxml /workspace/work/review-shared-scratch/independent-f17.xml --journal /workspace/work/review-shared-scratch/independent-f17-journal.jsonl
```

Earlier impact collection/execution used
`tests/integration/p1 tests/integration/p2 tests/integration/p3 tests/integration/p4 tests/integration/p2_p3_compatibility tests/integration/test_snapshot_read_limits.py`
with the same direct pytest JUnit/journal options (`impact-final.*`). Direct repo
pytest uses its existing conftest journal registration; external scratch tests use
`python -m pytest -p scripts.ci_journal` once. Bare pytest with external plugin
import initially failed to resolve `scripts`; switching to module execution fixed
that tooling/bootstrap issue, which is not a product-test result.

`shared-review-reconciliation.json` records all final node IDs, per-run artifact
hashes, counters and final scratch source hashes. The earlier
`independent-final-journal.jsonl` intentionally preserves two iterative executions
(70 then 74 starts); it is not the final exactly-once receipt. Final `*-f17` journals
are fresh paths and reconcile exactly once.

No remaining material shared finding. This shared review does not itself establish
final P5/P6 combined-tree acceptance, installed distribution success, hosted
Development CI, P7 durability/recovery or Full Release Acceptance. Those remain
separate evidence scopes. No main update, real-data operation or publication was
performed by this reviewer.
