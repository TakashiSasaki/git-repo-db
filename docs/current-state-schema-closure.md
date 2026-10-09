# Current-state correctness and schema closure

This follow-up starts from PR #13, branch `refactor/latest-state-transport`,
commit `db3a5ecfbf95b4c1318198aa308ca6dc749876a1`. The working branch is
`fix/current-state-schema-closure`, targeting that verified branch. Schema 15
is a fresh incompatible development format. Earlier catalogs/backups are
rejected; no migration is added.

## Mutable projection and evidence

The two current-resource tables keep their existing typed natural keys. Each
resource has one mutable row, not a normalized edit history. Both now include
`field_evidence_json`: a map from canonical JSON-array paths to the evidence
for the currently retained value. A body and its availability status are one
field; nested provider metadata retains object-shape and leaf evidence. Each
entry has the original provider clock/scope, observation and parse times,
parser profile and captured acquisition context. Unknown physical defaults do
not become observed fields. Entries are replaced or pruned when their values
are replaced; storage grows with current metadata paths, not edit count.

A newer partial response updates only supplied fields. Inherited values keep
their earlier evidence. A compatible equal-clock complete response fills the
remaining fields without creating a false conflict. Older complete responses
may fill fields never observed in newer responses while retaining known newer
values. A serialized live fence can resolve genuinely unordered supplied values,
but cannot override a proven newer provider clock or certify omitted fields.
Contradictory supplied values without justified ordering remain staged and hide
an undisputed normal-query winner.

## Exchange and acquisition boundaries

Staging ownership uses table and reason classification, independent of record-key
spelling. Current candidates and immutable exchange envelopes follow their
respective dispatch and competing-variant rules. Exact repeated evidence is
idempotent; the same semantic value with stronger field/update evidence is
reevaluated. Staged variants retain stronger comparable evidence, including
unknown-to-known clocks, without appending another capture history.

Issue transfers cascade current child repository, binding and number only when
membership actually changes. A comment's original capture remains attributable
to the original repository/Source/endpoint/time. Those detached captured
identifiers are canonical non-owning snapshots: exchanging destination B does
not create repository A or assert Source membership in B. Locally available
captured bindings/Source relations are checked, and actual live acquisition
requires its current typed scope. Later genuine destination acquisition replaces
only the supplied field proofs. Review captures retain exact PR ownership.

`last_checked_at_us` belongs to the receiving catalog's valid serialized live
check: initial, identical and edited responses update it consistently. Import
and replay preserve the receiver's local value and do not install a sender's
check. Provider update, state observation, parsing and local checking retain
their distinct meanings. Identical captures keep the original state observation
unless a genuine live capture changes acquisition scope.

Recorder failures retain sanitized allowlisted diagnostics before best-effort
warning emission. Warning-as-error and failing warning output cannot invalidate
a successful response. Cancellation and transport/parser/storage failures
retain their ordinary behavior. Both transport and collection aggregation keep
the last 100 diagnostics.

## Demonstrated removals and retention

`review_resources.title` had no supported producer or semantic reader and is
removed. Issue titles remain. The unreachable historical document-thread lookup
and three absent current-pointer exchange exclusions are removed. Real preferred
endpoint exclusion and generated typed-FK discriminators remain necessary.
The complete column roles and measurements are in
[the liveness matrix](current-state-schema-liveness.md), and the before/after
DDL objects and columns are in [the inventory](current-state-schema-inventory.md).

Latest-only normal views do not imply automatic physical deletion. A synthetic
20-edit fixture retained one current row, no immutable document observations,
20 exact text bodies, and 19 unreferenced older bodies (19,380 bytes). Its current
field map stayed at seven entries. No automatic GC or retention policy is added.
Writes update only changed columns; unchanged membership does not cascade to
children. Shared bodies, PR/Git/thread history and required immutable inputs
retain their existing roles. CAS-41, coverage v2, explicit profile selection/trust
and optional archive independence remain part of final acceptance.

## Reproduction and acceptance evidence

The attached source-equivalent probes are seeds, not production acceptance.
Production regressions reproduced F1–F6 using complete DDL, shared admission,
actual transport/collector, normal readers, and Graph/application exchange.
New regressions include both resource families, reordered sparse/full responses,
three-plus conflicts, stronger staged evidence, reopen/reexport, transferred
captures, warning-as-error and receiver-local check isolation.

Independent combined-case review additionally found and corrected nested
object-to-scalar conflict resolution, stale live-response overwrites, foreign
review capture attribution, unsupported field-profile attribution and leaf-only
metadata evidence bypassing ancestor ordering. Final direct-SQL probes also
required runtime SQLite integer checks for signed-int64 field-proof times;
malformed exchanged proof times now enter invalid staging without rolling back
an independent valid resource. The performance gate retains
its original 60-second deadline; the initial integrated run exceeded it, and
profiling identified repeated field-context/reference validation as the cause.

Final local acceptance passed 1,452 ordinary cases and both isolated installed
variants, without bootstrap, failures, errors or skips. Independent review
passed 107 overlapping cases. The original large-pagination test passed in
29.94 seconds under its unchanged 60-second subprocess deadline.
[The local receipt](validation/synthetic/2026-10-09-current-state-schema-closure.md)
and its JSON bind the tested implementation; the submitted PR body separately
records exact published HEAD, tested merge/tree and hosted outcomes.
No live authenticated acquisition, retained user-data mutation, release,
physical power-loss or non-Linux restore is exercised.
