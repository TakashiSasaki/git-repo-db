# Independent review, second frozen candidate

Reviewed commit `d9d6860131111d0d0ef6d386e809a759bb6fc3cd`, tree
`5551d30561331ccc5ceacbd8c46ca62db5c48690`. Input manifest SHA-256:
`82a4daf7eb8b96abb6292da74d12a8ffec8feff397067216a94b6ee9f55d3e0e`.
Composed SQL SHA-256:
`c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee`.
The reviewer used a new detached worktree, checked every frozen input hash, and
did not modify candidate inputs.

## Corrections independently verified

IR-F01 and IR-F02 from [round one](round1-review.md) are corrected. Independent
Parent provenance is now an explicit support coordinate in real composite FKs;
its original clock remains in its full scope key, independently of the Transfer
clock. Independent attribution/clock succeeds without rewriting either report.
Cross-paired members/provenance still fail actual FKs. Missing Parent provenance
fails CHECK rather than escaping through a NULL composite FK.

Changed Resource non-key identification metadata is rejected before INSERT,
IGNORE, REPLACE, `DO NOTHING` and `DO UPDATE`. Exact `DO NOTHING` retains the
original row; UPDATE remains forbidden, even for a no-op payload. The trigger
is not mislabeled as an FK guarantee.

The reviewer independently repeated the author driver: baseline 9 controls and
candidate 13 grouped cases/140 steps on both real runtimes. The separately
written reviewer script records 70 observations on each runtime, with 70 matching
their explicitly stated expectations. Runtimes remain Python 3.12.14 / SQLite
3.53.1 and Python 3.13.5 / SQLite 3.51.3. These reruns and overlaps are not added
into a distinct-test total.

IR38 independently verifies a real mid-unit rollback: the report group and
first endpoint are inserted, the second endpoint's absent Repository triggers
an actual FK error, and the savepoint rolls back the report and both endpoints.
The already admitted Event, Issue and Parent report remain. SQL traces show both
endpoint INSERT attempts; post-failure rowsets equal the pre-unit rowsets.

## Additional finding: IR-F03

IR39 supplies a Transfer report whose `members_json` declares a complete Provider
Repository ResourceKey and whose corresponding Provider endpoint ID matches it,
but that Resource does not exist in the disposable database. The experimental
`admit()` routine accepts and commits the report and endpoint; no Provider
Repository Resource is created, and FK/integrity checks pass.

This is **not** a defect in the demonstrated typed Parent or exact support FKs.
Those constraints do not cover arbitrary JSON member lists. It is a missing
dependency check in the experimental typed Transfer-unit path, relevant to the
preserved general member/dependency semantics in T10/T11. The general
reconstruction example already checks its members explicitly. The Transfer
helper must likewise withhold a missing declared Resource member, or the verdict
must remain bounded to its narrower proven referents. It must not fabricate the
member or silently erase it from the original coherent group.

The receipt marks IR39 as a counterexample. A matched observation is not a passed
contract obligation. The appropriate verdict for this frozen round is
**PARTIALLY DEMONSTRATED**: typed Parent/reference relocation succeeds, but
complete Transfer-unit dependency preservation remains unsatisfied by this
helper. No new architecture choice or authority table is needed to address it.

## Additional finding: IR-F04

IR40 independently supplies `True`, `100.0`, and `"100"` as the Python
`observed_at_us` argument to the experimental Transfer admission routine. All
three are accepted and committed as SQLite INTEGER values (1, 100, and 100).
ADR 0028 explicitly requires refusing booleans, floats, and numeric strings at
the Python/API boundary. SQL storage affinity and CHECK cannot establish the
original caller type. The helper needs the existing strict observation-time
validator before issuing SQL; this is an application-boundary gap, not a defect
in the typed Parent FK or a claim that SQL alone must reject pre-affinity types.
IR40 records these successes as counterexamples, not satisfied obligations.

## Evidence and documentation review

[Script](round2-probe.py), [current runtime](round2-current.json),
[minimum runtime](round2-minimum.json). Their hashes, actual errors, transaction
state, SQL traces and rowsets are retained. The first-round counterexamples are
not rewritten by these corrected executions.

The appended prose-only section “Verify immutable replay before conflict-ignore
handling” in `.agents/skills/three-store-invariants/SKILL.md` accurately records
the observed failures and the distinction between replay triggers, row-local
CHECKs, and real FKs. It is a procedural lesson, not an architecture acceptance
or product-change permission. This prose review is outside the frozen executable
inputs and is not represented as runtime execution of that later file.
