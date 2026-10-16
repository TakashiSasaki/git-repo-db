# P4 independent review and verification

Final executable reviewed: `b7000705fbf396f8297309d332aa6b61880f4da5`, tree
`501f7ca965c0b361819e8ba2b3f5154c7d45c061`. The later documentation/evidence
commit preserves every executable/packaging/schema/test input at that revision;
the [receipt](p4-execution-evidence.json) records their exact SHA-256 values.
Review agents were read-only, independently inspected executable source and
constructed counterexamples. None authored its reviewed implementation. These
are local independent reviews, not GitHub approvals or Release Acceptance.

## Findings and exact corrected revalidation

| Finding | Reproduced failure and root cause | Correction and regression | Final status |
| --- | --- | --- | --- |
| B1 | Persisted invalid UTF-8 in inventory TEXT raised raw SQLite error, no stop, later write succeeded. New inventory reader lacked trusted decode boundary. | `_decoded_read` on direct typed inventory (also protects projection caller); both formats/direct+projection regressions. | Independently closed at final executable |
| B2 | Supported coordinator SQL committed forged receiver-intrinsic known-empty without structural evidence; next read poisoned sound catalog. Only Python admission rechecked proof. | Actual full-Capture joined `notes_inventory_guard` + native UDF, shared decoder, valid/forged/report/limit callback matrix. | Independently closed at final executable |
| B3 | Bounded 20KB deeply nested damaged stored provenance escaped via RecursionError; no stop and later write succeeded. `_stored` omitted decoder recursion failure. | Trusted stored-value guard catches RecursionError; direct/projection × both formats publish persistent stop before output. | Independently closed at final executable |
| C1 | Deleting work rows refunded exhausted request to zero; deleting discovery allocation minted new Capture on retry. Presence-only validation ignored detectable partial loss. | Mandatory atomic checkpoint for rows/totals/budgets/attempts/allocators/exact progress; supported progress APIs; live/reopen loss regressions and no false Core stop. | Independently closed at final executable |
| C2 / I-01 | Core A retained body while unrelated Operational B/request paid. Optional identity/scope conventions were unenforced by app. | Mandatory actual Core/Operational/catalog/local-source/intent and work-progress binding; external Capture attribution preserved separately. | Resource and integration reviewers independently closed |
| C3 | Every reservation SQL trigger SUM scanned all earlier work, despite cached Python checkpoint checks. VM work grew 310→16,308 at 0→2,000 rows. | Operational cached `spent_or_reserved`, atomic O(1) insert/settle/delete triggers, overflow-safe subtraction, independent resume reconciliation; real VM-work regression. | Independent original probe is constant 326 at all five history sizes |

Integration also identified an import-order lint failure (I-02), corrected before
final validation; full Ruff check and format now pass.

All six material findings were reproduced by the author, corrected, given
committed regressions and independently revalidated. The initial C2 and I-01 are
the same defect, not two distinct corrections. No unresolved material finding
remains. An early accounting-agent suspicion about SQLite int64 comparison was
disproved by its counterexample and was not claimed as a defect; the final cache
arithmetic still has explicit int64 boundary tests.

## Independent execution (overlapping selections, never summed as unique coverage)

| Reviewer | Final exact-source verification | Result |
| --- | --- | --- |
| A — native/proof | Final inventory/proof/output tests | 56 unique passed, zero failures/errors/skips |
| A — source-identical native inputs | 88 real-Git adversaries, 21 nomination checks, both-format promisor-object Git traces | Passed; no fetch; actual native/proof/app input blobs identical to already reviewed corrected source |
| B — database/domain | P4 + P2 + P1 Core | 470 unique passed, zero failures/errors/skips |
| B — independent adversaries | Corruption/callback/atomicity/replay 14; Operational counter/rollback/tamper 4 | 18 unique passed, zero failures/errors/skips |
| C — resources/failure | Complete production P4 suite | 202 unique passed, zero failures/errors/skips |
| C — independent probes | Live/reopen loss, discovery/cross-catalog refusal, SQL VM work, actual read lost-ack | Passed; uncertain input 129 remains charged, successful reopened retry cumulative input 451 |
| Integration | Compatibility 20 + installed variants 12 + P4 accounting/inventory 96 | 128 selected/started/JUnit identities exactly once; all phases passed |
| Integration — installed counter probe | Own wheel and wheel-from-sdist outside checkout | Both reserve 8→settle 3→reserve 7/final 10; overshoot and reopened retry refused; installed new column verified |
| Integration — pair/loss | Actual Git Notes + independent Context paired reads, then remove Operational | SHA-1 and SHA-256 preserve both authorities; old request cannot safely resume |

Independent installed budget probe built identical wheels from both distributions,
SHA-256 `cf0f8c4379b1bb7e649077e708d0f420e6553b85fd7dd7b7090636e72c69ee90`.
Independent integration Ruff/format (275 files) and all four required audits passed.
Raw independent JUnit/probe sources and integration receipt are retained under
[p4-evidence](p4-evidence/). The main author run separately executes **897 unique
nodes**, all passed, including 202 P4, 266 P1, 194 P2, 75 P3, 128 architecture
probes, 20 compatibility and 12 installed variants. Four inherited xunit2
record_property warnings do not alter test identities/outcomes; no test is skipped.

## Known inherited failures and verification limits

The independent reviewer reproduced exactly these five on unchanged main
`5e778bf61ef660f65bf5fb22bdb08840503b8464`, tree
`2c6eca80e6432a1b4f89a2111e7ded69c6b9a507`:

* `test_catalog3_git_runtime.py::test_interrupted_fixed_refs_resume_without_new_remote_observation` — `cache_leases`.
* `test_catalog3_model_cli.py::test_cli_retires_http_reparse_without_mutation_or_remote_observation` — `jobs`.
* `test_catalog3_portable_identity.py::test_no_usable_source_rejects_before_job_and_observation[None]` — `jobs`.
* `test_catalog3_portable_identity.py::test_no_usable_source_rejects_before_job_and_observation[first]` — `jobs`.
* `test_catalog3_queries.py::test_backup_restore_requires_absent_destination_without_removing_empty_dir` — `cache_locators`.

All paths are under `tests/integration/`. The baseline run collected/executed five,
passed zero, failed five, errored/skipped zero; exact selected/start/JUnit and three
phases reconcile. The receipt retains raw hashes, source binding and the initial
external CLI-shim harness error separately from the corrected reproduction.
They are outside the focused 897 selection and remain failed, not silently
reclassified or waived. No source/test was deleted, skipped or xfail'd for them.

The accepted local run is focused development verification. Hosted Development CI
runs selected inexpensive checks, not complete hosted runtime/packaging Release
Acceptance. Process SIGKILL and SQLite transaction/fault tests do not establish
host-power-loss, P7 recovery or activation. No real catalog, authenticated external
acquisition, main merge, deployment or release was performed.
