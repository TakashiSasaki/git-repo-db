# P5 correction execution evidence

The production freeze is `c90e9b12f7b240efdeb5dcffc12098680b04317f`, tree
`4266da7f4b0f169260112cfe8075a9f1691b6ce5`. The submitted branch additionally
merges the identical shared final `f3cd1c9fa81d78e4a77efb824f5eb4a6b4b95f0a`
and contains the explicit-ledger packaging fixture fix
`2833e50b694ee330d6630d1fe631d9fa158a992f`. Evidence/skill prose follows without
changing runtime code. No P6 implementation is an ancestor of this P5 branch.

- `author-focused/`: 160 collected/executed/passed (47 P5 + 113 P2 native), zero
  failures/skips, at `3c4e62fd4006bfc6c27f3188062d596a9e81e7da`, tree
  `aed20939f958c459f876516eeee7664356be2b5c`. Source/selected test inputs are
  unchanged in submitted283; the changed packaging fixture is not part of this
  160-node selection. Ruff, format, locked sync and four required audits passed.
- `independent/`: separate read-only reviewer executed all47 P5 plus17 external
  adversarial/control nodes, 64 unique passed, on exactc90. Its original receipt,
  command/version/input inventories, JUnit, phase journal and test sources are
  preserved. [Review](independent/review.md) maps nine independently reproduced
  defects to corrected-SHA re-execution, and identifies six Provider-order
  permutations that already passed the baseline. The reviewer authored no
  production change.
- `distribution-clean/`: 4 passed (SHA-1/SHA-256 × wheel/sdist-wheel), exact283,
  from a clean `git archive` extracted outside the author's scratch-bearing
  checkout. The isolated installed modules are checked to come from site-packages.
  Manifest records wheel, sdist and sdist-wheel SHA-256 and every sdist member;
  no work scratch or SQLite/WAL/SHM is included. Both wheel hashes are identical.
- `reconciliation.json`: exact selected/start/setup/call/teardown/JUnit mapping
  plus post-execution input differences. c90→submitted differences affecting
  executable inventory are the common P1 SQL-fixture-purpose correction (tested
  and evidenced by the common branch) and explicit-ledger distribution fixture
  (rerun here). Production and all47 independently selected P5 nodes are identical.
  Skill prose is separately identified. The47 overlapping P5 nodes are never
  added twice to claim a larger unique total.

`baseline-reproduction/` preserves independent8-failure original-source receipt,
separate ninth completion-stop failure, six successful Provider-order controls
and non-time-real control artifacts. Exact baseline8 source digest matches the
original receipt. The historical six-control source digest predates its appended
non-time-real test; the final fully bound sources and64-node run are in
`independent/`. Historical evidence is not rewritten as a new PASS.

`nonfinal/` preserves author iteration JUnit/journal failures. The old broad
runner reported844 passing tests but source changed during its later phases;
that mixed runner is explicitly excluded from final acceptance and unique counts.
Its4 distribution failures reproduced the missing explicit Operational fixture;
that fixture was corrected rather than skipped. A subsequent scratch-bearing
sdist's installed tests passed, but its artifact was not a clean committed-tree
package; it is likewise nonfinal. The clean-archive4-node distribution phase is
the accepted package evidence. Auxiliary `author-focused/packaging*` records are
superseded by that explicitly bound distribution phase.

The final P1–P6 combined tree,20 P2/P3 compatibility nodes, hosted Development CI
and formal cross-sibling tests-only PR are owned by the integration report. This
P5 receipt does not infer them from sibling green checks. Full Release Acceptance,
P7 recovery/activation, host power loss and P8 runtime activation were not run.
All source/test data is synthetic; no authenticated live fetch, main update,
real catalog/backup operation, release or publication was performed.
