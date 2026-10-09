# Independent current-state boundary review

This review used disposable temporary catalogs, actual packaged production DDL,
synthetic parser profiles, synthetic HTTP responses, and direct SQLite statements.
It did not acquire live repositories or use retained user data. The reviewer
worked independently of the implementation owners and sent reproductions before
the owners fixed the affected code.

Environment: Python 3.12.14, SQLite 3.53.1. The worktree branch was
`refactor/latest-state-transport`, based on
`a3a4cb7482d42709f79d137b802f1789e3aa45cb`. These focused receipts cover the
uncommitted implementation during integration; the final integration receipt
must identify the submitted commit/tree separately.

## Reproduced findings and retained regressions

| Boundary | Before-fix counterexample | Fix and regression |
| --- | --- | --- |
| Canonical provider identity | Direct SQL accepted decimal text followed by NUL and a hidden nondecimal suffix in all three independently exercised kinds. | Byte length must equal SQLite text length. `test_provider_identity_cannot_hide_noncanonical_suffix_in_sql` exercises ordinary Issues, reviews, and review comments. |
| Stable code target identity | Direct SQL accepted 40 hex characters followed by NUL and an invalid suffix in both original and target commit fields. | OID guards validate the full byte length. `test_review_target_oid_rejects_hidden_nul_suffix` exercises both fields. |
| Reply/thread consistency | Updating a reply parent's thread left its existing child assigned to another thread. | Parent updates validate existing children as well as the changed row's own parent. `test_parent_thread_update_cannot_make_existing_reply_inconsistent` retains the reproduction. |
| Completeness member ownership | A repository-wide receipt accepted a review member from another service/binding of the same repository. Repository equality alone did not establish acquisition scope. | Python and standalone SQL member guards compare the member PR binding to the collection's resume scope. `test_repo_wide_receipt_rejects_member_from_another_binding` retains the reproduction. |
| Resume after unresolved admission | A terminal receipt persisted before an unresolved admission error; a subsequent resume reset the in-memory uncertainty flag and could mark the collection complete without another request. | The collector rechecks durable member dependencies/diagnostics before sealing. Collector-owner regression: `test_unresolved_terminal_receipt_does_not_become_complete_on_resume`. |
| Optional recorder bugs | Unexpected exceptions raised specifically by the recorder callback propagated after a valid HTTP response, preventing domain admission. | Exceptions inside that callback produce a generic secret-free `ARCHIVE_FAILURE`; cancellation and failures outside the recorder retain their meaning. `test_unexpected_recorder_failure_is_reported_without_blocking_current_admission` proves one request, visible diagnosis, no secret leakage, and a readable accepted Issue. |
| Explicit parser selection | After a newer current candidate was staged under an unselected parser profile, explicitly selecting its verified/trusted profile hid the old row but did not promote the waiting candidate. | The application parser command promotes current-resource staging in the same transaction as parser decisions. `test_explicit_profile_selection_promotes_waiting_newer_current_state` retains the public-reader reproduction and passes after the fix. |

The initial direct-SQL run reproduced six failures: three provider-key variants,
two OID variants, and the parent-thread update. Nine additional failures at that
moment were temporary missing-fragment integration failures, not independent
product defects. After the fragments and JSON guards were assembled, the review
reproduced the same-repository/different-binding receipt defect as the sole
remaining failure among 35 cases. The implementation owners fixed all seven
direct-SQL reproductions.

## Other exercised boundaries

The independent module additionally checks NULL, wrong-kind and cross-service
Issue parents; wrong Issue number and NULL acquisition service; malformed, NULL,
uppercase, duplicate-member and duplicate-key completeness metadata; and exact
body preservation across sparse nested projections. A receipt remains immutable
after the current body changes.

Application cases verify that an untrusted alternative parser cannot replace a
trusted incumbent or expose a staged body through a parser filter; tied or
missing provider clocks cannot advertise the incumbent as an undisputed winner;
and replay cannot claim live-request authority using a supplied catalog revision.
Every public query assertion uses the ordinary application reader.

The reviewer also raised transferred-Issue selective exchange as a counterexample
candidate. The exchange implementation qualifies receipt completion using member
natural-key dependencies while keeping body digests independent of mutable rows.
Exporting the old repository does not pull the destination repository's row/body;
a fresh old-repository receiver stages the unavailable-member completion claim.
The exchange owner maintains the corresponding transfer regression.

## Focused receipt

Command, with `REPO_CATALOG_TEST_BOOTSTRAP` absent:

```sh
.venv/bin/pytest tests/integration/test_current_state_independent_review.py -q
```

Result after the fixes and seven additional recorder/parent cases: **42 passed in
12.68 seconds**. The tests establish synthetic profiles explicitly and do not
claim to certify the installed built-in parser artifact. The test module also
passes Ruff checks and formatting. The final ordinary suite, exact built-in
certificate regeneration, distribution checks, and hosted submitted-HEAD checks
belong to the integration acceptance receipt.

A subsequently added 43rd case reproduced the explicit-profile-selection gap:
the isolated test failed in 0.88 seconds, with an empty ordinary Issue query after
the profile selection command. This does not retract the earlier 42-case receipt;
after the command fix, the same full command passed **43 tests in 14.77 seconds**,
again without bootstrap. Final submitted-tree acceptance remains a separate
integration check.

## Final proof-profile API review

The final page-receipt model also stores a required immutable
`parser_profile_uuidv4`, including for empty pages. The reviewer identified an
optional-argument inference path as an attribution risk: inferring a parser from
a mutable current row or its selected profile could label an old observed digest
with a replacement parser. Production collectors already supplied the producing
profile explicitly. The implementation removed the inference path entirely and
made the keyword argument mandatory.

A read-only signature assertion verified that `parser_profile_uuidv4` has kind
`inspect.Parameter.KEYWORD_ONLY` and default `inspect.Parameter.empty`, and that
the `_profile` inference method is absent. DDL review verified the non-NULL FK,
capability guards, immutable receipt protections, and profile index. Selective
exchange follows the page's exact profile dependency; replacing the current
resource/profile cannot relabel an existing receipt. The ordinary suite includes
`test_receipt_keeps_exact_parser_after_current_profile_replacement`.

The independent module remains **43 cases**. No 44th case or implementation change
was introduced during the final validation freeze. These final read-only checks
found no further concrete defect in the proof-profile change.

## Integration certification status

The integration lead first reported a successful complete development-bootstrap
run: **1,310 passed in 187.69 seconds**. That run included the 43 independent
cases after the mandatory-profile boundary change and is historical integration
input. After the last integration fix and an additional regression, the lead
reported the final frozen-source bootstrap receipt: **1,311 passed in 175.66
seconds**. The lead regenerated the built-in parser certificate against that exact
snapshot of 35 implementation modules, packaged resources, schema 14, and all 13
capabilities. These bootstrap runs are certification input, not final ordinary
acceptance.

The lead reported final acceptance with bootstrap absent: **1,311 ordinary tests
passed in 197.66 seconds**, including the 43 independent cases; **2 isolated
wheel/sdist distribution checks passed in 61.76 seconds** against the final
certificate. Both runs had zero failures, errors, or skips. The ordinary receipt
is `artifacts/latest-state-ordinary.log` and its XML result; the distribution
receipt is under `artifacts/latest-state-packaging`.

The lead also reported fresh production-DDL verification: 103 tables, 48 views,
496 triggers, 108 named indexes, 55 classified JSON fields, empty FK violations,
and `integrity_check=ok`. Ruff checks/formatting covered 203 files; diff and report
validation also passed. These full acceptance results are lead-run integration
receipts, distinct from the independent focused **43 passed in 14.77 seconds**
receipt obtained before the last proof boundary change. The submitted HEAD and
tested tree will be recorded in the final PR after committing; this document does
not infer a submitted commit identity from the earlier uncommitted worktree.
