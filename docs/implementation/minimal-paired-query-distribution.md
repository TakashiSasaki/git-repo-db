# Minimum paired Query distribution (OP-04)

Baseline: reviewed Context read stack through PR #246 at
`047f8800846dbe1e016b00e1700372e6050bb978`, tree
`802da3f839120bb874e34cb5275a5268b63bda6c`.
[ADR 0037](../adr/0037-operation-scoped-module-independence.md),
[ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md) and the
[operation contract](../architecture/module-independence-contract.md) govern the
scope. Implementation, executed evidence and target guarantees remain distinct.

## Ownership and dependency closure

`repo-catalog-paired-query` depends on Core, Context, runtime and contracts.
Core and Context each retain their independent runtime/contracts closure; neither
imports or requires the other. The composed product depends on paired Query.
The five-product minimum installs no concrete Access/Operational/Search or
high-level acquisition/Exchange/Recovery orchestration. The composed product now
has one additional distribution; no universal module registry or plugin framework
is introduced.

| Canonical module | Owner and use |
| --- | --- |
| `adapters/sqlite/paired_coordination.py` | Paired Query: pair identity, intra-store FK and embedded/cross-store reference validation, pinned read coordination. `PairSnapshotCoordinator` inherits Core coordination and opens only Core/Context. |
| `application/paired_query.py` | Paired Query: existing topology, single-authority delegates, paired Resource/list operations and Core resolution. Context-only snapshots delegate the canonical Context reader. |
| `domain/paired_query.py` | Paired Query: paired views and paired endpoint validator; ResourceKey meaning is validated by Context's canonical validator. |
| `cli/paired_query_features.py` | Paired Query: existing paired commands, reusing the existing Context commands. |
| `application/query_pagination.py` | Runtime: the unchanged single generic bounded pager. |
| Rich `adapters/sqlite/p1_coordination.py` | Admission/backup orchestration and WorkLedger remain rich. PairCoordinator inherits canonical paired reads and imports the same validation functions. After OP-05/06 it reexports the Search-owned SearchProjection facade. |
| Rich `application/production_query.py` and `domain/production_query.py` | Search extension and types are composed/reexported from the optional [Search distribution](minimal-search-distribution.md); paired application/views remain inherited/reexported. Existing rich API paths remain available. |

There is one owner for each packaged file and each moved model/algorithm.
The minimum paired integration contains four product modules; it moves existing
mechanisms rather than copying them into shared runtime. Existing workspace,
namespace preflight, build inputs, formatter paths and source inventories include
that owner explicitly.

## Read semantics and refusal boundaries

The public minimum is `PairedQueryService`, with the existing opt-in
`python -m repo_catalog.cli.production_query` commands. Paired reads require both
existing authorities, matching permanent repository/catalog identity and valid
required cross-store dependencies. The shared gate remains held while SELECTs
pin both SQLite transactions. Results retain their snapshots until production
finishes. Known catalog stop, in-flight stop and the final completion fence after
coordinator cleanup remain binding.

`available_in_core` means the nominal object is present; the object view retains
actual Core field/observation/Notes evidence. It does not infer facts from URLs,
Access, Source membership or Provider authenticity. Selected metadata bytes are
returned as verified only through the existing actual-byte checker. A logical
match or retained-row presence supplies no new physical-byte verification.
Required `core_references` differ from attributed report-only candidates; the
latter can remain unavailable without inventing a Core object.

Explicit `context_only` ignores opaque coexisting Core and returns unresolved
Core qualifications. Explicit `core_only` similarly ignores Context. Existing
`auto` topology semantics are unchanged. A paired operation never silently
becomes a single-authority success. Without the integration distribution,
Core/Context readers explicitly refuse paired capability and CLI discovery does
not advertise paired commands. Search requires rich/optional Search capability.

Paired ResourceKey/bool/page/filter/cursor values are checked before stored-row
classifiers. ResourceKey reconstruction is shared with the Context reader and
retains the canonical copy. Full semantic ordering, exact counts, bounded pager
retention, endpoint/filter/mapping-evidence/snapshot cursor binding and two-phase
selected-text verification remain. Metadata-only snapshot hashing and all
existing required validators retain their original scope; no whole-authority
byte verification is claimed by an ordinary read. Genuine stored corruption
persists global stop; caller errors, unavailable capability and read-budget
exhaustion remain distinct. Reads do not repair authorities.

## Verification scope and exclusions

Minimum direct and sdist-derived installs use ordinary offline dependency
resolution outside checkout, with unique owners/origins and physically absent
optional code. External probes exercise Core/Context/paired API and existing CLI,
semantic reference resolution, explicit checked bytes, qualification, pagination,
identity/dependency refusal, pinned/stale tokens, opaque siblings, caller errors,
budgets, real corruption/no repair and all completion fences. Separate resolver
installs of Core+Context without integration exercise missing-capability refusal.
Artifact members/metadata and input/artifact hashes bind each build path.

Affected composed coordination/admission, backup/Recovery/Exchange and Query/CLI
regressions preserve the other consumers of the moved mechanism. Their scoped
results do not establish their independent installation targets. Source/artifact
counterexamples and independent review are recorded in the PR; test existence
or this document alone is not a PASS.

No ordinary Schema21 activation, Transfer enablement, Context initialization,
mutation/recovery minimum, release qualification, SQLite/CPU matrix, live catalog,
merge, release, tag or manual deployment is included. After OP-04, independent
Search combinations, acquisition and Exchange remain separate increments.
