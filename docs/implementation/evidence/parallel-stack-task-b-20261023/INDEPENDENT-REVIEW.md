# Independent Task B audit — PASS for evidence/plan submission

Independent non-Author agent review of the root agent's frozen-source integration
impact audit. No production source, existing PR, branch ref, accepted ADR or old
evidence was edited. Independent reproduction created only local scratch Git
objects and temporary indexes. The candidate is an audit simulation, not a
published product integration branch. The assembled README, PLAN, DAG, CI-AUDIT, DESIGN-REVIEW and new skill
lesson have been read and checked against the actual evidence. This scoped PASS
supports documentary Draft submission; it does not accept product integration.

## Verified results

- All assigned fixed Git trees match: I6-A #149 `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`
  / `e7ca7e361b8b766f1976a12fc84d5cc50ac32232`; sdist #144
  `ededcd83eb2d99a602ba18c8fe3c177125c825ac` /
  `2c721a0e8a58ebe8d1f795da821ea4e317b73e7e`; C0-E1 #147
  `e7762952e18061de8c8235beaeddf42f20ad9f5a` /
  `9c220c6606703aa36606896eb52d0a8966914a36`. Their actual pairwise merge-base
  is #133 `f16e5b1713bde9a2f18263a25397c4b450fd5773`.
- Independently recomputed the saved full 50-node DAG (34 open and 16 recent
  merged/closed PRs): every HEAD/tree, base/merge-base, ancestor flag and reduced
  edge agrees. Current main is `cb532242c7aa86c6af5b6232b71c0906ea38f5c5`, tree
  `318ad07874ab436206e6a61f231b308a421cfc54`. Its merge-base with all frozen
  features is `d92377599a50f192f534836fc12402a5fe87ca83`; main merge commit
  non-ancestry is historical topology, not a conflict. Read-only main/feature
  merge-tree calculations preserve each exact feature tree.
- Recomputed six shared files, all between I6-A and sdist. Independently executed
  all six integration permutations, resolved the two actual text conflicts by
  preserving both imports and both independent skill lessons, and obtained the
  same exact candidate tree `2c61c7d79bf9a95c4f04ccdbda8fae1fe15d5491` every time.
  Four auto-merged shared files retain both parent changes. Complete `src` is
  identical to I6-A; planner/checker blobs are exactly sdist's, emitter exactly
  C0-E1's. Separate commits/temporary indexes were used instead of trusting the
  author's resolution script or saved tree IDs.
- Independently checked actual source execution: 560 distinct collected IDs equal
  journal starts and JUnit identities; exactly one successful setup/call/teardown
  per node (1,680 phases), one successful finish, process exit 0, no failure/skip.
  The recorded input hash recomputes, and every recorded input byte still equals
  the tested candidate. Real Python 3.12.14 / built-in SQLite 3.53.1 safety probe
  passed with null loader overrides. This reviewer did not rerun product tests.
- Inspected both actual built wheels independently of the author's checker. All
  158 current product files (135 Python, 19 SQL, 2 JSON, 2 GraphQL) equal current
  source bytes. Both wheels have a unique, complete RECORD with every hash and
  size verified; all member maps agree, SHA-256
  `b92078f0153c187dd5d06773b75d98e134970694a79a58534b59c4f8503da878`.
  The actual 690,942-byte combined sdist has 162 regular members and all current
  158 product files; no fixed historical 155-file target was imposed.
- Installed I4/I5 evidence independently reconciles each artifact's 217 I4 and
  29 I5 cases, exact JUnit/journal nodes/phases and exits, and actual installed
  origins during collection and execution. The standard driver remains **exit 1**:
  both original Access smokes stop at `ExchangeService.export_package`, line 397,
  `AdmissionRefused(PERMISSION_DENIED)`. Actual logs match frozen I6-A history
  after replacing only observed harness and venv path prefixes. Downstream
  assertions, including normal Transfer, are unexecuted. Older #133/sdist's
  Transfer-first refusal is a different historical baseline.
- Independently reconciled each installed artifact's additional I6-focused
  290 unique selected/JUnit/journal cases, 870 passing phases, successful
  collection/test/runtime exits, four installed-origin checkpoints and all
  158 product file hashes including GraphQL. Actual installed safety probes
  passed using the same measured Python/SQLite. These cases overlap the source
  cohort and are not additional distinct ordinary-suite coverage.
- The new skill lesson also merges cleanly with the combined candidate's two
  existing appended lessons: independent `git merge-file -p` preflight exits 0
  and preserves all three lessons. This is text preflight, not new product work.
- The CI report correctly distinguishes missing Access routing/cohort coverage
  from the intentional Development policy. Unfiltered tests workflow and Release
  selection prevent a demonstrated violation of the stated planner contract;
  no bounded CI-fix PR is justified from non-start alone. The custom routing
  harness is not pytest and imports PyYAML, so its initial description as
  “stdlib” was a minor wording correction communicated to the Author.
- The dependency report's conditional I8-A assessment agrees with the frozen
  reviewed I6 design: basic generic reads may follow frozen non-Author-reviewed
  I6-B; Transfer Query/Search acceptance waits reviewed C/I7 and integrated tests.
  #119 and #137 are correctly treated as historical scoped review/prerequisite
  evidence, not present independent acceptance.

## Findings, limitations and evidence

**No unresolved material finding.** The final prose accurately separates
executed passes, retained failures, unexecuted scope, simulation-only trees,
review HEAD bindings and future obligations. The DAG wording now explicitly
distinguishes API-reported base snapshots from live branch refs: #137 retains
API/merge-base `217cf200...` while current #135 branch ref is `18ba867d...`.
The original PyYAML wording issue is corrected. Initial
independent reconstruction failed because the reviewer helper stripped source
newlines and then appended one spurious blank line. The failed helper/log/exit
are preserved as `verify_independent.initial.py.txt`, `verification.initial.log`
and `verification.initial.exit.txt`. Corrected raw-byte handling reproduces the
exact tree; this was a review-harness failure, not a product or Author finding.

Commands and source bindings are in `commands.json` and `verification.json`;
actual wheel/RECORD inspection is `artifact-verification.json`; installed
I4/I5/refusal checks are `installed-verification.json`, installed I6 evidence is
`i6-installed-verification.json`, and full topology is `graph-verification.json`
with `graph-commands.json` / `main-topology.json`. Final assembled prose hashes,
source inventory and backend-only probe validation are in
`final-claims-verification.json`. The additional shared P1 package cases pass
exactly, giving 562 unique source cases of 6,229 ordinary cases; the actual
6,231-case full collection includes one live and one benchmark. The remaining
5,667 ordinary source cases are unexecuted. The backend-only probe has only
five locked backend packages, no product installation/Git on PATH, no original
checkout reads through its audited Python path hooks, and the same actual rebuilt
wheel digest. Its scoped hooks are not an OS sandbox assurance. Each helper has an output
log and numerical exit file. These are evidence-audit executions, not new pytest
or release runs; reviewer JUnit/pytest journals are inapplicable. The Author's
underlying JUnit/journals and process receipts were actually inspected.

Current safety fences and failure propagation remain intact because candidate
product `src` exactly equals the frozen I6-A source. Full ordinary regression,
normal Transfer, I6-B/C/I7/I8 implementation, full independent local and hosted
Release acceptance, merge/release/deploy remain outside this review's proven
scope. No denied/pending/uncertain external mutation occurred in this subtask.

The Author will bind the final public PR HEAD/tree and selected hosted CI
separately. Indexed raw archive integrity is checked separately after the
complete payload is frozen; that later check does not turn this audit into
product or Release acceptance. No new skill was created by this read-only
reviewer; the Author's existing-skill addition was independently preflighted.
