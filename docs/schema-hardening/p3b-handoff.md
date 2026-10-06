# P3B identity conversion handoff

This handoff covers offline identity conversion into the independent
`repo-catalog/catalog3-p1` version 3 target. The ordinary application uses v2.
Only disposable synthetic databases and caches are used. Archived bytes,
normalized identity execution, semantic readiness and activation are separate
results; activation remains forbidden and lifecycle remains `building`.

## Repository boundary

The starting feature SHA was `e40430e3f38d3339d67017a04262445f9415a8ec` on
`design/schema-v2-hardening`, PR [#1](https://github.com/TakashiSasaki/git-repo-db/pull/1).
The fetched base was `9a4110185d7e7abffc291f9cfd118ca71587f998`. The starting
base-to-feature delta comprised 15 commits and 85 files, 41,511 insertions and
26 deletions. PR #1 was open, with no newer feature changes to overwrite.

Run [37392666849](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37392666849)
is historical P3A evidence for that starting feature: 520 normal, 2 isolated
packaging and 317 minimum-SQLite tests. It does not validate P3B. Final committed
SHAs and fresh hosted acceptance will be recorded after implementation and
verification; there is no merge, real-data migration or runtime switch.

## Guarded commands and ownership

All commands enter the existing dedicated worker and require Linux, audited
SQLite >=3.46.1, immutable input evidence and the OS writer lock. Dependencies
and authentic predecessor fixtures are prepared outside that worker.

```bash
uv run --no-sync python scripts/offline_convert.py identity-init \
  --work-dir artifacts/synthetic-conversion --batch-size 100
uv run --no-sync python scripts/offline_convert.py identity \
  --work-dir artifacts/synthetic-conversion --batch-size 100 --max-batches 2
uv run --no-sync python scripts/offline_convert.py identity \
  --work-dir artifacts/synthetic-conversion --batch-size 100
uv run --no-sync python scripts/offline_convert.py verify-identity \
  --work-dir artifacts/synthetic-conversion
```

The source must already have a complete typed P2 archive and a verified P3A
receipt. `identity-init` establishes a distinct `p3b-identity/1` owner in the
existing `conversion_runs` ledger before domain writes. Exact resume remains
mandatory within P3B. The accepted reviewed P3A predecessor is the authentic
implementation at the starting SHA; synthetic tests execute that historical
converter to demonstrate the upgrade instead of relabeling a current workspace.

The receipt binds the source physical/core/full-schema identities, seal and
preservation dispositions, exact P3A run/receipt bytes and original P2 proof,
target instance/DDL, converter fingerprint, conversion and invariant contracts,
encoding, batch size, recipe order and explicit write ownership. P3A predecessor
acceptance is limited to its reviewed converter/contract pair. Existing P2/P3A
commands keep their original exact rules. There is no force-resume or hash-ignore
mode, and changing converter inputs inside P3B refuses continuation.

No target DDL transition is necessary. The unchanged complete DDL has 74 STRICT
tables and SHA-256
`fd39297f3b73abc190aa82a28164f2d496048d773cbbcc9039a54972046a5709`.
The executable `p3b_identity` contract specifies each recipe's source key,
dependencies, transform, target key, ownership, diagnostics and validation.
Existing reviewed production semantics are pinned separately; a structurally
valid contradictory production cannot silently change the conversion policy.

## Immutable parents and phase-aware proofs

P2 typed records/values, conversion source/run, committed batches, historical
map IDs and diagnostic IDs/times remain unchanged. P3A receipt and run bytes
remain unchanged. New batches and diagnostics belong to the P3B run; new maps
are linked to archived source keys and enumerated by their committed P3B proof.
Reason strings alone do not establish ownership.

The parent proof view substitutes only the independently derived original P2
repository projection and excludes only explicitly P3B-owned evidence. Original
P2 repository hashes remain historical proofs. P3B separately compares every
current repository's name/metadata/ID against source even before its repository
batch has run. The only allowed enrichment is a NULL preferred endpoint pointer
to the exact source-proven same-owner endpoint; its before/after relation has a
separate P3B batch proof. Current snapshot/publication pointers stay NULL.

`verify-identity` is the phase-aware read-only proof path, including parent
verification. Old `archive`/`handoff` writes refuse the third owner before native
writable open. Read-only verification refuses all target sidecars. A recognized
hot rollback journal may be recovered only by a P3B write command: inspect bounded
run headers and receipts, identities and schema before open, allow SQLite target
recovery, then verify the complete recovered source/parent/output proofs before
success or domain mutation. A spilled uncommitted receipt is never accepted as
committed evidence. Source journals/WAL/SHM are never recovered or removed.

## Implemented identity recipes

| Source -> destination | Identity and exact relation |
|---|---|
| `service_instances` -> same | Preserve ID, provider kind, unique name, base URL assertions, exact object metadata and original nullable creation time; never merge by URL. |
| `sources` -> same | Preserve source ID, optional instance, name and settings. `local-git` becomes `manual_git`; `github` becomes `github_inventory` and requires a valid GitHub instance. Recorded paths/URLs are never resolved, accessed or rewritten. |
| `repositories` -> same | Preserve catalog ID, name and object metadata. Verify/reuse an eligible P2 representative ID/map; otherwise insert the original ID. URL/name/shared OID never merge fork/mirror records. |
| `repository_bindings` -> same | Source composite `(repo_id,instance_id)` maps atomically to one newly allocated UUIDv4. Preserve native ID including legitimate NULL, metadata and creation time. Reject conflicting scoped native ownership. |
| `repository_endpoints` -> same | Preserve endpoint ID and same-repository edge, exact URL/transport/nullable label/metadata/time. `is_preferred` stays archived source evidence. |
| `repository_names` -> `repository_name_assertions` | Preserve `(repo_id,name)` and original nullable observation time; no fabricated name history. |
| `source_repositories` -> same | Preserve source/repository edges and original nullable bounds with strict RFC3339 ordering and target representability. Bounds are aggregates, not a sequence of observations. GitHub membership requires the exact valid repository/instance binding. |
| `repositories` + endpoint evidence -> preferred pointer | Set only one valid source-preferred endpoint belonging to the same repository, with matching legacy URL. Missing/ambiguous preferences remain NULL with attributed diagnostics. |

New binding allocation promises stability of committed mappings within one
workspace, not random UUID equality across independent conversions. Other IDs
retain their original type/semantics. Exact source bytes remain in the typed
archive even when target TEXT uses the correctly decoded source encoding.

Normalized v2 bindings/endpoints/membership take precedence over legacy
repository source/provider/URL columns. Legacy-only or contradictory assertions
remain archived with attributed reasons; they cannot manufacture a binding,
native ID, membership, endpoint or observation. Local legacy source IDs are not
provider-native IDs. NULL nested metadata, nullable native IDs/labels/base URLs
and observation times remain distinct from empty values.

Malformed keys/text/object JSON, unknown kinds, missing/unsafe references,
incompatible owners and unsupported or reversed times receive deterministic
diagnostics tied to `record_id`, original column and recipe. Unsafe dependent
rows are omitted, with a source decision for every processed record. No malformed
JSON becomes `{}`, unknown time becomes the conversion clock, or missing edge
becomes an arbitrary existing row. Prior diagnostics are never overwritten.

`complete` means the identity batch sequence and all decisions are processed.
`identity_ready` additionally requires completion and no retained parent or P3B
blocking diagnostics. `parent_diagnostics`, phase diagnostics and combined counts
remain visible. Partial facts and later domains still need their own gates;
neither readiness nor completion permits activation.

Inventory observations are deferred: exact `inventory_runs` values/IDs/times
remain archived. Membership aggregates need no fabricated individual inventory
observations. Git objects/acquisitions/snapshots, PR/document/search reconstruction
and all runtime/current-publication work remain outside this slice.

## Atomic batches and verification boundaries

The writer lock covers initialization, recovery, resume and read-only proof.
Each batch prepares source decisions, domain output, maps, diagnostics and hashes
before BEGIN, then commits them with progress and its source/output proof in one
SQLite transaction. Pre-COMMIT interruption rolls back; post-COMMIT interruption
reuses committed maps and facts. Completeness comes from the independently
recomputed committed prefix, not a separately advanced cursor or success flag.

Verification re-runs the recipes from sealed typed source evidence, checks exact
values and relations, source decisions and complete key ownership. Coherently
changing a mutable domain value and recalculating its stored output hash still
fails source comparison. Unattributed rows/maps/diagnostics and early pointers
are rejected. Original source/cache/copy/descriptor fingerprints are checked at
command boundaries and after conversion, not for every small identity batch.

Extraction and batch buffers are bounded, and committed identity manifests are
streamed. Full verification still keeps O(N) key/map/diagnostic sets; the parent
view keeps O(repository count) projections and historical map IDs. Original P3A
verification accumulates representative/map evidence and serializes parent
batch/map/diagnostic proof metadata. Writer entry/initialization performs several
full parent-verification passes per invocation. These costs remain explicit
before the much larger Git/PR phases; this task does not establish real-data
performance or remove the immutable-input restart boundary.

## Fresh validation and measurements

The consolidated local conversion closure passed all 252 pre-collected IDs on
both native SQLite 3.53.1 and audited minimum SQLite 3.46.1 with Python 3.12.14.
The selection consists of the original 156 P2/P3A cases plus 22 identity recipe,
17 identity owner and 57 guarded identity flow cases. Both JUnit results were
independently reconciled: every selected ID passed exactly once, with no errors,
failures, skips, duplicates or extra IDs. These are fresh focused results, not
full hosted acceptance or reused historical P3A evidence.

| Local focused lane | Fresh passed | Reused | JUnit suite seconds |
|---|---:|---:|---:|
| Native SQLite 3.53.1 | 252 | 0 | 38.952 |
| Audited SQLite 3.46.1 | 252 | 0 | 45.340 |

The exact selection and JUnit/reconciliation files are retained locally under
`artifacts/p3b-validation/`: `closure-selected-ids.json`, `closure-native.xml`,
`closure-minimum.xml` and corresponding reconciliation JSON. Command scope:

```bash
uv run --no-sync pytest tests/integration/test_conversion_foundation.py \
  tests/unit/test_conversion_protocol.py \
  tests/integration/test_conversion_source_admission.py \
  tests/unit/test_conversion_phase.py tests/integration/test_p3a_operational_flow.py \
  tests/unit/test_conversion_identity.py tests/unit/test_conversion_identity_phase.py \
  tests/integration/test_p3b_identity_flow.py -q -n 4 \
  --junitxml artifacts/p3b-validation/closure-native.xml
uv run --no-sync python scripts/run_sqlite_minimum_tests.py \
  --files-from artifacts/p3b-validation/closure-files.json -q -n 4 \
  --junitxml artifacts/p3b-validation/closure-minimum.xml
```

The genuine e404 converter produces operational bare and application-created
FTS/ANALYZE workspaces outside the current worker; its actual converter digest is
asserted before current initialization. Integrated checks compare IDs, exact
archive bytes, edges, names, original bounds, partial assertions and parent
receipts/maps/diagnostics independently. Both representative-map modes pass.
Malformed JSON/keys/kinds/references/times and contradictory or legacy-only
provider assertions retain the source values and attributed decisions.

Guarded tests exercise graceful faults and `os._exit(77)` before/after both owner
and binding batch COMMIT, repeated invocation, stable committed UUID allocation,
competing OS-lock holders, genuine spilled hot journals, read-only refusal of
pending state and source/target sidecar aliases. Source/cache/copy writes,
network and child-process probes are denied. Old phase writes cannot mutate a
P3B-owned destination. Altered source/copy/cache, parent receipt/predecessor,
archive/map/DDL, P3B owner/maps/proofs and a coherently rehashed mutable domain
value are rejected before continuation. Target same-owner/FK/immutable-identity
constraints and retained blockers/building lifecycle are verified. These checks
do not invoke normal sync/hydrate/restore/GC or acquire external content.

Ruff check/format passed all 119 Python files; contract validation retains all
287 source columns and 74 target tables, and `git diff --check` passed. CI
registration/selector regressions retain the baseline IDs and add both new
modules, protocol inputs, authentic historical fixture exports and all three new
test modules to native/minimum-p2. Policy and shared-fixture changes require
fresh full acceptance under the existing planner, including P1, application,
audited SQLite, isolated offline packaging and the always-running exact-ID gate.
The first substantive commit will undergo that consolidated acceptance; hosted
results will be recorded separately after they complete.

Two disposable size samples ran authentic P3A -> current P3B initialization ->
two-batch pause -> resume -> independent verification -> repeat, using identity
batch size 50 and archive batch size 100. All original source/cache/copy/seal and
parent evidence hashes stayed unchanged; the repeated command added zero batches.

| Synthetic item | 50 repositories, bare core | 250 repositories, FTS/ANALYZE |
|---|---:|---:|
| Source core rows / bytes | 315 / 573,440 | 1,527 / 983,040 |
| Normalized identity rows / P3B batches | 303 / 9 | 1,503 / 37 |
| Typed archive values / P2 batches | 1,672 / 53 | 8,117 / 65 |
| Target bytes before -> after P3B | 1,830,912 -> 2,076,672 | 3,633,152 -> 5,410,816 |
| Initialization wall / CPU seconds | 0.440 / 0.439 | 1.289 / 1.045 |
| Pause + resume wall / CPU seconds | 1.121 / 1.104 | 4.599 / 3.651 |
| Independent verification wall / CPU seconds | 0.246 / 0.246 | 0.752 / 0.623 |
| Peak ordinary P3B RSS, KiB | 29,268 | 32,128 |

Peak RSS is Linux `wait4().ru_maxrss`; CPU is child user+system time. One sample
per size, different derived structures and shared runner activity prevent a pure
scaling/speedup claim. Target growth includes maps, full identity output metadata
in batch proofs and ownership evidence, not just domain rows. A separate guarded
profile of the larger sample attributes about 60% of its 1.390 seconds to identity
source-derived verification and 30% to parent proofs (overlapping cumulative
call-tree measurements, not additive independent costs).

Definitive local measurements are `artifacts/p3b-size/final-code/measurements.json`
(SHA-256 `885f774f6fd62fad06ff8769b7cfa024f2d6feb96dca17ee745b422b3491f1ac`)
and `notes.md`. Both receipts and complete before/after code/resource snapshots
used converter SHA-256
`bc539be4fd5f83810162fdd8161644a03a2f689c8d9869aa313803a48495fd75`,
with conversion contract
`8b020200aec824ed57788df73b9107bb9deed042ce87e0d198e0c5a7515ecb60`.
Earlier development measurements have different converter identities and are
retained separately. No DB/cache/payload or benchmarking framework is committed.

## Next bounded scope

P3C must define ownership beyond this frozen identity owner before writing stored
Git facts. It must preserve object/content/digest/acquisition/snapshot IDs and
bytes, same-owner edges, parent order, raw names and archived assertions, with
new source-derived proofs and explicit missing-original diagnostics. Local raw
reconstruction is P4, saved API/PR history P3D, and integrated normalized proof
P3E. Normal runtime/first-sync integration, real-data dry-run and cutover remain
P5/P6/P7; none is authorized by these synthetic identity results.
