# Implementation plan and remaining boundaries

## Completed foundations

P1 defines the independent catalog3 DDL and executable contracts. P2 seals stopped
v2 input, preserves every typed core value, and supplies guarded atomic batches,
mappings and restart proofs. P3A admits recognized operational FTS/ANALYZE layouts.
P3B normalizes identity under its own owner; its historical acceptance is recorded
in [p3b-handoff.md](p3b-handoff.md).

## Integrated stored-data milestone

P3C/P3D/P3E are combined implementation labels, not separate review gates. The
current feature converts stored Git and GitHub PR facts, repairs bounded saved
normalization gaps, and exposes explicit read-only target queries and scan search.
See [integrated-handoff.md](integrated-handoff.md) for runnable synthetic commands,
source dispositions, verification measurements and precise limitations.

The `p3-integrated/1` owner follows a complete P3B parent. One supported current
sealed-v2 path establishes archive, handoff, identity and stored-domain owners;
one bounded transition accepts the authentic reviewed P3B implementation.
Parent archive/receipts/identity rows remain immutable. Domain checkpoints commit
rows, mappings, diagnostics and source/output proofs together. Receipt hashes and
fingerprints stay exact; no hash-ignore or historical compatibility matrix exists.

| Implemented domain | Preservation and usability |
|---|---|
| Identity and inventory | Repository IDs, bindings/endpoints/names/membership, inventory assertions/times; equal URLs/OIDs do not merge repositories. |
| Stored Git | Objects, commits/ordered parents, trees/raw paths, tags, content/digests/maps, acquisitions/snapshots/refs, roots/all origins, stored manifests. Newly verified flags require reconstructable matching bytes, hash and size. |
| Saved API/PR | Payload bytes, page occurrences, collection scopes/membership, PR observations, document bodies/versions/observations, reviews/threads/comments/events and code listings/Git links. Saved replay retains source observation times and partial coverage. |
| Read-only target | Explicit target DB and building opt-in; repositories, commits/trees/files/digests, PR history and original-text code/commit/PR scan. No migration, network, Git, index repair or pointer publication. |
| Evidence | Independent bytes/IDs/edges/order comparisons, actual process interruption/resume, source/cache/network guards and modest synthetic scaling. Required final CI remains the acceptance gate. |

Target lifecycle remains `building`; execution completion and normalized readiness
are separate from publication, operational activation and online synchronization.
Missing raw content never becomes empty bytes. Unsupported/malformed facts remain
in the typed archive with attributed diagnostics. Every source table has an
executable disposition in `conversion-contract.json:p3_integrated`.

During editing run focused recipe/query selections. At integration run affected
closure and compact guarded end-to-end tests. At stable implementation run required
final CI, including minimum SQLite and isolated offline packaging, once; fix actual
failures and rerun affected/final checks. Existing planner-verified prose reuse and
the fail-safe final gate remain unchanged.

## Remaining work

| Work | Required evidence before acceptance |
|---|---|
| Additional offline reconstruction | Explicit supported payload shapes or local Git read boundary; original bytes/times/coverage and proof comparisons. Unresolved GraphQL/history/scope gaps must remain visible. |
| Online runtime and first sync | Collector uses catalog3 ownership/lifecycle; scope/principal/API/parser/profile checks; synthetic request logs prove safe cursor/validator/watermark reuse and avoid blanket downloads. |
| Separately scoped real-data dry run | Explicit sealed real input/cache, capacity budget, private comparison/report and real timing; no default catalog switch. |
| Separately scoped cutover/rollback | Validated target, first-sync/operational gates and explicit external active pointer/rollback plan. |

Only disposable synthetic inputs are authorized here. Real-data access/conversion,
production activation, main commits, automatic PR merge, provider expansion and
multi-catalog exchange remain outside this milestone.
