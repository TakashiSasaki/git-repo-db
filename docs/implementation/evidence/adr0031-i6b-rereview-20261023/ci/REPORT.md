# Independent hosted CI audit of PR #153

Observed 2026-10-23 using live GitHub run/job/PR APIs and raw run/job logs.
No workflow was dispatched and no product or historical evidence was changed.
This is a CI provenance/scope audit, not a release acceptance verdict.

## Pinned identities and existing review search

PR #153 remains Draft, head `61e44291e293f773904a0127606e20c8cb83c95e`,
tree `4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`, base
`review/adr0031-i6b-independent-20261023` at
`8521158f2996f125d2fcaac36ea79ac1296a7cf7`.
The actual GitHub test merge is `99477234735b9f45cbb4d0634bb8372eaf120710`;
its ordered parents are base/head above and its tree equals the feature tree.
Initial latest-100 pull-request inventory ends at #153, with no later same-scope
review PR. PR #153 had zero review submissions, inline review comments and issue
comments at retrieval. Existing #152 is the parent review, not a duplicate
re-review of the corrected source.

## Exact final-HEAD runs

| Run | Conclusion | Verified receipt | Indexed payloads | Scope |
| --- | --- | --- | --- | --- |
| [Development 39975300074](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39975300074) | success | 91,302 bytes; `b9380f4201eed5f20f2b5e05c40e6b5de2e3c194b428e441b3d4ca72a441f15d` | 21 | `development_checks_passed`, `full_acceptance=false`, zero hosted product pytest cases |
| [Access 39975300189](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39975300189) | failure | 1,953,448 bytes; `436c4c647bdf7943e23ef341700c73f412a8d93600bb71cbd1f1ad30d44ce37a` | 121 | separate overlapping lanes retain failures |

The independent offline verifier checks run/event/attempt, feature, actual checkout,
ordered parents, effective tree, all archive members, unique JSON keys, exact
index/member identity and every payload byte length/SHA256. It does not execute
any downloaded payload. Source code is `verify_independent_ci.py`; its actual
invocation exit is in `verify.exit` (0), with full output in `verify.log` and
machine-readable output in `independent-verification.json`.

Direct `gh api .../actions/jobs/JOB/logs` retrieval for the two jobs failed on
the redirected storage endpoint (Forbidden); zero-byte outputs are retained.
The authorized GitHub job-log connector succeeded for those same jobs. The
Development run-log ZIP request returned HTTP 503 and a 91-byte error payload;
that failed payload is retained and was not parsed as a log. The Access run-log
ZIP request succeeded. These are retrieval failures, not product failures or
automatic approval denials. No denied destination was retried.

The Access job/full-log view and its step-log view each omit one distinct
120-character base64 chunk (90 decoded bytes). Individual views therefore fail
the declared byte length/hash; neither is a valid complete receipt alone.
The independent verifier aligns the actually observed payload sequences,
requires every overlap to be equal (rejects replacement), and retains only the
two complementary observed chunks. It recovers 21,705 chunks, exactly the
declared bytes and SHA256. Original views and the two chunk-origin ranges/hashes
are retained. No missing byte is guessed, synthesized or obtained from Author
output. This independently confirms the Author's 21/121 indexed receipt claim.

The initial tool-text file transfer appended one extra terminal newline to each
connector log. Actual original character counts and tails were checked; exactly
that additional byte was removed. Initial files remain in `*-added-newline-v1.log.gz`,
with before/after lengths and hashes in `raw-log-transfer-correction.json`.
Receipt payload bytes and their verified hashes were unaffected. The current
`*-connector-job.log` files preserve the connector text losslessly.

## Hosted test and distribution scope

Main Access JUnit is 2,487 PASS / 279 FAIL / 20 ERROR; separate I5 regression
JUnit is 2,849 PASS / 279 FAIL / 20 ERROR. They overlap and must not be summed.
Every retained hosted Access JUnit has zero cases from both new correction
modules `test_context_scan_budget` and `test_exchange_received_digest`; the
56 new M01/M02 regressions were not hosted by these runs.

The actual hosted runtime is Python 3.12.15 / loaded SQLite 3.53.1, with source ID,
compile options and runtime bindings retained. The cloud review environment's
Python 3.12.14 is a separate environment. No alternative SQLite was acquired,
built or swapped for this audit.

The receipt binds the installed distribution build to actual merge tree
`4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`. Clean archive, direct wheel/sdist
build, derived wheel build and both installations report exit 0. Each wheel is
791,300 bytes with SHA256
`2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`.
The publication-tree sdist is 167,509,792 bytes, SHA256
`352bf204122e726e5702b3bbbf4661ad118dd9cb01007a30ab452ac9d227a9e9`;
it is distinct from the Author's earlier executable-freeze sdist.
Each installed artifact has I4 217 PASS and I5 29 PASS; I2/I3 scripts exit 0.
Runtime/import receipts resolve to each artifact's own site-packages. The hosted
module inventory contains 158 `.py` files; it is not the complete 160-file
product/member/metadata/RECORD audit requested for independent local artifacts.

Both original Access smoke subprocesses exit 1 at generated smoke line 187:
unconnected `ExchangeService(producer).export_package(...)` refuses
`PERMISSION_DENIED`. Original later assertions are unexecuted. The exact static
list of 28 downstream assertion statement lines is in
`original-access-smoke-unexecuted.json`; this does not claim tracing of the
earlier assertions. This refusal is preserved rather than bypassed with grants.
Runtime, distribution, historical comparison and ledger steps retain actual
failure conclusions. No Release workflow run or release acceptance is claimed.

## Evidence use

`development-verified/receipt.zip` and `access-verified/receipt.zip` contain all
verified indexed payload bytes. Expanded views are retained externally for
inspection and can be regenerated by the verifier from the saved raw logs.
Packaging these ZIPs plus the verifier, raw views, metadata and summary preserves
all payload evidence without duplicating 57 MB of expanded Access files in Git.
This audit changes no Accepted ADR, safety guard, product code, existing test,
Provider/Transfer fence, existing PR branch, repository setting, merge or release.

## Sibling branches remain separate

Fresh read-only GitHub PR/compare snapshots confirm all three are open/unmerged:

| PR | Latest head | Compare sibling head to #153 | Common merge-base |
| --- | --- | --- | --- |
| #144 archive re-review | `ededcd83eb2d99a602ba18c8fe3c177125c825ac` | diverged; 24 target-only / 8 sibling-only commits | `f16e5b1713bde9a2f18263a25397c4b450fd5773` |
| #147 C0-E1 re-review | `e7762952e18061de8c8235beaeddf42f20ad9f5a` | diverged; 24 target-only / 4 sibling-only commits | same |
| #150 parallel-stack audit | `4fc00b1fbc57f10f6c0c6352dee702e1738f65b7` | diverged; 24 target-only / 1 sibling-only commit | same |

None of those three exact heads is an ancestor of #153. The immutable compare
metadata establishes the DAG relationship; its changed-file list is capped at
300 and is not represented as an exhaustive file-level integration audit.
PR #150's current description explicitly calls its tree a documentary audit and
simulated combined candidate, states no product integration branch is published,
and makes future integration/re-freeze recommendations. Its bounded combined
measurements do not establish that #153 contains the archive/C0-E1 siblings.
The target's current `.gitignore` still excludes `artifacts/`, and its
`pyproject.toml` has no new minimal-sdist target configuration. The independent
distribution audit owns the exhaustive omission/product-input checks; this DAG
audit does not substitute the #144 measurements for #153 distribution results.

## Fresh independent source versus hosted unsuccessful nodes

The separately completed source ordinary invocation is
6,045 PASS / 279 FAIL / 20 ERROR, 57 passing subtests, exit 1, 509.20 seconds.
Its JUnit SHA256 is
`239b10af1752343b4ef4a73a46bc690b119defb7d56ec3f127857fd280424f83`.
`compare_source_hosted.py` independently compares that JUnit and all actual
worker exception sidecars against each of main Access and I5-broad JUnit:

- Both hosted lanes have exactly the same 299 unsuccessful node identities,
  with zero new/missing nodes and all 299 phases/outcomes/primary-message-first
  lines matching. All source typed refusal codes remain present in their hosted
  messages and all message refusal token sets match (299/299).
- Full JUnit message attributes match 280/299; complete raw traceback bodies
  match 0/299. The rendered project-frame projection matches 135/299. Complete
  paired raw text and actual source ExceptionInfo frames are retained in
  `source-hosted-entries.json.gz`; no complete traceback equality is claimed.
- The hosted workflow did not emit actual ExceptionInfo or assertion-entry
  sidecars. Therefore this comparison establishes neither actual hosted frame
  function equality nor hosted assertion reach. Source-to-parent actual-frame
  and assertion reach reconciliation is a separate independent source audit.

The initial v1 observer comparison used an overstrong equality between a single
exception `.code` and every refusal token in its message. It reported 264/299
for that metric because SQL exceptions can carry a refusal string without a
`.code`, nested AdmissionFailure carries both codes, and AssertionError text
can quote a refusal. V1 output/script remain explicitly preserved. The corrected
metrics compare source/hosted message token sets separately and require each
actual source `.code` to remain present, without deleting a test/assertion or
reclassifying a failure. Other comparisons did not change. The corrected
comparison process exits 0 (`source-hosted-comparison.exit`).
