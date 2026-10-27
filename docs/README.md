# Canonical contracts and retained project records

`docs/` is not a second documentation workspace. It retains the [ADR index](adr/README.md),
accepted decision and governance sources, design/technical contracts under
`architecture/` and existing phase/implementation records, machine-consumed
inputs, and historical evidence in place. Status and authority are determined
by each record and its accepted supersessions, not by its directory or age.
Do not edit dated receipts, archived reports, or their bytes to make them appear
current. The maintained [current runtime guide](../documentation/current-runtime-reference.md)
lives in the documentation workspace. Navigation banners in historical guides
link directly to it; their original historical bodies remain unchanged.

Some current operational and validation guides remain here because they are
normative inputs or referenced by product/tooling and accepted contracts. Check
callers and authority before proposing a move. Human-facing derived guides and
site sources belong in the separate [documentation workspace](../documentation/README.md);
its [agent instructions](../documentation/AGENTS.md) define publication and
refresh boundaries. A source move does not authorize making it public.

For the file-by-file inventory, run `documentation/.venv/bin/python documentation/tools/inventory_content.py`
from the repository root. The reviewed `documentation/content-inventory.json` records each
non-frozen tracked path individually, including status, source and authority,
producer, consumers, and publication intent. Static consumer references are a
bounded literal scan; dynamic references and ambiguous names are not proven
absent. New nested files require explicit entries. The two frozen evidence
collections are enumerated from their pinned Git trees, including paths, file
modes and blobs; changes or additions fail the inventory check. See each record
and the ADR index for scoped supersessions, rather than treating an inventory
category as new authority.

The checked-in `static_consumer_references` are a snapshot, not a live scan
performed by the inventory checker. To reproduce the literal search for a file
whose basename is unique within the inventory, substitute its basename below:

```sh
rg -l -F --max-filesize 1M --glob '!docs/implementation/evidence/**' --glob '!docs/phase2/reviews/**' --glob '!documentation/content-inventory.json' --glob '!*.lock' -- 'BASENAME' docs documentation src scripts tests .github
```

Exclude the file itself when recording inbound references. If a basename is
shared, inspect full and relative paths manually; neither this scan nor an empty
result establishes that dynamic consumers are absent. Update the recorded
snapshot after evaluating the results.

For each explicit entry, `status` describes the assessed scope of the file;
`owner` is its intended location; `source` names the record itself and
`baseline_git_object` identifies its original mode and blob when present at the
pinned product revision. `authority` describes how the record relates to accepted
decisions, while `producer`, `consumers`, and `publication` identify the
creation path, known uses, and existing staging intent. `source_heading`, cited
ADRs and status evidence are aids to review, not new authorities.

For numbered ADR files the inventory additionally stores the literal
`status_in_source`. The checker compares it to either the YAML `status:` field
or the bold Markdown status line and fails if neither form matches. This is a
text consistency check, not a semantic decision or proof of implementation;
consult the ADR index and scoped supersessions for that interpretation.

Generated schema presentation files, including `documentation/schema/README.md`,
come from `documentation/tools/schema_viz.py` and selected-product neutral IR.
Regenerate them through the documented workflow; do not hand-edit the outputs.
Operator and validation guides that are contracts or tool inputs retain their
existing location. Historical navigation banners point directly to the current
runtime guide; their original bodies remain byte-identical.
