# P1 physical disposition reconciliation

The authored [column routes and physical constraint ledger](p1-disposition.json)
account for **84 baseline product tables and all 625 physical columns**, including
baseline generated columns. Each column has either concrete target store/table/
column references with its encoding and domain meaning, or a reason for
elimination. This is a target representation contract, not a legacy extraction
implementation, compatibility format, or permission to modify user catalogs.

The baseline remains the PR #70 inventory and disposition decisions. The checker
requires exact baseline table/column set equality and preserves its 48 replace,
16 split, 13 move, 4 eliminate and 3 retain classifications. A retained baseline
table receives the same direct semantic-key audit as every other table.

Run from the checkout:

```sh
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync pytest tests/integration/p1/test_disposition.py -q
```

`--check` constructs all four isolated schemas in fresh SQLite memory databases
with required UDFs, foreign keys and recursive triggers. It compares recorded DDL
fingerprints, exact table SQL (including CHECK constraints), physical generated
columns, ordered PKs, UNIQUE indexes, local FKs and trigger SQL to SQLite's actual
introspection. It requires every physical target table to have an explicit
owner, durability, mutation, semantic-key, cross-store and retention contract.
It rejects omitted baseline columns, nonexistent target references, unclassified
target tables, missing Core immutable triggers and prohibited active quarantine/
Publication tables. An explicit list excludes the isolated P1 modules from the historical baseline
source-callsite audit; a regression rejects imports of those modules from the
normal runtime. Both historical audit receipts still reproduce without rewriting
their baseline observations. The separate admission suites test the behavior of these
constraints and the supported connection boundary.

`--write` refreshes physical introspection evidence only after the authored
routes validate. It never invents column routes or ownership declarations. A
new table or a renamed target column requires an explicit authored correction.
The full JSON intentionally records exact SQL, rather than merely asserting
that constraints exist. Packaged DDL construction/fingerprints and installed
wheel tests remain separately necessary.

The isolated schemas currently contain **46 tables: 18 Core, 17 Context,
8 Operational and 3 Search**, including one physical `store_identity` table in
each file. The JSON records exact current composed fingerprints; schema changes
must regenerate that evidence. No unclassified baseline column or target table
is allowed. Production Schema 21 and its initializer remain separate.

The important mixed routes are concrete:

- Permanent `repositories.repository_uuidv4` goes to Core `repositories` and,
  independently when needed, Context `repository_context`. Provider names,
  endpoint configuration and Source registration never become required Core
  dependencies.
- Git acquisitions, roots, refs, snapshots, manifests and membership use actual
  Capture occurrence coordinates plus typed `git_observations.kind`, complete
  semantic `scope`/`value` and original provenance. Optional actual fields such
  as peeled OID, predecessor, raw path, endpoint and completion evidence survive
  within their named typed observation. Mutable cache generations and acquisition
  progress belong to Operational. Existing local aliases are removed.
- Object attributes use typed scalar claims; parent/tree/tag relationships use
  whole immutable ordered relation values. Exact raw metadata bytes remain
  optional checked native representations. Raw headers/message metadata may
  independently be reported as lossless attributed fields. Counts, binary names,
  actual offsets and complete decoder settings have explicit column routes;
  decoder hashes and mutable target-resolution pointers do not survive.
- Provider entities use full service/resource-kind/provider-resource identities.
  Child document identity additionally preserves actual parent, document kind
  and Provider document ID. Current fields retain original per-field source
  clocks/provenance; Context relations retain whole actual membership/roles/
  paths/patches/scope. Source-only empty inventory has its own durable
  `source_inventory_evidence`; it needs no fabricated Provider resource or known
  repository membership.
- Coverage scopes retain normalized typed ownership and CHECK-equal reversible
  whole coordinates. Both authoritative stores have exactly five actual claim
  columns. Claims are keyed by full owner kind/coordinates, actual observation
  time and state; advisory details do not create a new claim. Dependencies use
  full semantic claim/terminal references. The old local claim/scope/marker
  aliases and global Exchange-blocked eligibility rows are eliminated.
- Repository identity assertions/cancellations use Core repository claims when
  they describe repositories; service/Provider assertions remain Context. An
  assertion does not rebind or replace the permanent repository UUID.
- Ordinary-file body/digest/text preservation and generic decoded file content
  are excluded. Useful genuinely supplied digest/size metadata may remain
  attributed claims. Exact commit/tree/tag and role-proven note representations
  have concrete allowed targets; no general blob-content map, opaque rejected
  body staging, active quarantine state or same-database repair survives.

Whole-value encodings store the actual semantic value with canonical lossless
JSON, including full original coordinates and ordered membership. They do not
create shorter opaque scope aliases, hash-only claim keys, independent row IDs,
or invented event/time evidence. Source legacy aliases cannot manufacture
missing genuine source coordinates: an eventual extractor must reject an
inadmissible unit while preserving independent valid units. Physical-copy UUIDs
and actual request/attempt/Capture occurrence UUIDs identify those genuine
occurrences, not join convenience. Context text SHA-256 is a checked body-content
address, distinct from the full semantic resource/field claim key.

The checker does not prove arbitrary application data flow, truthful external
attribution, privileged filesystem/DDL protection, or P2–P8 implementation. The
JSON specifies where each allowed meaning is represented; complete acquisition,
Exchange extraction, parser expansion, Search integration and recovery activation
remain the assigned later stages. P1's admission/coordination tests provide
executable boundary evidence without claiming the eventual public runtime has
already switched.
