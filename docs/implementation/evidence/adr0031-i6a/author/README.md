# Author execution receipts

Read [REPORT.md](REPORT.md) and [MATRIX.md](MATRIX.md). This directory is new;
historical I4/I5/I6 evidence remains unchanged. Author verification is separate
from non-Author acceptance. The final PR body carries publication HEAD/tree.

## Environment and commands

The selected existing complete Python was:
`/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3.12`.
It loads its built-in SQLite. No SQLite library, binding or loader replacement
was installed. Locked setup used writable `UV_CACHE_DIR` and an explicit
`UV_PROJECT_ENVIRONMENT`, with `uv sync --locked --group dev --group docs
--python <that-python> --no-managed-python`. Dev+docs are both needed: a preserved
initial final-collection attempt using a dev-only environment failed on missing
PyYAML before product execution. It is not counted as a passing run.

The baseline worktree was separately checked out at #141 and had its own editable
venv. The first source freeze was
`30888b6558f25d1a26092e020217d635b9c9a718`; the intermediate correction was
`cc6e611d366230438f2c25e4040156c90cf4897f`. Final executable source is
`770e42d4828238cc0001c96663d078605ac44841`, tree
`9769a431eed95b841c9ac2d5a54a83ea248fc5be`. These are distinct executions,
not relabeled receipts. Evidence-only commits afterward preserve executable/test
input hashes. [VERIFICATION.md](VERIFICATION.md) gives their actual outcomes.
Each run records interpreter, imported paths, SQLite identity, commands and
process exits. JUnit uses xunit1 for stable classname/name identity and the
existing conftest journal registration exactly once (no duplicate `-p` option).

Focused commands (actual source node lists in receipts):

```sh
python -m pytest -q -o junit_family=xunit1 \
  --junitxml focused.xml --journal focused.jsonl \
  tests/unit/test_context_refusal_order_i6a.py \
  tests/integration/p1/test_coordination.py \
  tests/integration/p1/test_disposition.py \
  tests/integration/access/test_registry_isolation.py \
  tests/integration/p3/test_transfer_sql.py \
  tests/integration/p3/test_transfer_admission.py \
  tests/integration/p3/test_parent_reports.py \
  tests/integration/i6a \
  tests/unit/test_context_admission.py \
  tests/unit/test_transfer_originals.py \
  tests/unit/test_context_fences_i6a.py \
  tests/unit/test_context_oid_admission_i6a.py \
  tests/unit/test_context_admission_bounds_i6a.py \
  tests/unit/test_context_coordinator_admission.py
ruff check src tests scripts
ruff format --check src tests scripts
git diff --cached --check
```

The historical cohort is the exact 3137-node list from `scripts/verify_i5.py`.
The complete ordinary selection is `not live and not benchmark`; its remaining
nodes execute disjointly rather than being silently excluded. Baseline/final
collection, selected node lists, JUnit and journal must have duplicate-free exact
set/multiset agreement. Failures remain visible; no skips/xfails were added.
Replay or old fixture failures are classified by the first reached phase,
exception and assertion, separately from later-stage ownership.

The inherited journal emits additional call reports for unittest subtests. Its
original strict duplicate-phase check remains false and is preserved. Final
execution additionally records actual report classes in an external sidecar,
reconciling each raw report and distinguishing main phases from subtests. The
serial/xdist positive and intentionally failing subtest probes are separate from
product results. No blind deduplication or synthetic passing outcome is used.

The installed lanes build a direct wheel and a fresh wheel from the sdist, then
install each into a separate venv. Copied tests/support live outside the source
checkout; all product imports must resolve to that lane's site-packages. Runtime,
product files, DDL, fingerprints, archive members, dependency lock/wheelhouse and
artifact SHA-256 identities are independent receipts. The inherited sdist
contract is used; Task A/ADR 0033 is not in this ancestry.

## Raw adversarial evidence

[SQL probes](raw/sql-admission-probes.json) retain actual SQLite trace, in-flight
counts, constraint codes, explicit rollback, post-rollback counts and independent
Parent original time. [I5 node mapping](raw/i5-node-mapping.json) preserves all29
old IDs with their new contract assertion mapping. Prelaunch API snapshots
preserve main/#130/#133/#134/#141 heads, trees, reviews, comments and CI state.
No green development badge is called full runtime or independent acceptance.

Large logs/JUnit/journals/node inventories may be gzip-compressed. The compression
manifest binds original bytes and stored bytes; inspect without executing archive
content. Packaging artifacts and installed tests are synthetic; no real Provider,
real catalog, release, deploy, recovery activation or scheduled task is operated.
