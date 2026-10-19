# R3 independent post-fix review, first candidate f81a399

Reviewer R3 did not write the reviewed production changes or their regression
tests. This report preserves review of the first corrected candidate separately
from any later correction. Start: 2026-10-18 12:51:22 JST.

Commit `f81a3992ac85542e015cb8f37a5ae9fc31f265b5`, tree
`666dfaaa38dbe1f8163d5d196253b0715d98a78e`; clean read-only worktree
`/workspace/access-review-post`. Python 3.13.5 loaded this worktree's package and
actual SQLite 3.51.3 with source ID
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
Source and tests were not modified. All scripts, logs and synthetic data are under
`/workspace/access-review-evidence/r3/post`.

## Material findings in the first corrected tree

| Finding | Severity | Exact first-candidate source | Independent reproduction | Required correction |
| --- | --- | --- | --- | --- |
| R3-P01 | Medium | `src/repo_catalog/application/acquisition.py:864` and `:1762` | Real `GitMetadataInput` + supplied `GitNotesSource` + durable Operational request fails `REQUEST_SCOPE`, both standalone and prepared paired, with SHA-1 and SHA-256. | Build the same target/actual-instance/source-attribution/source-scope custom request scope used by `NotesProgress.bind`; keep physical seed/instance pairing separate. |
| R3-P02 | High request-source fence | `src/repo_catalog/application/acquisition.py:860`, `:884`; `src/repo_catalog/domain/native_acquisition.py:319` | With explicit shared cumulative work/progress, identical request first uses actual Notes source A then different source B. Both calls succeed; B returns the original A discovery from saved progress. The frozen semantic value has no actual Notes source scope. | Freeze supplied live Notes source scope and format in the saved intent, including the explicit-work/progress path; reject before source I/O or Core admission. |
| R3-P03, extension of R3-02 | High selected-target fence | `src/repo_catalog/application/acquisition.py:167` and `:879`; actual delayed refusal in `_run_notes_spec` | Existing Capture pair belongs to R2; supplied incoming Capture has the same pair but falsely selected owner R1. Without Capture Coverage, all explicit/claim/group paths reach late `INCOMPATIBLE_REPLAY`; standalone has already inserted selected R1 registry and claim rows. Paired rolls back but reports `ADMISSION_FAILED`. Original Capture correctly remains unchanged. | Resolve actual existing owner for every incoming Notes Capture pair before any admission, even if no Capture Coverage is supplied. Do not rely on later immutable replay checks as the selected-target preflight. |

The high labels describe original request/target scope violations, not demonstrated
remote exploitation, UUID rewriting or failed Core immutability. Core correctly
refuses capture rebinding. These findings do not authorize relabeling an external
Capture's source to equal the outer intake source.

Executable evidence: `probe_notes_post.py`, run without `--expect-fixed` against
this candidate, writes `f81a-notes/results.json`. Its 12 observed groups include
four live-Notes refusals, the accepted A-to-B switch, six existing-foreign-owner
refusals/aftermath comparisons, and the positive exact external-source-preservation
control. Early minimal observations are separately retained as
`notes-source-check.json`, `notes-source-switch.json`,
`foreign-existing-capture.json`.

## Confirmed first-round corrections and independent 58-group matrix

`probe_metadata_post.py` imports no repository test fixtures. The successful
`f81a-metadata-v2/results.json` contains runtime/commit/tree/module binding and 58
API+SQL check groups:

- Four nonseed target controls across standalone/prepared paired and SHA-1/SHA-256:
  selected R1 succeeds, actual physical seed/instance remains R0, original
  observations remain exact, replay leaves all authoritative rows unchanged and
  actual metadata expenditure grows from 5 to 10 units.
- Sixteen registered-foreign nested-value refusals: claims, observations, explicit
  Notes captures, external Notes claims/groups, repository Coverage scope/claim/
  proof. All eight shapes in both APIs reject with `REPOSITORY_SCOPE` before any
  authoritative row changes.
- Twenty-four Capture Coverage controls: scope/claim/proof containing selected,
  foreign, absent or new incoming selected captures, in both APIs. Positive cases
  preserve the entire actual Capture key; negative cases reject with no writes.
- Two positive global OID/field Coverage cases, preserving their independent
  meaning without fabricating Repository membership.
- One real foreign Operational identity refusal, preserving all Core rows.
- Six changed-source-attribution/time/objects retry refusals and two explicit new
  requests adding compatible facts under the exact original Capture UUID pair.
- Native retained-body repetition charges actual input (152 to 304 bytes) and
  verification (608 to 1,216 bytes); neither raw text, hex nor unique body canary
  enters Operational continuation JSON.
- Same-seed onward Exchange retains exact RepositoryClaim and GitObservation
  rows. Cross-seed Exchange still rejects `REPOSITORY_MISMATCH` without changing
  any authoritative row. The production Exchange files are unchanged.

The first attempt of this new matrix compared `sqlite3.Row` with a tuple and
stopped at its positive Capture assertion. That fixture failure is preserved in
`f81a-metadata.stdout`/`.stderr`. The corrected matrix normalizes actual rows to
tuples, preserving all production guards; it passed at 12:54:35 JST. No earlier
failed matrix is represented as a successful run.

These checks confirm R3-01 and the direct R3-02 counterexample are corrected at
this tree. P01–P03 prevent calling all general metadata/Notes source boundaries
complete. The root correction owner was informed immediately and is preparing
another tree; first-candidate results must not be carried forward as final PASS.

## Semantic review of the 46 new regression cases

R3 read every assertion in `tests/integration/access/test_review_corrections.py`
but did not execute that pytest cohort while root's controlled suite was active.
Its parametrization counts are 8 indirect-config, 1 safe-BOM, 2 command-boundary,
2 callback-boundary, 4 nonseed, 16 foreign nested, 6 Capture-owner, 1 pairing,
1 no-body intent, 1 explicit new request and 4 changed-intent cases: 46 total.

The tests assert concrete no-command/no-callback behavior, descriptor cleanup,
typed refusal codes and all-table authoritative equality, rather than only test
names. The nonseed cases preserve actual seed/instance and original observations;
their Exchange controls preserve the existing seed fence. The body-progress test
checks decoded body exclusion and increasing input work; the new independent
matrix additionally checks hex/canary exclusion and real durable progress. The
existing Capture-owner parametrization only puts the pair in `coverage_scopes`;
R3 expanded it to claim/proof and exposed the separate incoming-Capture path.
The input-intent tests freeze attribution/time/selection but do not exercise a
real supplied Notes source, which is why P01/P02 survive the 46-case cohort.

Original externally reported Notes sources/provenance are independent of outer
intake attribution and must remain exact. The positive external-source control
confirms the candidate preserves that distinction. A fresh explicit request may
add compatible facts under the same actual Capture pair; an old request may not
silently retarget actual source A to B.

## Remaining gates and unexecuted work

No R3 heavy pytest, installed-distribution or hosted run was performed in this
post-fix pass. Root's first-candidate full workflow was interrupted before edits
and is a separate superseded checkpoint, not final exact-tree acceptance. The
Exchange selection contract remains the baseline R3-03 gap; its guard is retained.
No real data, secrets, backups, activation, main/parent push, merge, release, tag
or deployment was performed. Whole-ADR acceptance and merge remain human gates.

Reusable skill refinement after correction: when adding a durable request wrapper
around an existing subservice, reproduce its real `progress.bind` scope through
all standalone/prepared paths, and also test a caller-supplied cumulative progress
object. Freeze the actual source separately from its claimed attribution. Check
existing immutable Capture owners on every supplied path, not only when a
Coverage row happens to mention the pair.
