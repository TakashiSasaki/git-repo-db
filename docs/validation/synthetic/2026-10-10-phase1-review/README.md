# Independent Phase 1 review evidence

The owner authorized review, correction, acceptance, and sequential merge of PRs #19 and #20. These reports preserve the independent reviewers' findings and their exact reviewed source hashes. The implementation lead corrected shared production code; reviewers constructed counterexamples and reran the corrected behavior. Reviewer C also added two disjoint performance tests after completing its production review.

| Workstream | Evidence | Final focused result |
| --- | --- | --- |
| PR #19 decisions | [Decision review](reviewer-pr19-decisions.md) | Final document at `1cd407b` verified; authorization ambiguity corrected |
| A: CLI/parser/collector | [Report A](reviewer-a-cli-collector.md) | 58 passed without bootstrap |
| B: CAS/schema/recovery | [Report B](reviewer-b-cas-schema.md) | 72 CAS/payload cases passed without bootstrap; schema audit passed |
| C: Exchange | [Original findings](reviewer-c-original-exchange-findings.md), [corrected review](reviewer-c-exchange.md), [performance evidence](exchange-performance.md) | 108 corrected Exchange/CAS cases passed without bootstrap; includes two scaling regressions |
| D: collection/Coverage | [Report D](reviewer-d-coverage.md) | 314 passed without bootstrap on unchanged effective files |

Focused counts overlap and must not be summed. The failed or mixed-tree developmental runs remain disclosed in the individual reports; they are not acceptance. Final full ordinary, isolated wheel/sdist, and hosted CI receipts are recorded by the lead for the final submitted HEAD and effective tested tree. The final bootstrap certificate-generation receipt covered 1,718 passing cases; the later two deterministic scaling cases do not change the frozen production definition and are included in ordinary final acceptance.

The Phase 1 decision and implementation preserve historical publication, Source inventory, accepted partial roots, live restart, exact 304 reuse, historical exchange proof, and physical integrity where those retained paths still require originals. Independent saved-API replay, reparse, extraction, rejected-response reuse, API-only repair, and original-only distribution remain retired. This review selects no deferred lifecycle, completeness, cache, publication, field-inventory, or garbage-collection architecture.
