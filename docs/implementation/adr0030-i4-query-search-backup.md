# ADR 0030 I4: Query, Search and paired backup integration

I4 starts at I2+I3 integration PR #110 HEAD
`8519056d5b9484eb0cc4dcf9f693285b4e65518a`, tree
`a77503505127367e9378c57c5ab9ee9ae11767f3`. PRs #107–#110 and main
are unchanged. The I4 Draft targets #110's branch. ADRs 0029/0030 remain
accepted policy; no public Schema 21 switch, P8, merge, release or real Catalog
operation is included.

## Query contract

`ContextResourceView.repository_roles` contains the current
`Context.provider_repository_roles(resource, evidence=...)` evaluations.
`repository_relations` separately contains retained typed Core-target evidence.
`repository_uuidv4` is a convenience candidate projection for Issue owner or PR
base only when all current primary-role reports agree on one undisputed Mapping
target. It does not establish Provider authenticity. Missing, explicit NULL,
unmapped Provider, competing Mapping targets, contested Dispositions and
incomparable/equal/unknown clocks remain visible in typed roles and serialized
output. PR head remains a separate role. Child resources do not inherit a
parent's membership. The retired field candidate and API have no shim.

Repository-filtered Context/paired lists match current active Mapping candidates
for any reported role, or active represents_repository claims for Provider
Repository resources. Conflicts remain candidates with their qualifications;
filters do not assert unique ownership. Historical owner/base/head and Transfer
endpoints never supply current membership. A newer unresolved Provider owner
therefore excludes the old mapped owner from these filters while preserving the
old Core-target relation as evidence.

`ProductionQueryService(..., mapping_evidence=MappingOperationEvidence(...))`
accepts genuine currently available operation evidence from its caller. Omission
never invents confirmation from claimed issuer, local Source or store identity.
Query reads retain complete ClaimKeys and Disposition references. Pagination
filters bind this transient evidence as well as the snapshot and selectors;
changing qualification cannot continue another evaluation's cursor. Evidence is
never persisted into domain, Search or backup as local-check authority.

## Search contract

The existing `context_text` projection now includes current Provider-role documents
and stored typed Core-target relation documents. Summary `kind` distinguishes
`current_provider_repository_role` from `stored_core_target_relation`.
Text candidate summaries also expose current qualified roles. Document keys use
original Resource coordinates, complete role scope and provenance, or complete
relation ClaimKey. Equal-clock candidates sharing provenance cannot overwrite
one another merely because their Provider targets differ.

Generation, rebuild and every search read use the pinned Context facade. Search
stores derivative text and keys only; current summaries and qualifications are
recomputed from authority. Candidate dictionaries are compared with authoritative
matches before acceptance. Missing, stale, incomplete, corrupted or differently
qualified indexes fall back to authority scan. Rebuild replaces derived projections;
ordinary authoritative corruption invokes P7 Stop, including rebuild and backup.
Existing snapshot fences, deterministic sorting, cursors, finite SQL/row/document
work limits, exact text verification and ordinary-file-body exclusion remain.

## Paired backup and fresh restore

Whole SQLite snapshots already copy all 19 Context tables; I4 verifies the new
`resource_repository_relations` and `repository_mapping_dispositions` with their
full dependencies, rather than adding a lossy row serializer. Restore retains
original ClaimKeys, correction subjects/replacements, EventReportKeys and whole
Transfer reports, Provider relations, Coverage, Source membership, observation
times, text and provenance. The complete Context row multiset is compared before
and after restore in the new tests, including generated FK columns.

Stored semantic validation now shares I2's strict Provider scope validator and
checks referenced Provider Resources. A matching outer checksum/fingerprint does
not excuse a wrong role, member, original time or missing Mapping support.
Restore verifies packaged DDL/fingerprints, FK/integrity/domain invariants and
pair identities before fresh no-overwrite activation. Bad backup candidates do
not stop a sound source; authoritative source corruption does stop ordinary
service. Existing P7 retained-byte and recovery controls remain binding.

Manifest store scope remains Core-only or Core+Context. An explicit exclusion
notice identifies Access/Operational/Search and disclaims saved access settings
and repository file checkout. Access is an independent durable configuration and
approval store; Operational/Search remain independently reconstructible. Their
files and local-check authority are excluded from paired domain backup. Git-only
scope retains its existing guarantees and does not acquire Context requirements.

## Validation and I5 handoff

The baseline reproduces all 27 known P6 failures. Updated P6 tests retain the
same 50 nodes and reach the intended Query/Search assertions. New I4 tests cover
the newer-unresolved-owner counterexample, base/head independence, Mapping
conflicts, NULL/absent/unresolved states, equal/incomparable/unknown clocks,
Disposition qualification, exact cursor filters, Search fallback/rebuild,
actual-work refusal, P7 Stop and checksummed malformed backup rejection.

The minimum-SQLite workflow retains all prior targets and extends P1 to its full
suite, adds P5/P6 compatibility and I4, without duplicate P1 collection. Direct
wheel and sdist-derived-wheel isolation now exercise installed I2→I3→I4 Query,
Search, Disposition qualification and fresh paired restore. No test is removed,
skipped or made xfail. Exact committed source, results, failed development
attempts, hosted execution, independent review and final input binding are
recorded in [the I4 evidence](evidence/adr0030-i4/README.md).

I5 still owns independent assembled end-to-end acceptance: freeze the intended
integration tree and recheck effective merge dependencies, adversarial mixed
selection/qualification/recovery flows, Core/Access isolation and installed
artifacts. Focused I4/expanded CI is not a complete release receipt. No full
release qualification, merge, production activation or data migration is claimed.

### Source-diagnosis correction found by the I4 counterexample

On initial pushed source `b4caae054326a60f4aeb0e5f71e8b042f2c132f9`,
the I4 suite passed 25 nodes and failed the backup Stop assertion. Trusted
stored Provider decoding raised a wrapped ValueError. P7's generic cause-chain
classifier deliberately treats unexpected implementation ValueError as
indeterminate, so it also misclassified this proven stored-data violation.
`StoredContextInvariantError` now marks only the trusted pure stored-relation
decoder boundary, retaining the original cause for diagnostics. Source diagnosis
recognizes that proof while arbitrary adapter errors, I/O, SQLite locks and
resource exhaustion still cannot declare corruption. The original failed
execution and the focused correction/revalidation are retained in the evidence.
