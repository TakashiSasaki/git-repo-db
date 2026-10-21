# Frozen product control and runtime basis

This is baseline evidence, not candidate proof or an independent candidate review.
The reference is commit `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree
`117d580b31098ecb8287281bd843894fdfad71fc`. Product source and packaged DDL are
unchanged. The baseline script imports the actual packaged composition and calls
`initialize()` and `connect()`; it does not reconstruct a simplified schema.

## Actual baseline observations

`reproduction/baseline-runtime.py` executes nine direct-SQL controls on each real
runtime. `results/baseline-current.json` and `results/baseline-minimum.json` contain
SQL/parameters, expected and actual outcomes, exception codes, commit/rollback
outcomes, resource rowsets, schema rows, FK inventories, compile options and
connection/reopen pragmas. Both executions passed the expected controls, found
19 tables, an empty `foreign_key_check`, and `integrity_check = ok`.

| Control | Result on both runtimes |
| --- | --- |
| B01: complete baseline Event E9 before Issue I7 | Rejected, `SQLITE_CONSTRAINT_FOREIGNKEY`; transaction rolled back |
| B02–B03: admit I7, then E9 | Both committed with original keys |
| B04–B05: ordinary Comment exists, then Transfer | Comment committed; Transfer rejected by typed FK |
| B06: Issue-parented Timeline Event Transfer via direct SQL | Committed, even without `transfer_event_report` group |
| B07–B09: PR-parented Timeline Event, then Transfer | PR and Event committed; Transfer rejected by typed FK |

B06 is deliberate evidence of the existing division of enforcement: the SQL FK
establishes structural Event typing; it does not establish actual event semantics,
complete report-unit admission or authenticity. The production adapter requires a
`TransferEventReport`, validates `event_type='transferred'`, uses a savepoint,
requires the Issue, retains the coherent report in existing `resource_relations`,
and checks immutable endpoint/scope/time replay. Its direct-SQL factory is trusted
infrastructure, not the supported product public admission API. The candidate's
supported experimental SQL boundary must be declared separately.

## Schema and contract inspected

- `p1_schema.py` still declares `MIN_SQLITE = (3, 51, 3)` and Python project input
  requires `>=3.12`. Composition includes `store_identity`, packaged `context.sql`
  and `coverage.sql`, plus immutable store-identity triggers. `verify_declared()`
  verifies the actual fingerprints before initialization and opening.
- `resources` currently combines native document coordinates and semantic Parent:
  a mandatory Parent FK applies to review/comment/thread/document; the key encoding
  CHECK uses `(parent kind, parent ID, document kind, provider document ID)`.
  Candidate U4=B cannot succeed while retaining this FK as Parent authority.
- `resources_typed_event_fk` is UNIQUE on ResourceKey, `document_kind`, and
  `parent_resource_kind`. The RRR Transfer FK supplies generated `timeline_event`
  and `issue` values, and the six-role CHECK restricts Transfers to `comment`.
- `resource_relations` keeps a coherent group. Its PK is ResourceKey,
  `relation_kind`, whole canonical `members_json`, `provenance_json`, `scope_json`.
  Observation time is nonkey immutable evidence. Generic member syntax/referent
  guarantees are not all expressible by the baseline row CHECK; typed admission
  and stored semantic validation matter.
- Existing `transfer_event_report` relation groups carry original scope, clock
  and endpoint representation. `selective_exchange.transfer_reports()` pairs only
  `(EventResourceKey, clock_json, provenance_json)`, reconstructs typed reports,
  rejects changed immutable payloads and uncovered endpoint rows. `bound_sections()`
  groups report and endpoint rows as one bounded Transfer unit. A selected subset
  of an originally two-sided report cannot be recast as genuinely one-sided.
- `production_context.py` preserves typed admission and separates corruption from
  ordinary missing dependencies; `p1_coordination.validate_pair()` performs
  SQLite integrity/FK and semantic validation. A candidate experiment must not be
  opened through unchanged product fingerprint gates and called compatible.
- ADR 0017 requires genuine semantic composite keys, without storage-only relation
  IDs. ADR 0028 requires original classified microsecond times and canonical
  SHA-256 consistency, not authentication. ADR 0029 preserves the five-store
  boundary and independent durable Context. ADR 0030 Q-S10 explicitly combines
  typed SQL references with actual-event admission checks.
- ADR 0030 Q-E5/Q-E6 and `selective-exchange-contract.md` require explicit bounded
  selection, whole coherent units, truthful missing dependencies and no durable
  unadmitted-body staging. Selection is not permission to invent or register
  otherwise unpermitted dependencies. Original provenance survives relay.
- I4 backup contract uses whole SQLite snapshots and compares full Context rowsets;
  restore checks packaged schema, FK/integrity/domain invariants and paired
  Core/Context identities before fresh activation. A disposable candidate
  snapshot/reconstruction experiment is not product Exchange/backup acceptance.
- Core INSERT-only, six Repository roles, permanent Repository UUIDs, Source
  known-positive membership and five-column Coverage remain separate obligations.
  Baseline controls do not claim exhaustive revalidation of these unchanged areas.

Repository guidance read includes root `AGENTS.md`, ADR index/policy and relevant
accepted ADRs. The scoped investigation and three-store-invariants skills informed
source inspection; the latter explicitly defers to current five-store decisions.
No nested instruction applies under `docs/implementation` in the frozen tree.

## Genuine runtimes

| Role | Python | SQLite | sqlite_source_id() |
| --- | --- | --- | --- |
| Exact minimum | 3.13.5 | 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| Newer supported | 3.12.14 | 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

The minimum is built from the official amalgamation archive using
`reproduction/baseline-build-minimum.sh`. That optional setup builds outside the
repository. `results/baseline-runtime-build.json` binds its source hash, compiler,
flags and official-doc retrieval receipts. It also preserves initial setup
failures: an incorrect configure working directory and the ineffective attempt
to override statically embedded SQLite in default Python. Neither failed attempt
was relabeled as an exact-minimum run.

Run baseline controls from repository root:

```sh
PYTHONPATH=src python docs/implementation/evidence/context-resource-u3-cprime/reproduction/baseline-runtime.py
LD_LIBRARY_PATH=/tmp/u3-sqlite-runtime/minimum/lib PYTHONPATH=src /usr/bin/python3 docs/implementation/evidence/context-resource-u3-cprime/reproduction/baseline-runtime.py
```

The environment's `/usr/bin/python3` is dynamically linked and honors this library
selection. Other machines must independently verify the printed version/source
ID; this is not a portable promise that any default interpreter can be switched.
Full compile-option differences are recorded, not assumed equal. The controls use
stdlib and actual source imports; no dependency installation or version spoofing.
The receipt hashes `pyproject.toml`, `uv.lock`, packaged SQL, fingerprints and
schema composer. The candidate harness must additionally bind its own validators.

Both production factory connections and reopened connections actually set
`foreign_keys=1`, `recursive_triggers=1` before transactions. Initializer uses WAL;
`synchronous=3` (EXTRA), `defer_foreign_keys=0`, `ignore_check_constraints=0`, and
`trusted_schema=1` were observed. Deliberately disabling protections is outside
that supported connection boundary and needs separate labeled probes.

## Official SQLite rules relevant to candidate construction

Retrieved 2026-10-21, with bounded excerpts and full-document hashes in the runtime
build receipt:

- [Foreign keys](https://www.sqlite.org/foreignkeys.html): FK enforcement must be
  enabled per connection before a transaction. Composite child keys with any NULL
  component can avoid the requirement for a matching parent row. Referenced
  non-PK columns need a suitable full UNIQUE key/index and matching collations.
- [Generated columns](https://www.sqlite.org/gencol.html): generated columns can
  participate in UNIQUE, CHECK, NOT NULL and FKs, but expressions are row-local
  deterministic scalar expressions, not lookups/subqueries. They cannot be PK
  columns. Index-backed exact full report references are therefore worth testing.
- [CREATE TABLE CHECK](https://www.sqlite.org/lang_createtable.html): a NULL result
  passes CHECK. Required projected fields need explicit non-NULL guards rather
  than relying on equality that might evaluate NULL.
- [Conflict algorithms](https://www.sqlite.org/lang_conflict.html): REPLACE's
  implicit deletes fire delete triggers only when recursive triggers are enabled.
  IGNORE is not payload comparison or validated replay; FK failures still ABORT.
- [Pragmas](https://www.sqlite.org/pragma.html): record actual configuration;
  `integrity_check` and `foreign_key_check` answer different questions. Application
  semantics and original pre-affinity caller types require additional checks.

These rules motivate adversarial tests. They are not proof that any particular
candidate satisfies them, nor that a structurally consistent report is authentic.
