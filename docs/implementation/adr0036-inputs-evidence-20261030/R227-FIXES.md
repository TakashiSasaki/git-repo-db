# R227-01/02 repair and selective verification

Cloud-only, same Draft PR 227, based on independently reviewed FAIL candidate
`d7dda1e96f431e99893fec45538189b5c8855d51` / tree
`8ff54624b4b87e34dee25f868066d743f6f9c302`. Parent PR 226 remains fixed at
`1e70d1ddfe5c9f4a43f52775bcc39598b8d656cc`; main remains
`2ff4aab59dcdbada264d9a6a978c07b6ac4ad0d2`. No Search/physical-family work,
schema/wire change, merge/deploy or formal APPROVED is included.

## Preserved independent FAIL and corrections

The parent supplied independent results: 77 cases, 51 passed/26 failed, no
error/skip/unexecuted, 231 reconciled phases. R227-01/P2 accounted for ten
Group-only failures (eight object/Core-or-paired cases and two actual paired
resource resolutions); R227-02/P1 accounted for sixteen caller-budget
require/charge JSONDecodeError identity/no-stop failures. The original review's
28 independent successes included controls, proof/permission and page boundaries.
These are the reviewer's historical results, not relabeled author execution.
Original raw evidence remains with the parent/reviewer; their different
`/workspace` paths are not assumed locally accessible. No old 403 artifact was
retried or bypassed.

| Finding | Correction | Regression |
| --- | --- | --- |
| R227-01 | Include bounded interpretation headers from Group-only reports in candidate discovery. Count/byte-check headers before fetching them; do not parse membership in discovery SQL. The existing exact-Claim/root projection reader validates membership before matching the target. No Mapping row, Claim or proof is synthesized. | `test_r227_01_group_only_object_and_wrong_claim_target` (8 cases) and `test_r227_01_group_only_paired_resource` (2). Wrong target/Claim remains unassociated, reported Groups retain no fabricated canonical note or receiver evidence. |
| R227-02 | Wrap caller work in existing `_QueryWorkBoundary` before entering the application snapshot and pass that wrapper through Core/paired classifiers. Restore the identical original exception object only after exiting the outer snapshot. No corruption classifier or stop condition changes. | `test_r227_02_callback_identity_and_healthy_catalog` (16 cases); follow-up ordinary listing succeeds and no stop file exists. |
| Preservation control | Real malformed Group JSON and invalid stored observation/provenance still stop ordinary service and keep the subsequent read in RECOVERY_STOP. | `test_r227_02_real_stored_corruption_still_stops` (16 final cases). |

All nodes are in `tests/integration/p6/test_r227_fixes.py`. No old assertion or
test was removed or weakened. The existing transition contract and investigation
skill record these reusable boundaries.

## Executions and time (no full or repetitive broad suite)

All product runs used verified `scripts/local-run.sh`, Python 3.12.15,
Python-loaded SQLite 3.53.1, x86_64 and two workers.

| Actual run | Result | Wall time | Reason |
| --- | --- | --- | --- |
| `r227-probe`, 42 selected | 34 passed, 8 failed during synthetic observation-corruption preparation | 7.81 s | First execution of the 26 review conditions plus 16 real-corruption controls. Malformed provenance JSON could not be written through the real expression index, so those eight did not reach the product reader. The 34 successful cases were not repeated. |
| Direct quiet/budgeted pytest, observation-corruption subset, 8 selected | 4 passed, 4 failed at earlier paired FK validation | 2.62 s | Only the failed fixture subset was repeated with valid JSON of invalid provenance shape. Core-only cases reached the reader and passed. Paired cases altered a referenced key, so they reached a different gate from the intended Query classifier. |
| `r227-paired-corruption`, 4 selected | 4 passed | 3.09 s | Only those four paired fixtures changed to damage a non-key subject field, preserving PK/FK pairing and reaching the intended reader. |
| `r227-regression`, 11 selected | 11 passed, no failures/skips | 7.61 s | First execution after this repair of existing Query/pagination/CLI boundary modules; no full suite or prior broad cohort repeated. |

Thus the 42 final repair/control node conditions and 11 existing regression
nodes have successful outcomes. This is a union across the explicitly described
runs, not a claim that one clean run executed all 53. There were 65 actual test
executions in total: 53 passes and 12 pre-correction fixture failures. Initial
failures and complete logs remain intact. The direct eight-case fixture rerun
has its complete pytest log; unlike profile runs it has no separate JUnit/journal.

Ruff check, format check and `git diff --check` also passed. Unchanged schema
audits, full release, installed distribution tests, additional architectures,
and already completed original Query/Core independence cohorts were not rerun.
Hosted development checks/skips are reported separately against the final HEAD.

## Source binding and evidence

Clean regression HEAD `6ef25d6d8c7c8994d6698288ffae03a142fbe23b`, tree
`a2d393e783aa05af19933cd3a679fbec5123996f`.
The only production file changed is `application/production_query.py`, blob
`068c42ab02e4ba5906e9667febcca4a12a85e26a`. Its bytes were unchanged from the
first probe through the fixed commit and clean regression; only synthetic
corruption fixture construction changed during the selective retries.

Earlier repair/control receipts honestly retain HEAD `d7dda1e...` and
`dirty=true`; they are working-tree executions, not clean-HEAD receipts.
The session's edit trail and archived product bytes bind that production change
to the later commit. No retrospective clean execution or measured phase
reconciliation is invented for the direct fixture rerun. Later evidence/ownership
commits leave product/tests/scripts unchanged and do not trigger a local product
retest merely to restate success. The parent explicitly requested this efficient
selective execution after the first probe.

[`r227-repair-profile.tar.gz`](r227-repair-profile.tar.gz) retains necessary raw
logs, JUnit/journals/failure indices for profile runs, direct fixture log and
source/binding snapshots. Original uncompressed evidence is under
`artifacts/r227-*` in this environment. The prior evidence archives/reports are
unchanged. Final HEAD/tree and hosted CI URLs are recorded in the Draft PR and
handoff. Independent re-review is pending; author green results do not close the
historical FAIL by themselves. Requested model/effort was Sol/high; receipts do
not independently attest that runtime identity.
