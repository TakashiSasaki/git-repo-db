# Canonical contracts and retained project records

`docs/` is not a second documentation workspace. It retains the [ADR index](adr/README.md),
accepted decision and governance sources, design/technical contracts under
`architecture/` and existing phase/implementation records, machine-consumed
inputs, and historical evidence in place. Status and authority are determined
by each record and its accepted supersessions, not by its directory or age.
Do not edit dated receipts, archived reports, or their bytes to make them appear
current. The maintained [current runtime guide](current-runtime-reference.md)
lives in the documentation workspace. Navigation banners in historical guides
link directly to it; their original historical bodies remain unchanged.

Some current operational and validation guides remain here because they are
normative inputs or referenced by product/tooling and accepted contracts. Check
callers and authority before proposing a move. Human-facing derived guides and
site sources belong in the separate [documentation workspace](https://github.com/TakashiSasaki/resource-atlas/blob/web/website/README.md);
its [agent instructions](https://github.com/TakashiSasaki/resource-atlas/blob/web/website/AGENTS.md) define publication and
refresh boundaries. A source move does not authorize making it public.

The [canonical persistence mapping](architecture/persistence-model.json) assigns
separated-format tables to logical persistent classes under [ADR 0043](adr/0043-separated-persistence-class-mapping.md).
Run `scripts/local-run.sh python scripts/persistence_model.py --check` to check
structural coverage, or `--format markdown` to print DDL-derived fields, ordered
keys and physical FKs alongside Python input/projection correspondence. Keep the
JSON assignment canonical; generated reports are not another editable source.
Normal startup and web presentation remain independent of this design increment.
Dedicated row classes are checked-in generated product sources in each owning
domain. Regenerate with `scripts/local-run.sh python scripts/generate_persistence_rows.py
--write`, or use `--check` to compare without writing. The version-2 mapping
records `row_type` separately from existing Python input/projection bindings.
Generated/hidden SQL columns are readable but excluded from INSERT bindings;
omitted SQL defaults remain SQLite's responsibility. Codecs check primitive
shape, not admission, recovery or authorization semantics.

For the file-by-file inventory, run `scripts/local-run.sh python scripts/content_inventory.py`
from the repository root. The reviewed `docs/content-inventory.json` records each
non-frozen tracked path individually, including status, source and authority,
producer, consumers, and publication intent. Static consumer references are a
bounded literal scan; dynamic references and ambiguous names are not proven
absent. New nested files require explicit entries. The two frozen evidence
collections are enumerated from their pinned Git trees, including paths, file
modes and blobs; changes or additions fail the inventory check. The checker
refuses assume-unchanged and skip-worktree flags on frozen entries so that Git
cannot conceal modified evidence; it does not change those flags. See each record
and the ADR index for scoped supersessions, rather than treating an inventory
category as new authority.

The checked-in `static_consumer_references` are a snapshot, not a live scan
performed by the inventory checker. To reproduce the literal search for a file
whose basename is unique within the inventory, substitute its basename below:

```sh
rg -l -F --max-filesize 1M --glob '!docs/implementation/evidence/**' --glob '!docs/phase2/reviews/**' --glob '!docs/content-inventory.json' --glob '!*.lock' -- 'BASENAME' docs website src scripts tests .github
```

Exclude the file itself when recording inbound references. If a basename is
shared, inspect full and relative paths manually; neither this scan nor an empty
result establishes that dynamic consumers are absent. Update the recorded
snapshot after evaluating the results.

For each explicit entry, `status` describes the assessed scope of the file;
`owner` is its intended location; `source` names the record itself and
`baseline_git_object` identifies its original mode and blob when present at the
recorded product execution snapshot. `authority` describes how the record relates to accepted
decisions, while `producer`, `consumers`, and `publication` identify the
creation path, known uses, and existing staging intent. `source_heading`, cited
ADRs and status evidence are aids to review, not new authorities.

For numbered ADR files the inventory additionally stores the literal
`status_in_source`. The checker compares it to either the YAML `status:` field
or the bold Markdown status line and fails if neither form matches. This is a
text consistency check, not a semantic decision or proof of implementation;
consult the ADR index and scoped supersessions for that interpretation.

Generated schema presentation files, including `website/schema/README.md`,
come from `website/tools/schema_viz.py` and selected-product neutral IR.
Regenerate them through the documented workflow; do not hand-edit the outputs.
Operator and validation guides that are contracts or tool inputs retain their
existing location. Historical navigation banners point directly to the current
runtime guide; their original bodies remain byte-identical.
