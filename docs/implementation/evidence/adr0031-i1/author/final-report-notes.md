# Frozen I1b scoped validation

Validated code commit `e0e5c0ed37ac9d6c860db185415616c60161b30d`, tree
`b6484a7185e9f410a8d05ff5bd4fa574e6dc45e2`, with exact I1a parent
`d92377599a50f192f534836fc12402a5fe87ca83`.

Both actual runtimes executed sequentially against the same frozen inputs:

| Actual SQLite | Selected | Executed | Passed | Failed | Errors | Skips / xfail |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.51.3 / Python 3.13.5 | 564 | 564 | 561 | 3 | 0 | 0 / 0 |
| 3.53.1 / Python 3.12.14 | 564 | 564 | 561 | 3 | 0 | 0 / 0 |

The three failures on each runtime are:

- `tests/integration/i2/test_provider_intake.py::test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]`
- `tests/integration/i2/test_provider_intake.py::test_graphql_transfer_parent_namespace_and_original_type`
- `tests/integration/i2/test_provider_intake.py::test_graphql_event_does_not_infer_destination_from_current_issue_repository`

All three raise the explicit admission error:

> Current packaged DDL requires nonempty scalar local document IDs; generalized
> Document persistence is deferred to ADR 0031 I2

The frozen implementation preserves genuine native GraphQL Node identity arrays.
These existing integration cases reach the intentionally unchanged packaged
scalar-local-document-ID DDL boundary. They remain actual failures, with pytest
exit 1 on both runtimes. No skip, xfail, fallback, double encoding or later-stage
DDL expansion turns them into passing claims. The remaining scoped tests pass.

All 37 disposable SQL comparison cases executed on both runtimes. Their actual
connection settings were foreign_keys=1, recursive_triggers=1, encoding=UTF-8,
journal_mode=delete, synchronous=2, trusted_schema=1 and temp_store=0. Full compile
options and every executed SQL node ID are retained in each runtime directory's
`sql-runtime-and-cases.json`. These test tables are I1 BINARY-equality/compound-FK
comparison harnesses, not generalized production DDL.

Actual source IDs:

- 3.51.3: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`
- 3.53.1: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`

`input-manifest.json` binds all 426 tracked src/tests/scripts/configuration inputs
to the frozen commit using Git blob hashes and SHA-256. The runner compared
these inputs before testing and after each runtime; every comparison passed.
It reconciled the complete selected-node multiset to executed journal starts,
JUnit case identities and exactly one setup/call/teardown phase for every test.
Both journal finishes match their real pytest exit codes. No test/product source
was changed during these runs.

The nine modules selected were the identity codec, ResourceKey and GitHub
identity unit modules; P1 identity SQL, Context, Context relations and Coverage;
I2 Provider intake; and I3 selective Exchange. Exact argv, explicit validation
environment, timestamps, subprocess exit codes and log paths are recorded in
each `*.execution.json`. `cohort.json` lists the paths. Per-runtime selected and
executed node inventories, raw logs, JUnit, event journal, runtime settings,
failure details and summaries remain available. `summary.json` is the combined
machine-readable report.

An earlier attempt using the repository's existing `--journal` stopped after
192 starts. A codec counterexample temporarily patches shared `json.dumps` until
fixture teardown, while that journal resolves `json.dumps` during the call report.
That interaction caused a pytest INTERNALERROR, before SQL tests ran. All its
failed receipts and the original runner are preserved under
`attempt-1-journal-conflict-sqlite3513` and `run_validation.attempt-1.py`.
The final run uses work-only `-p i1_event_journal`, which captures its serializer
before test execution. This fixes validation instrumentation without changing
frozen code/tests or relabeling the aborted attempt as product success.

This is scoped development validation, including explicit unresolved I2 product
failures. It is not complete integrated-product, wheel/sdist, release, activation
or merge acceptance.
