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

Generated schema presentation files, including `documentation/schema/README.md`,
come from `documentation/tools/schema_viz.py` and selected-product neutral IR.
Regenerate them through the documented workflow; do not hand-edit the outputs.
Operator and validation guides that are contracts or tool inputs retain their
existing location. Historical navigation banners point directly to the current
runtime guide; their original bodies remain byte-identical.
