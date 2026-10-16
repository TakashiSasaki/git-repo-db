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

## Committed validation and independent recheck

Exact corrected implementation `2d4f5d4e30903a4ddd9f1f7977560b47cfe29e6b`, tree
`5829799cb8ab0da0dad5306f74df82ff9f84cd31`, passed **828** selected/executed
unique nodes (P1–P4, 20 P2/P3 compatibility, snapshot helpers and installed P1–P4
wheel/sdist-wheel variants). Zero failures/skips. Locked sync, ruff check/format,
schema fingerprint/disposition, implementation-boundary and callsite audits all
passed. Source hashes and real before/after Git status remained unchanged/clean.

Final executable source `f17dd2154f22f965883d8a1943c140f9cc439ae8`, tree
`952c18132b11f393715e67baad33b730e3404e12`, adds disjoint authority-validation
and snapshot-token timing instrumentation and clarifies the synthetic generic
SQLite signed-storage fixture's column name. Its focused **77** nodes passed,
with the same requested checks. This is a focused rerun, not a claim to have
rerun the full 828 selection at that SHA. The root's final combined-tree run
covers both siblings and this final common source separately.

Independent final review executed **119** committed focused nodes and **74**
reviewer-owned counterexamples on exact `f17dd21`, all passing with three passing
phases each, no failures/skips. Those selections overlap local coverage and the
earlier independent **816** impact nodes at `2d4f5d4`; their counts are not added
into a fabricated unique total. The independent source binding, initial
counterexamples, fixes and final executions are recorded in
[evidence/p5-p6-shared/independent-review/shared-review.md](evidence/p5-p6-shared/independent-review/shared-review.md).
The independently reviewed owner design note is retained alongside that report.

Shared material finding **SHARED-R1** was independently reproduced at `3e82802`:
a typed Core snapshot accepted catalog A's read with caller directory B, allowing
corruption stop misrouting. `2d4f5d4` binds trusted snapshot ownership, rejects
foreign/unbound readers and preserves owner notification; Context rejects foreign
snapshot ownership too. A real retained-byte counterexample independently
confirms source A is stopped and unrelated B is untouched after a valid A read.
The new regression also exercises caught fault completion fencing. No material
shared review finding remains.

Raw evidence is under [evidence/p5-p6-shared/](evidence/p5-p6-shared/): exact
commands, environment versions, full source hashes, collected/executed IDs,
setup/call/teardown journal, JUnit, logs and artifact hashes. `.gz` files are
losslessly compressed originals (use `gzip -dc`). The earlier exact `3e82802`
run deliberately remains: **826 passed, 1 failed** because a cancellation-control
monkeypatch did not forward the new `metadata_only` option, plus a legitimately
stale source-index audit. Both were corrected, not skipped. Its first runner
hardcoded `status_before="clean"` while untracked scratch `work/` existed; do not
use that field as a clean-worktree assertion. Tracked source hashes stayed
unchanged. Later receipts capture actual status and put scratch outside the tree.

The old input mapping above preserves the signed-native and provenance/overflow
purposes explicitly. The existing cancellation test now forwards optional
validation arguments and continues asserting actual SQLITE_INTERRUPT without a
corruption stop. No inherited Schema 21 failure is hidden or counted as passing;
the final combined evidence owns their exact-revision reclassification.

## Final test-purpose follow-up

A final legacy-negative check found one more unrelated zero observation input in
`test_generated_source_clock_is_real_sqlite_value`: its missing-clock SQL could
fail the observation CHECK before reaching the intended clock guard. The
one-line test-only correction at `f23dfdabff5a2f9a95104fa8703b81f62802b7cb`,
tree `e087eb66e243bf4fb2d671820370d74923a805b1`, changes that input to observed=1.
No production source, DDL or executable script changes from independently
reviewed `f17dd21`. The same node and imported P3 scenario now exercise their
original missing-clock purpose under a valid unrelated observation coordinate.

Exact clean `f23dfda` passed **79** focused nodes (the preceding 77 plus these two
P1/P3 controls), all requested checks, zero failures/skips. Selection, exactly-once
starts, 237 passing phases and JUnit identities reconcile in the added evidence
folder. The final docs-only input-identity proof now binds all 307 scoped source/test/script/project/lock files to
`f23dfda`; the earlier ae087d3 proof is retained with its original name. These
focused runs overlap, so their passing counts are not additive unique coverage.

The independent [f23 addendum](evidence/p5-p6-shared/independent-review/shared-review-f23-addendum.md)
executes both changed-purpose controls on exact `f23dfda`: **2 passed**, zero
failures/skips, fresh reconciled three-phase/JUnit evidence. It independently
confirms no production `src` delta from `f17dd21`; the prior full/focused review
receipts retain their original revision scope. The two nodes overlap earlier
coverage and are not added into a unique count.


## Evidence identity scope clarification

Independent review measured a distinct live CI-planner acceptance-input hash at
`f23dfda` versus `f3cd1c9`: 22 added evidence files are included by the unchanged
conservative CI policy. The scoped 307-file SHA-256 map proves unchanged declared
code/test/build inputs; it does not prove full CI acceptance-hash equality. Exact
CI hash values, changed paths and Git blob entries are saved in the independent
`evidence-ci-inputhash-delta.json` artifact and the evidence README. Subsequent
evidence additions may change that live CI hash again. This wording correction
changes no source, tests, scripts or CI policy and makes no new execution claim.
