---
name: efficient-repository-investigation
description: Reduce context output when locating Python code or inspecting large git-repo-db evidence, JSONL journals, JUnit files and compressed logs. Use scoped ripgrep, structural ast-grep queries and bounded summaries before reading complete files.
---

# Inspect narrowly, retain complete evidence

Use this skill when broad source searches or raw evidence reads would return
large amounts of irrelevant text. Keep raw files intact outside model context;
summarize with local tools and read only the relevant locations. A short summary
does not establish full acceptance without the underlying execution receipts.

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
