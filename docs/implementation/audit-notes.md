# Boundary audit engineering notes

The audit executes the packaged production composition from `schema.py` in memory,
including `json_contracts.sql`, with the same Git-verification SQL functions
registered by `schema_viz.py`. It finds **70 Core, 10 Operational and 4 Search**
static product tables. The target table total is intentionally unspecified.
`schema-inventory.json` contains the exact production table, view, trigger and
index SQL and fingerprints, ordered composite keys, generated columns, partial
UNIQUE predicates, inbound/outbound FKs and exact source line/function references.
`table-disposition.json` contains an explicit classification and a disposition for
every current column of all 84 tables. The source is never opened as a catalog.

Run:

```sh
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync pytest tests/integration/architecture_spikes/test_audit.py
```

`--check` requires exact table-set equality, complete authored column routing and
byte-for-byte generated artifacts. It detects new tables and columns, changed
composition/fingerprints, triggers, guards, indexes and lexical references. The
reference scan includes SQL constants and table registries. It does not pretend
to solve arbitrary dynamic SQL: [the call-site audit](callsite-dependencies.md)
traces generic Exchange, validators, importer, backup and CLI dispatch. Static FTS
counts exclude SQLite internal tables and runtime `catalog_fts_*` virtual/shadow
tables. Those runtime tables remain derivative Search, never domain authority.

## High-risk mixed boundaries

| Baseline | Column-level target boundary | Concrete implementation consequence |
| --- | --- | --- |
| `repositories` | `repository_uuidv4` is permanent Core identity; `name`, `preferred_repository_endpoint_id`, `metadata` are Context configuration/presentation | Initializing Core never initializes Source/Provider/endpoints or needs a Context FK. Optional independently attributed local Git naming evidence has its own immutable claim, not a mutable repository name. |
| `git_acquisitions` | Actual repository/format/ref-time/endpoint-string/root evidence remains Core; `source_id`, `repository_endpoint_id`, PR `kind` associations belong to Context; execution `request`/start/progress settings belong to Operational | Replace opaque local aliases with genuine capture evidence contract; do not mint notes Captures on retries. Extract only actual necessary immutable provenance from a request; no Core-to-Context FK. |
| `root_origins` | Ref capture/root/name coordinates remain Core; PR/assessment anchors and their association remain Context; `legacy_unknown` remains unknown | Replace all origin/root/assessment integer aliases. Actual order is evidence; do not invent ordinals or ref paths to obtain a key. |
| `snapshots` | Actual capture/ref membership/predecessor evidence remains Core; `generation` belongs to physical Operational cache bookkeeping; `complete` becomes separately admitted immutable scoped evidence | No Core UPDATE, current pointer or implicit union of partial snapshots. A later observed identical ref/root is still a separate genuine observation. |
| `commits`, `commit_parents`, `tree_objects`, `tree_entries`, `tag_objects` | Typed OIDs and attributed scalar/relation groups work without bytes; actual offsets/raw headers/message/tag bytes are permitted exact representation evidence only | Remove mandatory byte/offset/count fields from metadata admission; no late-filled object-ID pointers. FKs use full typed OIDs and genuine whole-group/provenance semantic keys. |
| `git_objects` | `(object_format, full_oid)` alone is nominal identity; `type`, `size` are attributed claims; `verified` becomes independently scoped immutable local evidence | An earlier bad reported type/size cannot block later valid byte verification. Unavailable parent/child bytes do not block true OID relations. |
| `git_object_payloads`, `stored_bytes`, `payloads` | Allowed exact metadata and receiver-role-proven notes body representations only; content digest is not physical-copy identity | Reject ordinary blob bodies before any durable insert, staging, text decoding, cache or Search path. True physical copy identity and checked evidence remain separately attributable. No blob retrieval/restore API follows merely from note eligibility. |
| `contents`, `content_digests`, `blob_content_map` | Remove general file-content authority and integer `content_id`; useful supplied digests remain qualified metadata; checked allowed content references actual representations | A Git OID is not raw SHA-256 or size. Do not run preservation/hydration for ordinary file bodies or synthesize digest claims from absent input. |
| `git_commit_facts`, `git_name_facts`, `git_text_facts` | Commit/name and purpose-bound notes interpretation stays Core with actual decoder provenance; ordinary file `raw_text` has no target owner | Remove generated `git_fact_uuidv4` aliases; use actual subject/settings/value/provenance. Explicit binary-safe notes are not lossy decoded ordinary files. |
| `code_commits` and `code_*` assessments | PR ordered membership, Provider signature/actor reports and head/base/role anchors stay Context; independently admissible reported Git fields may append Core claims | Provider assertions are never receiver Git verification. A Context association may reference committed Core evidence, but it is not Core ownership or complete Git closure. |
| `code_listing_progress`, `preservation_obligations`, `resume_scopes` | Durable domain completeness and necessary original scope remain with their owner; mutable cursor/count/settings/progress belongs to Operational | Operational loss cannot erase facts or prove completion. No ordinary-file preservation obligation survives; automatic retry retains cumulative actual-work scope. |
| `identity_relations`, cancellations, names, staging | Repository identity assertions can remain immutable Core evidence; service/Provider assertions and presentation belong to Context; discardable transport belongs to Operational | Dispatch by actual typed assertion. Retain separately attributable conflicts; no domain truth hidden only in a disposable staging table, and no rewriting permanent identities. |
| Coverage and Exchange | Typed owning domain determines Core versus Context; durable alternatives remain there; transport receipt/deduplication is Operational | Domain replay deduplicates on semantic identity even after receipt loss; no Publication-like resource owner. |
| `database_identity` | True physical-instance/format declaration is immutable; `local_revision` and mutable `lifecycle` cannot remain Core facts | Replace every revision consumer together: request/live-read fences, search snapshots, Exchange export, backup manifests, handover and CLI cursor checks. An append-only counter ledger is not the replacement. |

The machine-readable column routes expand this table for every mixed column.
Current mutable candidates are explicitly listed per product table and qualified
by full production guard SQL. SQL guards allowing write-once pointer filling or
monotonic bit advancement are still incompatible with target Core INSERT-only.
A table having no intended mutable columns does not imply safety from privileged
DDL or arbitrary schema bypass.

## Coverage: five columns and KEY-P01

Production `coverage_claims` has exactly these five columns:
`coverage_claim_id`, `coverage_scope_id`, `coverage_state`, `observed_at_us`,
`details_json`. Its semantic UNIQUE identity is **scope, observation time,
state**; details are advisory. The local integer `coverage_claim_id` and generated
opaque `coverage_scope_id` are storage-only aliases. Neither is grandfathered by
moving the table to Context. Adding an observation UUID would not solve this.

P1 must reconcile the exact five-column **physical authoritative claim relation**
with the normalized direct semantic PK/FK representation, and prove it before
introducing product writes. A five-column view over a six-column authoritative
table is not a solution. A derived API presentation may expose the actual full
semantic claim coordinate but cannot excuse additional physical claim columns.
The representation must not introduce a shorter opaque alias, a sixth claim
column, a new observation identity, a hash-only key or a local-ID translation
authority.
This audit fixes no new target DDL or wire encoding and does not assert that this
engineering gate is already implemented. The real owner scope is typed and
semantic: repository/kind or actual Provider/PR/Source owner/kind. Child marker
and conflict references must address that exact scope/time/state coordinate and
actual original proof subjects. Normalized proof relations remain separate from
the five-column claim and never become a Publication authority.

Preserve the established admission/read contract: stale claims are not promoted;
selection considers the maximal actual observation time, including unknown and
all conflicting candidates; advisory details never break a tie or make a new
claim identity. No older complete fallback is allowed. No terminal observation
is unknown, whereas a real empty terminal observation can be known-empty. Source
membership remains known-positive. Metadata/notes inventory completeness is
distinct from retained allowed-body presence and excluded file restorability.
Required P1/P3/P5 regressions include the five-column surface, same-time competing
states, details-only replay, newest unknown, missing/empty terminal, nested child
head/base scope, reverse transfer and loss/reconstruction of disposable indexes.

## Retention and engineering decisions

This task does not extract, migrate or delete any legacy catalog. A later
explicitly authorized fresh-format extraction must list excluded legacy ordinary
file bytes, preserve source databases/backups unchanged and validate only admitted
typed units in a fresh destination. Admission may omit an intentionally
unacquired body; loss of already admitted permitted bytes is corruption and
triggers ADR 0026 catalog stop/read-only salvage/fresh verified restore/validated
merge. `payload_quarantine` and `unresolved_payloads` have no new active-state
replacement, count or release lifecycle; `payload_admission_staging` is eliminated.

Engineering work includes exact semantic scope encoding, real non-notes capture
and explicit request occurrence contracts, physical-copy coordinates, SQL layout,
proof serialization, finite budgets, cumulative request accounting, read fences
and paired manifests. These require concrete tests and independent review in the
listed stack, not a new owner policy. No new architectural contradiction or owner
blocker was identified. Context GC-03/04 and stronger issuer authenticity remain
deferred; ADR 0027 permits unauthenticated attributed reports without PKI or
signatures. The accepted policy is not being revised by this audit.
