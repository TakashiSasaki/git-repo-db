# P6 correction implementation and bounded verification

The owner accepted classified microsecond timestamps and SHA-256-only Exchange
in [ADR 0028](../adr/0028-classified-times-and-sha256-exchange.md). This branch
implements the P6 correction on the shared correction stack; acceptance of that
decision does not mean this PR is approved or merged. The public Schema 21
runtime is unchanged. Historical P6 receipts remain attributed to their original
executable; their 780 count is not a new correction-run result.

## Query and Search contract

`ProductionQueryService` uses `GitCore.for_snapshot`, a supported typed capability
which checks its owning catalog and expires on context exit. The application no
longer assembles a Core with `__new__`, accesses raw snapshot connections or
replaces coordinator authorizers. A detected stored JSON, UTF-8 or typed-domain
reconstruction failure persists the catalog stop before returning an error;
subsequent ordinary reads fail closed. Invalid external cursors and finite query
budget exhaustion do not imply corruption. Selected typed byte reads still check
actual bytes and stop on corruption; a metadata query does not acquire or hash
all retained bodies.

A versioned streaming metadata fingerprint covers schema, all selected metadata,
keys, sizes and declared digests. It excludes `body`, `proof_bundle` and
`text_value`. It proves metadata snapshot equality, not retained-byte integrity.
Paired reads retain identity/FK/embedded-reference validation without performing
full retained-body certification on every query. Explicit backup validation keeps
the shared full-validation default. Context-only and Core-only reads do not
pretend to certify absent stores.

`ProductionSearchAdapter` uses ordinary `search_documents` tables and SQLite
`instr()`. It implements no FTS5 accelerator. Every query extracts and validates
the complete bounded authoritative projection before comparing derivative
candidates, so `verified_projection_scan` means a checked derivative scan plus an
independent authority scan. It does not mean indexed acceleration. Missing,
stale, incomplete, corrupt or over-budget Search returns `authority_scan` and
never publishes a catalog recovery stop. Projection replacement is transactional
per kind at one pinned metadata snapshot; unsupported/missing generations do not
prove completeness. No FTS technical row identifier becomes a domain PK.

Matching is literal case-sensitive Unicode substring membership, without
normalization or tokenization. Japanese, one-character queries, punctuation,
quotes, backslash, emoji and NUL keep literal meaning. Empty queries, unpaired
Unicode surrogates and queries over 4096 code points are refused. Binary Notes
and undecodable tree names use UTF-8 decoding with `backslashreplace` for search
presentation (`0xff` becomes the literal characters `\xff`); typed byte reads
return the unchanged original bytes. Ordinary file bodies remain excluded.

## Cursor and work limits

Cursor envelopes carry `checksum_sha256`, a public SHA-256 checksum over canonical
payload JSON. They are neither signatures nor authentication MACs. Anyone can
recompute the checksum and select another valid position; doing so grants no
capability. Endpoint-specific key arity, string types, OID/UUID ranges and typed
coordinates are checked independently. Catalog and snapshot token, endpoint and
filter mismatches fail closed. Malformed recomputed-checksum keys raise
`INVALID_CURSOR`, including bool, number, nested arrays and malformed OIDs.
Encoded cursors/snapshot JSON are bounded to 65536 characters, key strings to
32768 characters, and page sizes to 1..10000.

P6 requires an actual finite `SnapshotReadLimits`; passing `None` is refused.
Defaults per pinned authoritative store are 64 MiB logical SQLite pages, 10000
stored rows and 5000000 SQLite VM instructions. Callers may supply higher
positive finite limits through `ProductionQueryService(..., read_limits=...)`.
Bounds are installed before snapshot validation and projection extraction.
Derivative lookup separately applies finite SQLite page/row/VM bounds and checks
stored encoded document length before `instr()` or Python text materialization.
Search extraction additionally permits at most 10000 documents, 1 MiB per encoded
key+text and 16 MiB aggregate encoded key+text. Those explicit working-set ceilings
are currently adapter constants; exceeding them refuses the authoritative query
or falls back from a derivative query. There is no silent truncation or unlimited
fallback. Python callbacks/decoders are bounded by the finite stored/input byte
and row limits; VM counts are SQLite instructions, not a CPU-time guarantee.

List endpoints stream views into a heap retaining at most `limit+1` candidates
instead of building and sorting every view. Selected Context/paired page items
resolve their text after selection. Exact `total_count` still requires a bounded
O(N) candidate scan; metadata fingerprint generation also scans bounded metadata.
This is not keyset SQL acceleration. Growth checks exercise 100 and 10000
synthetic candidates and track live retained objects rather than wall-clock
speed under parallel agent load.

`last_costs_ns` reports `snapshot_total` (inclusive opening/preflight/pinning),
`authority_validation` and `snapshot_token_generation` as disjoint paired phases,
`authority_identity_validation` and token generation for single-store snapshots,
then `authority_search_validation:<kind>` and `projection_scan:<kind>` separately.
Single-store identity validation is not full-catalog certification. Timings are
instrumentation of actual work, not a claim of measured acceleration.

## Findings, causes and regression mapping

| Finding | Reproduction and root cause | Correction and formal regression |
| --- | --- | --- |
| Search acceleration overstatement | Source uses ordinary `instr()` and extracts all authoritative docs before lookup; historical FTS5 wording was inaccurate. | Honest backend name, documented bounded scan; existing `test_search_projection_and_five_fallback_scenarios_never_stop_catalog` retains its complete fallback purpose. |
| Recomputed-checksum cursor keys | Short/malformed keys were accepted or leaked `TypeError` because only nonempty tuple was checked. | Per-endpoint typed validation; `test_recomputed_checksum_still_validates_key` and `test_recomputed_valid_position_grants_no_authenticity`. |
| All-view page retention | Each endpoint accumulated a list and sorted it per page. | Lazy candidate generators and finite heap; `test_page_selection_memory_scales_with_limit_not_catalog`; original all-endpoint pagination equivalence test remains. |
| Escaped Core capability | Application fabricated a Core on raw private snapshot DB and never revoked it. | Supported owner-bound expiring factory; `test_core_and_context_snapshot_capabilities_expire` and shared snapshot tests. |
| Metadata body rehash | Full snapshot digest and paired integrity checks selected/checked all retained bodies. | Metadata fence and scoped typed validation; `test_metadata_queries_do_not_hydrate_or_rehash_all_retained_bodies` allows metadata after synthetic body damage, then proves selected byte read stops. |
| Invalid stored JSON/UTF-8/type/provenance | View construction and argument unpacking occurred outside a stored-value failure boundary. | Complete stored reconstruction scopes; `test_persisted_json_utf8_and_typed_metadata_stop`, `test_persisted_provenance_shape_failure_stops`, `test_persisted_search_observation_shape_stops`. |
| Binary Notes projection | `surrogateescape` produced unencodable SQLite TEXT. | Documented escaped representation; `test_binary_notes_rebuild_and_scan_equivalence`. |
| Unbounded or late derivative check | `fetchall()` and `instr()` processed oversized derivative text before budget checks. | Independent preflight byte/row/VM checks, cursor iteration, bounded document maps; `test_oversize_derivative_row_falls_back_before_text_construction`. |
| Derivative JSON depth falsely stopped authority | Independent reviewer corrupted a bounded Search key with excessive nesting; `RecursionError` escaped into the authoritative decoding scope. | Catch derivative parser exhaustion as fallback; `test_derivative_deep_json_falls_back_without_catalog_stop`. |
| Silent unlimited P6 reads | Type annotation allowed runtime `read_limits=None`. | Runtime finite-limit enforcement; `test_unlimited_p6_read_configuration_is_rejected` and all three `test_snapshot_budget_refusal_preserves_ordinary_reads` topologies. |
| Substring edge semantics unclear | Small ASCII happy paths did not demonstrate meaningful Unicode/special matches. | Ten meaningful populated cases in `test_literal_unicode_short_special_search_semantics_and_cost_phases`, plus empty rejection and binary Notes. |

Existing nodes were preserved. Backend assertions in
`test_search_projection_and_five_fallback_scenarios_never_stop_catalog`,
`test_ordinary_file_blobs_are_never_indexed_in_search`,
`test_cli_all_subcommands_pagination_and_error_handling` and
`test_p6_installed_query_search_and_cli` now use the accurate backend
name; their behavioral purpose is unchanged. No P6 timestamp fixture was weakened,
removed, skipped or xfailed. Shared time fixture mappings are recorded by the
shared correction evidence.

## Verification status

Initial executable `debbed63dd79c73c37402398bdb3817a41e2ff85`, tree
`246e60f94d23839090202dd7c95e6289e9d4aece`, is the initial frozen correction input.
The implementer executed 55 selected P6/shared snapshot nodes successfully.
Cleanup `07a6131e22cb9f07ee95968240f195249ece1654`, tree
`d2278b48e34476865e547909381b2e43a87eec9a`, removes duplicate shared helper
definitions introduced by a stack merge and restores exact common helper bytes.
The independent final rerun uses this cleanup, not an inferred unchanged-input
claim for the earlier helper file.
The [implementer receipt](p6-correction-evidence/receipt.json) records the
auditable run and preserved raw artifacts. Independent reviewer evidence is recorded separately
with actual selected/phase nodes, JUnit, journal and input hashes. The final
combined tree and wheel/sdist-wheel validation belong to the integration receipt;
individual PR checks do not establish combined-tree success. Development CI,
local pytest, distribution checks and independent review are separate from Full
Release Acceptance, which was not invoked. No main merge, public runtime switch,
real-data mutation or activation occurred.

Late source correction `df912d6c43c6c448f9122f2eaaf2728c38956dbf`, tree
`adcc1f0ddba4e15fed00f945ec58108361f6b941`, closes derivative JSON depth
exhaustion incorrectly reaching the authoritative stop boundary. Its targeted
formal regression passed; final independent/combined evidence uses this revision.

## Independent final re-execution

The read-only P6 reviewer executed the corrected `df912d6` input with a separately
written adversarial suite. The [final independent receipt](p6-correction-evidence/independent/final/receipt.json)
records **82 unique executed nodes: 50 formal P6 + 6 shared snapshot + 26 independent
adversarial nodes**, 246 passed setup/call/teardown phases, zero failed or skipped
nodes, and exact collection/journal/JUnit reconciliation. The initial 55-node
implementer selection overlaps these nodes and must not be added as new unique
coverage. Source/test/script/lock/project hashes matched before and after the
independent run, including the later docs-only common merge.

The reviewer independently reproduced baseline expiry, malformed typed metadata,
recomputed-checksum cursor keys, binary Notes, derivative preallocation and deep
JSON false-stop failures, then re-executed their corrected controls. Growing
256-resource Context pagination also demonstrated bounded retained view objects.
Pre-fix failures and the 80-node pre-depth run remain separate historical
artifacts; their success did not close the subsequently discovered depth defect.
The [artifact index](p6-correction-evidence/independent/artifact-index.json)
checks compressed/raw evidence hashes. The independent reviewer authored no
production change and reported no remaining known blocker within this reviewed
P6 scope. This is not a GitHub approval or Full Release Acceptance.

Final common ancestor is `f3cd1c9fa81d78e4a77efb824f5eb4a6b4b95f0a`. Its
late shared change updates one P1 missing-clock fixture observation from 0 to 1
so it still isolates its original missing-clock rejection. Production code and
all P6/shared-snapshot selected test inputs remain identical to the independently
reviewed `df912d6`; the [exact final stack delta](p6-correction-evidence/final-stack-input-delta.json)
records the changed P1 file rather than claiming all tests were unchanged. The
final combined execution separately validates that shared fixture change. The
[reviewer-authored report](p6-correction-evidence/independent/final/independent-review.md)
records the independent finding closure and review limits.
