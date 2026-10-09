# Stack review correction acceptance — 2026-10-09

Branch `fix/pr-stack-review` starts at PR #9 `f8c1764c02da45c93437d36465a39ed68952d67d`. This corrects the cumulative stack #4 → #5 → #7 → #8 → #9, without changing its ancestry, schema 11 or workspace 2. Tested clean implementation commit: `eaa280f30cf33a5e83782d2305db86770bdc649d`; Git tree: `0d80e0ce286c84114f57f1beb00937f3a264065b`. Evidence-only commit `5d38f507c346e43e5bbafe902a453018b0d66b72` passed report checks with the same acceptance input fingerprint and zero runtime tests rerun. The later workflow-reference correction below changes that fingerprint and requires separately completed full hosted acceptance.

## Result and attribution

**PASS: 1,027 ordinary tests and 2 installed packaging cases, 1,029 selected/executed exactly once across 55 files.** There were zero failures, skips, duplicates, excluded files or unexecuted ordinary acceptance files. One final full acceptance was run on this clean implementation commit. Ruff lint/format, report validation, locked wheel preparation, SQLite FTS5/trigram capability and doctor passed. Ordinary command wall time: 96.44s with four workers; sequential packaging: 4.08s. These are measurements, not fixed performance gates.

Environment: Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19, Linux x86_64. The gate records `full_acceptance=true`, `acceptance_status=full_acceptance_passed`, and acceptance input hash `7acf02e2d44f2580b2588214c8959b3ecbe7b029509d114328c0ee5bfee4b25a`. [Adjacent JSON](2026-10-09-stack-review-fixes.json) contains the exact command arrays, runtime, counts, timings and SHA-256 digests of local profiles/JUnit/selection evidence. Hosted CI is separately attributed to its published merge commit and run in the PR; it is not claimed by this local record.

## Review findings resolved

| Finding | Correction and regression coverage |
| --- | --- |
| F1: 101-comment thread reported complete after only its first page | Require the selected thread's root boundary and, when needed, completed same-parent child evidence. Tests cover saved-comment count, partial roots/children, unrelated child failure, error-only attempts, older-job resume and newer child-only observations. |
| F2: display name overrides selected service routing | Registered REST/GraphQL routes determine the endpoint; default routes are captured when registering. Duplicate/renamed display names and explicit source overrides are tested. |
| F3: timestamp parsing silently changes fractional hours/minutes and invalid offsets | Admit explicit calendar/week and clock syntax; reject unsupported fractions and out-of-range offset components. Guarded salvage preserves the raw value and diagnostic with NULL normalized time. |
| F4: timeline failure contradicts document-only coverage | Share one classification for query and acquisition coverage, including PR-prefixed code/timeline aliases; unknown kinds remain conservative. |
| F5: malformed REST values lose evidence or publish an invalid boundary | Validate JSON/string shapes, exact OID widths/formats, int64 values and requested PR ownership before normalized admission. Keep exact bytes, attributed API_SCHEMA, committed earlier pages and the same safe retry URL. Programming errors remain distinct. |
| F6: missing bodies repeatedly read/hash one response | Keep one bounded validated payload key per conversion context; independent verification gets a fresh context. Regressions bound whole-page read/hash counts for 11/101 missing bodies and still detect changed declared hashes. Detail ETag updates also reuse the admitted occurrence reference; 304 creates no observation. |
| F7: new ordinary tests omitted by an allowlist | Discover both pytest filename patterns in all four ordinary directories, including add/rename/delete cases. |
| F8: imported test/helper changes omit consumers | Inspect test imports and conservatively expand uncertain/dynamic/plugin dependencies, including aliases and relative imports. |
| F9: synthetic JSON unnecessarily selects full yet is not validated | Classify it as report evidence and validate nonempty finite JSON objects, including nested paths. Fingerprints retain explicitly executable/shared inputs. |
| F10: live smoke uses removed repo_id output | Use repository_uuidv4 and add an offline mocked CLI-contract regression; no live acquisition is performed. |
| G: duplicate wheel build and missing recovery/package boundaries | Reuse the two isolated wheel/sdist-wheel workflows for populated v2 salvage, finalize, query, full check and original DB/cache hashes. Add before/after-COMMIT process-death recovery, paired state, exactly one publication and idempotent retries. |

Two JSON-constraint regressions now supply valid mandatory source registration identities, so rejection is specifically the JSON CHECK rather than an unrelated NOT NULL failure. Current operating/identity/time/coverage documentation is reconciled, and workflow actions move to Node 24 releases. CI explicitly reports selected-only success and an acceptance-input fingerprint; a prose-only green run never proves runtime acceptance. Final integration remains a documented manual comparison against completed full acceptance, with no unconditional full run on every push.

## Reproduction and protection

Run `python scripts/ci_plan.py --full` through the planning profile wrapper, then the report/dependency/wheelhouse/static/smoke commands listed in the adjacent JSON. Run `uv run --no-sync python scripts/ci_execute.py collect`, the `tests` and `packaging` lanes, and `python scripts/ci_execute.py gate`. All final command profiles must have the same clean SHA, runtime and run identity. CI performs these same operations automatically; see [workflow](../../../.github/workflows/tests.yml) and [CI selection documentation](../../change-aware-ci.md).

Only disposable synthetic source catalogs, caches, Git repositories and mock HTTP services were used. Guarded import still denies source writes and acquisition; tests preserve original source/cache hashes. Imported first-sync conditional detail, saved-listing reuse, request logs, resume and authorization/replay fencing remain in the full suite. No original user database, live source, active-catalog switch, release or main merge is part of this acceptance.

Focused development checks preceded the final clean run. Initial focused failures from CLI PATH setup and new recovery/boundary expectations were corrected; the existing code-check transport-failure regression was corrected before final acceptance. Independent review also caught resumed-child ordering, dynamic import aliases and REST Unicode/OID edges; their regressions now pass. Those intermediate checks are not counted as fresh final acceptance.

## Limits and follow-up

Published as [PR #10](https://github.com/TakashiSasaki/git-repo-db/pull/10), based on #9. Initial hosted [run 37875595982](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37875595982) failed during action resolution, before any test ran: `astral-sh/setup-uv@v10` has no floating major tag. The published `v10.2.0` tag exists and is now used explicitly; the other three `v7` action tags were also checked against their remote refs. This follow-up changes workflow/docs only, not application or tests. Its final hosted full result and exact SHA are recorded in the PR after completion; the earlier local fingerprint is not claimed to cover the changed workflow.

Process termination before/after the actual SQLite COMMIT validates process-death recovery, not physical power-loss durability. Real-source acquisition remains unexecuted. Further fixture caching was deferred: the review did not demonstrate a benefit warranting added fixture state, while the measured duplicate wheel build and repeated payload hashing were removed. Existing roadmap work (portable acquisition identities, parser/selection DAG, exchange, durable conflict staging, quarantine/repair, hash-verified backup/restore and frozen Job inputs) remains separate from these corrections.
