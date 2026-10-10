# Phase 2 determined corrections — Schema 19

This PR corrects accepted contracts and their execution cost. It is stacked on
the [investigation and integrated proposal](README.md), which remains **Proposed /
Pending Owner Decision**. It does not choose historical retention/selection,
publication identity, replacement completeness, cache/checkpoint, field inventory,
normalized Exchange trust or garbage collection. No compatibility layer or
speculative production table is introduced.

## Resulting behavior

**Sparse current projections preserve presence and origin.** A supplied actor
without `login`, review/reply parent without `fullDatabaseId`, or commit object
without `oid` leaves that selected field unasserted. It can no longer clear a
previous value and incorrectly replace its evidence. Explicit top-level null and
selected OID null retain their existing meanings; null canonical parent IDs and
malformed object/scalar shapes reject. The producing module version is advanced
for the changed interpretation; inherited/imported earlier field evidence retains
its actual earlier version. All current identity, transfer, clock/conflict and
receiver-local check rules remain intact.

**Rejected known resource evidence keeps its real time.** After a committed page
at 150, a recognizable in-scope resource response rejected at 200 records partial200.
A valid retry 175 cannot certify complete 200; equal 200 remains conflict and valid 300
can supersede it. Unknown/malformed responses, another Source, wrong scope,
cancelled or fenced attempts cannot lend a resource observation clock. Terminal
cancellation can resume the already committed proof rather than creating a false
partial or advancing its clock. Full Issue summary evidence uses the actual
Source/job scope and relevant partial boundary. Adapter response timestamps must
be signed-int64 microseconds, including genuine zero/negative values.

**Historical proof requires its actual page boundary.** Historical complete
markers require unique contiguous ordinals 0..N, continuation on intermediate
pages, and an explicit final terminal boundary. Accepted partial GraphQL roots
with errors retain their existing retry semantics: a raw/current continuation
difference is admitted only for the exact typed root, ordinal and observation
clock, with SHA-256/length-verified unquarantined retained error evidence. An
unrelated injected receipt, corrupt bytes or a rawless root cannot manufacture
complete proof. The existing current-receipt thread-comments child and independent
ordinary-current/304 paths keep their established proof contracts. Reordered,
repeated and selective Exchange stages missing closure; late dependencies restore
eligibility without discarding valid individual facts.

**Conflict-free refresh has bounded work.** Exchange first clears stale barriers
and recomputes pending historical selection scopes. With no actual conflict seeds,
it returns before building an unnecessary whole-catalog dependency graph. Actual
conflicts keep dependency propagation and Coverage blocking. At 4,096 unrelated Git
objects, refresh changes from 24,651 statements to four; selected export remains 223.
This preserves Phase 1's exact dependency closure and bounded proof construction.

**Historical output sealing uses result-led indexes.** Seven indexes cover
`code_observations`, `change_request_events`, `snapshots`, `ref_observations`,
`code_commits`, `code_file_changes` and nonnull-result repository name observations.
The name index is composed after its table in `identity_relations.sql`. Existing
`ParserModel.publish_result` now uses SEARCH plans on those seven branches instead
of scanning unrelated histories. Independent actual sealing stays 1,088 VM steps
at 100/2,000 unrelated histories; removing only the indexes yields 3,329/45,151. These
are deterministic operation counts, not clean concurrent elapsed-time benchmarks.

## Schema and files

Active runtime is Schema 19 with complete DDL SHA-256
`d0fba8d577ffad700b17a7504f67228c375a00c16583e1d1c6a7eef7e12c9415`.
The index revision retains 103 product tables, 665 columns, 226 FK constraints,
48 views and 498 triggers; explicit indexes rise 106→113. The exact Coverage claim
contract and current maximum-observation predicates are unchanged. Fresh schema
identity/check and packaged DDL share this version/fingerprint. Earlier development
catalogs are rejected under the existing fresh-only contract; no migration is
introduced. Schema 18 investigation snapshots remain historical evidence.

Production changes are in `adapters/github/current_parser.py`, `collector.py`,
`persistence.py`, `adapters/sqlite/exchange.py`, `schema.py`, and packaged
`catalog3.sql` / `identity_relations.sql`. Six new integration modules exercise
actor/nested presence, rejection clocks/fences, historical proof attacks, Exchange
scaling and actual publication scaling. Existing Exchange fixture continuations
are corrected to be truthful intermediate pages. The built-in historical
certificate is regenerated from the frozen implementation and successful
synthetic capability tests because its existing historical consumer is still
active; it is not part of the proposed final architecture.

The current guide, README, data model and testing instructions name Schema 19.
The acquisition characterization now expects the repaired partial200 boundary.
The [conditional disposition](schema-disposition.json) and
[field contract](field-contract.json) are explicitly the investigated Schema 18
snapshot, rather than being silently overwritten as Schema 19 runtime receipts.

## Verification and independent review

The [independent review](independent-review.md) and [integrated interaction review](independent-integrated-correction-review.md) record actual counterexamples,
correction source heads and development failures/bootstrap flags. Each correction
was reviewed in a separate worktree; the combined production diff receives a
further independent review. Its clock/reordered-Exchange/retry probe, fresh Schema 19 checks and explicit version-origin tests passed with the disclosed certificate boundary. These fixes are independent of the proposal choices.

Reproduce current composition/field inventory without changing the historical
proposal artifacts:

```sh
uv run --no-sync python scripts/audit_phase2_dependencies.py --output artifacts/schema19.json --source-output artifacts/schema19-source.json.gz
uv run --no-sync python scripts/audit_phase2_fields.py --output artifacts/schema19-fields.json
uv run --no-sync python -m pytest docs/phase2/prototypes/test_acquisition_characterization.py
uv run --no-sync python docs/phase2/prototypes/completeness_probe.py --threads 10000 --expect-hardened --output artifacts/hardened-completeness.json
```

Certificate regeneration captures the implementation definition **before** the
successful synthetic bootstrap capability run and refuses a changed definition.
Final complete acceptance is run without that override. Ordinary acceptance
includes fresh initialization, composed fingerprint/JSON/FK/integrity, view/trigger
behavior, ordinary integration/e2e, collection/Coverage, Exchange/CAS corruption
and quarantine, and sequential isolated wheel/sdist installs. Ruff and CI
selected/executed reconciliation are required.

The first integrated development capability run at `250cb14bc9483af772eddf34f87c370dac612512`
passed 1,920 cases and failed one overbroad recorder-test assertion that no completion
marker could exist after a recognizable rejected first response. Independent
review confirmed that Phase 1 already requires reason-only partial evidence for a
new collection with zero admitted occurrences; see
`test_phase1_retirement.py::test_observed_rest_rejection_preserves_latest_coverage_candidate_set`.
The recorder test now checks the exact partial scope/time/reason and all zero
resource/page/byte/staging/diagnostic counts, while storage failures retain their
zero-marker requirement. The corrected frozen run at `47be2fd780f0a5278d950d0053cde9ac6fb6f196` passed all 1,921 ordinary cases without skips under explicit development bootstrap. The pre-run definition still matched after docs-only review integration, and the certificate was generated from that successful report. The failing report is retained as development evidence
and cannot generate a certificate. A focused assertion initially compared JSON
whitespace; it now checks the exact decoded reason contract instead.

Exact final feature SHA/effective tree, actual test totals, selected/executed gate,
hosted CI URL and any failures/unexecuted checks are recorded in this PR's body and
its `ci-profile` artifacts after execution. Earlier focused/bootstrap counts are
not full acceptance. No live authenticated collection, retained catalog mutation,
private data, merge, release or deployment is authorized or performed.
