# ADR 0036 acquisition input checkpoint

## Source and authorization

- Environment: cloud project `/workspace/git-repo-db`; no local-PC work.
- Re-fetched main/parent: `2ff4aab59dcdbada264d9a6a978c07b6ac4ad0d2`.
- Implementation and actual test HEAD: `dde476ce454843a98320585a164272ad0a842711`.
- Implementation/test tree: `1300625f7d5c05162ca6d88ee57fd3389c769e2e`.
- Branch: `codex/adr0036-acquisition-inputs`, directly on main, no stacked PR parent.
- Main remained unchanged on the second fetch. Open PR search returned zero
  before work. Current AGENTS and relevant repository skills were read.
- Owner scope: reassess the dated plan, implement the first necessary coherent
  unit, test it, create a Draft PR, then await the parent's independent review.
  No merge, deployment, formal approval, branch deletion, permission change,
  real-catalog operation or repeat of PR #221/#223's callback repair.

## Decision and implemented boundary

The current [transition contract](../adr0036-legacy-consumers-contract.md)
records the disposition of all six proposed stages. Existing observation,
enumeration, Claim-aware Query, inventory proof and typed-salvage APIs already
exist. A standalone D0 and fixed six-PR stack are unnecessary. Explicit
new-model acquisition input remains necessary; generic Query/paired resources,
Search and coordinated legacy API/family retirement remain later work.

`RefNotesInput` carries an original immutable subject, multiple result Claims and
reported Mapping Claims/Groups, with explicit repository and Claim binding.
It carries no receiver evidence or body. Request replay binds every coordinate,
including raw non-UTF-8 ref/symbolic bytes. Imported metadata alone authorizes
neither retained Notes nor complete Coverage. Rootful supplied Claims independently
use the existing native receiver proof/body paths; unknown/absent or source-missing
requested work is reported as deferred. Paired preparation retains all supplied
Claims, with inventory verification after the existing coordinated commit.

The new explicit-input path produces no Capture/legacy Notes row. Legacy
explicit inputs and dual discovery production remain for actual downstream
consumers. No schema, fingerprints, wire family, shared grammar, ordinary
GitObservation/discovery ID, Query/Search implementation, backup or salvage
implementation changes. No prior behavior test was removed or weakened.

## Actual development verification

All product commands used `scripts/local-run.sh` and the verified project
environment: Python **3.12.15**, Python-loaded SQLite **3.53.1**, **x86_64**.
The bootstrap receipt includes runtime hashes/capabilities and preflight.
The first bootstrap could not write its default home under the read-only
filesystem. The documented `GIT_REPO_DB_PYTHON_HOME` and `UV_CACHE_DIR` were set
under `/workspace/runtime`; the normal verified bootstrap then passed. No Python
or SQLite guard was bypassed, and SQLite was not independently replaced.

The frozen profile command was:

```sh
scripts/local-run.sh python scripts/ci_profile.py profile \
  --name adr0036-inputs --output artifacts/adr0036-inputs --workers 2 -- \
  tests/unit/test_native_acquisition_values.py \
  tests/integration/p5/test_ref_notes_inputs.py \
  tests/integration/p5/test_ref_inventory_wiring.py \
  tests/integration/p5/test_git_acquisition.py
```

Result: **241 passed, 0 failed/error/skipped/unexecuted**, child/process exit 0,
81.71 seconds elapsed with two workers. The profile runtime records the clean
implementation HEAD/tree above. The existing runner reports
`ALL_PASSED_UNVERIFIED_SELECTION` for an ad hoc profile; this raw status is
preserved. Separate collection on the unchanged tree and the existing
`summarize_pytest.py` helper reconciled **241 selected = 241 starts = 241 JUnit
cases**, exactly **723** successful setup/call/teardown phases, successful finish
and process exit. Its `consistent_success` is true. That consistency helper
does not itself bind source; the profile's `runtime.commit_sha`, `tree_sha` and
`dirty=false` provide that separate recorded binding.

The 60 new-input cases cover SHA-1/SHA-256, bare/non-bare, native/metadata and
Core/paired admission; original unauthenticated reports and non-UTF-8 identity;
multiple roots plus present/unknown/absent Claims; source-unavailable deferral;
reported Group versus receiver proof; body permission and no target-body archive;
same-request replay, changed-intent refusal and cumulative work; foreign subject
and finite-budget refusal. Existing wiring regressions cover caller-owned
transactions, paired commit/post-commit failure, corrupted stored proof stop,
callback exceptions/reentry and shared-snapshot Coverage. Existing native/Git
tests cover preserved acquisition behavior.

Additional checks passed: changed-file Ruff check, Ruff format check,
`git diff --check`, and `scripts/local-run.sh python
scripts/audit_p1_schema.py --check` (zero unclassified schema items).

An initial dirty-tree probe passed 52 tests before the additional assertions and
eight cases were added. Its initial collection failed on a mistaken test import;
the import was removed before execution. Both original failure and corrected
probe logs are preserved. The final 241-case profile includes the final new-input
cohort; probe counts are not added to it. The final profile was required to bind
complete evidence to the clean implementation commit; it is not release testing.

Complete logs, JUnit, journals, profiles, final node reconciliation, initial
failures, setup receipt and local development plan are in
[`local-profile.tar.gz`](local-profile.tar.gz), with lengths and SHA-256 in
[`archive-index.json`](archive-index.json). The original uncompressed evidence
also remains at `artifacts/adr0036-inputs` in this environment.

## CI and limits

The common development planner selects static/smoke and leaves ordinary full
tests/packaging not applicable. That selection is not evidence that those scopes
executed. Product changes trigger `tests`, Access-registry verification and the
documentation preview workflow; the latter still prepares documentation tools
independently. No workflow or skip policy was changed. Hosted statuses/URLs must
be checked against the final Draft PR HEAD and reported separately at handoff.

No full local suite, installed wheel/sdist behavior, hosted full release,
cross-architecture validation, actual recovery/migration or documentation-site
publication was performed. Ordinary Schema 21 stays default. The eventual
physical cut still needs Exchange, backup, salvage and collision-guard acceptance.

Next: parent reviews this fixed candidate independently; then migrate generic
Query/paired resource/CLI projections, Search identity/extraction, legacy API
producers and finally physical/wire/recovery families in dependency order.
No owner-policy blocker was found for this input boundary. B03/exact grammar,
normal-format activation and release qualification remain separate scope.

Skills used: cloud-environment runtime, efficient repository investigation,
three-store invariants (target/baseline distinction), CI final-tree verification
and lessons-to-skills assessment. The efficient-investigation skill records the
verified frozen-evidence placement lesson below. Model identifier and effort are not exposed by the
execution evidence, so no specific values are asserted. No independent review
or APPROVED status is claimed by the implementation author.

## Evidence-placement correction after the initial CI

Initial candidate `f25fb4e600b1abd051c3d4da29f220ebe7ac6869` passed
[product CI](https://github.com/TakashiSasaki/git-repo-db/actions/runs/41060535402)
and [Access-registry CI](https://github.com/TakashiSasaki/git-repo-db/actions/runs/41060535476).
The former executed static/smoke, schema guards and minimal sdist checks; its
full test/installed-artifact steps were skipped by the common development plan.
The latter executed preflight, ownership/format checks; broad/installed suites
were likewise skipped. These green jobs are scoped development evidence.

[Initial pages preview](https://github.com/TakashiSasaki/git-repo-db/actions/runs/41060535526)
passed schema visualization freshness, then failed five documentation ownership
cases (100 others passed). The three newly added evidence files were unclassified
and inside `docs/implementation/evidence/`, a historically frozen tree. This
was an author evidence-placement error. Move only those new files to
`docs/implementation/adr0036-inputs-evidence-20261030/` and register their exact
paths in `documentation/content-inventory.json`; leave the frozen tree and its
guards intact. This also corrects the report's relative contract link. No
derived diagram or site content refresh is required.

The failed job's complete log and downloaded 9,217-byte documentation artifact
remain at `artifacts/adr0036-pages-job.log` and
`artifacts/pr226-documentation-verification.zip`; the remote artifact is
`documentation-verification-41060535526-1` (ID `12977914324`, seven-day retention).
The original local product archive remains byte-identical after relocation.
Product source/tests, scripts, dependencies and schemas remain unchanged from
the clean tested implementation commit; no product cohort is rerun solely for
this correction. Common acceptance-input hashes differ because the added
evidence JSON/archive are conservatively included; they are not presented as
equal or as complete release evidence. Final HEAD/tree and final CI status are
reported separately at handoff.

The first local ownership launch failed before test execution because it used
uv's read-only default cache. Retrying with the setup cache ran 16 cases: 14
passed and two frozen-index negative controls failed because their temporary
index reads `HEAD`, while the relocation/manifest were still staged. That uv
launch also inherited the root environment selector. Preserve those receipts
under `artifacts/adr0036-docs-ownership`; freeze the correction and run the
ownership cohort with the explicit isolated documentation Python. Do not
classify the earlier local invocation as isolated-documentation acceptance.
