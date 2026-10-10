# Reviewer D — Independent Coverage and Exchange Review

## Conclusion

I independently reviewed the corrected PR #20 Exchange root-preflight, selective-export, delayed-dependency, and collection/Coverage behavior in read-only mode. I made no repository code edits, commits, pushes, or merges. I found no reproduced correctness defect in Coverage v2 or in the reviewed Exchange paths. The review does not authorize deferred completeness or retention redesign.

The review was independent in analysis and execution, but used the shared `/workspace/impl-pr20` filesystem. The lead integrator later changed collector source while my consolidated focused test command was running; that run therefore crossed implementation snapshots and is not a coherent acceptance result.

## Reviewed identities and environment

- PR #20 reference source HEAD: `f9bff8b2dc17ddffd6b3f7662791022f25175c44`.
- PR #20 reference feature tree: `319738f3586240c80d5fa4d6d5fab3099352a7ff`.
- Documentation-integrated commit/tree observed during the consolidated run: commit `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9`, tree `bf6f5e1b037cf18b798086b9ef56abd68e211380`.
- The consolidated run overlapped a later collector edit, so the commit/tree above must not be represented as the sole effective tree for all test cases in that run. The lead confirmed those collector edits did not alter Coverage or Exchange source.
- Previously generated parser-definition snapshot SHA-256: `33c3d6918747ce9e1513220c3a10ec8ae04f61f1cb3024bd58ec3bfb15318be8`.
- Previously generated bundled parser-verification resource SHA-256: `6e34b19a378e8c5fea2eb6dd764c45abb7dde6c0b96b7d2f4906aa76a8d1a029`.
- Earlier bootstrap JUnit artifact SHA-256: `172422d8c1a1987e580bbac189ff9a8ce777db2014538eaaaba33e16258a1b66`. The lead reports that this certificate snapshot was generated from 1,715 successful cases. New collector edits made it stale; a fresh 1,718-case bootstrap was pending when this report was written.
- Environment observed: Python 3.12.14, SQLite 3.53.1, uv 0.12.19, Linux x86_64.

## Test evidence and separation of earlier failures

On the corrected implementation before the latest collector edits, the focused no-bootstrap evidence was:

- Exchange and retirement Exchange files: 53 passed.
- Coverage v2, ownership, and coverage-query files: 196 passed.
- Phase 1 retirement/collector tests: 37 passed.
- Selective Exchange: 11 passed, 2 certificate-blocked.
- Exchange integrity audit: 10 passed.
- Two additional certificate-sensitive cases (nonterminal current-page coverage and cached-head/304 race): each failed before reaching its intended assertion because the bundled parser verification was stale.

That first focused set comprised 311 unique test instances: 307 passed and 4 failed at parser verification (`BUILTIN_VERIFICATION_STALE` / `PARSER_SELECTION_UNRESOLVED`). After the parser certificate was regenerated, the four previously blocked instances were rerun separately without bootstrap and passed: nonterminal page 1/1, 304 race 1/1, and production complete-proof cases 2/2. Those reruns raised the cumulative evidence for that pre-latest-collector snapshot to 311/311 passing instances. A further focused selective subset reported 7 passed; it overlaps the 311 and is not an additional unique count.

A later consolidated no-bootstrap run returned 298 passed and 13 failed out of 311. It started while collector source was being changed, invalidating the certificate during that run. The failures were six GraphQL-child retry parameters, three retry-clock parameters, two production complete-proof parameters, the nonterminal-page test, and the cached-head/304 race test. Each reported stale verification or its resulting parser-selection failure. Because the source changed mid-run, these are neither evidence of a stable semantic defect nor an accepted green run. The lead is responsible for the final frozen-tree bootstrap and clean no-bootstrap acceptance run.

Separate executable checks performed by this reviewer included two inline disposable-catalog probes: empty-complete collection round-trip passed, and selective-single-fetch versus full-collection completeness passed. The delayed/reopen tests `test_missing_dependencies_survive_reopen_and_promote_without_new_ids` and `test_delayed_required_bytes_satisfy_retained_domain_staging` passed (2/2); they overlap the 53-test total above.

## Boundary cases A–I

| Case | Evidence and outcome |
|---|---|
| A. Missing terminal page | `test_truncated_unit_cannot_publish_complete_coverage` passed: an incomplete transfer did not admit a complete claim. `test_nonterminal_current_page_cannot_inherit_complete_family_coverage` passed in the isolated post-certificate rerun; its later mixed-tree run was certificate-blocked. |
| B. Empty complete collection | Inline disposable-catalog regression: a successful `[]` response had one fetch occurrence, zero domain members, an exact terminal marker, and a complete claim. Collection-selective export/import produced `current_coverage = complete@100`, with no staging. |
| C. Newer partial observation | `test_observed_rest_rejection_preserves_latest_coverage_candidate_set[200]` passed: a newer partial assessment remains current over an earlier complete claim. Coverage latest-time tests also passed. |
| D. Same-time contradictory claims | Coverage v2 truth-table tests passed; same-maximum-time complete/partial derives `conflict`. The sync retry at clock 200 also preserved conflict instead of picking a winner. |
| E. Old successful retry after newer partial | `test_sync_retry_cannot_use_rejected_clock_for_complete_summary_or_code[150]` passed: the newer partial assessment was not replaced by older successful evidence. |
| F. Partial GraphQL parent/child | GraphQL root/child rejection and safe-cursor retry tests passed in the 37-test Phase 1 retirement run. Partial or malformed child evidence did not yield a false complete assessment. |
| G. Selective Exchange | `test_collection_and_explicit_fetch_subset_exact_proof` passed. Inline probe: a single selected fetch omitted the collection marker and complete claim; selecting the whole collection included both, and the receiver derived `complete@100`. |
| H. Conditional 304 reuse | `test_selective_304_closes_original_without_sibling_fetch`, `test_empty_304_collection_selects_boundary_and_exact_original`, `test_304_self_authored_evidence_uses_received_original_observation`, and `test_304_marker_cannot_complete_before_its_original_payload_and_observation` passed. `test_304_never_attaches_cached_head_to_newer_race_observation` passed in the isolated post-certificate no-bootstrap rerun. These checks retain the exact cached representation digest and original observation identity; an A-to-B race does not attach cached A to newer B. |
| I. Scope mismatch | `test_304_marker_rejects_an_original_observation_from_another_repository` passed. A forged `requires` owner was rejected as `invalid:completeness_manifest`; the claim did not become current. Scope/source/parent and collection proof checks remain enforced by the existing proof validator. |

## Coverage v2 contract

The five-column `coverage_claims` shape remains `coverage_claim_id`, `coverage_scope_id`, `coverage_state`, `observed_at_us`, and `details_json`. No schema or derivation change was made in this review. Current Coverage derives the candidate set only at the maximum observation time for the scope; older claims cannot supply a fallback, and contradictory candidate states at that maximum time derive conflict. The direct coverage suite’s latest-time, conflict, empty-scope, ownership, duplicate, and query cases passed (196 passed across the selected files).

## Delayed Exchange dependencies and retained Phase 2 boundaries

The reopen/promotion tests preserve legitimate missing-dependency staging for domain records. A valid domain unit whose required API bytes arrive later converged with no staged records. Reverse/repeated imports and reopen/full convergence also passed in the selective Exchange tests.

A deliberate split-transfer probe removed the fetch occurrence from a unit containing an otherwise valid complete marker. The marker and domain facts staged, unverified original bytes were rejected, and the receiver did not report complete. Sending only the omitted fetch later did not complete the graph; replaying the full valid unit promoted it with no staging. This is a resend requirement for partial-unit delivery, not a false-completeness defect: retaining the bytes before their root is verifiable would restore an archive staging path.

The retirement remains scoped to standalone saved-API-original capabilities. Historical PR publication/observation, Source inventory, collection proof, 304 validation, restart, and Git object identity/content paths remain shared Phase 2 dependencies where their contracts still require them. This review does not claim that every API body has been removed from the core or that those deferred contracts have been redesigned.

## Findings

- Critical/high findings: none reproduced in the Coverage/Exchange scope.
- Medium/low findings: none that warrant a code change within this review. Partial-unit delivery may require full-unit resend when the missing root evidence is what would justify retaining an API original; completeness stays conservative until then.
- Merge decision: the earlier mixed-tree run was not acceptance. The frozen-snapshot addendum below supplies a clean focused no-bootstrap run; the lead remains responsible for full acceptance and required CI.

## Final frozen-snapshot focused rerun

After the lead reported that production was frozen and the parser certificate had been regenerated, I reran the complete focused selection without `REPO_CATALOG_TEST_BOOTSTRAP`. The effective working-tree tree hash was `50f41aba1bdf0fac8bc8ad661b073d031ae17905` both immediately before and after pytest. The committed HEAD remained `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9` (committed tree `bf6f5e1b037cf18b798086b9ef56abd68e211380`); the effective test tree included the five pre-existing uncommitted documentation, collector, verification-resource, and regression-test files listed by `git status`. `git diff --check` passed. The bundled parser-verification resource SHA-256 was `daa5bc41c5be3fd3df2b46d12766ddcc83133d50ce57bebf62992a94a59f434d`.

Exact command selection (no bootstrap override):

```text
env -u REPO_CATALOG_TEST_BOOTSTRAP uv run --no-sync pytest -q \
  tests/integration/test_catalog3_exchange.py \
  tests/integration/test_phase1_exchange_retirement.py \
  tests/integration/test_catalog3_coverage.py \
  tests/integration/test_catalog3_coverage_ownership.py \
  tests/integration/test_catalog3_coverage_queries.py \
  tests/integration/test_phase1_retirement.py \
  tests/integration/test_catalog3_selective_exchange.py \
  tests/integration/test_catalog3_exchange_integrity_audit.py \
  tests/integration/test_current_review_query_coverage.py::test_nonterminal_current_page_cannot_inherit_complete_family_coverage \
  tests/integration/test_catalog3_github_runtime.py::test_304_never_attaches_cached_head_to_newer_race_observation
```

Result: **314 passed in 91.76 seconds, 0 failed**. The earlier planned selection was described as 311 cases, but the frozen tree includes three newly added collector regression parameters, so pytest collected 314. The previously observed stale-certificate failures and source-edit-overlap run remain recorded above as historical failures; they are superseded for this focused selection by this stable no-bootstrap pass and are not counted as final semantic failures. Separately, the lead reports the fresh bootstrap verification completed **1,718 passed in 192.58 seconds** on this frozen implementation snapshot. This reviewer did not run that broader bootstrap suite.

The focused final rerun exercises A–I evidence listed above, including selective versus full collection completeness, partial/nonterminal boundaries, latest-time candidate selection and same-time conflicts, 304 exact-original/scope/race cases, delayed dependency reopen/promotion, and Exchange integrity. This update does not change the Coverage v2 five-column schema or its latest-observation-time candidate-set semantics. No Coverage or Exchange defect was reproduced. Retained Phase 2 publication, Source inventory, collection-proof, 304/restart, and Git-content dependencies remain explicitly in scope as shared paths rather than claimed retired.
