# Shared classified-time correction

Implementation follows accepted [ADR 0028](../adr/0028-classified-times-and-sha256-exchange.md),
after its design commit `7d2e736`. This document records the opt-in common change
consumed by both P5 and P6; it is not approval, merge or Release Acceptance.

## Reproduction, root cause and correction

The shared foundation accepted all signed-int64 observation/Provider times and
required a known FieldCandidate observation time. Its generic signed conversion
was correct for Git-native author/committer/tagger times but overbroad as an
observation input policy. The new separate validators enforce classification by
field meaning without changing conversion or original Git bytes/OIDs. Nullable
non-key observation values retain honest unknown time. Coverage, collection and
Source inventory/proof observation coordinates remain positive and required.
Stored-value CHECK constraints and JSON original-type guards have different
roles; SQLite affinity is not claimed as original API type validation.

An initial changed-tree P1–P4/compatibility execution found 14 old fixture failures
and 748 passes. The failures were disallowed negative/zero observation inputs,
including two intended provenance negatives accidentally failing earlier at the
new time guard. The following mapping preserves each original test purpose.
Subsequent execution results and exact input bindings are separate receipts.

## Existing node mapping

| Old node or input | Replacement / retained purpose |
| --- | --- |
| P1 `test_signed_epoch_microseconds_and_observations[-9223372036854775808/-1/0/9223372036854775807]` and imported P2 replay | Renamed `test_nullable_positive_epoch_microseconds_and_observations[None/1/9223372036854775807]` preserves actual Core observation/repository replay; new `test_git_native_signed_values_remain_exact` preserves both signed boundaries and -1/0 native scalar storage |
| P1 `test_generated_source_clock_is_real_sqlite_value` and imported P3 scenario | Generated clock checks now store positive int64 maximum rather than minimum; new invalid Provider matrix rejects the former minimum |
| P1 `test_epoch_int64_boundaries[-9223372036854775808]` | Same test at 1; max case unchanged; new signed native matrix retains minimum coverage |
| P1 `test_missing_provenance_rejected_at_intended_source_evidence_boundary` / imported P3 | Both Python and SQL use observed=1, preserving the provenance-specific failure |
| P1 `test_raw_sql_source_clock_json_overflow_is_rejected_at_actual_type` | Valid observed=1 isolates the original JSON integer-overflow/real extraction guard |
| P2 `test_real_ref_root_observations_retain_force_push_and_replay[sha1/sha256]` | 1-based observation times preserve force-push, immutable distinct captures and duplicate replay |
| P3 `test_current_fields_scale_not_full_edit_history` | Range 1..1000 preserves exactly 1000 updates and one current winner |

The shared new `test_time_policy.py` matrix covers unknowns, strict API input
types, JSON original types/overflow, SQL stored ranges, nonordering unknown
clocks, missing/null, immutable replay, explicit unit conversion and native
signed boundaries. P2's new real Git object tests preserve negative/zero author,
committer and tagger bytes under both SHA-1 and SHA-256. No old test is deleted,
skipped or xfailed to hide a failure; incompatible old allowed values are mapped
to the accepted field class while signed-native obligations remain tested.

## Scope and evidence

The common implementation changes the opt-in Core/Context DDL only; Operational,
Search and public Schema 21 DDL remain unchanged. Nullable observation columns
are not PK/FK components; all composite Coverage/terminal/proof keys remain
required. Existing fingerprint and full disposition audits continue to run.

P5 separately owns Provider/Exchange input and P6 separately owns query/search
behavior. Their integration and independently reproduced five inherited Schema
21 fixture failures must be reported against their final exact combined tree.
