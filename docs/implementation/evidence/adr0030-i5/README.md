# ADR 0030 I5 independent acceptance evidence

Read [the acceptance report](../../adr0030-i5-independent-acceptance.md) and
[owner merge preparation](../../adr0030-i5-merge-plan.md).

The corrected executable source is `c2c3735439a714bbc9d4128421e7be2c0e88f5b4`,
tree `fdafb830ba63a7f547c5882fe677f9d25ae36bd3`. This directory is an
evidence follow-up. Final Git coordinates/checks are in Draft PR #112 and its
independent final evidence-tree review; frozen source identities remain unchanged.

- `tests/report.md`, final-combined-summary and final2-inventory: all4934 nodes,
 4933 successful nonlive nodes as an explicitly bound union, one prohibited live
 test. Original additional run2579 pass/4 fail is retained; the same4 corrected
 nodes pass in separate author/independent runs. This is not one monolithic4933 run.
- `e2e/`:20 new end-to-end cases, all19 populated Context table PK/rowsets,
 selective exchange, qualified Mapping/current affiliation, Transfer and Search.
- `packaging-correction/`, `triage/`: real omitted-fixture failure, main comparison,
 separate test-only correction and successful installed retests. No product fix.
- `independent/`: source1 review473 pass and corrected-tree4 pass, original
 failures independently reconciled, own source/config/interpreter/import binding,
7 helper controls and corrected packaging review. Historic `review-in-progress`
 and interrupted/probe-error receipts remain historical; latest review is
 `corrected-packaging-review.md`. Reviewer did not author the reviewed tests.
- `distribution-corrected/`: final five source/isolated smoke executions,8 static
 audits, full/minimal dependency isolation, actual source ID/DDL/package hashes.
 `distribution/` and `distribution-final/` retain earlier source-bound results;
 historical Access11/15 assessment is in `distribution/access-reevaluation.md`.
- `hosted/`: #111 and I5 actual logs, validated receipt members, collection/JUnit,
 archived executable-input comparison and upload/digest proofs. Final runtime
 cohort2353 is narrower than the complete applicable local4933 coverage.
- `stack/`: live PR metadata, all five original test-merges,6 I3-exclusive
 ancestor proof, two-parent local simulations, frozen I5 test-merge/main-tree
 equality and unchanged main/parent heads. No refs were merged/retargeted.
- `root-docs-unit.*`:8 overlapping docs-unit reruns; these add no unique coverage.

Index entries bind transport and original bytes. Logs/node lists/JUnit/journals
are gzip; external executable scripts are transported as `.py.txt.gz` or
`.sh.txt.gz`, with original paths/commands recorded. Restore names intentionally
before reproduction. Source-relative aliases are retained in the index. No
Catalog DB, credentials, compiled library, package binary, full source archive
or venv is committed. The synthetic URI rejection node IDs deliberately contain
fake `token=` inputs; they are test keys and must not be redacted into mismatches.

No release qualification, owner merge approval, P8/public switch, real Catalog
operation or live acquisition is authorized or claimed. All PRs remain Draft.
