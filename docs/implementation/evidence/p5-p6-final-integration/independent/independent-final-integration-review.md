# Independent final combined-tree and evidence review

The reviewer owned no production implementation. Review and execution used the
separate detached clean worktree `/workspace/work/review-integration-tree` with
its own locked editable environment; root artifacts were read only.

## Final reviewed input and result

Commit: `0cb51d46d87d99c035f5162f4a7ed11970cf3b4c`.
Tree: `443c4b25478c1e406136c77d6689e87bd72231f9`.
Live CI-planner acceptance input hash at that executed commit:
`60c94caae7eed9d7045ccf98127481da31a1100f93ae54b2f588c65096d3535b`.

Independently collected and executed **49** nodes: all **29** formal P5/P6
compatibility nodes and the existing **20** P2/P3 compatibility nodes. All passed,
with zero failures/skips, exactly 49 unique starts, 147 passed setup/call/teardown
phases and matching JUnit identities. The imported-function JUnit `file` attribute
was not used as the collection identity. The execution ended successfully and the
review worktree remained clean. See `reviewer-reconciliation.json`, `selected.txt`,
`journal.jsonl`, `junit.xml`, `pytest.log` and `uv-sync.log`.

Commands:

```sh
uv sync --locked --group dev
uv run --no-sync pytest tests/integration/p5_p6_compatibility tests/integration/p2_p3_compatibility --collect-only -q
uv run --no-sync pytest tests/integration/p5_p6_compatibility tests/integration/p2_p3_compatibility -q -o junit_family=xunit1 --junitxml /workspace/work/review-integration-evidence/0cb51d46d87d/junit.xml --journal /workspace/work/review-integration-evidence/0cb51d46d87d/journal.jsonl
```

## Actual branch/PR DAG and tree difference

Read-only `gh pr view` and `git ls-remote` matched the pushed heads:

- #82 design: `7d2e736f6fd4aa5e30417fb99fa72d27f93ea270`, base #79.
- #83 shared: `96db618285d5ce7b0d0c276d18f81bdbc50c34c1`, base #82.
- #80 P5: `48b60231b1ef7075c55ff6f43aca0c68ad95e5a8`, base #83.
- #81 P6: `76489443687123ef99fb33510c77fd40ce739d28`, base #83.
- #84 sibling assembly: `f67e9298ff7915b4f7b1f0bef0c344f56d2cc064`, base #83,
  with both actual P5/P6 heads as ancestors.
- #85 formal compatibility tests: reviewed `0cb51d4`, base #84.

Both siblings contain the identical common #83 commit; neither contains the
other's head or initial/corrected production implementation. The exact diff from
assembly `f67e929` to tested `0cb51d4` is five files under
`tests/integration/p5_p6_compatibility/`, with **no production-source difference**.
Thus the tests have a formal review/integration route, not a temporary validation
branch alone. `dag-and-tree-review.json`, `pr-state.json` and `pr85-state.json`
preserve actual identities and checks. The observed remote main remained
`5e778bf61ef660f65bf5fb22bdb08840503b8464`.

## Root full selection and receipt independently audited

The separate root final selection has **1,091** unique nodes, all passed, zero
failures/skips. The reviewer independently checked every collected/start/JUnit
identity, all 3,273 phases, one successful journal finish, root reconciliation
flags, clean before/after state, all 342 declared source/test/build/policy input
SHA-256 values against the exact Git commit, and every recorded raw artifact hash.
The receipt SHA-256 is
`6d75d7dbabb9b2215646a8c588e2e3a9691239d3db7b95faad3e1a486e34345b`.
All required sync/lint/format/schema/boundary/callsite commands and the additional
publication audit exited zero. The separately classified legacy run exited one
as expected; it is not represented as a passing lane.

Actual final partition: P1 317; P2 197; P3 75; P4 202; P5 47; P6 50;
P2/P3 compatibility 20; P5/P6 compatibility 29; architecture spikes 128;
shared snapshot tests 6; packaging 20. The independent 49 nodes are a rerun of a
subset of these 1,091 nodes, **not 49 additional unique committed tests**.

The five legacy Schema 21 cases were executed normally and have exactly the same
node identities and failure messages as the initial baseline: one missing
`cache_leases`, three missing `jobs`, one missing `cache_locators`. No deletion,
skip or xfail hides them. Their final JUnit and journal remain separate; the
independent comparison is in `root-receipt-review.json`.

The intermediate root `0088a3d` run retained 1,086 pass / four installed P5 fixture
failures. The fixture still relied on an implicit Operational ledger that the
corrected API refuses. The explicit ledger fixture correction is included in the
final clean input, where all four SHA1/SHA256 direct/sdist-wheel P5 cases pass.
The earlier run is failure history and is not accepted as final verification.

## Installed distributions and absence of scratch/database contents

Independently checked all **18** saved archives: **12** wheels (six direct plus
six built from sdists) and **six** sdists. Each byte count and archive SHA-256
matches the root receipt. Every archive contains exactly the same **118**
`repo_catalog` source/resource entries as the reviewed Git commit, with identical
per-file SHA-256 values and no missing/extra package sources. Archive members were
read without extraction. Separate path checks found no workspace/scratch,
`.git`/`.venv`, DB/SQLite, WAL/SHM or bytecode-cache members.

These checks substantiate archive/input identity; installed behavior comes from
the separately executed 20 packaging tests. Per-archive manifests and hashes are
in `distribution-source-review.json` and `archive-path-review.json`; reviewer
scripts `check_distributions.py` and `audit_root_receipt.py` are retained outside
the reviewed tree. Python 3.12.14, SQLite 3.53.1, Git 2.52.0 and uv 0.12.19 were
recorded; editable imports resolve to the separate intended review worktree.

## Findings and closure

1. **Shared stop-owner binding:** independent real-byte corruption initially
   showed a typed A reader routing stop to unrelated B. Fixed in the common
   contract and independently rechecked on exact corrected shared source; the
   final combined source retains that correction. Shared reviewer reports bind
   its executable counterexamples and exact SHA/tree separately.
2. **Combined test/evidence precision:** unused duplicate format parametrization
   and the unsupported native-byte claim in a Context-only test were removed;
   complete Search hits are compared across projection/fallback, rather than
   count alone. The final independent 49-node execution includes these corrections.
3. **Actual export exclusion:** the imported thread timing test alone did not
   prove that a writer reached its OS lock. The reviewer independently ran a
   separate-process `LOCK_EX|LOCK_NB` probe at the actual after-Core/before-Context
   export cut: acquired before, blocked at the cut, acquired after release. Root
   formally integrated that counterexample as `test_export_gate.py`; its final
   exact-tree node passed independently. This proves cooperating local lock
   exclusion at that cut, not power-loss durability or hostile-writer safety.
4. **Docs-only input wording:** saved evidence files change the unchanged CI
   planner's conservative acceptance hash. A scoped runtime/test/build hash map
   can prove byte identity without implying equality of that larger CI hash.
   This distinction was corrected in common `96db618`; the exact measured earlier
   f23/f3 hashes and 22 evidence-file deltas remain preserved. Any later evidence
   commit must state its own scope/hash rather than claiming full CI-hash equality.

No remaining material final integration/evidence finding. This review verifies
focused local development/integration, independent reexecution and exact evidence;
it does not turn Development CI green into complete runtime acceptance. Hosted
Development CI is separately verified below; full repository/Release Acceptance,
P7 recovery/activation and P8 public activation remain unclaimed scopes. No main update, real-data or
backup mutation, release/tag, authentication-based live acquisition or intentional
Pages publication was performed by this reviewer.

## Hosted Development CI receipt independently checked

For run `38860098880`, independently decoded actual timestamped bounded-log
records (excluding echoed script text), checked the ZIP byte length and SHA-256,
and verified all **21** indexed member sizes/digests. The stored binding/index/
manifest match decoded members. GitHub's Git-commit API independently confirms
that hosted temporary merge `47e051f694b5428dae4f5af24fbb6af340ab84c8` has tree
`443c4b25478c1e406136c77d6689e87bd72231f9`, exactly the executed feature tree.
The checked receipt reports `development_checks_passed`, `full_acceptance=false`,
**zero hosted runtime nodes**, and the exact tested CI input hash above. Thus
the development check result is verified without implying hosted runtime or
Release Acceptance execution. `hosted-development-review.json` and retained
`check_hosted_receipt.py` document this independent read-only verification.
