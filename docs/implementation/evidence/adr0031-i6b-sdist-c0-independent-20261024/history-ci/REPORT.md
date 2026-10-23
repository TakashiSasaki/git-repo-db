# Independent history and hosted-evidence review

Reviewed published PR155 `fee364c6d61a5feebf08dbdd830a5a57ee2d872b`, tree
`ace7e44cd89194d189a30a0aa6cf513a45b3b87c`. This work reads the fresh review
clone and GitHub's published objects only. It accesses no Task A workspace or
unpublished I6-C work and changes no product, assertion, workflow or ADR.

## Result

History/provenance checks PASS. Hosted evidence verification is PARTIAL with
the precise Access log-retrieval limitation below. No Critical/High/Medium
product finding was established in this scope. One Low, nonblocking evidence
precision observation is recorded separately. These checks confer no merge,
Release, I6-C or fence-retirement authorization and make no scanner finding.

At 2026-10-23 21:05:25 UTC, live REST metadata showed 40 open PRs, zero formal
PR155 reviews, no PR directly based on its integration branch, and unchanged
main `cb532242c7aa86c6af5b6232b71c0906ea38f5c5`. Relevant PR144/147/149/150/
152/153/154/155 heads and bases are retained under `raw/`. PR144 and PR147 are
ancestral integration inputs; their GitHub PRs remain open Drafts, so ancestry
must not be described as GitHub main-merge acceptance.

## Git-object verification

`audit_history.py` reconstructs the following independently from Git objects:

- Actual first merge `9c3de77475d042bb5e8c465a64e5f4b47d2eda23` has ordered
  parents exact154 `91827360c185cbf813277bf32a6627d894b1b20a` and exact147
  `e7762952e18061de8c8235beaeddf42f20ad9f5a`. Fresh `merge-tree` reproduces its
  `ab1222093f4fe74ddd55032f28a4ef91dddddb15` tree without conflict.
- Actual second merge `9f005eb2dbd97a5c160872740794143a2bd560f7` has ordered
  parents that first merge and exact144 `ededcd83eb2d99a602ba18c8fe3c177125c825ac`.
  Fresh `merge-tree` reports exactly the two text conflicts in the CI skill and
  P1 distribution imports. Removing conflict-marker lines and concatenating
  both sides reproduces each resolved merge blob byte for byte. The final
  subsequent style commit sorts the import union without dropping either side.
- The six shared paths are independently recomputed. The other four paths
  (Access workflow and three distribution drivers) equal their automatic merge
  blobs. Full blobs, lengths and complete-byte SHA256 are retained.
- Pairwise154/144/147 merge-bases all equal frozen133
  `f16e5b1713bde9a2f18263a25397c4b450fd5773`. PR150
  `4fc00b1fbc57f10f6c0c6352dee702e1738f65b7` is not an ancestor of target.
- All160 `src` blobs equal154. The hardened sdist checker/planner authority
  equals144; C0 emitter/regression authority equals147. Both Transfer SQL
  fences are retained exactly, with their text and SHA256 in the result.
- All31 numbered preexisting ADR blobs equal154; ADR0033 equals144. Every
  preexisting file under `docs/implementation/evidence` is preserved from154
  (7625),144 (2797),147 (2711), including historical FAIL records.
- All493 executable/build/distribution inputs equal tested source
  `fb5d7b5a0c4b92c8a282daac154e66fa6d361e64`; no input addition/removal is
  hidden by the evidence-only publication commits. This is a specified input
  inventory, separate from CI's broader input-hash contract.
- The actual fetched GitHub test merge `90e222635a01e89f095e9a256ac69ecfc759ec4e`
  has ordered parents154/155 and exactly target's tree. A clean textual merge
  alone is not semantic acceptance.
- The target's Author660-payload index has SHA256
  `e2356b7d82f561dd9e3dc5745e30cb1b5df5568e9ce9f190d2d2f09aa8566449`;
  all660 complete-byte member lengths and hashes verify against published Git.

## Hosted results and limits

Live API/job metadata and saved decoded job logs confirm final source runs:

| Run | Terminal result | Independently observed scope |
| --- | --- | --- |
| Development40006927076 | success | Manifest `development_checks_passed`, `full_acceptance=false`;0 product pytest executions,232 required test files unexecuted. Lightweight sdist gate skipped as not applicable on evidence/prose synchronization. |
| Access40006927148 | failure | Main console279FAIL/2487PASS/20ERROR. Logged broad driver reports3148 executed=2849PASS/279FAIL/20ERROR, exit1, zero skip/xfail/xpass. These overlapping lanes are not summed. |
| Pages40006927071 | success | Console8 docs tests PASS; actual deploy job skipped. |

The Development receipt is fully independently verified:86002 bytes, SHA256
`9449cf850e69b9922fc8604f308d63f370e9b8df599e60ded74f823ae90a895c`, closed
ZIP/CRC, all21 indexed payload sizes/hashes, binding to run/attempt1/actual merge/
target tree. Its measured hosted Python3.12.15 loads SQLite3.53.1. Separate
sqlite-policy job metadata is retained; product pytest0 does not erase its
infrastructure checks or turn them into product acceptance.

The Access receipt is **not fully independently verified in this review**.
The current supported connector job-log view and REST run-log ZIP both yield
1993868 decoded bytes,90 fewer than the BEGIN declaration1993958. Observed
SHA256 is `29a5e29e8a91d4f52ce8b9283e52da40596b1bf4121af5ee2d2eb149c8653411`,
which differs from declared
`60b73fee0f3fed6d0c220d94a5fb62b450ad18bbb2ff58c662bb3f9bee3b090a`.
The independent decoder refuses this stream and exits1; raw inputs and failure
are preserved. `gh run view --log` returned exit0 with an empty file. No missing
byte was guessed, inferred from hashes or substituted from another run.
Author comments6372792292/6372799048/6372802446 report an earlier complete123-
payload verification; those assertions and indices are retained and attributed,
not adopted as this review's execution. Current exact hosted JUnit/journal/
assertion reconciliation is therefore incomplete here. Root review's source
regression analysis is a separate task.

Access console independently shows both external installed forms importing from
separate `site-packages`, each refusing the original minimal Access smoke with
`AdmissionRefused: PERMISSION_DENIED`, and logs wheelSHA256
`2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8` and
sdistSHA256 `9d228f889f9507cdc5a166b9658e80873fcbd48255c6c958eb90e33954014b54`.
Full distribution behavior remains the separate independent distribution study.

Artifact metadata/log confirms upload12524818073,856700515 bytes, reported
digest `sha256:ca97a1db8fff294fad2d5d4be893e3f4338a9737381a17a9010ac1efc9a33872`.
This is an API/log observation, not a downloaded-byte hash. No binary artifact
download was attempted after the inherited Azure Forbidden/zero-byte limitation;
there is no new denial or successful download claim. Actual hosted overflow was
not exercised. Local real-ZIP boundary checks are a separate scope.

## Routing assessment

ADR0001/0033 and the current `docs/change-aware-ci.md` distinguish inexpensive
Development checks from explicit full Release qualification. The observed
Development synchronization changes evidence/prose inputs; skipping the sdist
preparation and product pytest is consistent with that lightweight contract.
`ci_plan.py` explicitly selects sdist preparation for product/build/README and
distribution verification changes. Access's direct trigger list lacks several
new I6-specific paths and its fixed cohorts do not provide complete I6 coverage;
this remains a coverage limitation, not evidence that ordinary Development must
duplicate full hosted runtime testing. No Release dispatch or extra expensive
hosted run was started by this subreview. Upload follows emitter with `always()`
in Access; Development also keeps upload under `always()`.

## Nonblocking observation and next checkpoint

HCI-L01: Author `audit/provenance.py.txt` hashes `git show` output after `.strip()`.
All24 recorded shared-path/version SHA256 values hash whitespace-stripped bytes,
while all Git blob OIDs are correct. This review records actual complete-byte
hashes. There is no product mismatch or ancestry change. Retain the historical
record and use complete bytes in future provenance emitters; no product repair
belongs in this review PR.

Next checkpoint: maintain exact155 binding, obtain a complete already-existing
Access receipt through normal authorized access when available, then verify
all123 indexed members and exact current hosted node sets. Do not infer those
bytes from the Author's report. The incomplete current receipt and historical
artifact access limit are evidence limitations; neither proves a product safety
defect nor authorizes release. Independent I6/scanner and distribution verdicts
must be considered separately.

Reproduce from this clone with `python <this-directory>/audit_history.py`,
`python <this-directory>/fetch_live_metadata.py`, and
`python <this-directory>/verify_receipts.py`. The last command intentionally
returns1 for the saved incomplete Access log. Git-object checks are fixed to the
published source; live metadata is timestamped and may change.
