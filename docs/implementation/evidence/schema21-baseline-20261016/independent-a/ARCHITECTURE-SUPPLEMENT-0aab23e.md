# Independent A supplement — decoder projection fixture and verified skill lessons

Reviewer: `/root/review_a`, no remediation production author.
Reviewed commit `0aab23e08eba6e8ed5b62a826f3b879203e14d64`, tree `3669ad70cf226a4d260a8bbec91082087de50fbe`, parent `83d3c1401891b62eb98724262dd8709f6b3c44eb`.

**APPROVE the decoder-test correction.** The two remaining stale Core queries now read actual Search projections through explicitly opened readonly `SearchStore` contexts. Original assertions remain: rebuilt code contains only genuine canonical content despite a deliberately injected corrupt decoder candidate; semantically equivalent commit metadata cannot suppress or duplicate a valid commit projection. The subsequent public QueryService checks still reject fabricated byte interpretations and return the genuine code hit. Nothing was skipped, xfailed or relaxed. This is the same proven stale-observation boundary, not a new production routing change.

`git diff 31b7bf3..0aab23e -- src` is empty: independently reviewed/executed production remains unchanged. Packaged schema resources are unchanged. Previous architecture review and independent42-node source-regression execution remain valid for identical production; this supplement makes no claim that the interrupted or disk-exhausted full runs passed. Exact full/cohort results belong to the new final execution evidence.

The layered-root-cause skill paragraph accurately instructs running the full affected lifecycle cohort after correcting SQL, retaining actual partial/fresh IDs, prefixes, clocks and honest current Coverage. Workspace TMPDIR/basetemp guidance correctly treats disk exhaustion as a separate environment failure, preserves failed evidence and limits deletion to confirmed completed disposable directories. Independent current df inspection confirms /tmp and /workspace are distinct capacity domains (/tmp8.8GiB versus workspace32GiB); these measurements are diagnostics, not performance benchmarks or blanket disk-capacity guarantees.

One precise skill wording finding: the201-obsolete-input regression exercises a complete stale-only200-row SQL batch followed by mixed remaining input. It does **not** establish more than one complete stale-only200-row batch. The author has already identified and agreed to change that phrase to a stale-only200-row batch. No production expansion, additional huge test or weakened assertion is requested. Skill approval is subject only to that literal precision correction; the intended current-key filtering, cancellation, repeated/empty rebuild, retained Core text and non-global-atomicity guidance are otherwise approved.

This is a read-only narrow review. It adds no new runtime execution, owner authorization, P7 redesign, real catalog action or merge.
