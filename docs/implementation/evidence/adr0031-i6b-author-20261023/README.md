# I6-B Author validation

I6-B Author implementation and scoped validation are complete. Independent
non-Author I6-B review and complete Release acceptance are unexecuted. Both SQL
Transfer fences and unconnected Provider/Exchange refusal remain in force.

The actual sole base is #149, `review/adr0031-i6a-task-c-20261023`,
HEAD `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`,
tree `e7ca7e361b8b766f1976a12fc84d5cc50ac32232`.

The once-complete ordinary run at `2f874ce` / `e0b50e8` executes 6,288 unique
nodes: 5,987 PASS / 281 FAIL / 20 ERROR, exit 1, plus 57 passing subtests and no
skip. All 212 new wire/planner cases pass. Two old guard fixtures stop at v5's
strict seven-column Resource boundary; one fixture assignment is migrated using
existing `ResourceIdentification`, with all other test AST and four assertion
ASTs unchanged.

Final source `a354348b800177608f6a83e2484cb6a784b7190a`,
tree `169f0f95449c7bd728261b3d7799f795162c03fd`, has exactly the same complete
product tree as that ordinary run. Its source safety 626 (I4 217 / I5 29 included),
wire/planner 212 and external 34 pass. Matched 745 diagnostics give 446 PASS /
279 FAIL / 20 ERROR: only the two fixture cases change FAIL to PASS. The remaining
299 retain the historical I6-C 242 / I7 composition 14 / Transfer 43 allocation.
**The final-commit complete ordinary suite is unexecuted; no replacement aggregate
is reconstructed from these overlapping invocations.**

Each separately installed direct/derived wheel passes safety 626, wire 212,
external 34, reused authorization 27 and reused Task C 132, plus retained control
probes. All product bytes, actual imports, archive and installed RECORD, schema,
UDFs, both fences and integrity/runtime checks are verified. The product has
160 measured files / 6,022,477 bytes. All 5,273 frozen source files survive in the
5,274-member sdist; direct and derived wheel bytes are identical.

The unchanged original Access smoke **fails** at unconnected export in each
minimal installed environment (one node/exit 1 each); subsequent smoke steps are
unexecuted. Its earlier jsonschema-missing collection attempt exits 4 without
executing the original child. These failures remain separate from successful
I6-B and safety lanes. No skip/xfail, permission widening or Transfer activation
is used.

- [Author report and exact scope](REPORT.md)
- [R02–R09 / V01–V09 / T01–T27 requirement map](MATRIX.md)
- [Exact synthetic vectors and hashes](vectors/manifest.json)
- [Lossless execution/tool transport index](raw-index.json)
- [Verified raw-index receipt](RAW-INDEX-VERIFICATION.json)
- [Fresh GitHub/base/tree/duplicate checks](submission/CHECKS.json)
- [Complete evidence inventory](ARTIFACTS.json)
- [Initial GitHub/base/duplicate/setup checks](initial/attempts.json)

Raw receipts retain actual commands, process exits, source HEAD/tree, input hashes,
JUnit, journals, import/RECORD inventories and per-node failure/assertion
comparisons. Failed, interrupted, parser-control and nonfinal development attempts
retain their actual meanings. Final publication HEAD/tree and selected Development
CI are bound separately in the PR/handoff; Development Success is not Release
acceptance. The parent requests the non-Author review next; this task does not
start it.
