# Independent exact-tree review: fourth I3 candidate

Reviewer: read-only subagent `/root/i3_invariants` (no production authorship).
Target HEAD `3b73cddd92fce7566114100169cfc09899eafdd1`, tree
`845f05b7846a097284545013c05a2ae176ffd883`, committed and pushed.
Independent I3 suite: 64 passed; schema/fingerprint and call-site audits passed.
Verdict: **CHANGES REQUIRED**. All historical findings were confirmed corrected.

An empty package with `max_work=0` and an omitted receiver selection nevertheless
bound its PackageKey and wrote domain checkpoints after consuming decode work.
Only the explicit receiver-selection path installed the cumulative processing
ceiling; a nonempty fixture's database read limit had masked the empty case.

Correction: install the same ceiling for the resolved default receive selection
before preflight/binding. Check already charged cumulative work immediately when
the effective ceiling is learned; do not refund or restart bounded decode work.
Regressions compare implicit and explicit zero-work receive on an empty package.

The subsequent committed/pushed SHA/tree and verdict are recorded in PR #108.
This historical record remains CHANGES REQUIRED and is not final approval.
