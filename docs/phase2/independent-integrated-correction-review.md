# Independent review of the integrated Phase 2 corrections

Status: independently reviewed source and focused executable evidence. This
review does not accept the proposed Phase 2 architecture, authorize a merge or
substitute for final ordinary, certificate, installed-package or hosted CI
acceptance.

## Exact reviewed source

The documentation base is
`ed5f06cf242bb915ea5be05f8387954fce12bb09`, tree
`927e879406cfa98fd93d426bb5e9ffd84a4a36ac`. The integrated implementation source
reviewed read-only in the separate `/workspace/p2-audit` worktree is
initially `250cb14bc9483af772eddf34f87c370dac612512`, tree
`c34995235648ec26bd9f258d48f87162c1f816a6`, on
`impl/phase2-evidence-integrity-20261010`. It includes the six independently
investigated corrections, coordinated schema 19 finalization and current parser
version 2. The reviewer changed only documentation/prototype files in the
separate review branch, and used generated disposable catalogs and local mocks.
The lead subsequently corrected the recorder regression in
`47be2fd780f0a5278d950d0053cde9ac6fb6f196`, tree
`db5f34b664ef33c36a8fedc65276c9b0079a0916`; only that test and its documentation
changed. The final independent interaction/structural receipt is bound to this
later revision with all production-source fingerprints unchanged.

The [machine-readable receipt](independent-integrated-correction-receipt.json)
records all seven changed production-source SHA-256 values, the exact source
revision/tree, Python 3.12.14 and SQLite 3.53.1. The source hashes and Git revision
were unchanged across the independent interaction probe. Its parser hash is
`e6f60f73fe88748d240c7c4f9e3aaa9b18863dd1d4fb6915d88652f9f69660eb`;
the integrated Exchange hash is
`b63b914c0100f3116c5c549e2c046a897bf065d2ff57c387446362f69af0cc81`.
The production diff and actual package-test version fixtures were reviewed;
installed package execution remains the lead's final acceptance step.

## Interactions challenged

| Boundary | Independent finding |
| --- | --- |
| Rejected current resources and collection completion | A decoded, scoped response with a known current-resource identity may preserve its actual incomplete-observation time without admitting its malformed values or HTTP bytes. A complete marker uses admitted receipt clocks, so older retries cannot borrow the newer rejected time. Issue aggregation is constrained to the active repository, Source and job; completion excludes partial-marker times. Cancellation, stale attempts, scope mismatches and unrecognized responses do not invent observations. |
| Current proof versus hardened historical proof | `historical_page_boundaries` runs inside the surviving legacy complete-proof branch. Current-resource page proof, partial assertions and the existing no-new-fetch 304 branch retain their distinct handling. A typed current-only thread child can prove its own empty terminal collection; a rawless historical root cannot borrow that exception. A partial GraphQL root's raw/receipt cursor disagreement is accepted only with checked, nonquarantined exact bytes containing actual errors and a nonterminal receipt. This is validation of the temporary historical boundary, not its replacement or a new API replay feature. |
| Exchange cleanup versus domain partialness | The no-seed return occurs after deleting obsolete derived barriers and preserving pending profile/fact selection barriers. It skips graph propagation that cannot produce a barrier without a conflict seed. It does not delete Coverage candidates or turn an incomplete current collection into complete proof. Positive conflict propagation remains intact. |
| Sparse fields and producer versions | Source NULL and selected-key NULL retain their existing clear/invalid semantics; a present object without the selected key omits the normalized field. New extraction is version 2. Omitted values retain real version 1 field evidence, while new body/clear assertions carry version 2. Provider clock ordering remains independent of parser version. Prior-version collection receipts cause an actual rescan rather than version 2 falsely claiming their production. |
| Publication indexes and schema composition | All seven result-led indexes are composed into the same packaged DDL used by initialization and runtime. `ParserModel.publish_result` explicitly orders its typed member output, so different index traversal order cannot change the publication seal. The interpreted-name partial index excludes local names without a result; no publication, ownership or selection rule changed. |

No unresolved implementation interaction was found in these reviewed production
changes. They correct existing identity/presence/clock/proof contracts or avoid
unnecessary scans; they do not settle historical retention, permanent publication
identity, normalized collection schema, cache policy, checkpoint lifetime,
Exchange trust or physical deletion.

## Independently executed integrated checks

Fresh composed schema 19 initialization passed with DDL SHA-256
`d0fba8d577ffad700b17a7504f67228c375a00c16583e1d1c6a7eef7e12c9415`:
103 ordinary tables, 665 columns including generated columns, 226 FK constraints,
48 views, 498 triggers and 113 explicit indexes. The seven added indexes are the
only change in those object counts. The fingerprint equals the actual composed
SQL hash; generated JSON guards exactly equal the packaged SQL.
`PRAGMA foreign_key_check` returned no rows and `PRAGMA integrity_check` returned
`ok`. These are fresh structural checks, not behavioral acceptance of every
view/trigger or a final certificate check.

The independent
[combined interaction probe](prototypes/independent_integrated_exchange.py)
executed actual current acquisition, durable receipt/completeness handling,
Coverage, `Graph.export`, repeated and reversed `Graph.receive`, and no-conflict
barrier refresh. Both sender and receiver obtained exactly:

| Actual observation and operation | Expected and observed receiver state |
| --- | --- |
| Empty terminal acquisition at 100 | Complete at 100 |
| New acquisition: committed empty prefix at 150, identifiable rejected resource at 200; reverse and repeat Exchange | Partial at 200 |
| No-seed barrier refresh, replay older complete unit, restart with valid terminal retry observed at 175 | Partial at 200 |
| Fresh valid empty acquisition at 300; reverse and repeat Exchange | Complete at 300 |

Sender acquisition retained no `stored_bytes`, `payloads`, `fetch_occurrences`,
source inputs or unresolved/staged payloads; the receiver had no fetch occurrences.
Receiver FK and
integrity checks passed. The probe used the frozen version 2 production source
and no `REPO_CATALOG_TEST_BOOTSTRAP` override. It does not benchmark performance,
exercise every historical family or replace the separate adversarial suites.

The focused integrated provenance selection passed **37 cases without
bootstrap**: 20 author, 16 nested live/import and one changed-parser rescan.
Two older-complete cross-endpoint cases failed only at
`BUILTIN_VERIFICATION_STALE` when entering the retained historical thread
publisher; rerunning just those two with explicit development bootstrap passed.
Both runs, failures and exact node IDs are recorded in the same JSON. They cover
retained version 1 author/parent/OID evidence through version 2 sparse updates
and explicit clears, live/import admission, and older complete responses filling
unknown fields without replacing newer fields. The earlier
[independent correction review](independent-correction-review.json) contains the
larger isolated exact-commit challenge runs and VM-operation measurements; those
remain development evidence, not final integrated acceptance.

To reproduce the interaction and structural checks, select the implementation
checkout explicitly and supply a fresh disposable directory:

```sh
env -u REPO_CATALOG_TEST_BOOTSTRAP PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/absolute/implementation/src:/absolute/implementation \
  python docs/phase2/prototypes/independent_integrated_exchange.py \
    --source-root /absolute/implementation \
    --state-dir /absolute/new-disposable-directory \
    --output /absolute/receipt.json
```

The helper deliberately imports implementation regression fixtures. Run it only
against a checkout containing the integrated corrections; its declared source
root must match the actual imported module. It rejects a source revision that
changes during execution.

## Findings and final acceptance limits

**Resolved provenance finding:** keeping `PARSER_VERSION = "1"` after changing
the field-presence interpretation would blur two actual producer versions. The
integrated version 2 correction addresses this without rewriting older imported
or inherited evidence. The package test now reads the producer from the isolated
installed package, compares it with the submitted source, and asserts that actual
producer in live and received rows. Cross-version test seeds explicitly declare
versions 1 and 2 instead of depending on the current constant.

**Resolved recorder test finding:** the lead reported one
failure in the first complete bootstrap run: the parser branch of
`test_recorder_failure_preserves_actual_parser_and_storage_errors` expected zero
completion markers for a scoped canonical Issue with malformed body. Independent
source review confirms that this rejected first page legitimately produces only
reason/scope/actual-time partial evidence. A committed prefix is unnecessary:
`test_phase1_retirement.py` already tests a new failed historical collection with
zero fetch occurrences and a newer partial/conflicting Coverage candidate. The
recorder regression must preserve its original parser/storage exception and
recorder-failure assertions, assert the exact partial marker in the parser case,
and retain zero markers in the storage-error case. Neither case may admit
rejected originals, current values or successful page receipts. This finding
does not authorize relaxing source identification or recording routine transport
errors as domain observations. The reviewer inspected the resulting
`47be2fd780f0a5278d950d0053cde9ac6fb6f196` diff: the real transport clock is fixed
at 200; the parser case checks one exactly scoped `partial`/`API_SCHEMA` marker
and partial Coverage at 200, while the storage case checks zero markers. Both
preserve the original errors, recorder diagnostic and zero raw/current admission.
Both corrected cases passed independently without bootstrap; the exact rerun
and node IDs are recorded in the receipt.

The retained historical builtin certificate binds changed source hashes. The
reviewed source is consequently not a final no-bootstrap acceptance tree until
the lead regenerates the artifact from successful tests of the exact frozen
definition and executes final ordinary and isolated wheel/sdist acceptance.
Hosted CI must match the submitted HEAD. No final full-suite, installed-package,
hosted CI or certificate-success claim is made by this document. No PR was merged.
