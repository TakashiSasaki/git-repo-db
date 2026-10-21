# Task D review-only publication

The [complete original report](REPORT.txt) records the independent review's
**NOT READY** verdict, one new High finding F1, exact source/input hashes,
confirmed invariants, actual SQLite source IDs and pragmas, SQL results,
product-integration risks, and prerequisites for proceeding with I2.

F1 is an incomplete temporary Transfer fence. The proposal fences both endpoint
roles in `resource_repository_relations`, but a Provider-only
`transfer_event_report` can enter `resource_relations` without touching that
table. The existing reference reader returns the report with no native I7
Resource, Parent report or endpoint rows. This is not an independently verified
production fix or a new interpretation of G3=A.

## Frozen evidence

- [Minimal literal SQL](F1-reproduction.sql), [execution helper](reproduce_f1.py),
  and actual observations on [3.51.3](F1-minimal-3513.json) and
  [3.53.1](F1-minimal-3531.json).
- [Independent probes](independent_review.py), [original runner](run_review.py),
  and [receipt reconciliation](finalize.py).
- [Minimum summary](minimum-summary.json) and [newer summary](newer-summary.json).
  Each has 301 unchanged-candidate cases: 295 pass and six unexpectedly accept
  the reserved report. Seven separate mitigation controls pass. The combined
  independent runner exits 1; the Author's fresh 133-case rerun exits 0.
- [Physical schema comparison](schema-comparison.json). The original
  `product-vs-candidate.diff` is preserved inside the evidence ZIP.
- [All 3,723 original input hashes](input-manifest.json),
  [end-of-review binding](final-binding.json), [independent runtime provenance](runtime-provenance.json),
  and [Task C archive verification](archive-verification.json).
- [Original evidence ZIP](task-d-review-evidence.zip),
  [its original index](artifact-index.json), and [bundle receipt](bundle-receipt.json).
  The ZIP is 7,824,546 bytes, SHA-256
  `569df9d613db368cf4b4515d70d54df5c66be5eaa75ed74443f81ba9e30f0280`.
  All 60 indexed files verify; the 61st member is the index itself.
- [Publication binding](publication-binding.json) verifies the 18 byte-identical
  readable/archive copies and unchanged reviewed inputs.

The ZIP contains full SQL traces, parameters, per-table pre/post rowset hashes,
runtime options, process receipts and the original failed serializer attempt.
It also preserves the Author-case reruns, independent source ZIPs and built
SQLite libraries. It contains synthetic disposable data, not a real catalog.
The full 60-file index describes the extracted archive, not just the readable
subset copied alongside this guide.

The preserved report SHA-256 is
`c3c3757bdb87aa7517a2f12dbcf3e9e597ef6a2124c01477ef5176f6537bca6c`.
No result was edited for publication. Earlier statements prohibiting GitHub
writes describe the review freeze. The subsequent owner instruction,
“レビュー専用のプルリクエストとして提出してください”, separately authorizes
this review-only Draft PR. It authorizes no product implementation or merge.

## Reproduction

Extract the ZIP into a new disposable workspace. Provide a checkout at exact
`9eaa5111c94204c4adf791cd1565b704728493f1`; do not use the moving default branch.
The original runner paths are recorded in `process-receipts.json` inside the ZIP.
For another location, point `PYTHONPATH` at that checkout's `src` and the
extracted `author-rerun` directory. Select the independently built SQLite library
using `LD_LIBRARY_PATH`, or rebuild the included official source ZIP using the
commands in [runtime provenance](runtime-provenance.json). Query the actual
`sqlite_version()` and `sqlite_source_id()` before interpreting results.

Run `independent_review.py NEW_EMPTY_OUTPUT_DIRECTORY EXPECTED_SQLITE_VERSION`
or `reproduce_f1.py` with those settings. Both return exit 1 when F1 is reproduced.
The complete original commands and source-ID assertions remain in the archive.
For the Author rerun, use the preserved `author-rerun/probe.py` with a fresh
output directory. Do not overwrite existing review evidence or count earlier
iterations as additional independent cases.

This publication validates byte preservation, syntax, links, diff scope and
documentation infrastructure. It does not rerun or approve the product suite,
installed distributions, Access smoke, I3–I8 or release qualification. A green
Development check does not change the NOT READY review verdict.

## Procedure and reusable lesson

Applied repository procedures: [exact-tree CI verification](../../../../.agents/skills/ci-final-tree-verification/SKILL.md)
and [lessons-to-skills assessment](../../../../.agents/skills/lessons-to-skills/SKILL.md).
No skill or policy file is changed in this review-only PR. A future authorized
implementation handoff should add this verified lesson to the existing Context
registration/Exchange guidance: when temporarily disabling a typed operation,
enumerate and fence both relation-report and endpoint representations, including
Provider-only reports; an endpoint-only trigger is not a complete operation
fence. Retain the positive general-report controls and both real runtime results.
