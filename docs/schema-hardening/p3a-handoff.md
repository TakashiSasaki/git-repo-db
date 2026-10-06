# P3A operational-source admission and verified phase handoff

This is the English handoff for the bounded P3A slice. It extends the synthetic P2 archive foundation; it does not convert every domain, activate the independent target, or establish that any real database has migrated successfully. The normal application still uses schema v2. The target remains `repo-catalog/catalog3-p1`, schema version 3, lifecycle `building`.

## Repository and evidence boundary

Work started on `design/schema-v2-hardening` / PR #1 at feature HEAD `1e052e4b666039704ad0b8ea3a1d7a752d561358`, with base `9a4110185d7e7abffc291f9cfd118ca71587f998`. The initial base-to-feature delta was 14 commits / 78 files, 38,732 insertions and 26 deletions; these include earlier P1/P2/CI work. The reviewed substantive CI implementation `0d3ca4693a03d5daa8210e2fd3a44dd1e613cd09` and full run [37386072605](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37386072605) are historical evidence: 419 required tests and 228 minimum-runtime tests. The report-only run [37387002516](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37387002516) reused that evidence with zero fresh tests. Neither run proves this P3A change.

Only disposable synthetic source databases and caches are used for P3A verification. No actual user DB/cache, acquisition API calls, normal-runtime migration, active current-pointer publication, real-data dry-run or cutover is included.

## Source admission and preservation

The source identification contract has two distinct proofs. The approved v2 core must match the 53-table/287-column fingerprint and the original 001/002 migration checksums. The complete physical database bytes and complete schema inventory remain part of the seal and resume proof. Recognized derivatives are never removed from the physical identity or admitted solely by a `catalog_fts_` / `sqlite_` prefix.

Every accepted object and column has a machine-readable preservation disposition. Core values remain exact typed archive input. Derived FTS/statistics bytes remain in the hashed sealed source and have an explicit exclusion/rebuild description; they are not original content and do not become independently verified content. Original acquisition facts, index-generation registry and membership rows remain in the core archive.

`sealed.json` records `admission_version: operational-v2/1`, `accepted`, `core_schema_sha256`, `source_schema_sha256`, `source_inventory`, `preservation_dispositions`, `derived_generations`, `capabilities` and admission diagnostics. The existing `schema_sha256` field and `conversion_sources.schema_sha256` continue to mean the strict core fingerprint. `source_schema_sha256` hashes the full inventory, including internal/automatic objects, root pages, stored definitions, table columns/FKs and index metadata. The physical file SHA-256 remains a separate proof.

A classification rejection produces `workspace/source-admission.json` with the complete readable inventory/dispositions, `state: rejected`, `sealed: false` and observed physical `source_fingerprint`. This is a read-only diagnostic observation, not an immutable seal or permission to archive unknown input. It is written through an exclusive part file, fsync and rename under the writer lock; an identical existing report is recognized, while a changed existing report is refused rather than overwritten. Unknown objects remain visible and are not dropped. Earlier filesystem/sidecar/open failures do not promise a schema inventory. CLI errors expose safe codes/counts; the local report may contain source identifiers or definitions and must not be committed/published with real data.

Each disposition records object/type/classification, preservation policy, rebuild source, per-column policy and whether a core table is eligible normalized input. `strict_v2_core` table rows/columns use `exact_typed_archive`; core index/trigger definitions use `sealed_bytes_rebuild_excluded` with `reviewed target DDL` as rebuild source. `application_fts` and `sqlite_statistics` also use the sealed-byte policy with their stated rebuild source. Unsupported input has `blocking_unsupported`. Eligibility is not a claim that the corresponding normalized recipe is implemented.

| Source layout | Admission and preservation |
|---|---|
| Bare v2 baseline | Accept with strict core/migration/identity checks; archive all 287 core columns. |
| One or multiple application FTS generations | Accept only exact `fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)` definitions and locally demonstrated virtual/shadow layouts, valid generation IDs/kinds/states and matching membership/document relations. Keep all FTS bytes in the seal; rebuild later from archived `search_documents`. |
| `building`, `ready`, `retired` or present `unavailable` FTS | Accept when structure and provenance agree. Report complete/incomplete membership coverage and staleness when newer documents exceed the generation bound. No generation is promoted to complete or fresh. |
| Missing `removed` / `unavailable` generation | Accept the documented excluded-missing state; removed generations must have no membership. Registry facts remain archived. |
| `sqlite_stat1`; `sqlite_stat4` when locally demonstrated | Accept exact capability-probed shape and valid table/index references/value types. Keep source statistics bytes in the seal; future target statistics come from ANALYZE over rebuilt target indexes. |
| Supported FTS + ANALYZE combinations | Apply both checks and retain the full combined schema inventory. |
| Unknown table/view/trigger/index, arbitrary `sqlite_` names, orphaned or changed shadow layout | Reject with explicit diagnostics. |
| Wrong FTS columns/options/config, unsafe or conflicting registry, missing live generation, incompatible generation membership or mismatched FTS row IDs | Reject; a name prefix grants no authority. |
| Modified core schema, catalog identity or 001/002 migration ledger/checksum | Reject; never rewrite checksums or drop extras to pass. |
| Malformed core values or a non-FTS registry row that authorizes no derived object | Retain typed values and semantic diagnostics; do not let the row authorize an FTS lookalike or activation. |

The capability probe uses fixed trusted converter DDL in an in-memory database, with extension loading disabled. It demonstrates the case-sensitive trigram MATCH behavior, contentless read interface and actual shadow/statistics layout on the linked binding. Source-supplied DDL is never executed. The recorded evidence has `fts_required` and includes only capabilities needed by the actual source, so unrelated native/minimum compile options do not change a baseline identity. A source FTS layout whose capability/layout is unavailable on the verifier runtime is unsupported even when its name looks familiar; a baseline source does not require FTS support. SQLite STAT4 is conditional on the binding producing the supported layout, not a blanket historical-statistics allowlist.

Component/fixture capability probes may run on an older native binding such as hosted SQLite 3.45.1 when it demonstrates the exact required behavior/layout. The report's `minimum_sqlite: 3.46.1` describes the guarded operational worker requirement; `engine.run` still refuses an older worker runtime.

FTS row IDs and generation membership are checked read-only. The converter does not issue INSERT-based FTS integrity/rebuild commands against the source or claim to prove every posting/content association. Potential stale/incomplete derived search remains explicit and excluded from original-content proof; the sealed file retains its original bytes. This is sufficient for preserving acquired core facts and declaring a later rebuild source, not for trusting the old FTS as a verified search index.

## Verified phase transition

P3A uses one concrete model: a phase-scoped receipt in a second `conversion_runs` row in the existing target. There is no alternate P3 workspace framework and no DDL change. This keeps the P2 run, batches, typed archive, representative maps and diagnostics in place and avoids copying large acquired payloads. The cost is that later phases must explicitly define and verify write ownership before changing any existing normalized output; the P3A receipt does not authorize those changes.

The handoff first verifies sealed source/cache identity, the complete P2 archive against source typed values, mappings, diagnostics, batch input/output proofs, target identity and DDL/contracts. A paused prefix is not a complete archive. The receipt binds the verified parent proof digest, source physical/core/full-schema identities, target identity, converter/contract/phase versions and permitted writes. Its persistent transition identity makes repeated handoff idempotent.

Verification and the receipt INSERT occur under the existing OS writer lock. `before_handoff_commit` rolls back the new phase while leaving P2 usable. `after_handoff_commit` may fail before success reporting, but restart recognizes the already committed receipt and returns the same transition identity. P2 commands reject a P3-owned destination before opening a writable connection; `verify-phase` is the handoff/restart verification command.

An immutable read can expose a spilled but uncommitted receipt while a target rollback journal is hot, so its presence alone is never reported as a committed phase. The bounded recovery path checks recognized run headers and the small receipt, source/target ledger identities, DDL/contract/converter/seal hashes and receipt digest before allowing standard SQLite recovery of the target only. It then rechecks the full parent archive/value/map/diagnostic/output proofs and ownership before any receipt INSERT, archive batch write or success result. The P2 archive can also recover this recognized current-version pending initialization and must prove recovered P2 ownership. `verify-phase` never recovers journals and refuses target sidecars. Writable target journal/WAL/SHM files reject symlinks, hardlink aliases and special files before native SQLite open. Original source sidecars remain unsupported and are never deleted or recovered by the converter.

Exact matching remains the rule within a phase. The handoff verifier also accepts one reviewed P2 predecessor: feature `1e052e4b666039704ad0b8ea3a1d7a752d561358`, converter SHA-256 `644d04524ae83ffeccc0169e7e496328d8dc20f2b7a0a438839f39e271c747d3`, with unchanged DDL/contract/parser and the exact original baseline seal representation. This is a bounded offline verifier, not an ordinary P2 resume upgrade or a hash-ignore option. Other predecessors fail closed.

The phase owns only its own initialization receipt INSERT. It owns no domain mutation. Semantic blockers stay visible and `activation_permitted` remains false. Archive completion, phase initialization and lifecycle validation/activation are separate facts.

The canonical receipt is the second run's `manifest`, with `parser_version: p3a-handoff/1` and state `paused`. Its `source` contains source ID, physical/core/full-schema hashes, seal hash and disposition hash; `parent` contains run/parser/converter identity, the full proof digest and reviewed predecessor revision when applicable. `target`, `signatures`, `write_ownership`, diagnostics and `activation_permitted` identify the destination and permission boundary. `transition_id` is `p3a:` plus the SHA-256 of the canonical receipt inputs, including `committed_at`. That timestamp equals the phase row's start/end times and is reused during verification, so a committed transition keeps the same identity. It is new converter time and does not replace any source observation time.

Receipt verification recomputes those inputs and requires exact canonical equality. It also rejects unledgered rows in unrelated target domains and nonzero publication sequence. Parent evidence includes its entire run/source/identity metadata, batch manifests, maps and diagnostic IDs/timestamps; source comparison independently validates archive values and representative projection relations. The receipt's integrity is a recomputed local proof, not an external signature or permission to edit the parent.

## Guarded synthetic commands

Prepare a disposable v2 source through the real application indexing path before entering the guarded worker. Dependency/runtime preparation is a separate process. Then use the dedicated command:

```bash
uv run --no-sync python scripts/offline_convert.py seal \
  --source artifacts/synthetic-v2.sqlite3 --source-cache artifacts/synthetic-cache \
  --work-dir artifacts/synthetic-conversion
uv run --no-sync python scripts/offline_convert.py archive \
  --work-dir artifacts/synthetic-conversion --representative-repositories
uv run --no-sync python scripts/offline_convert.py verify \
  --work-dir artifacts/synthetic-conversion
uv run --no-sync python scripts/offline_convert.py handoff \
  --work-dir artifacts/synthetic-conversion
uv run --no-sync python scripts/offline_convert.py verify-phase \
  --work-dir artifacts/synthetic-conversion
```

All actions enter the dedicated guarded worker. Linux x86_64/aarch64, local filesystems, CPython connection auditing and SQLite >=3.46.1 remain required. Source/cache/sidecar mutations, network acquisition, extension loading and all child processes, including read-only Git commands, remain denied. Source symlinks/special files, live sidecars and writable hardlink aliases remain unsupported. Keep the original DB/cache available at their sealed paths; this slice does not provide portable resume.

## Validation and CI scope

P3A tests belong to the existing native `p2` and `minimum-p2` lanes, alongside the original foundation/protocol modules. New classifier/phase code remains covered by the `scripts/conversion/**` dependency and converter fingerprint. The real v2 operational fixture and subprocess worker are shared dependencies, so their change conservatively expands selection to full. The original required-ID floors remain; new tests are collected in addition. This prose handoff is explicitly classified as a report, while SQL/contracts/generated views remain executable inputs.

| Test module | Evidence exercised |
|---|---|
| [source admission](../../tests/integration/test_conversion_source_admission.py) | Real application indexing, multiple/retired generations, cancellation after committed membership, stale/partial/missing states, ANALYZE combinations, core/migration drift, malicious lookalikes, runtime capability rejection and bounded old seal representation. |
| [phase protocol](../../tests/unit/test_conversion_phase.py) | Complete/incomplete boundary, exact parent preservation, unsupported predecessor/DDL/contract/source, archive/map/diagnostic tampering even after coherent manifest rehash, receipt/event/owner corruption, competing writer and pre-write P2 rejection. |
| [guarded operational flow](../../tests/integration/test_p3a_operational_flow.py) | Operational FTS+ANALYZE source through the dedicated CLI to seal/archive/handoff/restart; exact typed bytes, stable IDs/maps, relation/diagnostic retention, pre/post-COMMIT faults and abrupt worker exits, genuine hot-journal spill with exact parent rollback, actual competing worker and rejected source/cache/sidecar immutability. |

The final local affected closure passed on the pre-commit worktree, with Python 3.12.14 and converter SHA-256 `f7aa4b38bf91e95173a7c832b016c7add6c46334a9854e652fdea3a39b458362`. It includes all five P2/P3A modules, retaining the original guard/atomicity/resume tests. Both JUnit results were independently reconciled with the 156 pre-collected IDs in `artifacts/p3a-final-selected-ids.txt`; every selected ID passed exactly once with no errors, failures or skips.

| Final local lane | Fresh passed | Reused | JUnit suite seconds |
|---|---:|---:|---:|
| Native SQLite 3.53.1 | 156 | 0 | 11.336 |
| Audited minimum SQLite 3.46.1 | 156 | 0 | 14.094 |

These are focused affected-lane results, not full application/packaging acceptance or hosted-run timings. CI planner/selector and execution tests additionally passed 84 cases; Ruff check/format passed all 112 Python files and `git diff --check` passed. Commands for the final affected closure:

```bash
uv run --no-sync pytest tests/integration/test_conversion_foundation.py \
  tests/unit/test_conversion_protocol.py \
  tests/integration/test_conversion_source_admission.py \
  tests/unit/test_conversion_phase.py tests/integration/test_p3a_operational_flow.py \
  -q -n 4 --junitxml artifacts/p3a-final-native.xml
uv run --no-sync python scripts/run_sqlite_minimum_tests.py \
  --files-from artifacts/p3a-final-minimum-files.json -q -n 4 \
  --junitxml artifacts/p3a-final-minimum.xml
uv run --no-sync pytest tests/unit/test_ci_plan.py \
  tests/integration/test_ci_execution.py -q
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
git diff --check
```

`p3a-final-minimum-files.json` lists those same five test modules. Selection/JUnit artifacts contain synthetic test evidence, not DB/cache/payload files. New policy/shared fixture/worker changes require fresh full hosted acceptance; the historical old-policy CI evidence is ineligible as a P3A reuse claim. See [PR #1's validation record](https://github.com/TakashiSasaki/git-repo-db/pull/1) for the final committed SHA, hosted run/artifact IDs and full-acceptance outcomes. This file records local execution without a self-referential commit SHA.

Independent synthetic predecessor verification ran the authentic original P2 implementation from `1e052e4b666039704ad0b8ea3a1d7a752d561358` on native SQLite 3.53.1: 55 archive batches completed. The current guarded SQLite 3.46.1 worker handed off that old archive, and minimum/native repeated phase verification returned the same transition ID and parent proof. Its 34 blocking / 2 partial diagnostics remained present, lifecycle stayed `building` and activation remained forbidden. This demonstrates the reviewed offline predecessor boundary across those two supported bindings; it does not authorize an arbitrary implementation upgrade or resolve the synthetic semantic blockers.

A temporary audited CPython SQLite 3.45.1 binding, prepared outside converter execution, passed 40 source component tests in 2.03 seconds. Its component-generated all-FTS+ANALYZE synthetic seal had exact source identity when verified on audited SQLite 3.46.1. The real CLI on 3.45.1 correctly returned `UNSUPPORTED_SQLITE_RUNTIME`. This checks older hosted fixture behavior; it does not add an operational converter lane below 3.46.1.

The local native 3.53.1 and audited minimum 3.46.1 bindings do not enable STAT4. Their positive statistics evidence covers `sqlite_stat1`; a STAT4 source is rejected on these bindings because no matching capability layout is demonstrated. Conditional STAT4 admission is not claimed as a positively exercised layout in this validation record.

## What P3B may rely on

- A sealed operational v2 source with explicit per-object preservation decisions and strict core/migration identity.
- Exact typed values for every baseline source column, stable representative repository IDs/maps and retained diagnostics.
- A verified complete P2 parent boundary and persistent phase initialization receipt, with restart/tamper/writer checks.
- The independent target contract, same-owner/sealing/enrichment invariants, and the existing guarded offline execution boundary.

P3B must implement service/source/repository/binding/endpoint/name/membership conversion. Preserve existing IDs; use explicit typed maps for newly allocated identities; never merge repositories by URL or shared OID. Report conflicting legacy identity assertions instead of inventing a binding or choosing the newest name. Review a concrete P3B phase version/write-ownership contract and phase output proofs before mutating domains; the P3A initialization ownership is deliberately insufficient.

P3C stored Git facts, P3D saved API/PR history and P3E integrated normalized comparison remain later slices. P4 defines local reconstruction/reanalysis and derived target index rebuilding; missing originals remain missing. P5 defines the new runtime and first-sync scope reuse. P6/P7 require separately scoped real-data dry-run and cutover/rollback. Archive completion and this handoff cannot satisfy those gates.
