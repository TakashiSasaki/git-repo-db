# Canonical contracts and retained project records

`docs/` is not a second documentation workspace. It retains the [ADR index](adr/README.md),
accepted decision and governance sources, design/technical contracts under
`architecture/` and existing phase/implementation records, machine-consumed
inputs, and historical evidence in place. Status and authority are determined
by each record and its accepted supersessions, not by its directory or age.
Do not edit dated receipts, archived reports, or their bytes to make them appear
current. Existing `current-runtime-reference.md` is a navigation pointer retained
for historical links; the maintained derived guide lives in
[documentation/](../documentation/current-runtime-reference.md).

Some current operational and validation guides remain here because they are
normative inputs or referenced by product/tooling and accepted contracts. Check
callers and authority before proposing a move. Human-facing derived guides and
site sources belong in the separate [documentation workspace](../documentation/README.md);
its [agent instructions](../documentation/AGENTS.md) define publication and
refresh boundaries. A source move does not authorize making it public.

For a file-by-file inventory and role definitions, run
`documentation/.venv/bin/python documentation/tools/inventory_content.py` from
the repository root. It emits one role and owning location per tracked path in
the defined scope and refuses unclassified root paths or new top-level sections.
The inventory does not reinterpret old findings as current acceptance.

The inventory's `canonical-adr-and-governance` and
`canonical-architecture-source` roles identify locations whose actual binding
scope is resolved through the ADR index. `machine-structured-artifact` covers
tracked structured inputs and inventories outside immutable evidence directories;
check consumers before editing them. `retained-engineering-record` covers
plans, design/contract handoffs, dated reports and other engineering records;
individual records identify whether they are active contracts or historical
snapshots, and their placement does not create new authority. `historical-evidence`
identifies the large `implementation/evidence/` and `phase2/reviews/` collections;
preserve their bytes and links. Operator/validation guides remain in `docs/`
because existing entry points and policy consumers refer to them. The single
historical-link pointer is intentional: the navigation blockquotes in `cli.md`, `data-model.md`, `implementation-status.md`, and `model-integration-status.md` refer to it,
so retaining it avoids rewriting those evidence documents. This is navigation,
not a second editable guide.
