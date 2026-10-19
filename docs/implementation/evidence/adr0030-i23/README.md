# ADR 0030 I2 + I3 integration acceptance evidence

Draft PR [#110](https://github.com/TakashiSasaki/git-repo-db/pull/110) stacks on
I2 #109 and preserves I3 #108 as the second merge parent. No original PR branch
or main was rewritten or merged. This is bounded I2/I3 development acceptance,
**not full release acceptance or completed I4**. The registry remains failed
because its existing P6 failures are visible.

## Source, ancestry and evidence binding

[coordinates.json](coordinates.json) records complete SHAs and trees:

| Coordinate | Commit | Tree |
| --- | --- | --- |
| I1 / actual merge-base | `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | `14c694218109de1e3dfebc93e7776d48ad79faf3` |
| I2 / first merge parent | `9b8a6ad9b761bf23b45eda9f84d639569cee56ef` | `7c461c633c137086537158385feb03a1b79d7dfe` |
| I3 / second merge parent | `5c5b816998f7051703ca400e8cfeab377254c435` | `a4c0ea69a0cf5f31b6ffcdaba918b52de1ed6c91` |
| Two-parent merge, zero text conflicts | `6dccd3c3bc4919975117a9cea80818936f2b9a5e` | `269c3eec3598e8eb1cf63a70b80a67ce2eb26104` |
| Reviewed runtime correction | `c20d41cba4f229a93cd750b2f5fe1b1e986f45e9` | `9316c83fcde284cf44f8586ad4b36e6a32ce6f97` |
| Final source, including supplementary fixture repair | `6d50ba22f4b3092516bce004de4611a1a5bd566d` | `476ee24311a78efa3048b301ea598f22fb13bc45` |

The earlier temporary `ae6287b8cf91d1b8efa772fb46763bcbd9325076` is prior evidence
only. `git merge-tree --write-tree I2 I3` independently reproduced the merge tree.
All three parent commits remain ancestors. The start snapshots `pr-107.json`,
`pr-108.json`, `pr-109.json` include live HEAD/tree/base/state/CI; all matched the
owner's pins, were open Drafts, and had successful offline / failed registry
checks. [end-refs.json](end-refs.json) rechecks Git remote refs and PR states.
Main remains `6780088befd33e711230d570bb291edb2ee40cbf`.

[source-binding.json](source-binding.json) binds the two complete local registry
runs to c20d41c. [final-source-binding.json](final-source-binding.json) binds
packaging and final hosted source to 6d50ba2. Exactly two of 420 recorded inputs
changed: supplementary compatibility tests outside the 2,069-node cohort.
[cohort-input-binding.json](cohort-input-binding.json) verifies every runtime,
build, workflow/lock and selected test input stayed equal. It does **not** assert
that all 420 inputs, complete Git trees or sdist bytes stayed equal. The changed
tests and all supplementary nodes ran on committed 6d50ba2. Later evidence/skill
changes have no runtime/cohort/build-script change and must remain separately
identified rather than presented as another test execution.

## Actual results

| Executed scope | Runtime | Selected | Passed | Failed | Errors | Skipped |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Complete registry cohort, local | Python 3.12.14 / SQLite 3.53.1 | 2,069 | 2,042 | 27 | 0 | 0 |
| Same cohort, local actual minimum | Python 3.13.5 / SQLite 3.51.3 | 2,069 | 2,042 | 27 | 0 | 0 |
| Disjoint supplementary P1 + P5/P6 compatibility | Python 3.13.5 / SQLite 3.51.3 | 234 | 234 | 0 | 0 | 0 |
| **Unique expanded minimum-runtime scope** | SQLite 3.51.3 | **2,303** | **2,276** | **27** | **0** | **0** |
| Final-source hosted registry | Python 3.12.15 / SQLite 3.51.3 | 2,069 | 2,042 | 27 | 0 | 0 |

The minimum source ID is actually queried, not a version override:
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
The official sqlite3.c SHA3-256 was verified before compiling. The other local
runtime is explicitly the newer embedded SQLite; LD_LIBRARY_PATH is not claimed
to replace its static binding.

Primary successful groups: unit 456, Access 483, I1/P1 selected 150, I2 48,
I3 66, I23 34, P2 197, P3 80, P4 202, P5 48, P6 23, P7 255. Supplementary
P1 contributes 205 and P5/P6 compatibility contributes 29, disjoint from primary
node IDs. The full expanded P1 selection therefore contains 355 passing nodes.

Both local cohort runs and the supplementary run reconcile actual collection,
JUnit, journal starts and exactly-once setup/call/teardown Counters; finish and
process codes agree. Hosted artifacts contain collection and JUnit but no phase
journal: exactly-once selected/JUnit reconciliation is verified there without a
claim about independently recorded hosted phases. Commands, process receipts,
full JUnit, journals and logs are retained under `raw/` with deterministic gzip.
See [local-results.json](local-results.json),
[sqlite3513-results.json](sqlite3513-results.json),
[supplemental-results.json](supplemental-results.json), and
[combined-results.json](combined-results.json).

### Original five P5 Exchange nodes

All original names and their final behavioral assertions are retained. Each
passes locally in both bindings, in the independent focused suite, and in the
final-source hosted registry:

| Original node in tests/integration/p5/test_exchange.py | Result |
| --- | --- |
| test_exchange_export_import_repeat_reverse_and_multi_hop | PASS |
| test_exchange_selective_filters_and_partial_input | PASS |
| test_exchange_refuses_intrinsic_spoofing_without_validated_bytes | PASS |
| test_exchange_refuses_tampered_payloads_without_store_corruption | PASS |
| test_exchange_evaluates_core_dependencies_against_receiver_core | PASS |

The sixth direct I3 node also passes. Explicit independent R/O/C selection,
permissions, Operational initialization and request continuation replace old
implicit calls. Rehashed, exact-v4 tampering reaches native-integrity, text-digest
and retention-purpose checks. No skip, xfail, deleted test, v3 compatibility or
retired relationship API was introduced. Supplementary stale I2 argument fixes
preserve every original behavior assertion.

### New actual I2 to I3 tests and security controls

The 34 I23 nodes use actual I2 native Provider normalization and I3 v4 reception.
They preserve Issue owning / PR base/head, native ID namespaces, exact Mapping
support, competing claims, receiver-local Disposition evaluation, genuine Transfer
EventReportKeys, one/two-sided/null/unresolved/missing/selection omission, original
clocks/provenance, Source/Coverage, typed Core OIDs and Notes/Capture. Actual Access
settings and grants stay unchanged and their credential-reference canaries are
absent from the wire. The latest unresolved Provider owner stays unresolved even
while an older materialized Core-target row remains present.

I3's 66 executed counterexamples additionally retain complete Coverage/Transfer
units, exact ClaimKey times and Disposition/replacement references, independent
selection/permission and Source/Provider bounds, global PackageKey/digest binding,
SQL mutation guards, concurrent binding, real process exits between domain commits
and checkpoints, Operational-loss issuance, empty-package budget enforcement,
receiver Notes/native checks and P7 Stop. P1/P3/Access/P7 cohorts preserve existing
Core and access invariants. These are process/transaction tests, not host power-loss
or unsigned Provider authenticity guarantees.

### Remaining failures, with no masking

The **same exact 27 P6 nodes** fail in both local registry runs and final-source
hosted JUnit. Each contains a retired `Context.admit_repository()` setup call;
the primary query/search path is not reached. The full inventory and I4 owner /
resolution are in the result JSONs. There are no additional failing nodes in the
expanded tested scope. I4 must replace fixture admission and implement qualified
Query/Search/Backup behavior; the old API is not restored here.

Pytest exits 1. The Access acceptance audit also refuses a receipt containing
failed nodes. That is an honest failed acceptance gate, not another runtime test
failure and not a green result. Existing CI selections were kept; I23 was added.
Packaging and audits now run after a failed pytest step so their actual results
remain reviewable. No continue-on-error or expected-failure allowlist was added.

## Actual final-source hosted CI

[Registry run 39280209622](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39280209622),
job `118152806024`, ran on feature 6d50ba2. Checkout/test merge
`02804e9359ab8e1e0d0f496b76e573e4d97c327d` has the feature tree
`476ee24311a78efa3048b301ea598f22fb13bc45`.

The actual completed log and artifact `12201120483` prove execution despite
run/job metadata snapshots still reporting queued. Downloaded ZIP length
39,182,912 and SHA-256
`7a26ea0bb6487472b1e6e069a5a88dd0a86bfb0f810ae4866a1e10df205ecc38`
match the log's actual upload digest. Its source archive matches all 420 final
recorded input hashes. Its actual collection/JUnit node multiset, exact 27-failure
inventory, runtime source ID and wheel/sdist receipts were independently checked.
See [hosted-results.json](hosted-results.json) and retained raw receipts.
The 39 MB archive and executable binaries stay outside Git; selected small
receipts and their verified archive digest are retained here.

[Offline run 39280209580](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39280209580)
has a digest-verified bounded log receipt with all 21 index members checked.
It is `development_checks_passed`, `full_acceptance=false`, **zero executed pytest
nodes**, and its own runtime SQLite 3.45.1. It is static/development evidence,
not the minimum-runtime test run. No green development badge is substituted for
the separately failed registry. Direct cloud artifact redirection returned 403;
the authorized GitHub artifact-download connector supplied a reusable file
reference. No network policy was bypassed and temporary signed URLs are excluded.

## Distribution and static checks

[distribution-final.json](distribution-final.json) and its execution receipt bind
clean `git archive` source 6d50ba2 to two separately installed environments outside
the checkout, using `-I`, actual package origins and no httpx. Both direct-wheel
and sdist-derived-wheel smokes pass on SQLite 3.51.3, including actual I2 to I3
cross-seed intake, GraphQL Node Transfer identity, 19 Context tables/UDFs,
registration guards and Access/native/backup controls. The final-source hosted
job independently executes the same two installations and both pass.

- Direct wheel and rebuilt wheel SHA-256:
  `bee593057a73ca669756e68c09a9516c0721295a512fd179bb593144a215f9da`.
- Final-source sdist SHA-256:
  `68b9b933d35480a922b3ee8041465dcc6aa2ef221bd9e2b624808005c0e3062c`.
- Composed Context fingerprint:
  `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`.

[final-audits.json](final-audits.json) records exit 0 for full Ruff lint and
format, composed schema/fingerprint, P1 disposition, Context registration,
callsite and implementation-boundary audits. Hosted schema/registration/callsite/
boundary checks and hosted formatting pass too. Earlier rejected-source and
interrupted/bootstrap attempts are labeled as such in raw evidence; a literal
glob bootstrap ran no tests, and a review-triggered interrupted run's 997 passes
are not complete acceptance. The supplementary pre-fix run's five stale fixture
failures are retained rather than relabeled.

## Independent review and I4 handoff

[Initial independent review](initial-independent-review.md) rejected actual pushed
6b595ca. It independently ran 173 focused tests, then reproduced 12 additional
counterexamples exposing three High findings. The implementation added executable
regressions and corrected typed subtype preflight, primitive affinity and complete
Coverage dependency/order handling.

[Final independent source review](independent-review.md) closes R1/R2/R3 and reports
no unresolved blocking finding in this I2/I3 scope. The reviewer independently
ran **196 focused + 23 external counterexample/positive controls** on actual SQLite
3.51.3, plus **29 compatibility tests** on archived pushed 6d50ba2. It separately
reconciled implementer local/minimum/supplementary and actual hosted raw evidence;
it does not claim to have independently rerun all 2,303 nodes or packaging.
Original scripts and reviewer logs/JUnit/reconciliation checks are retained.

[The implementation handoff](../../adr0030-i23-integration.md) fixes I4's interfaces:
use `provider_repository_roles()` with actual receiver evidence for current roles;
preserve direct Mapping/Disposition keys, Provider scopes and EventReportKeys;
use independent `ExchangeSelectionScope` and explicit Repository permission;
preserve original request accounting, Package Binding/stage checkpoints and P7
Stop. Do not infer current ownership from old Core-target rows, transplant Access
or introduce a Witness/history authority. Query/Search/Backup integration and the
27 P6 failures remain I4 work.

Recommended dependency: **#107 -> #109 -> #110**; #110 already contains #108's
complete history. A separate #108 merge is unnecessary for ancestry, and any
alternative order needs a fresh effective-tree check. Retarget stacked children
only after separately authorized parent merges. No main merge is performed here.

Applied repository skills: efficient-repository-investigation,
ci-final-tree-verification, three-store-invariants and lessons-to-skills; the
managed cloud runtime skill governed environment/network setup. The existing
Context/Exchange lesson was updated with the independently reproduced subtype
and Coverage failures. The CI skill records the verified status/log/artifact
retrieval discrepancy. Neither lesson grants new policy or execution authority.
`index.json` binds every retained evidence file except itself, including compressed
and uncompressed SHA-256/length pairs. Reproduction commands are retained in
`reproduce/`; their absolute workspace/interpreter paths identify actual runs and
must be adapted deliberately in a different environment.
