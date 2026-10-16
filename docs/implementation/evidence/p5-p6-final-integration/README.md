# Final corrected P5/P6 integration evidence

Entry report: [corrected integration](../../p5-p6-corrected-integration.md).
`final/receipt.json` binds the clean committed final run to its source/tree,
exact342 tracked runtime/test/build inputs, full commands, environment versions,
1091 selected/executed/passed nodes and18 distribution archive hashes. Raw XML,
JSONL and logs are gzip-compressed with deterministic mtime0; stored gzip hashes
and decompressed hashes are in `artifact-index.json`. Distribution binaries remain
in the execution workspace; manifests and independent source-byte inspection are
retained here. They are not released/tagged artifacts.

`independent/` is separate read-only verification of49 nodes and distribution,
receipt and DAG inspection. Do not add its overlapping nodes to1091. Hosted
Development CI executes0 runtime nodes; its verified log receipt says
`development_checks_passed`, `full_acceptance=false` and uses the same effective
source tree. The21 indexed receipt files were SHA/size-checked after decoding the
bounded log ZIP. This is not Full Release Acceptance.

`intermediate-0088/` preserves1086pass/4fail before the explicit-ledger installed
fixture correction; it is not a final PASS. `inherited-main/` and final legacy
JUnit retain the same five pre-existing Schema21 fixture failures; none were
skipped, xfailed or removed. `fixture-iterations/` preserves earlier synthetic
fixture setup failures and subsequent targeted passes.

The scoped342 input hash identity is not the live CI acceptance input hash.
Adding these evidence files changes the latter under existing policy. No policy
was weakened to hide them. Exact final published SHA/tree and live CI hash are
reported outside the commit in PR#85 and the owner handoff to avoid self-reference.
