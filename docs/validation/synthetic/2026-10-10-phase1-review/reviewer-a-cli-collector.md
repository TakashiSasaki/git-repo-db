# Independent Review A — CLI, Parser, REST/GraphQL, and Source Inventory

## Review basis and independence

I reviewed PR #20 independently of the implementation work in `/workspace/impl-pr20`. I made no tracked-file edits. I first reviewed the PR implementation from a separate checkout, reproduced Source Inventory admission defects with disposable fixtures, then retested the lead corrections on the current frozen worktree. The current snapshot is commit `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9` plus the exact file contents identified by the hashes below; the correction and certificate files were still uncommitted in the shared worktree at review time.

I read `AGENTS.md` and the applicable architectural material: `docs/transport-independent-core-adr.md`, `docs/phase1-api-original-retirement.md`, `docs/phase1-api-original-retirement-implementation.md`, `docs/phase1-api-original-retirement-inventory.json`, `docs/transport-independent-core-implementation.md`, `docs/model-integration-status.md`, `docs/data-model.md`, and `docs/architecture.md`.

Review scope was R1–R3 and R6: CLI and application reachability, parser dispatch, REST and GraphQL rejected-input paths, Source Inventory identity checks, rollback/retry behavior, and retained boundaries. This review did not decide Phase 2 lifecycle or completeness policy.

## Findings reproduced in the original PR implementation

### Medium — Invalid authenticated identity response was admitted before validation

**Affected path:** `GitHubCollector.inventory()` in `src/repo_catalog/adapters/github/collector.py`, `/user` identity response.

**Minimal reproducer:** Use a valid Source with owner `fixture`; make `/user` return a JSON object whose `login` is `""` (also reproduced with `login: []`) and include a unique transport-only marker. Invoke `collector.inventory(source, job)`. In the original implementation, the raw `/user` response was admitted into `source_input_observations` before identity validation later rejected or mishandled it.

**Root cause and invariant:** Source Inventory was persisting its raw response before establishing that the authenticated identity was a valid nonempty string. This retained a rejected API original, contrary to R6 and the no-retention-on-rejection rule.

**Correction:** Validate the `/user` response object and nonblank string `login` before calling `inventory_input()`.

**Regression coverage:** `tests/integration/test_phase1_retirement.py::test_rejected_inventory_page_does_not_become_source_input`, parameters `identity` and `identity_empty`. The test asserts the rejected `/user` endpoint has no `source_input_observations`, raw marker, staging, or unresolved payload, then retries with a valid response.

### Medium — General inventory accepted malformed repository identity and retained its response

**Affected path:** General `/user/repos` or `/orgs/{owner}/repos` page processing in `GitHubCollector.inventory()`.

**Minimal reproducer:** Return a valid authenticated `/user` identity and a repository item with `id: 101`, `full_name: "fixture/"`, and a nonempty valid `clone_url`. The original owner check compared only `full_name.split("/")[0]` with the configured owner. It accepted the empty repository component and admitted the page response.

**Root cause and invariant:** The inventory validator established only an owner prefix, not a complete repository identity. A malformed, rejected inventory item could therefore become persisted Source input and a malformed repository result.

**Correction:** Require `full_name` to have exactly two nonempty path components before the owner-scope check and before admitting the page response.

**Regression coverage:** The same test, parameters `repository_name_empty` (`fixture/`) and `repository_name_extra` (`fixture/alpha/extra`), asserts the rejected page is not admitted and retry succeeds.

### Medium — Selected-repository path admitted an empty clone URL

**Affected path:** `include_repositories` branch in `GitHubCollector.inventory()`.

**Minimal reproducer:** Configure Source settings with `{"owner":"fixture","include_repositories":["alpha"]}`. Return valid `/user` identity and `/repos/fixture/alpha` JSON with `id: 101`, `full_name: "fixture/alpha"`, and `clone_url: ""`. The original code checked only that `clone_url` was a string, admitted the response, and returned a repository with an empty URL.

**Root cause and invariant:** The selected-repository branch checked URL type but not a usable nonempty effective URL before retaining the API input. This also differed from the general inventory branch.

**Correction:** Resolve the configured clone override or provider `clone_url`, require the effective value to be a nonempty string, and only then call `inventory_input()`.

**Regression coverage:** The same test, parameter `selected_clone_empty`, checks `API_SCHEMA`, absence of the rejected endpoint input and raw marker, and success on retry. The disposable pre-fix reproducer now reaches the intended validation error before admission.

No other R6 Source Inventory admission defect remained in the reviewed cases. The regression test also covers unsupported owner identity, selected wrong-owner identity, malformed provider ID, and malformed page shape.

## R1–R3 reachability review

- `parser reparse-message`, its saved-message context option, and the old action spellings are absent from CLI registration/help. Direct `ParserService.execute()` calls reject retired action names before reading message input or opening a catalog.
- `ParsingService.reparse()` accepts only IDs found in `git_acquisitions`; it raises `PARSER_UNSUPPORTED_INPUT` for API fetch occurrences before loading their payloads. Git-content reanalysis remains reachable through the Git reparse path.
- `inspect-message` remains a bounded, read-only diagnostic operation over the explicitly supplied archive path. It does not create domain observations or mutate the catalog.
- I found no alternate CLI dispatch, application API, dynamic alias, import, or maintenance route that replays an old API response into new domain observations.

## REST, GraphQL, corruption, rollback, and retry coverage

The reviewed transaction paths and focused regressions establish that malformed/rejected REST pages, malformed GraphQL roots, malformed or failed child pagination, and incremental comments with a missing Issue/PR parent do not fabricate successful observations or retain the rejected response as a reusable original. Valid accepted parent/root input may remain where the deferred live-restart contract depends on it; rejected child bodies are retried from their safe saved cursor. Physical CAS corruption and forced hash-collision admission failures reject the incoming API response without creating a new occurrence or putting that response into Git-only admission staging; corrected fresh requests can retry.

These checks preserve the distinction between a rejected incoming API body and successful historical inputs still needed by deferred publication, restart, 304, and proof behavior. This review makes no claim that all API bodies have been eliminated from the core.

## Verification

After the lead regenerated parser verification evidence, I ran the focused no-bootstrap suite with `REPO_CATALOG_TEST_BOOTSTRAP` explicitly unset:

```text
env -u REPO_CATALOG_TEST_BOOTSTRAP uv run --locked --group dev --no-sync python -m pytest -q \
  tests/unit/test_message_inspection.py \
  tests/integration/test_catalog3_parsing_runtime.py::test_core_http_reparse_is_retired_without_reading_original_or_mutating_catalog \
  tests/integration/test_catalog3_parsing_runtime.py::test_source_inventory_records_separate_owned_raw_inputs \
  tests/integration/test_catalog3_parsing_runtime.py::test_retired_http_reparse_rejects_quarantined_original_without_diagnosis \
  tests/integration/test_catalog3_parsing_runtime.py::test_valid_new_fetch_of_corrupt_digest_is_rejected_without_original_staging \
  tests/integration/test_phase1_retirement.py::test_rejected_inventory_page_does_not_become_source_input \
  tests/integration/test_phase1_retirement.py::test_rejected_rest_original_is_absent_and_retry_makes_a_new_request \
  tests/integration/test_phase1_retirement.py::test_rejected_graphql_root_has_no_saved_original_or_fake_completion \
  tests/integration/test_phase1_retirement.py::test_rejected_graphql_child_retries_its_safe_cursor_without_original \
  tests/integration/test_phase1_retirement.py::test_unknown_incremental_parent_needs_fresh_response_before_watermark \
  tests/integration/test_phase1_retirement.py::test_live_api_cas_corruption_rejection_does_not_save_replacement_original \
  tests/integration/test_phase1_retirement.py::test_failed_api_hash_admission_does_not_create_or_stage_original
```

**Result: 58 passed in 28.21 seconds; 0 failures and 0 skips.** The no-bootstrap run used Python 3.12.14 and pytest 9.1.1. Separately, the lead reported a full bootstrap development run of 1,718 passing cases in 192.58 seconds after regenerating the parser certificate. Before that regeneration, an exploratory no-bootstrap run correctly failed with `BUILTIN_VERIFICATION_STALE`; it was not counted as acceptance and the focused suite was rerun successfully after certificate regeneration.

## Remaining boundaries

The retirement is complete for the independent saved-response replay, retrospective API parsing/projection, and delayed failed-response reuse paths reviewed here. Successful API inputs may remain as shared dependencies for historical publication, live restart, conditional reuse, and collection proofs until their separately deferred contracts are decided. Source Inventory still retains accepted validated input; that is distinct from retaining a rejected response. These retained dependencies are not an authorization to restore standalone archive, replay, repair, or distribution operations.

## Reviewed file content hashes (SHA-256)

Production files:

```text
src/repo_catalog/adapters/github/collector.py          2d1d68c7690e64ce11140e2a09091f85d6d777420c0079ca682ce4676c98f7e5
src/repo_catalog/adapters/github/persistence.py        eb3715db570206a6c97eb1795cd20fef3a860c6ada2398bef56a1ea5c98fa6d4
src/repo_catalog/adapters/github/transport.py          b970b41099c8e4edb101db67e58047cee8c6132810b13bfc2fca0bc1c2acf714
src/repo_catalog/application/parser_service.py         2d39d61b0124e2892bba53ce0ab79e0e8d626abc36b50df43204fd0131199bce
src/repo_catalog/application/parsing_service.py        6684657a54c98600d43732ce24104ebb67f472acf35c912b0f8a0d7881c93f84
src/repo_catalog/adapters/sqlite/current_resources.py  dcaf95481c590eafd4d996447e745710c0161568b17a832728841d353954b006
src/repo_catalog/adapters/sqlite/payloads.py           9ce2d52bcfdd6a2dbcc6639e969eee60f8c237e2587b6451d6d10b51342dbbfc
src/repo_catalog/adapters/sqlite/cas_integrity.py      2468f3b36237faf135fff6973cabb529f1aee3fef4f496244a1b7eb15f7bcc38
src/repo_catalog/cli/main.py                           c35914ba2b508fdf1031f1212525627ebb8286741f4e86ee40bd42fa25d9273a
src/repo_catalog/resources/builtin_parser_verification.json
daa5bc41c5be3fd3df2b46d12766ddcc83133d50ce57bebf62992a94a59f434d
```

Regression files:

```text
tests/integration/test_phase1_retirement.py            e65814c6504b0e5432fd6e70f39d21b0fcf97823449cd1da926609aad029d9dd
tests/unit/test_message_inspection.py                  1e053dcc19f74e146a46e17f651e5ab7abad0c667cc75cdc632690a406b42b65
```
