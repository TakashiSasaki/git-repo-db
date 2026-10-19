# R4 independent baseline review: acceptance semantics, ADR preservation, CI/distribution/docs

Reviewer: R4, independent read-only reviewer. Start: 2026-10-18 12:36:09 JST.
Reviewed HEAD: `f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60`.
Reviewed tree: `a7b4521fb7fa6562c8e0bf67e2766743e0b82c5b`.
Read-only checkout: `/workspace/access-review-ro`; initial and final tracked dirty state empty.
Evidence only: `/workspace/access-review-evidence/r4`.

## Outcome and scope

No new material product-code defect is claimed by R4. This review independently inspected the actual assertion bodies of all 48 functions linked by the 26-item acceptance ledger, plus relevant supplementary tests, complete ADR0003 and all proposed ADR0029 carry-forward clauses, accepted ADR0014/0017/0021-0028, ADR policy/index, Access A1/A1a/A1b/A2a/A3/A4/A5/A6 reports, the routing ledger and the four requested repository skills. Existing design-only baseline statements were not mistaken for public runtime activation. Catalog3 Schema21 remains the default; this Access stack is explicitly invoked and local-Linux execution only.

Known baseline item11 remains an implementation gap; R2/R3/root counterexamples must be incorporated separately. An apparently covered requirement does not override an independently reproduced product failure. The full independent integration gate remains open until material fixes are independently rechecked at their changed tree. R4 did not execute product pytest or installed packaging and does not claim those operations. The root runner owns this session's serial full-suite/minimum-SQLite/distribution evidence.

## Evidence/reporting findings

| ID | Severity | Source | Minimal check / observed issue | Recommended disposition |
| --- | --- | --- | --- | --- |
| R4-01 | P3, reporting clarity | `docs/implementation/access-a6-acceptance.json:185`; its item16 gap at line195 | Read requirement16, then its gap: the requirement concerns wheel/sdist, schema/domain safety and time/trust invariants, while the recorded gap names reviewer execution, whole-ADR acceptance and release acceptance. Those are different gates, not one product feature deficiency. | Report item16 implementation verification against actual exact-tree execution receipts; track independent review, whole-record owner approval, merge, P8 and explicit release qualification separately. Do not demand release validation to continue ordinary fixes. |
| R4-02 | P3, evidence-link precision | `docs/implementation/access-a6-acceptance.json:83` and `:280` | Item7's positive exact-URI link tests Scope Locators, while the linked Repository grammar case only rejects negatives. Item24's stack fixture has one registration and its other linked case checks only MAX-time ties. Such a subset can pass without itself asserting the complete stated historical-prefix property. | Add existing positive Repository grammar link `tests/unit/test_access_connections_values.py::test_repository_grammar` and the full-history tests `tests/integration/access/test_backup.py::test_backup_retains_all_history_and_settings_but_not_consent` / `::test_restore_is_continuation_not_fresh_registrations`. They are already selected by the focused workflow. This does not establish an additional production bug or require new machinery. |

Item3/9 linked fixtures do not directly construct and compare Context Source memberships during Access profile edits. Their protection is additionally supported by the inspected independent-store ownership and callsite boundary, rather than a direct membership assertion in those linked bodies. No unsupported deletion-management feature or broad remote executor is inferred.

Item15 distinguishes three facts: the classification ledger exists; a legacy extraction tool is not implemented; real-data extraction/migration is outside this task. An unreleased project without compatibility obligations does not automatically require a legacy migration tool before Access can pass its scoped acceptance. No real catalogs, backups or credentials were inspected or modified.

## Semantic 26-item result

`semantic-acceptance.md` and `semantic-acceptance.json` provide every item's actual assertion semantics, exact function path/line, supplementary references, scope limits and independent static assessment. `linked-assertions.json` and ten `test-excerpts-*.txt` files preserve the 48 linked bodies and assertion/expected-exception extraction. This is meaning-level source review, not test-name existence checking and not 26 newly executed runtime tests.

The baseline author ledger remains 23 covered, 2 partial (11/16), 1 deferred (15). R4 does not edit historical results or automatically carry that count to a corrected source tree. The local static auditor was actually run without receipts, returned exit0, `executed_nodes=null`, `node_set_matched=false`; its stdout/stderr/command are saved. It proves ledger/source-reference consistency only.

## ADR replacement preservation and current/historical references

`adr-clause-map.md` / `.json` map 43 source-clause rows, including all seven Core rules, five Context rules, all isolation/recovery rules, PF mappings, preserved/deferred meanings, non-goals and six acceptance criteria. No material loss of a still-binding ADR0003 requirement was identified after applying already accepted ADR0004/0014/0026/0028 scope changes. ADR0029:357 expressly makes its carry-forward text operative; it is not only a pointer to a file that would disappear.

The specific substantive replacement is the explicit four-store count with five responsibility classes. Independent Core/Context authority, metadata-only support, original immutable captures/provenance, exact retained-byte validation, no ordinary-file archive, finite cumulative work, P7 stop/read-only source/fresh restore, truthful backup scope and correct-authority Search remain requirements. No new approval date or acceptance is inferred from implementation or a green check.

Complete tracked-text scanning found exactly25 files /26 occurrences of the ADR0003 filename, independently matching the prior report. `adr0003-inbound-raw.json` retains path, line, text and per-file SHA256; `adr0003-inbound-classified.json` classifies every hit. Three immutable distribution manifests remain untouched. The historical integration inventory remains historical. Plain `refines`/`replaces` metadata are history identifiers, not live links to globally replace. Current authority entry points/banners/procedures need coherent successor wording only after whole-replacement acceptance. Historical predecessor/dependency links need pinned Git history as appropriate, preserving their actual decision lineage.

`adr0003-symbolic-and-four-store-references.txt` additionally preserves the complete symbolic scan. It includes current AGENTS summaries and procedure descriptions that exact-filename searching misses, as well as legitimate historical P1/P7 implementation reports. Four-store reports for a historical or physical P1 component must not be rewritten merely because Access becomes a separate fifth component. The public MkDocs navigation includes only ADR0001/0002 and does not require widening for this change.

Still needed from a human: explicit whole-record replacement approval and its actual date/reference. Only a later authorized coherent lifecycle change should accept0029, retire0003, update current links/index and close that policy migration-debt entry. This task explicitly forbids performing that retirement or whole-record acceptance now. No broader ADR retirement or reopened Scope question is requested.

## CI, installed distribution and documentation scope

`ci-static-scope.json` records the exact frozen workflow SHA256 and both pytest argument lists. The collection/execution target argument sets are equal, including shell-expanded value files. They select the Access suite, relevant value tests, five P1 files and P2/P3/P4/P5/P6/P7 directories. They are not the complete ordinary/release suite; compatibility directories such as `p5_p6_compatibility` are not directly selected. After Exchange fixes, a risk-relevant supplementary compatibility run is appropriate without converting this task into release qualification.

The dedicated minimum-SQLite workflow compiles official3.51.3, checks the published sqlite3.c SHA3-256 and actual SQLite source ID, and does not substitute a version string or weaken the network guard. Runtime facts for this session must come from the root runner's current interpreter/source-id artifacts. R4 did not execute the binding itself.

The actual downloaded dedicated historical job log reports Python3.12.15 / SQLite3.51.3 with official source ID, 1802 passes, both installed smoke variants, and allowlisted placeholder-documentation/link/sensitive-output checks. These are historical hosted results bound to the fixed baseline; they are not this session's rerun of1802 tests. `hosted-log-summary.json` preserves actual timestamped lines.

R4 independently decoded the normal offline job's bounded receipt from its actual log, validated BEGIN/END digest/length, decoded strictly, then verified every index member length/SHA256. Receipt SHA256 is `5ffb28d0f794ab2db50d1a5a5d8862647b3162196c77e7b87da04e5d1bb8928e`,68844 bytes. Feature HEAD f4d0d448, checkout1ebb644d, effective tree a7b4521f match. `offline-hosted-receipt.json` contains the full decoded manifest/binding: mode development, `full_acceptance=false`, `acceptance_status=development_checks_passed`, executed0, selected files0. Its SQLite3.45.1 is the ordinary development smoke runtime; this was not a minimum-version Access runtime execution. General offline runtime/package lanes were not executed and are not counted as passed tests.

`verify_access_distribution.py:216` builds a direct wheel and a wheel from an extracted sdist; creates separate no-system-site-packages venvs outside checkout; installs with no dependencies; removes PYTHONPATH; invokes each interpreter with `-I`. Those are actual isolated installed smoke checks when the script succeeds. The code does not merely add checkout source to PYTHONPATH. The smoke covers packaged DDL, registry history, grants/ABA, real approved local Git into a nonseed repository, backup/restore/fork, Context SQL constraints and exact historical URL Exchange; it is not the whole pytest cohort run against both installations.

The MkDocs workflow calls existing `build_docs_site.py --no-mermaid`. Inspected staging is an explicit existing allowlist. Placeholder SVG generation at `scripts/build_docs_site.py:391` is not fresh Mermaid rendering; no deployment step is present. A successful build validates those staged links/templates/safety checks, not all internal Access/ADR prose. No site allowlist or public output was changed by R4.

## Separate gates at this baseline checkpoint

| Gate | R4 assessment |
| --- | --- |
| Scoped implementation correctness | Partly evidenced; baseline item11 plus independently reproduced R2/R3 issues require correction. R4's static map cannot override those failures. |
| Independent exact-tree review | R4 static scope completed. Overall integration review/fix validation remains open until separate reviewers recheck all material corrections at their actual source tree. |
| Whole-record ADR replacement approval | Pending explicit human approval; settled Scope rules are not reopened. |
| Merge / auto-merge | Not authorized or performed. |
| P8/default runtime activation | Not authorized or performed. |
| Release qualification / release / tag / deployment | Not requested or performed; passing focused tests does not satisfy full release acceptance and does not grant release authority. |
| Legacy extraction / real-data operation | Extractor absent; operation outside this task. Neither is silently performed or promoted to a blanket Access gate. |

## Skills and limits

Applied existing skills: ci-final-tree-verification, three-store-invariants, adr-workflow and lessons-to-skills. Existing bounded-receipt recovery, complete tracked reference scanning, exact-tree binding and current-versus-historical classification procedures worked as documented. R4 made no skill edits on the read-only tree. A useful follow-up within an authorized correction is to add a concise assertion-meaning reminder to the existing CI/ADR workflow guidance: all-history acceptance must compare an old prefix, while MAX-only ties do not establish that prefix; Scope URI grammar evidence does not by itself certify Repository Locator grammar. Root's independently reproduced product fixes may supply stronger reusable lessons.

R4 did not run product pytest, mutate reviewed source, create branches/commits/PRs, post GitHub reviews, merge, force-push, activate P8, operate on real user data, deploy or perform hardware-power-loss experiments. Root coordinates permitted publication and final source/PR/CI evidence. No other reviewer/runner's result is represented as R4's own execution.
