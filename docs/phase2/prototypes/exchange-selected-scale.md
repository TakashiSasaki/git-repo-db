# Supplemental large selected Exchange evidence

This supplement closes the Phase 2 investigation's large selected-graph evidence
gap. The earlier Exchange probe grew unrelated catalog rows while exporting one
repository record. The 10,000-child completeness workload exercised a proposal
validator. Neither measured a large selected production Exchange closure.

[The new probe](exchange_selected_scale.py) uses the production Schema 19
`Graph`, `ParserModel`, exact terminal proof, Coverage and CAS adapters. Its
[machine receipt](exchange-selected-scale-evidence.json) records actual SQL/VM
counts, record composition, intake outcomes and all production file hashes.
It changes no production sources, DDL or owner policies. Normalized publication,
completeness, Exchange trust, lifecycles and physical retention remain pending.

## Frozen execution

The operation-count run tested source HEAD
`5d4d73a00478fba1c2ca698ffbf062dbc57e140f`, tree
`09eced22e54bb1c6bd083a09663b33b1c4019c5b`, on Python 3.12.14 / SQLite 3.53.1.
Active Schema 19's composed SHA-256 is
`d0fba8d577ffad700b17a7504f67228c375a00c16583e1d1c6a7eef7e12c9415`.
The probe SHA-256 is
`c325026e2f4989c802181f8555f14d7ff816940798c3721860ea9c9ea1151f58`.
The receipt is separate from the subsequent docs-only evidence commit.

```sh
env -u REPO_CATALOG_TEST_BOOTSTRAP PYTHONDONTWRITEBYTECODE=1 \
  uv run --no-sync python docs/phase2/prototypes/exchange_selected_scale.py \
  --state-dir /tmp/git-repo-db-selected-exchange-new --sizes 64 256 1024
```

The actual run used `/workspace/p2-design/.venv/bin/python` with the probe's own
checkout explicitly selecting all production and fixture imports. It refused
bootstrap overrides, required a new state directory, and checked source revision
and hashes before/after execution. Other focused work could run concurrently;
no elapsed-time or CPU-time measurement or comparative timing claim is made.

## Workloads and counterexamples

At each scale N, the historical fixture creates N distinct natural comments,
N typed collection memberships, N page inputs and N sealed exact output
publications. The first page is observed at -1, later pages at their ordinals;
0..N-1 is contiguous and only the final page is terminal. The complete claim
uses the unchanged five-column contract and actual maximum time N-1.

Full, single-fetch, half-fetch and collection-selective exports are exercised.
The single-fetch graph has exactly 23 records at every size. Half-fetch exports
retain N/2 actual comments/publications and omit complete markers/claims.
Reverse full intake and repeat intake converge without duplicates. A half-prefix
is committed and reopened; a full unit missing its final fetch and output cannot
admit complete Coverage. Five dependent records remain staged. Later delivery
restores exact full graph equality, complete Coverage at N-1, and empty staging.
Receiver-local parser trust is absent in both full and restarted receivers.
The fixture's custom verification is synthetic; this is not production parser
acquisition or provider-authenticity evidence.

The Git fixture creates N verified blob identities, half SHA-1 and half SHA-256,
sharing N/2 exact physical bodies. Reverse/repeat intake converges. Omitting half
the bodies keeps logical identity/ownership available while required raw-object
mappings stage. Reopening and supplying only the missing body records promotes
the same identities and clears staging. Every final format/OID/type/size is
independently recomputed from raw bytes; the physical CAS scan finds no corruption.
All source/full/restarted catalogs have no FK violations and `integrity_check=ok`.

| N | Historical full records | Historical export SQL / VM estimate | Historical reversed receive SQL / VM estimate | Git full records | Git export SQL / VM estimate |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 660 | 10,145 / 189,000 | 56,135 / 1,612,700 | 259 | 3,283 / 53,500 |
| 256 | 2,580 | 38,369 / 723,400 | 216,263 / 6,165,600 | 1,027 | 11,923 / 192,500 |
| 1,024 | 10,260 | 151,265 / 2,863,300 | 856,775 / 24,390,900 | 4,099 | 46,483 / 747,000 |

These sampled full closures show approximately linear operation-count growth.
VM counts use progress callbacks every 100 opcodes; SQL includes triggers and
savepoints. The receipt records every operation, including repeated intake,
selective prefix and late promotion; these are not universal complexity bounds.

## Newly measured selective overhead

Single-fetch output remains 23 records, but SQL work grows
2,349 → 7,533 → 28,269 as N grows 64 → 256 → 1,024.
[`Graph.export`](../../../src/repo_catalog/adapters/sqlite/exchange.py)
first calls `required_original_keys(local_original_context(repository_uuidv4))`.
That context begins with all selected-repository historical domain facts and
complete markers; acquisition selectors apply later in `_export`. Thus keyed
selective expansion still pays for the selected repository's original-eligibility
context. The previous unrelated-repository bounds remain valid. This is an
existing linear overhead, not evidence of quadratic proof construction.

Narrowing that context is a possible contract-preserving optimization, but merely
filtering it by fetch is insufficient proof: proof-only/empty collections, 304,
multi-input results, DAG heads and rejected-original gates require exact closure.
No production optimization is implemented or claimed by this supplement.

## Independent review and remaining limits

An independent reviewer inspected the fixture, exact record comparisons,
terminal/missing-output failure, restart paths, raw Git checks and Source-settings
boundary. Their two evidence corrections were applied: startup now rejects any
inherited bootstrap variable, and both receivers explicitly verify no local
trust import. The bootstrap rejection exited 2 without creating a state directory.

Two initial size-2 draft checks failed because whole-record equality included
receiver-local Source settings and because the draft expected missing bytes to
prevent logical Git identity admission. The fixture now leaves Source settings
unconfigured and checks the actual staged raw mappings. A size-2 smoke passed,
then the frozen scale run above passed without bootstrap. These draft assertion
failures are not production bugs or passing evidence.

Reordered/repeated/selective/incomplete/late and SHA-1/SHA-256 scenarios here
supplement existing ordinary tests. Unordered current conflicts remain exercised
by `test_catalog3_current_exchange.py` and `test_current_exchange_followup.py`.
Physical corruption/quarantine, repair rollback/process death and CAS-41 service
backup/restore remain covered by `test_catalog3_cas_integrity.py` and
`tests/e2e/test_backup.py`; this probe does not claim to rerun that service lifecycle.
The read-only recheck verified all 175 Exchange/CAS cases in the successful
test-efficiency ordinary JUnit receipt, with no scenario test removal or production
changes from its Schema 19 base. Final integrated/hosted acceptance is recorded
separately by the submitting agent.
