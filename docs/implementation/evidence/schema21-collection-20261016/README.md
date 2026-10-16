# Schema 21 collection contract restoration

Base: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c` (unchanged public main).

The public three-store contract is ADR 0002 PF-P04/P06/P07/P12. Core owns
collection identity, normalized resources, pages and terminal evidence;
Operational owns jobs, attempts and collection progress. Tests previously queried
Operational tables through Core or joined them into Core SQL. The shared `sync`
fixture did so before many behavioral assertions were reached.

`collection_rows` performs two explicit, independent read snapshots after the
operation is quiescent. It offers no cross-store atomicity, completion authority,
ATTACH, aliases or compatibility tables. Existing domain-behavior assertions are
preserved. Restart checks now follow `ApiFacts.begin`: without a terminal Core
marker, fresh root acquisition preserves admitted resources and does not complete
the old collection. Retired `incremental_scans` is asserted absent from schema,
while the surrounding real incremental-acquisition behavior remains exercised.

Checkpoint: the added positive/negative physical-boundary regression passed
(1 node; JUnit and per-phase journal under `checkpoint`). Ruff passed across the
eight changed test/fixture files. The complete owned cohort is still under
investigation at this checkpoint; this is not final acceptance evidence.

Explicit replacement-node map (parameter suffixes preserved):

- `test_resumed_child_observation_governs_its_thread_without_new_root_request`
  -> `test_resumed_child_observation_governs_its_thread_after_fresh_root_request`.
- `test_thread_children_resume_from_normalized_committed_prefix`
  -> `test_thread_children_restart_with_retained_normalized_committed_prefix`.

No production implementation or schema has changed.
