## Validation plan

Effective SHA `d889c5335f89574ba9ab1132b0f1fb011f55a68c`; full acceptance selected: True.
Acceptance input hash: `50c4549e91f85d31b3dd63138462d1a6340c745e1a9d850f47be0cc28f89ca84`.

| Lane | Disposition | Test files |
|---|---|---:|
| static | selected | 0 |
| tests | selected | 102 |
| packaging | selected | 1 |
| smoke | selected | 0 |

Unexecuted acceptance files: 0. Earlier test results are never claimed as fresh execution.
Files outside current acceptance: 0; listed in plan.json.

Planner: 0.139s.

Dynamic test dependency requires full selection: tests/integration/test_catalog3_exchange.py
Unknown dependency path: docs/phase2/publication-free-schema-map.json
Unknown dependency path: docs/phase2/publication-free-test-disposition.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/b86-independent-35-results.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/b86-independent-35-results.xml
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/b86-new-exploratory-fixture-errors.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/b86-new-v2-results.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/b86-new-v2-results.xml
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/corrected-artifact-sha256.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/corrected-new-probes.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/test_independent_acquisition.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/acquisition/test_independent_invariants.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/architecture/portable-identity-tests.log
Unknown dependency path: docs/phase2/reviews/publication-free-b86/architecture/portable-identity-tests.xml
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/git-authorization-scale-b86ff2c96d7558379b2230489e1494630b073ef7.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/git_authorization_scale.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/metadata.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/pytest-26.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/pytest-crossmod-fixture-v2-code.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/pytest-crossmod-fixture-v3.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/pytest-crossmod-v1.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/selected-coverage-scale-b86ff2c96d7558379b2230489e1494630b073ef7.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/selected-pending-scale-b86ff2c96d7558379b2230489e1494630b073ef7.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/selected_coverage_scale.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/selected_pending_scale.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/test_corrected_code_proof.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/test_corrected_crossmod.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/test_corrected_crossmod.v1.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/test_corrected_crossmod.v2.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/domain-qa/test_independent_domain_qa.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-artifact-sha256.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-decoder-families.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-decoder-families.xml
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-decoder-sql-query.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-late-ref.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-own-counterexamples.txt
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-own-counterexamples.xml
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/b86-replay-after-receipt-loss.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/decoder_sql_repro.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/late_ref_repro.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/test_decoder_families.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/final-integrated/test_final_integrated.b86-frozen.py
Unknown dependency path: docs/phase2/reviews/publication-free-b86/hosted-b86-complete.log.gz
Unknown dependency path: docs/phase2/reviews/publication-free-b86/hosted-b86-failed.log.gz
Unknown dependency path: docs/phase2/reviews/publication-free-b86/hosted-ci-profile.zip
Unknown dependency path: docs/phase2/reviews/publication-free-b86/local-interrupted-ordinary.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/local-packaging-full.log
Unknown dependency path: docs/phase2/reviews/publication-free-b86/local-packaging.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/local-packaging.xml
Unknown dependency path: docs/phase2/reviews/publication-free-b86/local-plan.json
Unknown dependency path: docs/phase2/reviews/publication-free-b86/local-tests-full.log
Unknown dependency path: docs/phase2/reviews/publication-free-b86/manifest.json
Shared/executable input: scripts/audit_publication_free.py
Shared/executable input: src/repo_catalog/adapters/git/parsing.py
Shared/executable input: src/repo_catalog/adapters/sqlite/current_api.py
Shared/executable input: src/repo_catalog/adapters/sqlite/current_resources.py
Shared/executable input: src/repo_catalog/adapters/sqlite/exchange.py
Shared/executable input: src/repo_catalog/adapters/sqlite/git_intrinsic.py
Shared/executable input: src/repo_catalog/adapters/sqlite/index.py
Shared/executable input: src/repo_catalog/adapters/sqlite/json_contracts.py
Shared/executable input: src/repo_catalog/application/catalog_validation.py
Shared/executable input: src/repo_catalog/application/git_query_context.py
Shared/executable input: src/repo_catalog/application/query_service.py
Shared/executable input: src/repo_catalog/domain/git_decoding.py
Shared/executable input: src/repo_catalog/resources/exchange.sql
Shared/executable input: src/repo_catalog/resources/git_facts.sql
Shared/executable input: src/repo_catalog/resources/json_contracts.sql
Shared/executable input: tests/support/publication_free_node_dispositions.json
