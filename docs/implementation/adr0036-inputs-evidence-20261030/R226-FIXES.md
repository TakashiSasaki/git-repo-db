# PR 226: R226-01 and R226-02 repair checkpoint

This is author development evidence, not an independent APPROVED review.
Work remains in the cloud `git-repo-db` project. Query/Search and later
retirement stages are not advanced.

## Preserved independent FAIL

The parent supplied an independent **FAIL** review for HEAD
`5a6198184836fc5955b577e48a5db851b9df7400`, tree
`d153bbe0db69c195a068a35cafadd1a69f324788`: 303 cases, 283 passed,
20 failed, 909 reconciled phases. These are the reviewer's results, not a new
author execution. Original logs/JUnit/journal/failure index remain with the
reviewer; their remote `/workspace` paths are not assumed available here.

| Finding | Original counterexample and measured failure | Author correction |
| --- | --- | --- |
| R226-01 / P2 | After normal construction, `object.__setattr__(value.mapping_claims[0].mapping, "interpretation_version", 17)` was accepted and SQLite stored text `'17'`. All 16 format/bare/acquisition/admission combinations failed the refusal expectation. | Revalidate the exact typed nested NotesMapping and each of its root/annotated/note OIDs before intent/admission. Reject invalid input without catalog recovery or alteration of prior reports. |
| R226-02 / P2 | After constructing a Group with a 200,000-character member path, an `input_bytes=1` budget still allowed four 200,092-character Group encodings before the failed byte reservation. Four format/bare metadata/Core-only cases failed. | Shape-only bounded preflight, followed by request-owned reservation before variable-length validation, set/hash comparisons, keys, copying, encoding and replay comparisons. Preserve actual costs across failures/retry. |

The original event order was two large encodings, a metadata-unit reservation,
two more large encodings, then the failed input-byte reservation of 200,987.
That FAIL and its IDs are not relabeled as passed. Artifact `12978674006`'s
Azure-delivery HTTP 403 remains unresolved and its bytes unavailable here.
No retry, alternate route or access/permission change was attempted.

## Fixed source and scope

Actual tested implementation HEAD:
`ba5885e3f78ab83c98005e03d1de4c3ca9e1a408`.
Actual tested tree: `20ef8328f42808a40bf2046da06a74e06c4a88fc`.
Main/PR base rechecked as `2ff4aab59dcdbada264d9a6a978c07b6ac4ad0d2`.
The previous turn's uncommitted R226-01 fix and 16-case regression were retained
and extended. Later evidence/ownership commits are distinguished from the clean
execution above. Final candidate HEAD/tree and hosted statuses are reported at
handoff and in the Draft PR.

The new carrier has a shape preflight over exact allowed classes/tuples/scalars,
without calling post-init, hashing, semantic keys or content encoders. Child
visits are reserved before scheduling. Hard bounds are 100,000 nodes, depth 16
and 1,000,000 scalar characters/bytes. A processing stage reserves a conservative
128-times scalar length plus 256-times node count before text work. Successful
stages settle actual scalar UTF-8 input plus encoded carrier output; failed
stages retain uncertain reserved work through the existing abandon API.
These are engineering bounds under ADR 0023–0025. The prior one-megabyte final
intent bound remains. Pure value projections retain finite bounds but create
no request or evidence authority.

Native/metadata application entry points shallowly preflight legacy fields with
the new carrier excluded, then use the real request's work for initial carrier
intent. Actual replay serialization/comparison and later explicit-input
preparation are separately reserved stages because they perform additional
work. The old post-encoding input charge is removed. Carrier-bearing native
intent no longer constructs an unbounded dataclass `repr`. Legacy no-carrier
inputs keep their existing projection/approval behavior.

Paired preparation passes its existing budget/progress without creating another
request. Access requires an existing approved grant before allocating preparation
work; copying and displaying a new carrier precede executor activation review
but consume that same request budget. Actual Git acquisition reuses the same
attempt/work/progress, without a second `create_budget`. A declined activation
cannot refund already performed new-carrier preparation. The settings/plan is
rechecked before actual use. No source is read before the existing activation
grant/review rules permit it. No Source/Coverage/receiver-proof trust change,
Core schema/wire change, live catalog recovery or retained-data migration occurs.

The [transition contract](../adr0036-legacy-consumers-contract.md) records this
boundary. The existing efficient-investigation skill records how to instrument
supplied metadata only after fixture construction and follow all real callers.

## Finding-to-regression map

All nodes below are in `tests/integration/p5/test_ref_notes_inputs.py`, except
the two Access nodes in `tests/integration/access/test_git_acquisition.py`.

| Node | Executed scope |
| --- | --- |
| `test_r226_01_rejects_mutated_mapping` | 32 cases: original numeric-version refusal in all 16 combinations, plus invalid nested OID in the same 16; healthy catalog remains available. |
| `test_r226_02_no_large_encoding_before_request_budget` | 16 cases: both formats, bare modes, native/metadata, Core/paired, instrumented large encoding refusal and same-request retry with increasing metadata work. |
| `test_r226_02_caller_budget_prevents_large_serialization` | 4 cases: original metadata/Core-only counterexample with caller-owned exhausted budget; no large encoding. |
| `test_r226_02_failed_preparation_keeps_work_and_healthy_reports` | 8 cases: original reports admitted, invalid preparation retried with increasing durable input work, existing Mapping preserved, later valid continuation accepted without recovery stop. |
| `test_r226_02_access_preparation_uses_one_cumulative_request` | 2 formats: successful Access intake/replay; exactly one new attempt per invocation, cumulative work, idempotent reported Group. |
| `test_r226_02_access_tiny_budget_stops_before_encoding_or_activation` | 2 formats: exhausted new-carrier work refuses before large encoding/executor activation review, repeat stays in same request, no Core fact or recovery stop. |

The original independent 16+4 failure conditions are covered, with additional
OID, durable-budget, paired/native, failure/retry and Access boundaries. Original
behavior nodes are not removed or weakened.

## Actual local execution

Verified environment: Python **3.12.15**, Python-loaded SQLite **3.53.1**,
**x86_64**. `local_env.py verify --deep` passed. Product validation used
`scripts/local-run.sh`; no runtime guard or SQLite substitution was used.

```sh
scripts/local-run.sh python scripts/ci_profile.py profile \
  --name r226-fixes --output artifacts/r226-fixes --workers 2 -- \
  tests/unit/test_native_acquisition_values.py \
  tests/integration/p5/test_ref_notes_inputs.py \
  tests/integration/p5/test_ref_inventory_wiring.py \
  tests/integration/p5/test_git_acquisition.py \
  tests/integration/access/test_git_acquisition.py
```

**389 passed**, 0 failures/errors/skips/unexecuted; process exit 0; 110.81 s
elapsed, two workers. Collection, starts and JUnit each contain exactly 389
nodes; 1,167 successful setup/call/teardown phases, successful finish and exit
were reconciled by the existing `summarize_pytest.py`. Its `consistent_success`
is true. The ad hoc profile's original `ALL_PASSED_UNVERIFIED_SELECTION` status
is retained; the separate node reconciliation does not alter it. Source binding
comes separately from the profile's clean runtime commit/tree above.

Changed-file Ruff/format, `git diff --check`, and the P1 schema audit also passed.
The audit reported zero unclassified schema items; no schema inputs changed.
Preliminary focused counts are preserved as preliminary executions and are not
added to 389. They were expanded only for new mutations/paths and then followed
by a clean fixed-source regression profile.

Complete author logs, JUnit, journal, source-bound profiles, collection,
reconciliation, per-file SHA-256/length index and preliminary logs are in
[`r226-fixes-local-profile.tar.gz`](r226-fixes-local-profile.tar.gz), 128,913 bytes,
SHA-256 `5796fd97390e8cec9ea58f206b506914507c858e3e455a9d416908f6f22425b1`.
Uncompressed originals remain at `artifacts/r226-fixes` in the author environment.
The prior archive and report remain unchanged.

## Remaining verification

Independent re-review is pending. No full local/release suite, installed
wheel/sdist behavioral validation, another CPU architecture, actual recovery or
Query/Search follow-up was performed. Hosted static/smoke/sdist checks and their
full-suite skips must be reported as such against the final candidate; a green
development CI is not full release acceptance. No merge/deploy or formal
APPROVED review was requested or performed.

The parent requested GPT-6.1 Sol with xhigh effort for this continuation. The
execution receipts do not independently attest a model/effort identifier, so
the request is recorded without claiming a verified runtime identity.
