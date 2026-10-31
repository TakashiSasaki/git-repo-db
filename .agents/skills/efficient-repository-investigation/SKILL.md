---
name: efficient-repository-investigation
description: Reduce context output when locating Python code or inspecting large git-repo-db evidence, JSONL journals, JUnit files and compressed logs. Use scoped ripgrep, structural ast-grep queries and bounded summaries before reading complete files.
---

# Inspect narrowly, retain complete evidence

Use this skill when broad source searches or raw evidence reads would return
large amounts of irrelevant text. Keep raw files intact outside model context;
summarize with local tools and read only the relevant locations. A short summary
does not establish full acceptance without the underlying execution receipts.

## Keep the model's input bounded separately from stored evidence

For success, read counts, exit/reconciliation status, source binding and evidence
paths once. Do not print a complete profile JSON, journal, PR body or every job
step to reconfirm a status. In orchestration tools, retain full results locally
and print only the fields needed for the current decision.

For failure, read the compact status and a short failure list, then inspect one
selected node. The default terminal and query excerpts cap long exception text,
parameterized IDs and traceback lines; complete records remain on disk.
Use `--full` or raw `--json` only for a selected diagnostic need, redirect the
result to a file, then project the needed fields or lines before reading it.
Decode CI receipt/Base64 blocks to files; never print their encoded contents.

An output-truncation warning means the query was too broad: narrow its scope
instead of merely increasing the output budget. Apply the same rule to source
reads and tool discovery. Byte/character reduction is not a measured token or
billing reduction; report those quantities separately.

## Select the tool and scope first

- Locate files with `rg --files src tests scripts` before searching their bodies.
  Include hidden agent files explicitly with `rg --files .agents`. Evidence is
  a separate search scope; do not recursively dump the repository or tool catalog.
- Use `rg -l -F PATTERN SUBTREE` for filenames, `rg -n -m 3 -F PATTERN FILE`
  for a few locations, and `sed -n 'START,ENDp' FILE` for a bounded read. `-m`
  limits matches per file, not across the entire repository. Specify a subtree.
- Use installed `jq` for JSON projections and counts. In tool discovery, filter
  tool names/descriptions locally and return only matching names, then inspect
  the selected tool's schema. Printing every description defeats the filtering.
- Use `rg -z -n -m 5 PATTERN LOG.gz` for compressed text. For structured pytest
  evidence use the helper below; do not expand a complete journal into context.

## Python structural queries

`ast-grep` 0.51.0 was installed and exercised for this repository. Prefer the
explicit command name: a pre-existing system `sg` may be a different program.
Keep optional tools outside the checkout and its Python environment. If missing:

```sh
npm install --prefix "$HOME/.local/share/git-repo-db-agent-tools" \
  --save-exact --no-audit --no-fund @ast-grep/cli@0.51.0
"$HOME/.local/share/git-repo-db-agent-tools/node_modules/.bin/ast-grep" --version
```

Use the explicit installed path if `ast-grep` is absent from PATH. Run from the
intended checkout. This example finds Python execute calls and prints a bounded
projection, not their entire containing files:

```sh
ast-grep run --lang python --pattern '$DB.execute($$$ARGS)' \
  --json=compact src/repo_catalog/adapters/sqlite/index.py |
  jq '{total: length, examples: (.[0:8] | map({file, line: (.range.start.line + 1), text: .text[0:160]}))}'
```

Use `rg` for names, comments, literals and SQL text. Use AST patterns for Python
syntax and call shapes. An AST match does not analyze embedded SQL, resolve
dynamic imports/aliases or replace the authoritative boundary/callsite audits.
Validate a query against known positive code before interpreting zero matches.

## Mandatory 5-step agent investigation sequence

When investigating local test executions or CI failures, AI coding agents MUST follow this sequence to maintain token efficiency and prevent context exhaustion:

1. **PR/run metadata and compact summary:**
   Check the execution summary with `scripts/ci_query.py summary <evidence_dir>` or the runner's 1–2 line terminal output. Never download or ingest full multi-megabyte console logs into context.
2. **Failure counts and categories:**
   Inspect `scripts/ci_query.py status <evidence_dir>` to check total, passed, failed, and inherited vs unclassified counts.
3. **Bounded list of new/changed failures:**
   Query only new or changed failures with an explicit limit:
   ```sh
   scripts/ci_query.py failures <evidence_dir> --new-only --limit 10
   ```
   Never query unbounded failure lists.
4. **Exact single-failure traceback inspection:**
   Inspect the specific failing node:
   ```sh
   scripts/ci_query.py failure <evidence_dir> --node <nodeid>
   ```
   This retrieves only the bounded traceback for the target test without reading full logs.
5. **Open raw logs only if indexed evidence is insufficient:**
   If underlying raw logs must be opened:
   - Use `scripts/ci_query.py filter-log <raw.log> -o <clean.log>` to strip large Base64 receipts before viewing.
   - Use `scripts/ci_query.py extract-receipt <raw.log> -o <out_dir>` to unpack Base64 zip receipts directly to disk.
   - Never run bare unbudgeted pytest in agent sessions; always pass `--quiet` (`-q`) and use `scripts/ci_profile.py` or `./scripts/local-run.sh`.

## Summarize actual pytest evidence

The stdlib helper accepts ordinary or gzip files and returns bounded JSON:

```sh
python .agents/skills/efficient-repository-investigation/scripts/summarize_pytest.py \
  --nodes PATH/collection.log.gz --junit PATH/full.xml.gz \
  --journal PATH/full.jsonl.gz --execution PATH/full.execution.json
```

It preserves duplicate counts, compares actual collected IDs with JUnit
`classname`/`name` and journal starts, checks exactly one successful phase of
each kind, and requires successful finish/process exit. It exits nonzero on a
mismatch. Collection prose and blank lines are not test IDs. Small bounded
failure examples are diagnostic; raw artifacts remain the source of detail.

The helper checks evidence consistency, not authenticity, source equality,
default deselections, selection policy, installed import origins or hosted
execution. Apply `ci-final-tree-verification` for those independent requirements.
Do not infer a passed run from a collection-only log or missing process receipt.

Verified examples, tool versions and output byte counts are in
[the local tooling receipt](references/verified-tooling.json). Byte reduction is
not a measured percentage of model tokens, cost or runtime speed. Optional tools
may need reinstalling in a new cloud environment; the skill remains in Git.

## Compare traceback semantics separately from pytest presentation

Keep the raw JUnit/terminal comparison when changing observer output or pytest
traceback style. A saved short frame rendered with "in function" can become a
blank label under a long traceback; that does not establish a changed executed
function. Compare the actual worker ExceptionInfo frames (project path,
function, exception and typed refusal) from recorded sidecars. Retain physical
line-coordinate changes and the original text differences separately. Verify
node/phase identity first, and do not infer that an absent sidecar proves equality.
The [I6-B correction evidence](../../../docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/REPORT.md)
records this distinction and its comparator; assertion statement entry remains
separate from subexpression, other-thread and child-process coverage.

## Audit SQLite expression indexes without losing their semantics

When a schema disposition check fails while sorting index columns after an
expression index is added, inspect `PRAGMA index_info` before changing the
schema: an expression has no column name and SQLite returns `None`. Record a
stable ordinal placeholder for that slot and retain the full index definition
from `sqlite_schema.sql`, including the expression and any predicate. A
placeholder alone does not describe the uniqueness rule. Do not weaken or drop
the index to make the report sort. Verify both the regenerated audit and a
synthetic assertion over the actual expression SQL through the verified local
environment:

```sh
scripts/local-run.sh python scripts/audit_p1_schema.py --check
scripts/local-run.sh pytest -q -n 2 tests/integration/p1/test_ref_observation_i1.py -k audit
```

This addresses expression-index introspection in the P1 schema audit; it does
not certify a live catalog, a migration, or all SQLite schema features.

## Place new evidence outside frozen documentation collections

Before committing a new report or receipt, read `documentation/AGENTS.md` and
[the file ownership contract](../../../docs/README.md). The existing
`docs/implementation/evidence/` directory is frozen to a historical Git tree;
adding files there fails even if those files have explicit ownership records.
Use a separately named non-frozen directory and register every new tracked path
in `documentation/content-inventory.json`, with its actual scope, source,
producer, consumers and publication intent. Preserve all frozen bytes/modes;
do not broaden the checker or publication allowlist.

PR #226 first exposed five documentation ownership failures after successful
product checks. The root cause was new unclassified files inside that frozen
collection. Moving only those new files and registering their exact new paths
lets the ownership checks reach their intended assertions. Verify with the
isolated documentation environment's `documentation/tests/test_content_ownership.py`;
do not repeat an unchanged product cohort for this evidence-placement fix.
Freeze the new paths/manifest first: the frozen-index negative controls deliberately
read `HEAD`, so a staged-only relocation produces a different inventory mismatch.
When launching from the root environment, select `documentation/.venv/bin/python`
explicitly (or clear `UV_PROJECT_ENVIRONMENT` before `uv --project documentation`)
so the root launcher's environment does not select its Python for docs tests.

## Probe supplied metadata before its first serialization

When testing an input boundary that accepts frozen dataclasses, construct valid
fixtures first, then mutate a nested scalar/OID with `object.__setattr__` before
calling the actual application entry point. Constructors and SQLite affinity do
not replace boundary revalidation. Start encoder instrumentation after fixture
construction; pair a large path/provenance value with an exhausted request budget.
Check that reservation precedes validation, hashing, key/JSON construction and
replay comparison, that failed/repeated work accumulates, and that rejected input
does not stop a healthy catalog. Trace native, metadata, paired and Access paths:
a value-only helper's hard bound alone does not establish request accounting.
PR #226 findings R226-01/R226-02 and the scoped regression nodes document this
procedure; do not reinterpret the author's green run as independent approval.

For new Query methods accepting caller work, reuse `_QueryWorkBoundary` inside
snapshot reads and unwrap only outside every Core/paired/application classifier.
A caller's JSONDecodeError must not become a persisted catalog-corruption stop.
Pair callback identity/no-stop tests with genuine stored-corruption stop tests.
When discovering Notes associations, test Group-only reports: a whole Group can
be valid without any standalone Mapping row. Discover bounded headers and let
the checked exact-Claim reader validate members before attributing a target.

## Rename semantic keys through generated selectors and strict wire shapes

When renaming a persisted domain field, audit Python attributes/keyword calls,
SQL PK/FK/generated expressions, canonical JSON and dynamic selectors together.
A literal search misses expressions such as `prefix + "_target_oid"` and
`hasattr(value, "oid")`. Keep external Provider field names and pinned historical
schemas distinct from current internal fields; do not add an alias to hide a
missed caller. Inspect those dynamic expressions and fixture permission inputs
before interpreting an admission denial as a product authorization defect.

Strict Exchange row envelopes compare sorted field-name tuples. A rename can
change lexical order: update the actual row-shape declaration, preserving the
separate semantic identity tuple order. Exercise current typed SHA-1/SHA-256
roundtrips and rejection of old names/versions with recomputed checksums, then
exercise typed salvage and exact-Claim body isolation. The OID naming contract
and `tests/unit/test_ref_physical_format.py` record this verified case. Use the
existing schema fingerprint generator and physical audit for actual DDL changes;
never rewrite historical evidence or loosen exact-field validation to get green.
