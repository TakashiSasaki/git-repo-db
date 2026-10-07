# Provider-resource identity completion: synthetic validation

## Revision and scope

- Repository: `TakashiSasaki/git-repo-db`; PR #3, branch `refactor/portable-document-observations`.
- Interrupted starting revision: `e51be9e8b8a1af2bdf1b82db0acf11318e5d386d`.
- Clean substantive tested commit: `db69fe28dbf279627b9e3631682b1f009e20c362`.
- Tested tree: `e795aad41fa73a876a2a55a5d9e4891914a1a898`.
- Format: `repo-catalog/catalog3`, schema version 6. This report and its handoff link are evidence-only follow-ups.

Complete the agreed change-request names, remove normalized `provider_node_id`, replace synthetic review-thread IDs with `(change_request_id, provider_resource_id)`, and use same-parent comment references. Resource IDs are not required to be unique across unrelated parents or all providers. GitHub database IDs are canonical document identifiers; GraphQL Node IDs are not fallback document keys. Missing canonical IDs retain raw response evidence with partial diagnostics and retryable pagination. Original provider keys and values remain in raw evidence.

## Completed acceptance

The existing full planner, test collection, profiled execution and gate were used on the clean substantive commit. Final profiles report `tracked_changes=false`.

| Check | Result |
| --- | --- |
| Ordinary current acceptance | 383 passed; 4 workers; profiled wall 49.0161 seconds |
| Installed wheel and sdist-derived wheel | 2 passed; sequential; profiled wall 3.3292 seconds |
| Selection/execution reconciliation | 385 selected tests executed exactly once; 42 files; no failures, skips, unexecuted or excluded files |
| Ruff lint and format | Passed; 116 Python files formatted |
| STRICT/FTS doctor | Passed |
| Prose and report validation | Passed |
| Locked dependency verification | 24 compatible Linux-required wheels verified against `uv.lock` hashes |

The packaging tests built and installed actual distributions in independent environments outside the source checkout. They did not use the development source-path override.

Environment: Linux x86_64, Python 3.13.5, SQLite 3.46.1, Git 2.47.3, uv 0.10.0, Ruff 0.16.10, pytest 9.1.1, pytest-xdist 3.8.0. The downloaded wheel artifact excludes Windows-only `colorama`; its platform marker was verified before skipping it in the environment-only wheelhouse preparation. Repository dependency or safety contracts were not weakened.

Added regression coverage includes same resource ID under different parents, duplicate same-parent rejection, wrong-parent FK rejection, immutable thread keys, canonical ID type checks, removed Node-ID aliases, scoped long-name CLI selectors, root/child GraphQL partial-response retention and successful retry, and v2 missing-identity archive/diagnostics without fabricated identities.

## Earlier failed or interrupted checks

The starting revision's GitHub Actions run `37566067078` failed formatting before ordinary tests ran. During resumed local diagnosis, an unmodified full run completed with 356 passes and 2 failures, both obsolete schema-version expectations; those were corrected. Two earlier tool-limited invocations did not complete and are not counted as successful validation. Final acceptance above is a separate completed run.

## Evidence hashes and transport

Local `artifacts/ci-profile/validation-manifest.json` SHA-256: `765d92bf3fab8b12075fc44d566b524cc47838443b1e1cb84970894f7999378d`.

Ordinary JUnit SHA-256: `7b5cc95790d1527c39ad1a054ad458c53b52fa9e915af8884f37c8b3c9a7e141`.

Packaging JUnit SHA-256: `c2d3fe28f0675c317df7e854096cb666a3d6a4aec276191c040341b2c9397f00`.

The offline editing environment could not resolve external hosts. Temporary GitHub Actions transport supplied public tracked source and staged the exact tested Git objects after bundle SHA-256 and Git tree verification. Publication preserves history, including the tested commit. Temporary transport files/workflows are absent from the final application tree. This local result does not claim a later GitHub CI result; CI records remain separately attributable to their exact commits.

No real user database/cache, live provider collection, release, main merge, active-catalog cutover or multi-catalog exchange was executed. Historical schemas, v2 fixtures and prior validation records were retained unchanged.
