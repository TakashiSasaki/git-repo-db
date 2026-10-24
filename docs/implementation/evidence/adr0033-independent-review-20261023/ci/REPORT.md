# Independent CI and evidence review for ADR 0033

Responsibility: Task A CI subreview agent, independently inspecting the implementation;
no production changes were authored or changed. Parent reviewer owns the integrated
review decision. Outcome for this scope: no blocking CI defect demonstrated; one
Low advisory (`A-CI-01`) distinguishes runtime acceptance identity from the complete
sdist source identity. See [findings.json](findings.json) and its executable probe.

## Pinned identity and reviews

GitHub metadata was freshly read on 2026-10-23 UTC. PR #138 is open and Draft,
authored by `TakashiSasaki`, base `docs/adr0033-minimal-sdist-20261022`
`18ba867d1c2f33c7d17939b2722d22a67139363a`, head
`impl/adr0033-minimal-sdist-20261022`
`8cd89a3d25c811ee32d117ec32fe76a6022e6d94`.
Feature tree is `0f42e9d0e498e249bc2cc02f6b96df9ef87106a0`.
Actual merge ref `18f1a890c18a8aee5b4b52238b520d7444c5776f` has exactly those base
and feature parents and the identical feature tree. Merge-base is the accepted
base `18ba867d1c2f33c7d17939b2722d22a67139363a`. REST reviews returned `[]`;
no formal review is hidden by a successful badge. Parent reviewer separately
checked review PR duplication; #137 is preparation, not completed review.

## Actual hosted results, not release acceptance

| Run | Observed result | Verified execution scope |
| --- | --- | --- |
| [tests 39873626172](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39873626172) | offline and sqlite-policy success | Latest evidence-only synchronization: zero pytest nodes, `development_checks_passed`, `full_acceptance=false`; sdist gate correctly `not_applicable` for that delta |
| [tests 39872269754](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39872269754) | success | Frozen executable source `03e1192f5228c9a1ca40dcef88271419c6828874`, test merge `142f45ceae01603fe4a939399dffcb7ed4c1254c`, tree `b5bdcb3cf5361a339ecdcea496c9ee32d1ab61ce`; sdist gate selected and passed; zero pytest, no full acceptance |
| [Access 39873626305](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39873626305) | registry-runtime failure | Broad 3,058 pass / 59 fail / 20 setup errors preserved; original Access installed smoke exits 1 for both wheels at `I2_TRANSFER_UNSUPPORTED`; contract/equivalence checks passed |
| [Pages 39873626245](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39873626245) | build-and-validate success; deploy skipped | Checkout-based actual docs build, safety/link validation, 8 unit tests passed; no deploy performed by this review |

The initial gate receipt reports 677,902 compressed bytes, 5,921,698 unpacked
bytes, 159 members and 155 product inputs, with fixed 2 MiB / 8 MiB / 512
budgets. Its archive SHA is
`c72f86709f360b306daa1d39e2854e910f773e6acfce9f4bec7dae3396012e21`.
These are independently retrieved hosted observations, not a local rebuild by
this subreview. The parent reviewer is responsible for independent builds/tests.

The latest Access receipt includes the existing 79-node comparison with zero
additional and zero resolved failures, matching node identity, phase, refusal and
trace path/function sequences. This subreview verified its bytes/index and read
the actual failing logs; it does not substitute that Author-run comparison for
parent's independent regression execution. Four P5 packaging failures remain
visible in the focused hosted cohort and are not skip/xfail replacements.

`03e1192...` to `8cd89a3...` adds only the six Author evidence files. No claim
that latest development ran the older lightweight gate again is made.

## Receipt verification

`gh run view RUN --log` returned exit 0 but empty output for all three latest
runs. `gh api repos/TakashiSasaki/git-repo-db/actions/runs/RUN/logs` returned
actual log ZIPs successfully. The independent stdlib parser
[inspect_hosted_logs.py](inspect_hosted_logs.py) reads ZIPs in memory, takes the
aggregate job logs, checks actual BEGIN/DATA/END blocks, strict base64 decoding,
expected byte length/SHA-256, duplicate-free receipt ZIP paths and **every**
indexed payload's bytes and hash. It asserts current feature merge/tree binding.
The earlier frozen gate was parsed with the same algorithm and its separate
binding retained; it is not misattributed to the latest tree.

| Receipt | ZIP bytes | SHA-256 | Verified indexed payloads |
| --- | ---: | --- | ---: |
| Latest tests | 70,943 | `bb77dfa5a7b0e8d7c791900b35b7f2503e61f5ec792de9402bb43f84618f0ee0` | 21 |
| Initial gate tests | 81,861 | `6d17db9a9958dc8add6c7921bc6766750fdd0fa5a7be7a36b50762c1a895b341` | 24 |
| Latest Access | 1,664,698 | `c7c7a81671b2e9efd57354166987a2f054f609f4cd3a9331f598f31646a4f52a` | 102 |

The Author's existing `raw-evidence.zip` external index was independently checked:
whole archive size/SHA and all 107 indexed payload sizes/hashes match. Existing
evidence was not changed. This verifies preservation/internal consistency, not
third-party authenticity. Supporting JSON is kept locally beside this report;
complete decoded original receipts remain in ZIPs. Log convenience views omit
only redundant base64 DATA lines and are named accordingly. Raw run-log ZIPs
remain outside Git. Sanitization checks found no real credentials or signed
artifact links. The two URL `token=` matches are literal tracked synthetic test
parameters (`test_access_registry_values.py:104`,
`test_access_connections_values.py:43`), not private data.

## Static CI and builder audit

- `tests.yml:59-64` runs the lightweight source/hash/budget checker after locked
  dependency preparation; `ci_plan.py:449-453` selects it for changed sdist inputs,
  uncertain diffs and explicit release plans. Selection does not automatically
  expand hosted pytest. `ci_execute.py:1408` requires a successful, identity-bound
  `sdist_contract` profile when selected, and rejects unexpected profiles for
  unselected lanes. Gate reconstruction verifies preparation selection.
- New checker, builder, test-support and workflow paths are shared inputs and
  hashed; `sdist_inputs` covers package source/data, metadata, lockfile, license
  names, checker/planner, distribution builders and packaging tests. README's
  deliberate prose exclusion is the Low advisory, not a demonstrated bypass.
- Both generic/P1 distribution fixtures and Access/I4/I5 distribution builders
  call `check_sdist` before tar extraction and `compare_wheels` afterward.
  The lock/atomic-publish `build_once` adds both sdist and contract to its exact
  required product keys and hashes them before/after cache publication. It does
  not trust a stale `ready.json` with changed artifacts. No implementation was
  altered by this review.
- Direct wheel build uses Hatchling's explicit wheel target; sdist-wheel build
  runs separately under extracted Git-free input. I2/I3 distribution scripts are
  installed behavior probes, not unchecked distribution builders.
- Product subtree and SQLite safety predicates are unchanged. Workflows retain
  environment-loaded SQLite identity, offline product/network boundaries and
  failure exits. No SQLite setup/version swap, full release dispatch or guard
  relaxation occurred in this subreview.
- Pages workflow, docs builder and MkDocs configuration blobs are identical to
  the accepted base (`pages-unchanged-inputs.json`). Checkout plus existing
  explicit `stage_documentation` allowlist (builder lines 220-408) remains the
  source. No sdist docs path, publication expansion or deployment was added.

## Reproduce and limits

From the frozen checkout, using an existing Python, run:

```sh
python docs/implementation/evidence/adr0033-independent-review-20261023/ci/probe_readme_binding.py
# exit 0: asserts the advisory counterexample; disposable Git repository only.
gh api repos/TakashiSasaki/git-repo-db/pulls/138/reviews
# exit 0, observed [].
gh api repos/TakashiSasaki/git-repo-db/actions/runs/39873626172/logs > /tmp/adr0033-tests-logs.zip
gh api repos/TakashiSasaki/git-repo-db/actions/runs/39873626305/logs > /tmp/adr0033-access-logs.zip
gh api repos/TakashiSasaki/git-repo-db/actions/runs/39873626245/logs > /tmp/adr0033-pages-logs.zip
python docs/implementation/evidence/adr0033-independent-review-20261023/ci/inspect_hosted_logs.py /absolute/new-output
# exit 0: actual log and all receipt payload checks above.
```

All metadata/log REST reads, receipt checks and counterexample executions reported
here completed with exit 0. An exploratory `python -c 'import pytest'` failed
with ModuleNotFoundError in the bare selected interpreter; this agent did not
install dependencies or claim a pytest run. Parent handles locked test setup.
This subreview did not rerun product pytest, a local docs build, installed
behavior or complete release qualification. No hosted workflow was dispatched.
No remaining action is denied, pending or uncertain; publication is owned by the
parent. The only suggested follow-up in this scope is clearer/dedicated sdist
input identity, preserving accepted runtime acceptance semantics.
