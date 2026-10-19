# I2 recovery and validation evidence

The tested/reviewed code target is HEAD
`3298dfbdc0428ba7ba13fd26331e97554119a74c`, tree
`28b53a862db969e3231bd1a6f08a0c7f20d22874`, on
`impl/adr-0030-i2-provider-intake-20261019`. Its base is frozen I1 #107 HEAD
`9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7`, tree
`14c694218109de1e3dfebc93e7776d48ad79faf3`.
The final evidence follow-up changes only documentation; PR #109 records its
exact final HEAD/tree and read-only follow-up review. `runtime-inputs.json` binds
all 415 tracked source/test/script/workflow/dependency inputs. The follow-up must
retain identical bytes for these inputs; it is not claimed as a fresh test run.

## Recovery

`recovery.json` identifies the six original uncommitted I2 files and patch hash.
They were backed up before editing and reused. No public I2 PR, remote branch,
I2 commit or stash was found. The recovered application was still I1-gated;
normalizers/qualified reads had not been integrated. No reset, overwrite of
another branch, force push or changes to PR #107/#108/main were performed.

## Local supported-runtime results

Python 3.12.14, actual SQLite 3.53.1; the exact SQLite source ID is recorded in
`local-results.json`. This is a supported newer runtime, not the 3.51.3 minimum.
The command is the registry workflow's full selected list with
`tests/integration/i2` added. Its exact selected/executed 1,969 unique nodes and
exceptions are preserved in `local-tests.xml.gz` and `local-tests.txt.gz`.

| Group | Passed | Failed | Resolution |
| --- | ---: | ---: | --- |
| Unit values | 456 | 0 | Covered |
| Access | 483 | 0 | Covered |
| I2 counterexamples | 48 | 0 | Covered |
| Selected P1 | 150 | 0 | Covered |
| P3 | 80 | 0 | Covered |
| P5 | 44 | 4 | Four direct I3 guards, below |
| P2 | 197 | 0 | Covered |
| P4 | 202 | 0 | Covered |
| P6 | 23 | 27 | I4 retired API migration |
| P7 | 255 | 0 | Covered |
| Total | 1,938 | 31 | Zero errors/skips in this selection |

The five requested acquisition nodes now pass:

- `test_repository_unknown_observation_retained_without_fabricated_coordinates`
- `test_core_first_context_second_and_failure_retry_convergence`
- `test_late_core_dependency_reconciliation`
- `test_issue_vs_pull_request_intake_isolation`
- `test_explicit_null_vs_missing_fields_and_clock_competition`

All original P5 Exchange cases remain. Acquisition setup succeeds for all five.
`test_exchange_selective_filters_and_partial_input` passes the existing
Context-excluding I1 Core path. The following four directly fail at Context
export with `UNSUPPORTED_UNTIL_I3`:

- `test_exchange_export_import_repeat_reverse_and_multi_hop`
- `test_exchange_refuses_intrinsic_spoofing_without_validated_bytes`
- `test_exchange_refuses_tampered_payloads_without_store_corruption`
- `test_exchange_evaluates_core_dependencies_against_receiver_core`

These are now directly observed Exchange boundaries; the historical pre-I2 five
failures stopped earlier in acquisition and did not observe I3. The 27 P6
failures still depend on retired `Context.admit_repository()`: 25 wrapped paired
admission failures and two direct AttributeErrors. `local-results.json` records
every failed node, its actual exception, owner stage and resolution condition.
The remaining count changes 37→31: five I2 failures fixed and one Core-only
Exchange setup now reaches its successful existing path. No skip, xfail,
deletion or legacy API restoration is used.

Ruff check and format check passed (380 files). Composed schema/fingerprints,
P1 schema reconciliation, Context registration, call-site dependencies and
implementation-boundary audits passed. The 19-table Context and six roles are
unchanged. A preliminary registry run was interrupted to close the independent
parent-alias finding; it is not counted as acceptance. The final 1,969-node run
above completed after that repair.

## Distribution and hosted CI

`distribution.json` and `distribution.txt.gz` record clean `git archive` source
builds of a wheel and an sdist-derived wheel, installed without dependencies in
separate environments outside checkout. Both installed smoke checks passed,
including native acquisition, I1 Core-only Exchange, Access backup and the new
I2 native-Repository/Issue/GraphQL Transfer path. Both Context DDL hashes match
and report 19 tables. The installed smoke's v3 Exchange field describes the
independent I1 Core-only check, not I3 acceptance. Artifact hashes are recorded.

- [Development offline run 39272835525](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39272835525): SUCCESS,
  `development_checks_passed`, `full_acceptance=false`, **0 pytest nodes**.
  `offline-receipts.zip` and `offline.json` retain the exact feature/merge/tree
  binding. Outer archive and all 21 indexed member hashes/lengths were verified.
- [Registry run 39272835668](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39272835668): **FAILURE**, actual Python
  3.12.15 / SQLite **3.51.3**, **1,938 passed / 31 failed**. The merge commit
  `4235232e3b1384a19caabc4ef91c4b7b2703025f` has the same tested feature tree.
  `hosted-registry.json` and compressed actual log preserve source ID and exact
  31-node failure-set equality with local results. Lint/format passed. Later
  workflow packaging/audit steps were skipped after pytest failed; the separate
  local checks above provide that evidence. Artifact download returned 403, so
  no unavailable artifact receipt is claimed.

PR #109 records CI for the final evidence-only HEAD as well. This is development
validation, not release acceptance or a claim that the extended registry is green.

## Independent review

`independent-review.md` records exact pushed-target PASS by
`/root/i2_contract_review`: 19 independently executed targeted cases passed
(29 deselected); all relevant audits passed; unresolved I2 blockers **0**.
The reviewer authored no production changes. Earlier original-support, generic
Transfer, event-type binding and contradictory parent-alias findings were fixed.
Final documentation/input equality review is recorded in PR #109 against its
exact final HEAD/tree.

## Separate I2/I3 combined-tree probe

No I3 implementation was merged into I2. A disposable detached worktree was built
with `git merge-tree --write-tree` from exact I2 above and I3 #108
`5c5b816998f7051703ca400e8cfeab377254c435` (tree
`a4c0ea69a0cf5f31b6ffcdaba918b52de1ed6c91`). There were no conflicts.
`joint-results.json` records both parents, local validation commit and combined
tree `ae6287b8cf91d1b8efa772fb46763bcbd9325076`. This local commit was not
pushed, did not change either sibling and grants no merge authorization.

The initial combined run had **115 passed / 8 failed**. All 48 I2 cases,
66 I3 cases and the I3 replacement of the direct I1 guard passed. Five failures
were the original P5 Exchange cases, now directly stopped by v4
`R/O/C:SELECTION_REQUIRED`. The other three were a new probe's erroneous expected
resource count (six versus the actual five: two Provider Repositories, Issue, PR,
Event). Correcting only that probe assertion produced **3 passed / 0 failed**.
Both initial failures and corrected results are retained; no production behavior
was changed to satisfy the probe.

The corrected `joint-handoff-test.py.txt` covers different receiver seed,
I2-produced PR base/head and Issue roles, exact Mapping ClaimKeys and dispositions,
complete supported Transfer reports, original clocks/provenance and Access absence.
Original facts and Provider-qualified results match after v4 exchange for no
disposition, withdrawal and dispute. Replay/permission/crash/Stop/budget coverage
also remains in the independent 66-case I3 suite.

To reproduce, create an isolated checkout of the two recorded parents' merge tree,
install its locked development environment, copy `joint-handoff-test.py.txt` to
`tests/integration/i2/test_joint_handoff.py`, then run:

```sh
python -m pytest -q tests/integration/i2 tests/integration/i3 tests/integration/p5/test_exchange.py
```

The original P5 fixtures still need integration work: explicitly nominate R/O/C
(or explicit `all_selected=True`), freeze allowed Repository UUIDs, use genuine
new-request coordinates/Operational state, and adapt mutations to the v4 row and
PackageKey/Digest contract while retaining every original behavior assertion.
A selective Core-only fixture should explicitly set R, O, empty C/Source selectors;
omitting C is distinct from an empty tuple even when Context is excluded.
After those prerequisites, execute every original scenario to discover any later
assertion mismatch; the present first failure does not prove later behavior.

**An I2+I3 integration PR can start.** Typed producer/consumer compatibility has
passed these probes; complete combined P5 acceptance is still required there.
I4 must adopt `provider_repository_roles()` for current affiliation, not infer a
current owner from older materialized Core-target rows after newer unresolved
Provider evidence. I4 Query/Search/Backup and P6 migration remain outside I2.
