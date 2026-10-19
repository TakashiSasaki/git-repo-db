# Context provider-independence audit evidence

Product source: `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree `117d580b31098ecb8287281bd843894fdfad71fc`. Actual observation date is 2026-10-19 UTC (2026-10-20 JST). [Main report](../../context-provider-agnostic-audit.md), [findings](../../context-provider-agnostic-findings.md), [options](../../context-provider-agnostic-options.md).

## What ran

- **37 added probes passed**, using actual production typed APIs and packaged DDL on SQLite **3.53.1**, Python 3.12.14. [Receipt](results/probes/receipt.json) reconciles the collected and executed unique node sets and verifies unchanged input hashes before/after. `run_audit.py` also rejects source/test/dependency differences from the fixed main.
- **126 existing i3/i23/i4 cases passed**, 378 successful setup/call/teardown phases. [Reconciliation](results/existing-reconciliation.json), [process](results/existing-process.json), [collection](results/existing-collection.log), [JUnit](results/existing-junit.xml), [journal](results/existing-journal.jsonl), [stdout](results/existing-pytest.log). The process receipt was later enriched with the unchanged source/runtime binding; no second execution is implied.
- Schema fingerprint verification passed; 19 composed Context tables. [Environment/source ID/compile options/schema](results/environment-schema.json).
- Independent review executions are separately retained below and overlap existing coverage. Do not add their counts to 163 distinct author cases.

This is focused development audit evidence, not complete release acceptance, a minimum-version test, live Provider integration or a public-runtime switch. Refusal assertions establish the boundary, not support for the refused use. All databases and restore destinations are disposable synthetic fixtures.

## Reproduce

Use a checkout of the audit PR that leaves the product tree unchanged from the pinned main. Install the locked dev group with an interpreter whose **actual** SQLite is at least 3.51.3. Do not change reported version strings or substitute a toy schema.

```sh
uv sync --locked --group dev
uv run --no-sync python -c 'import sqlite3; print(sqlite3.sqlite_version); print(sqlite3.connect(":memory:").execute("select sqlite_source_id()").fetchone()[0])'
uv run --no-sync python docs/implementation/evidence/context-provider-agnostic/reproduction/run_audit.py --output /tmp/context-audit-new-probes
uv run --no-sync python docs/implementation/evidence/context-provider-agnostic/reproduction/run_audit.py --existing --output /tmp/context-audit-new-existing
```

Choose new empty output directories on every attempt. The runner fails instead of overwriting evidence; it hashes inputs, records source/head/module/runtime, collects tests, executes actual pytest, preserves stdout/JUnit and reconciles exact nodes and exit. The committed first existing run additionally used the repository journal; the runner's `--existing` command reproduces the same 126 selected behaviors with its own JUnit-based receipt, not an identical historical timestamp/journal file.

The original existing run command from repository root was:

```sh
uv run --no-sync pytest -c pyproject.toml tests/integration/i3/test_selective_exchange.py tests/integration/i23/test_provider_exchange.py tests/integration/i4/test_query_search_backup.py -q -o junit_family=xunit1 --junitxml docs/implementation/evidence/context-provider-agnostic/results/existing-junit.xml --journal docs/implementation/evidence/context-provider-agnostic/results/existing-journal.jsonl
```

Redirect stdout and record exit to fresh paths when replaying. The project's `tests/conftest.py` registers its journal; do not also add `-p scripts.ci_journal` to that run. Direct pytest avoids the historical double-registration wrapper issue. No product CLI/default initialization change is required.

## Evidence map

| Artifact | Purpose |
| --- | --- |
| `case-matrix.json` | All 12 requested adversarial families, input origin, actual result/classification and exact test nodes; overlapping memberships explicitly marked |
| `reproduction/test_provider_resource.py` | 18 cases for namespace, kinds/parents, annotations, absent OIDs, fields and document identity |
| `reproduction/test_mapping.py` | 9 forward/reverse/multiple/conflict/disposition/absence/replay cases |
| `reproduction/test_coverage_exchange.py` | 10 collection/coverage/generic Exchange/replay/dependency/clock cases |
| `reproduction/run_audit.py` | Non-overwriting execution/environment/input/node receipts |
| `research/provider-sources.json` | Official public URLs, fetched-at timestamps, hashes/excerpts and unsuccessful attempts; no authenticated Provider payloads |
| `research/provider-resource.md` | Detailed A/C investigation; distinction between real specifications and hypothetical inputs |
| `research/mapping.md` | Detailed B investigation, all requested tables and store-placement comparison |
| `research/coverage-exchange.md` | Detailed D/E stage-by-stage investigation and safe Coverage scope limits |
| `results/initial-github-state.json` | Fresh main and OPEN/Draft PR snapshot |
| `results/probes/` | Source-bound collection, execution, hashes and machine-readable verdict |
| `independent-review/r12.*` | Separate review of Provider/Resource and Mapping boundaries |
| `independent-review/r34.*` | Separate review of Collection/Coverage/Exchange/backup and reproducibility |

Research reports are investigator artifacts. Their preliminary local finding IDs/proposed classifications are reconciled in the central findings document; do not sum them as additional findings. Synthetic `MappingOperationEvidence` is explicitly caller-supplied qualification data, not evidence of issuer authentication. Other Provider labels in generic Exchange tests describe pre-normalized synthetic input, not a new API adapter.

## Independent review status

**Approved for this documentation-only Draft PR; no unresolved reviewer findings.** Both separate reviewers inspected frozen audit commit `19ff4031440e541eeff9a119605b2b564ca5dd6d`, tree `c5f8f3cecf30b6ba11f65ff7cd2aad3bdb248c9e`, against fixed main. [R1/R2](independent-review/r12.md) independently reran all 37 probes, 118 focused existing cases and [14 direct assertions](independent-review/r12-probe.py). [R3/R4](independent-review/r34.md) independently ran 11 focused I4 cases and reconciled both author receipts and the case matrix. These overlap author coverage. R3/R4 also verified two post-freeze wording corrections: C12 describes independent reports/provenance rather than new identities, and the original command receipt now spells the full output paths. Their hashes are in `r34.json`; no product/probe change or rerun is claimed. Final follow-up edits add these review records, status and submission checks only. The audit retains 0 Blocking / 3 Major / 2 Minor broader-use findings; reviewer approval does not resolve those designer choices.

## Scope and skills

No product Python/DDL/fingerprint, existing tests, approved ADR, workflow or default-runtime change. No real Catalog migration/deletion/restore, live credential use, release/deployment or merge. The audit branch and Draft PR are the authorized deliverables.

Applied repository skills: [efficient-repository-investigation](../../../../.agents/skills/efficient-repository-investigation/SKILL.md), [three-store-invariants](../../../../.agents/skills/three-store-invariants/SKILL.md) in its explicit opt-in target scope, [ci-final-tree-verification](../../../../.agents/skills/ci-final-tree-verification/SKILL.md), and [lessons-to-skills](../../../../.agents/skills/lessons-to-skills/SKILL.md). Cloud runtime/network guidance was also read through the installed cloud-environment skill. No new skill was created: the reliable procedures used here (source/runtime binding, exact node reconciliation, classification at first reached boundary, and qualified mapping checks) are already covered. New unresolved Provider/clock choices are not converted into skill policy.
