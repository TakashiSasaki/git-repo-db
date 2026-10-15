# Execution evidence and technical limits

The machine-readable [execution-evidence.json](execution-evidence.json) binds
executed nodes and file SHA-256 values to the frozen implementation-preparation
source commit/tree. The later evidence commit changes report content only; final
feature SHA/tree and GitHub development CI URLs are reported in the PR/final
handoff. A commit cannot embed its own resulting hash. This evidence does not
claim unexecuted full-product tests or release qualification.

## Baseline and environment

- Repository: `https://github.com/TakashiSasaki/git-repo-db`.
- Fresh `git fetch origin` confirmed main `57de60b65c2ef29420a885b0c2102dc90e11fa75`.
- Branch: `feat/implementation-boundary-spikes`, based directly on that main.
- Initial open PR query returned none; #69/#52 accepted design/governance is present.
- Git 2.52.0, Python 3.12.14, SQLite 3.53.1, uv 0.12.19, pytest 9.1.1, Ruff 0.16.10.
- SQLite supports FTS5, JSON, WAL, FK and recursive triggers. B explicitly checks
  separate file inodes/WAL journaling and requests synchronous FULL; A/C exercise
  native hashes/constraints. This is one binding, not a minimum-version guarantee.
- Dependencies prepared once with `uv sync --locked --group dev`; no lock changes.

## Executed local commands

```sh
git fetch origin
git rev-parse origin/main
gh pr list --state open --json number,title,headRefName,url
uv sync --locked --group dev
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync pytest tests/integration/architecture_spikes -q \
  -o junit_family=xunit1 --junitxml=/tmp/architecture-spikes.xml \
  --journal /tmp/architecture-spikes-journal.jsonl
uv run --no-sync pytest tests/unit/test_schema_viz.py \
  tests/integration/test_catalog3_schema.py -q -o junit_family=xunit1 \
  --junitxml=/tmp/baseline-schema-tests.xml --journal /tmp/baseline-schema-journal.jsonl
git diff --check
```

Focused author commands and independent rechecks are in prototype reports and
[independent-review.md](independent-review.md). Raw successful integrated JUnit
and journal are normalized into the receipt: one selected/executed node per test,
setup/call/teardown outcomes and persisted state properties. No node is invented
from a proposed requirement. The receipt also binds the extra failed baseline
check and detached-main reproduction.

## Results and failure accounting

- Integrated architecture probes/checker: **128 passed, 0 failed/skipped**
  (A43/B14/C67/audit4). Independent integrated execution also passed all 128.
- Full source/test/script Ruff lint and formatting passed; both audit checkers
  and `git diff --check` passed. Skills' YAML frontmatter/local links checked.
- Existing visualization/schema pair: **35 passed, 1 failed**, no skips.
  `tests/integration/test_catalog3_schema.py:244` executes `SELECT count(*) FROM jobs`
  on `facts`, whose `fresh_domain_db()` composes **Core only**; jobs belongs to
  Operational. This stale assertion predates the feature; production/test files
  are unchanged. To reproduce at baseline, create a disposable detached worktree
  of the baseline SHA and use the prepared interpreter to run:

  ```sh
  python -m pytest tests/integration/test_catalog3_schema.py::test_committed_resource_does_not_need_collection_or_operation_success -q
  ```

  Actual detached-main reproduction: **1 failed**, identical `no such table: jobs`
  at line 244. This is an existing test-boundary error, not authority invalidation.
  It remains an explicit P8 test repair; no baseline test is silently deleted or
  relabeled passing here. The separate visualization suite passed within the 35.
- `ci_profile.py profile --name architecture-spikes --output <disposable-output>
  --workers 1 ...` failed **before collection**, exit 1, missing JUnit, because
  `--journal` was registered twice. `profile_focused` loads `-p scripts.ci_journal`
  while `tests/conftest.py` delegates the same hooks. Direct pytest using the
  existing conftest hook once (command above) passed all 128 with journal/JUnit.
  This is not a successful profile receipt and is not a release receipt. The
  diagnosed workaround is captured in `ci-final-tree-verification` skill.
- During A development, 4 new closed-group tests failed before the conflict fix;
  4 compatible controls passed. Independent review found and rechecked the fix.
- During B review, a manual wrong-repository probe demonstrated false manifest
  creation; common pre-certification validation and 3 regressions corrected it.
- C initially had 2 fixture failures because Git loose objects are read-only;
  the tamper fixture explicitly made its disposable object writable, then the
  intended native identity rejection was exercised. Later 67 passed.
- Audit initially had 1 failed/3 passed when a temporary output outside repository
  made error-path reporting call `relative_to` unsafely. Error reporting was fixed;
  all 4 now pass. Initial lint import-order failures and JUnit xunit2 property
  warnings were corrected and are not hidden as behavioral successes.

No full product test, isolated installed wheel/sdist target runtime test, full
release qualification, production migration, deploy, merge or live acquisition
was run. Existing development CI is observed independently; green development CI
is not full runtime acceptance. Comparative performance was not measured; timings
are run metadata, not benchmarks.

## Crash-cut persisted evidence

The four subprocess exits bypass Python cleanup (`os._exit(86)`). Actual fresh
connections read separate persistent WAL stores after restart; each retry uses
the same provider/issue/observation evidence rather than an invented operation ID.
Counts below are `(Core objects, Context units, Context links)`.

| Injected cut | Reopened persisted counts | Retried counts | Coherent qualification |
| --- | --- | --- | --- |
| Before Core COMMIT | `(0,0,0)` | `(1,1,1)` | No falsely committed Core fact |
| After Core COMMIT, before Context | `(1,0,0)` | `(1,1,1)` | Independent valid Core survives |
| During Context, after header before member | `(1,0,0)` | `(1,1,1)` | No visible partial Context unit |
| After Context COMMIT, before acknowledgement | `(1,1,1)` | unchanged `(1,1,1)` | Replay deduplicates genuine identity |
| During paired backup after Core copy | Incomplete directory, no manifest | New destination validates | No false full-pair certificate |

The deliberately naive paired read produces an old Core snapshot with a newer
Context link and `resolved=false`; the gate/pinned-pair version stays old/old
through an actual writer then returns new/new on the next pair. A real nonblocking
OS lock probe during backup proves the writer is excluded at the between-copy cut.
Wrong repository, FK orphan, missing Core dependency and file substitution all fail
full backup certification/validation. Resolution is nominal identity only, not
Git bytes or closure.

## Remaining technical risk and implementation scope

A's supported connection/API and semantic whole-value keys demonstrate the domain
contract; they are not a fully general commit/tree/tag parser, privileged-writer
security boundary or production-scale encoding. C checks exact relevant Git
structure/body and retains only note-role content; it does not prove remote
origin/freshness, complete notes enumeration or target possession. Its durable
Operational counters have a kill gap after external I/O before charging; production
must reserve conservative work before performing it and reconcile actual costs
without resetting the explicit request's budget. Resource values are test choices,
not selected production defaults or owner decisions.

B process death is not power loss, sector tearing, directory fsync ordering or
atomic final activation. Production must preserve original WAL/journal evidence,
implement catalog-wide restart-safe corruption stop and use fresh verified
restore/validated merge under ADR 0026. Manifests require domain/schema/allowed-byte
validation, durability hardening and no-overwrite activation; their hashes alone
do not authenticate an issuer or make arbitrary rows true. No per-object quarantine
or global Publication authority was introduced. Search/Operational were absent
from authoritative probes and may be rebuilt later without invalidating sound data.

All source schema/runtime changes and real-data extraction remain outside this PR.
P1's physical five-column Coverage/semantic-key representation and the full P1–P8
integration are engineering work, not an undiscovered owner choice. Estimated
owner-level blockers remain **0**.
