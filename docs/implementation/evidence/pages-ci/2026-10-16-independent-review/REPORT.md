# PR #89 independent review — 2026-10-16

Reviewer: pages_review subagent; parent independently reviewed the remediation diff.

- Original head: 7cbe97f0be9b19127948c56bf1b7c0b4f6fcaae7, tree a9aeb0087014959e725bdb836999a9cb27580a5b.
- Corrected head: fbf3c37f6de3522e800a8cc282a332b3fbd1a0fd, tree 21d24e4f3460b1ddbbbaf6cfa8cbd23af7020982.
- Main baseline: b86c46761ec0c3f3843a19edd4f3e106ef5ef58c.
- Final GitHub test merge: b3e8d39742c669b6a9d3b85d9b8156f3613999da, same effective tree as corrected feature.
- Branch ordinary nonforce push checked expected remote 7cbe97 before push. Worktree clean afterward. No P7 changes; no deployment or merge.

## Reproduced and corrected defect

Seven existing documentation tests passed on the original HEAD, but an independent executable probe of schema_viz.py --check found ten executed Python dependency paths omitted by both Pages trigger lists. The actual checker imports SQLite registration helpers and domain parsing/error/time helpers. Edits to them could break publication validation without triggering Pages.

`check_import_trigger.py` records the independent reproduction. `transitive-before.log` has exit 1 and exact missing files; `transitive-after.log` has exit 0 and no missing files. The correction adds those exact paths to push and PR triggers and adds a subprocess-based regression observing the schema checker's actual import set. A lesson was added to the existing docs-site skill. The approved public staging allowlist, default Schema 21 runtime, deployment gates and full-builder invocation are unchanged.

The observed import closure is a guard for executed branches, not proof that future optional branches have no other inputs. The skill explicitly records this limit.

## Commands and evidence

All local commands run in /workspace/pages-ci using its separate .venv. `uv sync --locked --group dev --group docs` succeeded, Python 3.12.14, pytest 9.1.1, Ruff 0.16.10.

Original executable tree:

- `uv run --no-sync python /workspace/pages-evidence-20261016/check_import_trigger.py`: exit 1 (expected finding; preserved).
- `uv run --no-sync pytest tests/unit/test_build_docs_site.py -q --junitxml /workspace/pages-evidence-20261016/original-junit.xml`: exit 0, 7 tests.

Corrected immutable commit:

- `uv run --no-sync pytest tests/unit/test_build_docs_site.py -q -o junit_family=xunit1 --junitxml /workspace/pages-evidence-20261016/committed-junit.xml --journal /workspace/pages-evidence-20261016/committed-journal.jsonl`: exit 0, 8 passed. Reconciliation confirms 8 unique JUnit nodes, 8 journal starts, 24 passed phases, completed exit 0.
- `uv run --no-sync ruff check src tests scripts`: exit 0.
- `uv run --no-sync ruff format --check src tests scripts`: exit 0; 310 files.
- `uv run --no-sync python scripts/build_docs_site.py --no-mermaid`: exit 0; full MkDocs, endpoint, safety and links checks passed **with placeholder SVGs**. Its inherited summary says ten SVGs rendered, but this invocation does not establish real rendering.

Retained environment failures during real-render attempts:

- `uv run --no-sync python scripts/build_docs_site.py`: exit 1, pinned chrome-headless-shell unavailable.
- `/home/agent/.npm/_npx/fa58c8ce4c502b5d/node_modules/.bin/puppeteer browsers install chrome-headless-shell`: exit 1, browser download provider failure.
- `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium uv run --no-sync python scripts/build_docs_site.py`: exit 1, administrator blocks Mermaid's file URL. No policy bypass attempted.

## Exact-tree hosted evidence

- Pages run https://github.com/TakashiSasaki/git-repo-db/actions/runs/38917873071: SUCCESS, 68s job. Downloaded real log ZIP shows checkout b3e8d39 / tree 21d24e4f, all ten real Mermaid diagrams, MkDocs, zero safety violations, zero broken links, 8 passed in 1.61s. Deploy skipped.
- Development run https://github.com/TakashiSasaki/git-repo-db/actions/runs/38917873031: SUCCESS, selected development checks; actual runtime pytest execution count zero, not full acceptance.
- `gh run view --log` returned empty output for original runs. Supported GitHub run-log ZIP API supplied actual complete logs instead. Direct individual job-log URL download was Forbidden; preview artifact download was Forbidden. No unavailable artifact was claimed downloaded.
- Preview upload succeeded, artifact pages-preview-89 / 12053067229, according to actual API record. Its bytes could not be independently fetched.

## Timing and merge gate

Historical observed comparison: pre-skip run 38882486789 / 55dcf515 had 7 tests in 21.54s, Pages job 84s; run 38897854723 / 7cbe97 had 7 tests in 0.68s, job 53s. Both logs prove real full-build Mermaid rendering. This is an uncontrolled run comparison, not an isolated benchmark. Avoided path-filter runs yield expected savings; no measured per-commit or percentage saving is asserted.

Rulesets listing returned []; branch protection API returned 403 with current credentials. Therefore no claim that all required-check settings were independently inspected. GitHub path filtering can leave a configured required check pending. Owner must verify their required-check policy when authorizing merge; no policy was bypassed or changed.

PR body updated via structured REST PATCH (gh pr edit first failed due deprecated Projects Classic GraphQL field), removing stale counts and overclaims. Root reviewed correction. Ready for owner merge review, conditional on owner merge authorization and required-check policy. No known implementation defect remains in the reviewed PR89 scope. Local real-render limitation is covered by actual exact-tree hosted real rendering; downloaded preview bytes remain unavailable.

## Evidence-only follow-up

This directory is an internal evidence-only follow-up to the tested commit. The accompanying publication-inputs.json binds unchanged publication/build inputs to the tested commit. Its file hashes are checked before committing the evidence; no complete build is claimed rerun for this documentation-only follow-up. A future build would display the new evidence commit/tree in its metadata. Full raw logs and environmental failure records remain in the recovery workspace; narrow verbatim execution excerpts and durable GitHub run links are retained here.
