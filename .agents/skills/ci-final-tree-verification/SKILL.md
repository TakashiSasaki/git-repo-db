---
name: ci-final-tree-verification
description: Verify git-repo-db CI status and test execution against the exact feature HEAD and effective Git tree. Distinguish ordinary development checks (lightweight CI + local focused testing) from explicit release acceptance (independent local + hosted complete execution with test-node reconciliation). Use before PR submission, review, or release qualification.
---

# Verify the exact accepted tree

Use `docs/change-aware-ci.md`, `docs/testing.md`, and `scripts/ci_dependencies.json` as the live contracts. Follow [ADR 0032](../../../docs/adr/0032-environment-sqlite-validation.md) for the environment's Python-loaded SQLite; one version per environment suffices for development and release. Distinguish ordinary development validation from explicit release acceptance.

## Stacked integration trees and merge authorization fences

Separate feature-tree acceptance does not prove their combined executable tree.
Fetch all reviewed heads, record their exact SHAs and the actual main, then use
`git merge-tree --write-tree TARGET FEATURE` and a two-parent `git commit-tree`
chain in the intended order. Preserve every merge base, parent, conflict result,
effective tree and changed input set. Test the frozen combined source; later
evidence-only commits require explicit unchanged-input binding, not a rerun claim.
The [seven-PR acceptance evidence](../../../docs/implementation/evidence/seven-pr-combined-20261016/README.md)
includes an independently reproduced deterministic helper and owner preflight.

`gh pr merge --match-head-commit` checks the feature HEAD, not the base. It does
not atomically prevent another merger from changing main after local preflight.
Within separately authorized merges, coordinate a single-merger window, reread
main immediately before each command and verify the actual merge's two parents
and tree afterward. Stop on a changed HEAD, target, policy, checks or tree; do not
continue automatically. Retarget stacked children only after their parent merges,
without rewriting feature history. Expected trees are not predicted GitHub commit
SHAs. The verified read-only helper and plan do not grant merge authorization or
claim atomic base fencing; no production merge was executed to establish them.

If an older `gh pr edit` fails with the GraphQL `projectCards` / Projects
(classic) deprecation error, preserve the failed command and inspect the live PR
before retrying. This is a CLI compatibility failure, not evidence of missing
write permission. Use the supported REST pull-request update endpoint with a
JSON file containing only the intended `body` or `base` field:
`gh api --method PATCH repos/OWNER/REPO/pulls/NUMBER --input payload.json`.
Create the payload with a JSON serializer so Markdown newlines remain intact.
Reread the returned/live fields; after a base change, recheck the effective diff,
candidate parents, tree and checks before merging. This fallback grants no merge
permission and never bypasses repository protection or rewrites branch history.

For supplementary skill edits, also preflight against the pending reviewed
branches. Independent additions at the same end-of-file can conflict even though
both are prose. Preserve each lesson and choose a noncompeting section location;
verify the merged text and runtime input equality. Do not silently edit or rewrite
the reviewed branch to accommodate the documentation follow-up.

## Normalize collection files and preserve unique evidence targets

A historical file named `p7-node-ids.txt` also contained a blank line and pytest's
collection-summary footer. Comparing all text lines falsely reported a node-set
mismatch after a successful run. Parse actual `tests/...::...` records first,
preserve duplicates with a Counter, then compare normalized IDs. Never remove
unexpected actual nodes or convert a mismatch into success using counts alone.
Preserve the failed parser result and raw input; distinguish a parser correction
from a test rerun. See the seven-PR evidence's `p7-original-text-comparison.json`
and `reconciliation-footer-failure.txt` under `raw/`.

Evidence export also found `.py` and identical `.py.txt` aliases targeting the
same transport file. Index each transport path once, retain the original aliases
explicitly, and compare original/transport lengths and SHA-256 before deduping.
Fail on unequal bytes instead of overwriting one alias. Verify gzip originals as
well as compressed bytes. A review's index hash binds its recorded snapshot;
adding that review naturally changes a later index, not the frozen test source.

For bounded local inspection, use the
[efficient repository investigation skill](../efficient-repository-investigation/SKILL.md)
and follow the mandatory 5-step agent investigation sequence:
1. `scripts/ci_query.py summary <dir>` for compact metadata and execution summary.
2. `scripts/ci_query.py status <dir>` for failure counts and categories.
3. `scripts/ci_query.py failures <dir> --new-only --limit 10` for bounded new/changed failures.
4. `scripts/ci_query.py failure <dir> --node <nodeid>` for targeted tracebacks.
5. If raw logs must be inspected, use `scripts/ci_query.py filter-log <raw.log> -o <clean.log>` to strip large Base64 receipts, and `scripts/ci_query.py extract-receipt <raw.log> -o <out_dir>` for on-demand unpacking. Never load multi-megabyte Base64 payload logs into agent context.

Never run bare, unbudgeted pytest in agent sessions; always pass `--quiet` (`-q`) and use `scripts/ci_profile.py` or `./scripts/local-run.sh`.
Its summary helper validates consistency without claiming source/hosted release
qualification. Frozen historical reports and execution input hashes stay intact.

## Inventory beyond a focused CI cohort

For assembled acceptance, collect `tests/` with `-o addopts=` before applying
ordinary/live/benchmark markers. A green focused cohort does not cover omitted
nodes. Install both locked dev and docs groups: the ordinary docs-build tests
import PyYAML from the docs group. Prepare the locked wheelhouse before offline
packaging tests, and verify its manifest/lock and wheel digests. Dependency
preparation is distinct from executing Provider acquisition.

Use `scripts/verify_i5_offline.py --output NEW_EMPTY_DIR --execute` with the
environment's selected Python and its actual SQLite for disjoint focused/additional/benchmark
cohorts, quiet raw logs, JUnit/journal reconciliation and input hashes. It is
an acceptance evidence helper, not a release receipt. It refuses live nodes;
report those as unexecuted. Its default xdist workers isolate disposable Catalogs;
benchmark cases run separately without a concurrent timing comparison claim.

Include the intended venv's `bin` directory in PATH as well as selecting its
Python: subprocess `repo-catalog` must resolve to the same installed runtime.
I5 first reproduced FileNotFoundError from a missing CLI PATH, then independently
passed the same CLI/backup cases after fixing only the launcher. Preserve such
environment failures instead of labeling them product defects or deleting tests.

Exercise the installed pytest scripts as well as a dedicated distribution smoke.
I5 found four omitted P5 artifact fixtures still calling the retired I2 producer
argument, then relying on pre-I3 implicit selection/permissions. Preserve the
failure and baseline comparison; modernize genuine Provider roles/Mapping support
and explicit Exchange intent while retaining the original assertions. Do not
restore the retired product API or count the earlier failed run as passed.

Freeze input bytes before collection. If another worker adds tests in a shared
checkout, separate the immutable base-node inventory from the new tests and
recollect the final tree. Require normal subprocess completion and exact node
multisets; interrupted JUnit may contain a case without a completed result.
Missing process-exit evidence must stay missing. Never infer success from a
zombie process, progress dots, a partial XML case count or another run's badge.
See the [I5 merge preparation](../../../docs/implementation/adr0030-i5-merge-plan.md)
and its independently retained execution receipts.

## Development validation loop (ordinary PRs and stacked iterations)

### Local verified environment

Locally, run validation through `scripts/local-run.sh` after `./scripts/setup-local-python.sh`
([guide](../../../docs/local-python.md)); never with the system Python. Quote the receipt's
`artifacts/local-python/receipt.json` runtime identity and exit statuses as evidence, and report
a failed or unavailable bootstrap rather than substituting another interpreter.

### Hosted Python selection and built-in SQLite identity

When hosted Access fails `SQLITE_RUNTIME` before collection, compare the selected
Python's actual SQLite with the unchanged product guards. `setup-python` 3.12.15
on Ubuntu 24.04 was observed to load 3.45.1; upgrading Python's version selector
alone does not establish support. Use the complete checksum-bound prebuilt Python
selection described in [hosted runtime guidance](../../../docs/ci-python-runtime.md).
Do not repair an interpreter by obtaining or replacing a SQLite component.

Probe before dependencies, after each dependency preparation and inside each
actual installed-artifact venv. Record `sys.executable`, resolved
`sys._base_executable`, actual SQLite/source, compile options and loader mappings.
For built-in `_sqlite3`, `__file__` is absent: bind its `__spec__.origin` and the
base Python executable hash instead. JSON receipts normalize tuple/list shapes
before same-invocation comparisons. These comparisons reject child drift without
requiring an exact SQLite release across environments. Keep independent installed
origin/file checks, factory safety guards and offline protections intact.

An inherited test failure must not prevent later artifact lanes or evidence
audits from running. Retain nonzero outcomes, execute independent later checks
with `!cancelled()` and report unexecuted scopes explicitly. Keep the independent
stdlib-only policy job separate from product dependency preparation.

Measure the selected Python executable/version and `SELECT sqlite_version(),
sqlite_source_id()` before execution. Keep that Python through locked dependency
preparation, subprocesses and installed venvs. Do not obtain/build/install/swap
SQLite for tests or require multiple releases or an exact version/source ID.
Local and hosted SQLite may differ. Preserve product capability/WAL safety checks;
report an insufficient environment as failed/unexecuted work without version
spoofing, skip/xfail, guard bypass or a hidden substitute library. Obtain explicit
owner approval of the reason and scope before a policy exception.

Earlier minimum-runtime setup attempts and failed assertions are historical
receipts. Preserve them as facts; use the current [testing guide](../../../docs/testing.md)
for new executions. Runtime identity checks within one invocation still bind its
receipt, without pinning a release or aligning independent environments.

Review assertion meaning before extending acceptance links. Scope URI grammar
checks do not prove Repository Locator grammar, and a MAX-only restore check does
not prove the older history prefix survived. Link the existing positive repository
grammar and full-history backup/continuity assertions as appropriate; test-name
existence and passing counts are separate evidence.

1. Run focused tests locally while editing. Validate both lint **and format** for source/test changes:
   ```bash
   uv run --no-sync ruff check src tests scripts
   uv run --no-sync ruff format --check src tests scripts
   ```
   Passing `ruff check` alone does not imply format compliance. Before committing
   newly generated/untracked artifacts, stage the intended files and run
   `git diff --cached --check`; plain `git diff --check` does not inspect untracked
   content. Fix whitespace in the generator and regenerate instead of hand-editing
   an output that the deterministic checker will later reject.
2. Freeze the corrected commit and record `git rev-parse HEAD` and `git rev-parse HEAD^{tree}`. Distinguish GitHub's temporary test merge commit from the PR feature commit; compare their effective trees.
3. In ordinary development, local verification is the primary correctness method. Hosted GitHub Actions runs inexpensive static checks, formatting/lint, configuration verification, and smoke checks. Do not require or expect complete hosted test suite execution for ordinary development PRs.
4. Verify that hosted development CI passed its planned checks. A passing development CI run (`acceptance_status=development_checks_passed`) confirms development infrastructure integrity; it does not represent complete release acceptance.
5. On an evidence follow-up, verify unchanged input hashes, tree binding, and recorded test evidence rather than claiming unexecuted tests were rerun.

## Explicit release acceptance loop (release qualification only)

1. Release validation is an explicit, user-invoked operation requiring complete independent testing in both environments (local AND hosted).
2. Local requirement: execute the complete applicable ordinary pytest suite and packaging checks locally on a clean tree, generating a verified receipt:
   ```bash
   python scripts/ci_execute.py receipt --output-dir artifacts/ci-profile
   ```
3. Hosted requirement: execute the complete hosted suite (invoked via workflow dispatch with `mode: release`), isolated wheel/sdist packaging tests, schema/integrity checks, and exact test-node reconciliation.
4. Read the actual workflow job logs and `validation-manifest.json`. Require `full_acceptance=true`, `acceptance_status=complete_release_passed` (or `hosted_release_passed` reconciled via `python scripts/ci_execute.py reconcile-release`), zero unexpected failures/skips, exactly-once selected/executed node reconciliation, and exact input binding.
5. An explicit release validation does not authorize merge, release, publication, or deployment without separate explicit owner authorization.

## Frequent failure modes

- Ruff formatting fails even though lint passed.
- Mistaking a passing development check (`development_checks_passed`) for complete release acceptance.
- Attempting to force full hosted test execution on ordinary development PRs where local verification suffices.
- Stale test receipts presented against a changed Git tree or differing input hash.
- Synthetic or fabricated test node IDs presented in local receipts (rejected fail-closed by strict reconciliation).
- A raw SQLite fixture omits native UDF registration required by the composed production DDL.

Use actual receipts and explicit validation modes, not historical counts or prose claims, to resolve these issues.


## Focused-profile bootstrap failure: preserve evidence and use direct pytest

If `scripts/ci_profile.py profile ...` fails before collection with
`ValueError: option names {'--journal'} already added`, inspect both registrations
before interpreting the run as a product-test failure. The current wrapper loads
`-p scripts.ci_journal`; `tests/conftest.py` also delegates `pytest_addoption` to
that module. Loading both registers the same option twice. A missing JUnit file
then reflects failed bootstrap, not passing or failing test assertions.

Preserve the failed profile's output, command and exit status. When this duplicate
registration is present and CI-infrastructure changes are outside the task's
scope, use the existing conftest registration once through direct pytest:

```bash
focused_artifact_dir=$(mktemp -d)
uv run --no-sync pytest tests/integration/architecture_spikes -q \
  -o junit_family=xunit1 \
  --junitxml "$focused_artifact_dir/junit.xml" \
  --journal "$focused_artifact_dir/journal.jsonl"
```

Use the task's actual focused targets. Do not add `-p scripts.ci_journal` to this
fallback. Check the exit status, selected/executed node IDs, JUnit and journal;
record HEAD/tree and commands with these raw artifacts. A direct run does not
create a wrapper profile/complete release receipt. Report the wrapper failure
separately, and remove this workaround only after verifying that option
registration has one owner and the wrapper succeeds. The implementation-preparation
run diagnosed the duplicate registration and verified this direct invocation; it
did not repair unrelated production CI tooling or claim release acceptance.

## Recover bounded CI receipts from the job log

If a completed run's artifact download is unavailable (for example, the artifact
blob endpoint returns HTTP 403), do not infer receipt contents from a green badge
or change network policy. This repository's tests workflow also emits a bounded
receipt ZIP in its job log. Retrieve the normal GitHub log through the supported
CLI and inspect the actual emitted `CI_RECEIPTS_BEGIN_V1`, `CI_RECEIPTS_DATA_V1`
and `CI_RECEIPTS_END_V1` records. The implementation-preparation run verified this
fallback after an artifact-endpoint 403; the same completed run's log was readable.

```bash
receipt_work_dir=$(mktemp -d)
gh run view RUN_ID --log > "$receipt_work_dir/job.log"
```

1. Parse actual timestamp-prefixed output records, excluding the echoed shell
   script that contains the marker names. Concatenate DATA payloads in order and
   strictly base64-decode them. Verify the exact BEGIN byte length and SHA-256;
   require a matching END digest. Fail closed on missing/duplicate/truncated blocks.
2. Read the ZIP in memory; do not execute contents or blindly extract paths.
   Check every `receipt-index.json` entry's byte count and SHA-256 against its
   archive member. Read `receipt-binding.json` and `validation-manifest.json`.
3. Check run ID/attempt, feature SHA, checkout HEAD and tree. Fetch the actual
   PR merge ref and compare its effective tree with the feature tree; GitHub's
   temporary merge commit SHA normally differs. The manifest's acceptance input
   hash is a separate input contract, not a replacement for identity checks.
4. Report `acceptance_status`, `full_acceptance`, actual hosted executed tests
   and unexecuted coverage. `development_checks_passed` with zero hosted runtime
   tests does not establish full acceptance or validate every local test file.
5. Preserve the verified receipt digest and run URL in the PR/handoff. This is
   an alternative retrieval of the workflow's existing receipt, not a new receipt
   format or permission to bypass a blocked destination, re-sign evidence, claim
   unavailable artifacts were downloaded or launch release qualification.

If `gh run view RUN_ID --log` exits successfully but produces an empty file,
do not classify that as an empty job or missing execution. Retrieve the supported
run-log ZIP using `gh api repos/OWNER/REPO/actions/runs/RUN_ID/logs` and inspect
its text members without executing or blindly extracting them. The final P7
integration-readiness review reproduced empty CLI logs for both Development and
Pages, then obtained actual logs through this REST endpoint. Apply the same
bounded receipt checks above to actual timestamped output, excluding echoed
shell source. Preserve the empty-log attempt and the successful retrieval method;
never infer runtime coverage from a successful API/CLI exit alone. This fallback
does not authorize a new workflow, release validation, deployment or policy bypass.

## Bind child Python processes to the intended worktree

In parallel worktrees, use a separate editable environment for each tested tree:

```sh
uv sync --locked --group dev
uv run --no-sync python -c 'import repo_catalog; print(repo_catalog.__file__)'
uv run --no-sync pytest <focused-targets> -q
```

P2/P3 review reproduced a misleading failure when a reviewer launched pytest with
another worktree's venv and supplied only `PYTHONPATH`: the repository's autouse
network fixture replaced `PYTHONPATH` for child processes. Main-process imports
used the intended source, but child audit commands imported the other editable
checkout. Repeating with the tested worktree's own `uv` environment corrected the
binding and passed the unchanged tests. Record the working directory, interpreter,
actual imported module paths and child environment behavior when diagnosing this.
Do not infer subprocess source identity from the parent's import path or a passed
`PYTHONPATH` alone. This procedure retains the network guard; do not remove it to
force another checkout to import.

An external probe path above the frozen checkout can make pytest select the
parent directory's `pyproject.toml` and prepend the wrong source through its
`pythonpath`, even with the correct editable venv. Use explicit
`-c /absolute/frozen/pyproject.toml` when mixing external probes with a frozen
archive. Assert `config.inipath` and the actual imported validator/module path at
session start before attributing results to that tree. I4 independent review
preserved an old-source failure from this harness mistake, then passed the
correctly bound run. Do not present the misbound run as a regression of the
corrected source.

For imported contract replay tests, reconcile collected node IDs with JUnit
`classname` and test `name`, not its `file` attribute alone. P2's imported P1 test
functions correctly run with the production fixture under a P2 collection module,
while JUnit `file` still identifies the original P1 function definition. Counting
by that attribute would misclassify production verification. The paired receipts
verify all selected IDs against journal starts, each phase and JUnit identities.
For each installed distribution, also assert duplicate-free equality among the
collected node set, normalized JUnit identities and journal starts, with exactly
one setup/call/teardown result per executed node. Equal passing counts alone can
accept substituted node sets. Independent review of the integration-readiness
driver found that gap; explicit three-way identity checks passed on both stored
installed P7 executions. Keep these checks even when their counts agree.

## Revalidate complete originals on the actual intake route

A constructor or pure validator test does not establish validation at Store
intake. Trace its actual callsites, then challenge a previously valid nested
carrier after construction. Run initial admission and exact replay through both
the raw Store and facade. Compare full persistent rowsets, dependency reads,
transaction state and leases on refusal; retain ordinary stage-fence controls.
Use bounded synthetic typed-input mutations, such as replacing a declared
endpoint with None or an invalid state, rather than making an arbitrary-Python
sandbox or Provider-authentication claim.

Reuse the canonical complete-original validator after bounded input accounting
and current authority/selection, before dependency lookup, serialization, writes
or duplicate success. Dependency enumeration must not dereference malformed
convenience properties before that boundary. Never fill an absent original from
stored rows, translated endpoints or Event coordinates. Keep the original
clock/provenance/time and full endpoint declaration. Verify with:

```sh
python -m pytest tests/integration/i6a/test_originals_revalidation.py -q
```

ORIGINALS-M1 demonstrated constructor/replace refusal alongside actual
insert/duplicate and explicit-NULL laundering. The corrected source and both
installed wheel forms refuse those saved counterexamples, while preserving
normal fences and valid original roundtrips. These are implementation checks;
non-Author acceptance and release qualification remain separate.

## Require binding provenance after resolving transport

Resolve .json or .json.gz before testing whether a source-binding artifact is
present. A gzip-aware reader cannot help if an earlier plain-path existence
predicate skips the reader. Require both complete before/after bindings and
compare head, tree, input SHA-256 inventory and tracked status. Missing either
or both is an explicit provenance failure, not evidence of equality. Equal
missing dictionary values do not prove complete evidence.

```sh
python -m pytest tests/unit/test_i6a_regression_bindings.py -q
```

I6A-IR-L01 reproduced consistent=true with null source bindings on the actual
published compressed evidence. Verify the repaired parser on unchanged archives
and separately copied compressed mismatch/missing controls. Never rewrite old
ZIP/JSON evidence to make a new parser pass.

Set UV_CACHE_DIR to a writable external directory in the parent execution
driver before every uv subprocess, including uv pip install into artifact venvs.
Setting it only on uv sync leaves later offline installs using a read-only
home cache. Preserve that setup failure and use a new output directory for the
corrected execution; compare source and artifact hashes across the retry.

## Size acceptance storage and inspect fetch scope

Before broad concurrent acceptance runs, inspect `df -h`/`df -i` for the actual
pytest temporary filesystem and the workspace. Recovery tests retain many
synthetic catalogs. A large workspace does not imply a large `/tmp`: P7's first
parallel full-suite comparisons exhausted the separate 8.8 GiB tmpfs, producing
real, preserved ENOSPC failures. Do not classify the whole failed run as product
regressions or silently erase it. Record the failure and rerun on a sufficiently
sized filesystem with both `TMPDIR` and a new explicit pytest `--basetemp`.
Never reuse/delete an earlier run's directory to make the evidence disappear.
Concurrent reruns need distinct directories and enough aggregate capacity.

Keep installed-test directories outside the source checkout, with an unambiguous
path. The current generic distribution fixture tests checkout exclusion using a
string `startswith`: `/workspace/p7-distribution` incorrectly matches checkout
`/workspace/p7`, even though it is a sibling. Preserve that fixture failure and
rerun in a distinct nonmatching prefix; verify actual site-packages imports.
Prepare the documented external locked wheelhouse first and record
`REPO_CATALOG_WHEELHOUSE`. Initial missing-wheelhouse errors are not successes.

Inspect `git config --get-all remote.origin.fetch` before relying on a refresh.
This workspace initially fetched only main, so plain `git fetch origin` left
feature tracking refs stale. Fetch the intended refs explicitly, compare direct
`git ls-remote` heads before pushes, and preserve a concurrent remote commit
before an ordinary non-force reconciliation. A rejected push is a synchronization
boundary, not authorization to force-push. Evidence-only commits must retain the
frozen executable input hashes; report tested source SHA and final PR SHA apart.

## Classify the first reached failure, separately from future ownership

When a downstream integration test fails during a source fixture, record that
direct exception and the unexecuted stage separately. PR #107's five P5 Exchange
tests stopped in acquisition with UNSUPPORTED_UNTIL_I2; their names did not prove
that an I3 guard or Exchange validation ran. Use a separate I1-seeded source to
exercise the I3 boundary without I2, and keep the original integration failures
visible until I2 supplies their real fixtures. A passing unsupported-boundary
assertion proves refusal, not implementation of the deferred stage. Likewise,
retired API fixture failures precede query behavior; do not claim query acceptance
from those runs or restore a retired compatibility shim just to turn them green.


## Resolve stale status with exact job logs and artifact bindings

If run/job metadata remains queued while cancellation reports completion, verify
rather than infer either state. ADR 0030 integration observed queued metadata
alongside a complete job log and uploaded artifact for the same job/feature SHA.
Use the supported GitHub job-log connector for the exact job ID; preserve the
metadata snapshot, actual log and their discrepancy. Inspect real runtime, pytest
summary, process exits, cleanup and artifact ID. A completed failed run remains
failed even when every newly implemented test passed.

If cloud artifact redirection returns403, the authorized GitHub artifact-download
connector can supply a reusable file reference. Preserve the failed retrieval
without temporary signed URLs. Verify downloaded ZIP bytes against the actual
upload-log length/SHA256, then inspect allowlisted receipt members without blind
extraction. Bind source-revision, archived input hashes, actual SQLite source ID,
collection/JUnit multisets and failure inventory to the feature tree. Distinguish
static development receipts with zero runtime tests from the separate minimum
SQLite job. This is a supported retrieval route, not permission to bypass network
policy, fabricate missing receipts or reinterpret failed acceptance as green.
See the [I2/I3 evidence](../../../docs/implementation/evidence/adr0030-i23/README.md).

## Provider-qualified projections after ADR 0030

When retired Context Repository-field fixtures fail before Query/Search executes,
replace their setup with genuine typed Provider-role observations and explicit
Mapping claims. Do not revive `admit_repository()` or its special field. Current
ownership/base/head must come from `provider_repository_roles(..., evidence=...)`;
retained Core-target rows can outlive a newer unresolved Provider observation.
Verify both facts in the same counterexample, and check repository-filtered lists
as well as the single-resource view. A Mapping Disposition report alone supplies
no receiver operation evidence.

Derivative keys need the complete original role scope, not only Resource, role,
clock and provenance: two equal-clock Provider alternatives can share all those
coordinates while differing in their Provider target. Assert that both survive
Search rebuild and result projection. Preserve current/historical qualifiers and
recompute qualification from authority on every search read. I4's counterexamples
in `tests/integration/i4/test_query_search_backup.py` exercise this boundary;
run `pytest -q tests/integration/i4 tests/integration/p6` on the supported runtime.
These are projection rules, not permission to issue Mapping evidence, rewrite
original keys or infer execution approval from a Mapping.

For backup semantic decoder changes, test the source Stop as well as refusal of
an invalid restored copy. A generic cause-chain classifier may correctly reject
unexpected adapter ValueError as indeterminate yet misclassify a trusted decoder's
proven stored-data violation. Preserve the cause, use an explicit typed invariant
boundary and check both confirmed corruption and existing IO/lock/budget/error
negative controls. Do not classify every ValueError as authoritative corruption.

## Pytest subtest reports are additional measured phases

Pytest 9 unittest `subTest` execution can emit `SubtestReport` call records in
addition to the ordinary node's `TestReport` setup/call/teardown. I6-A's initial
ordinary-suite journals contained 57 passing subtest reports with repeated parent
node IDs. The old strict helper correctly refused its once-per-phase predicate;
that refusal must not be relabeled as strict phase reconciliation or repaired by
silently deduplicating records.

Keep the original journal, JUnit, starts and failure results. For a new execution,
capture each actual report class and subtest context in a separate sidecar hook.
First compare the complete raw journal phase multiset against every sidecar
report; then separately require exactly one ordinary setup/call/teardown for each
selected node and retain every subtest outcome. A failing subtest remains fatal,
even if the final ordinary call reports success. Node-set equality, ordinary
phase completeness and subtest acceptance are separate facts.

The [I6-A Author evidence](../../../docs/implementation/evidence/adr0031-i6a/author/README.md)
retains the original discrepancy and external sidecar/reconciliation helpers.
Its synthetic serial and xdist probes recorded two passing and one intentionally
failing subtest, preserved all raw reports and rejected subtest acceptance. This
procedure changes no product test, skip policy or historical receipt and does
not turn a failing ordinary suite into acceptance.

## Stage installed test support separately and bind pytest imports

When copied artifact tests import `tests.support`, copy the explicit test package
root and required support modules into the external harness. A product wheel
must not acquire a `tests` package to repair a test collection error. Run outside
the checkout with an explicit minimal pytest configuration: `--confcutdir` alone
does not prevent pytest from finding an ancestor `pyproject.toml` whose
`pythonpath = ["src"]` imports the checkout. Keep the offline network guard, but
never add product source to `PYTHONPATH`.

Check product origins and wheel file hashes inside pytest at session start and
finish, as well as in the separate runtime probe. Collect first, then reconcile
the actual selected IDs, JUnit cases and journal starts/phases; a collection error
or equal passing counts cannot establish execution of the required cohort. Use
the installed harness helper and its missing-support/shadow-product regression
controls. Preserve the failed artifact-lane logs separately from corrected runs.

For admission fixture migrations, declare finite identities and permissions at
fixture composition. Never infer grants from an attempted mutation, expand them
after refusal, or add an autouse unrestricted issuer. Keep the real product
transaction owner and commit-held leases. A previous raw `BEGIN`/rollback test
needs an explicit admission-owned rollback scope, not adoption of an arbitrary
caller transaction. Verify out-of-grant refusal, unchanged grants and rows,
revocation after an actual INSERT, rollback, and fixture expiry. File-backed
admission legitimately creates the catalog writer lock; an exact directory
assertion should still exclude extra stores while allowing that required lock.

See the [I6-A remediation evidence](../../../docs/implementation/evidence/adr0031-i6a/remediation-20261023/REPORT.md).
Fixture repair can expose a deeper Provider, Exchange or Recovery failure. Record
the newly reached production callsite and its stage; reaching it is not acceptance
of that stage and does not authorize opening its product route.

Split pytest `::` components only before the first parameter `[` when deriving
JUnit identities: a parameter can itself contain literal `::`. Keep embedded
installed-child traceback frames as well as pytest's outer frames, and label a
legacy source-only projection separately when comparing signatures. For actual
assertion reachability, a counterexample-checked line tracer can distinguish a
setup stop, an entered assertion and an unentered conditional/downstream line.
Report statement-line entry only; it does not establish assertion subexpression
coverage or execution in spawned threads/processes. Diagnostic repetitions stay
separate from the exactly-once ordinary test aggregate.
## Inspect actual sdist members after positive selection

Hatchling 1.32.4 still force-includes `.gitignore` and `PKG-INFO` when sdist
`only-include` lists only package/source metadata. Inspect the built tar, not
just TOML. Under ADR 0033, the common `scripts/check_sdist_contract.py` checks
`.gitignore` against its frozen source hash and enumerates generated metadata;
an unexpected forced file must fail rather than broaden the allowlist silently.
The evidence and regression cases are in `tests/packaging/test_sdist_contract.py`
and `docs/implementation/evidence/adr0033-minimal-sdist-20261022/README.md`.

Request a direct source wheel explicitly. A frontend's default combined build
may itself derive its first wheel from sdist and therefore cannot establish an
independent direct/derived comparison. Compare complete wheel contents and
validated RECORD entries, then retain the separate installed-behavior probes.
This does not authorize removing package data, changing SQLite or treating a
content-only gate as release acceptance.

When independently challenging archive gates, distinguish logical tar members
from the complete compressed input. Python `tarfile` consumes PAX extensions
before yielding a member and stops at the first tar end marker; a successful
iteration alone does not validate unknown extension payloads, appended archives
or gzip trailers. Use bounded synthetic PAX values, a second gzip/tar stream,
and corrupted/truncated trailers as separate negative controls. Independently
check gzip EOF/integrity, record logical regular-file bytes separately from total
decompressed/header bytes, and inspect the backend's actual extension keys before
proposing an allowlist. Never call a raw `gzip.decompress` of an untrusted large
artifact a production-safe bounded validator. The independent ADR 0033 probes at
`docs/implementation/evidence/adr0033-independent-review-20261023/archive/`
reproduce these parser blind spots without extracting files or importing product
code; their nonzero diagnostic exit reports findings, not an incomplete run.

Validate a finite whole-tar byte budget while inflating, before handing bytes to
`tarfile`, and inspect fixed-size physical headers before any extension payload
can be materialized. The hardening checker uses one gzip stream with verified
CRC/ISIZE/EOF, rejects bytes after the trailer, concatenated streams and nonzero
tar padding, and records `tar_stream_bytes` and `raw_header_count` separately from regular-file
bytes and logical members. Its Hatchling 1.32.4 calibration found 159 plain
headers and no PAX keys, so the current extension allowlist is empty. Do not
silently permit arbitrary PAX metadata to accommodate future long paths: inspect
the actual backend output and review bounded keys/values and budgets first.
Reproduce the positive build and bounded negative controls with:

```sh
uv run --no-sync python scripts/check_sdist_contract.py --build \
  --output artifacts/sdist-contract.json
uv run --no-sync pytest tests/packaging/test_sdist_contract.py \
  tests/packaging/test_sdist_hardening.py -q
```

Keep runtime and distribution input fingerprints distinct. README prose is
excluded from CI's `acceptance_input_hash` but included in the sdist's required
`source_inventory_sha256`; README changes select a fresh lightweight sdist check
without forcing full pytest. Matching runtime inputs cannot establish unchanged
distribution inputs. `tests/unit/test_ci_plan.py` covers that boundary and the
shared checker/verifier/fixture routes. These checks remain development evidence,
with independent installed behavior and explicit release qualification separate.

## Preserve line-leading BOMs when recovering strict log receipts

A job-log reader can concatenate chunks with a single U+FEFF at the beginning
of an interior timestamped line. An anchored digit-only timestamp parser then
omits an actual DATA record. Preserve the original log and failed length/hash
result. Permit exactly one optional BOM only before the strict timestamp at line
start; never strip arbitrary characters, whitespace or BOMs from payloads:

```python
r'^\ufeff?\d{4}-\d\d-\d\dT\S+ (CI_RECEIPTS_(?:BEGIN|DATA|END)_V1 .+)$'
```

Keep exactly one BEGIN, ordered DATA and matching END, strict base64, exact
closed-ZIP byte length/SHA256 and compressed bound, unique members, all index
lengths/hashes and actual run/feature/checkout/tree binding. Do not infer missing
chunks or repair payload bytes. The
[integration evidence](../../../docs/implementation/evidence/adr0031-i6b-sdist-c0-integration-20261024/ci-initial/LESSON.md)
retains the original missing-record failure and twelve parser controls, including
rejection of double/payload BOM, missing/duplicated/reordered/corrupt DATA,
malformed base64, duplicate BEGIN and a tampered inner index with a valid outer
hash. These controls verify receipt parsing, not product or Release acceptance.

## Shared package builds must bind the input content

A sealed artifact digest proves the cached output bytes, not that a caller asked
for those inputs. PR #191 found that the normal P1 fixture could prime a shared
cache, then a poisoned-sdist test with a different ROOT/runner would reuse the
normal wheels and never execute its rejection gate. Keep that REQUEST_CHANGES
record as historical evidence.

Use `package_build_inputs` with `build_once(..., inputs=...)`: bind actual working
source bytes (including untracked product files), packaging configuration/lock,
checker/builder and runner contracts, selected Python/uv, wheelhouse bytes and
build environment. A directory name or HEAD alone cannot detect edits at the
same path. Keep normal fixtures on the same sanitized builder/environment
contract so identical inputs still reuse one sealed build. Worker/test display
variables are excluded; meaningful build settings remain part of the digest.

Check input identity before building, before atomic receipt publication and
before returning artifacts. Preserve per-key interprocess locking and exact
artifact hashes. Missing receipts permit only a fresh complete checked build;
malformed/mismatched receipts or missing/changed sealed products fail closed.
Do not infer success from a leftover build directory.

Exercise both normal-to-hostile and hostile-to-normal order, same-path edits,
distinct input trees, corrupt/missing evidence, mid-build mutation and xdist
workers. Focused commands (through the verified project environment):

```sh
scripts/local-run.sh pytest -q tests/packaging/test_p1_distribution.py \
  tests/packaging/test_sdist_hardening.py tests/packaging/test_distribution.py \
  tests/unit/test_build_input_identity.py tests/unit/test_test_efficiency.py
scripts/local-run.sh pytest -q -n 2 tests/unit/test_build_input_identity.py
```

Use a writable `UV_CACHE_DIR` in restricted environments. A read-only uv cache
setup failure is not an archive-gate result. These checks do not retire either
Transfer SQL fence or convert the 43 known Transfer non-successes into passes.

The first PR #192 repair still missed Hatchling's automatic root/control inputs:
R192-01 demonstrated that adding `.hgignore` left the key unchanged although a
fresh sdist was rejected. Product source inventory alone is not backend input
inventory. Inspect the selected backend's automatic inclusion/config discovery
(`sdist.get_default_build_data`, VCS exclusion lookup and metadata config), and
uv's config discovery. Bind root regular files conservatively, inherited VCS
controls with their actual search boundaries, ancestor configuration and selected
user/system/explicit uv configuration contents. Record absence as well as content;
do not patch only the one reported filename. Reject linked/unreadable controls.

Keep real-backend warm-cache challenges for `.hgignore`, `hatch.toml`,
`hatch_build.py` and invalid `uv.toml`: adding an input must execute the fresh
checked builder and expose its refusal, rather than return old normal artifacts.
The R192-01 correction retains failing old-identity controls and green repaired
runs separately. Existing hostile archive gates remain unchanged in strength.

R192-02 found a second blind spot: supported `XDG_CONFIG_DIRS` could introduce a
system uv config without changing environment values. Establish the pinned tool's
actual discovery contract from upstream source, not familiar default paths.
For Linux uv 0.12.19, inspect `uv-dirs` system/user discovery, `uv-settings` and
its etcetera 0.11 XDG strategy. Test ordered/multiple XDG directories, defaults,
empty components, absent-to-present files, mutations, user HOME/XDG settings,
explicit override and intentionally masked configs with the actual uv executable.
Keep private config values out of evidence: bind hashes only. Do not claim another
platform from Linux execution. Relative external settings and project/cwd redirects
need an explicit multi-cwd contract; refuse ambiguous reuse rather than guess.

Account for **every build cwd**. Source config is not enough for a wheel rebuilt
from an extracted sdist. Bind cache/build ancestry in the key and seal generated
working-tree configuration in the receipt; check it before returning artifacts.
Adding/changing config beneath a sealed build must refuse reuse. Keep old unit
and actual-backend red controls separate from corrected green runs. A passing
CI on the old source does not clear an independent FAIL.

F186-01 found that scheduler tests mocking `available_memory_mb` missed the actual
/proc parser: normal MemTotal-first ordering returned total RAM before reaching
MemAvailable. Exercise the real parser with synthetic meminfo in both orders and
assert the resulting worker budget (16 GiB total, 1 GiB available, 8 CPUs and
350 MiB/worker must yield 2). Use a total-memory fallback only after searching
for valid availability. Keep zero availability as pressure, reject malformed or
nonfinite values per record, and retain CPU/affinity/cgroup caps. Missing fields,
malformed earlier records and low-memory cases belong in the focused regression
cohort; a high-level memory mock alone cannot establish parsing correctness.
