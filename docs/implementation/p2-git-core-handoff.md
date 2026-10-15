# P2 executable Git Core implementation brief

Status: depends on owner review of the P1 stacked PR. P1 depends on PR #70 at
`eb84be9b2061b026ad82b780cc95e062928f838a`. Use the exact accepted P1 feature commit,
DDL fingerprints and review/evidence binding in the PR; do not start from main
alone while those dependencies remain unmerged. This brief authorizes no merge,
production migration, release or P8 initializer switch.

## Stable inputs and first commands

The schema/API specification is [P1 contracts](p1-schema-contracts.md), the full
column inventory is [p1-disposition.json](p1-disposition.json), and the SQL source is
`src/repo_catalog/adapters/sqlite/p1_ddl/core.sql` plus shared `coverage.sql` and the
composed identity/immutable guards in `p1_schema.py`. The packaged
`p1_ddl/fingerprints.json` binds exact SQL and executed SQLite schema.

```sh
uv sync --locked --group dev
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync pytest tests/integration/p1/test_schema.py tests/integration/p1/test_core.py tests/integration/p1/test_notes.py -q
```

These commands are local development validation, not full release acceptance.
Use disposable synthetic catalogs; stateful CLI work always has an explicit
synthetic `--state-dir`.

## Contracts and implementation work

`domain/p1_core.py` provides `OID`, `Provenance`, `ScalarClaim`, `RelationMember`,
`RelationGroup`, `Capture`, `GitObservation`, `RepositoryClaim`, `NativeObject`,
`NotesClaim`, `NotesGroup`, `NotesProof`, `Projection` and scope-qualified
`CoreFailure`. `domain/ports/p1_core.py` fixes Core admission/read and work-budget
ports. Shared Coverage value types have neutral domain ownership; Core-specific
scope construction belongs to Core. Preserve exact accepted signatures and
semantic replay equality; adding production convenience never changes their keys.

`adapters/sqlite/p1_core.py::Core` is the executable reference behavior. Standalone
admission owns one Core transaction per typed unit. `Core.for_transaction(tx)`
binds the same port to the coordinator's active transaction, owns savepoints only
and expires afterward. Use the supported writer/read gate for every catalog
operation. Core-first independent success survives a subsequent Context failure.
No network work occurs while a write transaction is open.

Implement the complete production Git adapter and parser against those ports.
Admit nominal OIDs and metadata without raw bodies, Context, rehashing or complete
Git closure. Whole ordered groups preserve actually supplied coordinates,
unknown/partial/known-empty/complete status and original source evidence. Exact
replay deduplicates; changed immutable evidence coordinates fail closed; genuinely
independent conflicting reports remain separate and yield explicit alternatives.
Do not union groups or choose a report by clock/arrival/source/decoder.

Canonical projections require receiver-checked exact relevant native structure.
An earlier wrong report cannot poison later correct representation admission, and
matching bytes do not promote earlier reports to local verification. Keep decoder
settings and raw/decoded distinctions. Historical canonical metadata is independent
of current byte health; a byte-returning operation checks the exact selected/output
bytes, and detected authoritative corruption invokes the persistent catalog stop.

Retained physical copies are real independently addressable copy occurrences, not
content digests or another alias for a row. Metadata admission permits commit/tree/
tag representations; ordinary blob bodies fail closed. Notes blobs require the
captured root/tree/target/note role proof and exact native/body/digest checks.
Full notes ingestion is P4, but P2 must preserve its typed boundary. Never add a
generic raw-object/CAS, file-text, staging or restore-file endpoint.

## File ownership and dependencies

P2 owns new production Core adapter/parser modules, `domain/p1_core.py`,
`domain/ports/p1_core.py`, `adapters/sqlite/p1_core.py`, Core DDL and focused Core/
notes regression tests. P3 owns its own Context modules/DDL/tests; P2 must not edit
them. Both consume, without independently redesigning:

- `domain/p1_coverage.py`, `p1_schema.py`, shared `coverage.sql` and fingerprints;
- `domain/p1_coordination.py`, `domain/ports/p1_coordination.py` and the coordination
  adapter's catalog gate, callback transaction and pinned snapshot capabilities;
- reconciliation and disposition tooling and P1 shared schema/packaging fixtures.

Shared contracts are frozen by P1. Any necessary shared change is a separately
coordinated dependency commit with affected contracts rerun, rather than simultaneous
edits by P2/P3. Each stage adds its own implementation tests; it does not regenerate
or weaken another stage's contracts to make integration pass. P5 owns acquisition/
Exchange composition, P6 public readers/Search, P7 backup/recovery/activation and P8
the coherent initializer/runtime switch.

## Required adversaries and forbidden paths

Retain the focused P1 nodes and add production parser/admission cases for both Git
formats, arbitrary binary names, supported native headers, missing children, partial
orders, exact same-evidence replay, independent alternatives, rollback at every
intrinsic-unit cut, metadata-only Core with no Context and loss of derivatives.
Exercise correct lexical input when targeting semantic refusal. Test installed
packaged DDL and supported SQL boundaries, including prepared-statement reuse.

No Core UPDATE, DELETE, REPLACE, mutating upsert, FK hydration, progress/revision
counter, counter-history replacement, destructive repair, trigger bypass, GC,
Publication-like completion owner, sender verification promotion or ordinary-file
body archive is permitted. Unsupported grammar reports a typed scoped failure;
it does not silently accept or fabricate missing evidence.

Use independent read-only review subagents for source and actual executed evidence.
Reviewers must not rewrite or approve their own implementation. Fix material
findings, rerun relevant tests and obtain independent revalidation on the exact
feature SHA/tree before submitting P2 for owner review.
