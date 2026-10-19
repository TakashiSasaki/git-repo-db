# ADR 0030 I1 contract-freeze gate

## Scope and reference state

This gate fixes I1 type/admission consistency on Draft PR #107. It does not
implement I2 GraphQL acquisition, I3 selective Exchange or I4 query/search.
The accepted ADR is unchanged. Context retains 19 tables, existing composite
keys, exactly six relation roles and no Witness/history table.

GitHub REST was reread before work: PR head
`ebcf865ede7ee661446b6fd7edf1be6ef7e623a8`, tree
`e61ffd6d0aac0f27ae109fb5debedc96cdd2e860`; base/main
`6780088befd33e711230d570bb291edb2ee40cbf`; open, Draft, unmerged.
The initial `offline` check succeeded. The initial `registry-sqlite-3513`
[run 39239845865](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39239845865)
reported 1,861 passed / 37 failed. These are historical results, not the new
revision's acceptance. Final head/tree, hosted checks and independent review
are recorded in the live PR body after push and reread through the API.

## Reproduced contract violation and correction

On the initial revision, register an Issue, then
`ResourceKey.timeline_event(issue, genuine_event_id)`. Without registering any
Transfer report or event-type observation, create a
`ResourceRepositoryRelation(event, "transfer_from_repository", clock, target,
provenance, observed)` (or the `transfer_to_repository` role). Both
`ContextStore.admit_repository_relation()` and the production
`Context.admit_repository_relation()` successfully inserted it. Their result
wrappers also admitted it. All eight negative assertions (two roles, two
adapters, two APIs) failed with `DID NOT RAISE` before the fix.

The typed FK establishes `comment / timeline_event / parent issue`; it does
not establish the event type. Generic relation admission bypassed the separate
actual-type admission check required by **ADR 0030 Q-S10**, and allowed endpoint
writes outside the coherent event-report unit of Q-S4/Q-S5. Constructing a
TransferEventReport elsewhere was insufficient to protect those public paths.

Transfer endpoints now require `admit_transfer_event(TransferEventReport)`.
Generic admission, its result wrapper, and generic
`Context.relation(... relation_kind="transfer_event_report")` reject these
writes. The dedicated path uses a private row inserter only after complete typed
report validation, with its existing savepoint, EventReportKey pairing and
whole-report replay comparison. Selection-truncated reports remain inadmissible;
a genuinely one-sided report remains complete for what was actually supplied.
An endpoint FK failure rolls back the event Resource, scope and all endpoints.

The report's existing `resource_relations` scope retains explicit
`event_type="transferred"`. Reads and recovery validation no longer supply that
value when the scope/type is missing. Invalid stored data fails closed;
invalid incoming arguments do not create a corruption stop.

This is an I1 typed report contract. It does not authenticate Provider origin or
prove a caller's observation was true. I2 must extract and check the actual
Provider event type and genuine Resource coordinates. ResourceRepositoryRelation
remains an endpoint value type usable inside a report; it does not itself carry
Provider event-type authority. Raw SQL supplies structural CHECK/FK guarantees,
not Provider semantics; direct SQL endpoint insertion without a report fails the
stored semantic validation. No new table, FK, key, role or schema fingerprint
was needed.

## Verification and limits

The original 20 counterexample categories are retained and augmented by cases
21–24 in the [implementation contract](adr0030-i1-context-contract.md). New
parameterized cases cover generic admission/replay, missing/invalid stored type,
whole-unit rollback and generic scope admission. The stored-data test's first
attempt to UPDATE/DELETE immutable evidence was correctly blocked by the SQL
guard; the corrected fixture directly inserts incomplete disposable data without
disabling guards. That fixture setup failure is not claimed as product evidence.

Local focused verification uses the worktree's locked environment: CPython
3.12.14, SQLite **3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
This newer supported SQLite run is distinct from hosted minimum-version 3.51.3.

The P1/P3/Access focused run plus the direct I3 boundary control passed **910**
tests: P1 349, P3 77, Access 483, I3 refusal control 1. All five audits passed:
`build_p1_schema.py --check`, `audit_p1_schema.py --check`,
`audit_callsite_dependencies.py --check`,
`audit_implementation_boundary.py --check`, `audit_context_registration.py`.
Ruff lint and format checks passed across `src tests scripts`.

The accompanying [local verification record](evidence/adr0030-i1-freeze/local-verification.json)
records the broader CI-selection reproduction (**1,875 passed / 37 failed**,
with the exact same 37 failing nodes) and distribution checks. No failure
is hidden, newly excluded or xfailed to turn the registry job green; the
repository's existing default live/benchmark exclusions remain in force. This is bounded
I1 development validation, not complete release acceptance.

## Downstream failures remain visible

The [37-node baseline inventory](evidence/adr0030-i1-freeze/baseline-failures.json)
preserves each actual CI exception and assigns its prerequisite and later owner.
The [implementation contract §8](adr0030-i1-context-contract.md#8-categorization-and-root-cause-analysis-of-37-post-i1-integration-failures)
contains the complete human-readable node list and resolution conditions.

| Group | Count | Direct observation | Next owner and required rerun |
| --- | ---: | --- | --- |
| P5 intake/paired admission | 5 | `UNSUPPORTED_UNTIL_I2`; the paired-cut test instead sees this AcquisitionError before its intended injected RuntimeError | I2 implements typed intake and reconciliation; rerun all five |
| P5 Exchange integration | 5 | `UNSUPPORTED_UNTIL_I2` in `_setup_source_catalog()`; Exchange is not reached | I2 supplies real acquisition, then I3 runs the original five Exchange tests |
| P6 query/search | 27 | Retired `Context.admit_repository()` dependency, mostly in shared fixtures; two direct Context-only callers | I4 migrates fixtures to typed relations and tests actual query/search behavior |

The separate passing
`test_i1_relation_export_guard_without_i2_acquisition` constructs a source using
I1 admission and directly observes the existing `UNSUPPORTED_UNTIL_I3` export
guard. This is a standalone refusal check, not the five Exchange integration
failures and not implementation/acceptance of I3 Exchange. After I2, the original
five tests must reach and validate Exchange; I5 owns combined acceptance.

The independent reviewer must use the exact pushed head/tree recorded in the PR,
read only, checking Transfer admission, Mapping ClaimKey support, P7 stops,
public APIs, SQLite NULL/FK/trigger/REPLACE/UPSERT behavior, packaged schema and
these skill/documentation changes. The verdict and unresolved findings are
recorded against that immutable target in the PR; later changes require a new
review target. PR #107 remains Draft and is not merged.
