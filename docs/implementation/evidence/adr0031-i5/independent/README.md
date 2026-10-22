# ADR 0031 I5 independent review publication

**限定I5独立レビューPASS**, limited to the Typed Transfer Admission implementation reviewed in
[PR #129](https://github.com/TakashiSasaki/git-repo-db/pull/129). Product implementation findings:
**0**. Unresolved review findings:
- Three **Medium** boundary contract findings deferred to I6 Wire (**I5-A1**, **I5-B1**, **I5-C1**).
- Two **Low** observation findings verified PASS / mitigated (**I5-D1**, **I5-F1**).
- Two open carryovers: **I4-E1** (Low evidence-scope) and **Task G G-R1** (Medium candidate scoping).

Whole-product and whole-ADR acceptance remain NOT READY.

Read the [independent review report](REPORT.md), [machine summary](summary.json),
[findings register](findings.json), [all-79 baseline comparison](failure-classification.json),
[Git blob comparison](blob-comparison.json), [sdist input scope](sdist-input-scope.json),
and [publication binding](publication-binding.json).

This review publication is authorized on branch `review/adr0031-i5-independent-20261022` stacked on top of PR #129. Neither PR #129 nor its implementation branch (`impl/adr0031-i5-typed-admission-20261022`) is modified. No product/test code, accepted ADR, original Author evidence, or earlier report is changed.

## Execution and publication identity

- Base #128 HEAD: `2003a9ee4f25907bcf96a634980b8caffc133c4e`, tree `7a662517644541c3c321a111b9325e97ea5667a8`.
- Author executed HEAD: `3a749541fe4c41eb72e7ded9f36528f0abeb05ff`, tree `6a494efb510713dbfb3cebf6ef5ff85e703e0d18`.
- Reviewed public product and independent execution HEAD: `99e40c9af91f9ea36dd3d4ba97eccad46f6c6e14`, tree `d2d69b3094c8e07e375fc357e979ed8131bf39c5`.

The [publication binding](publication-binding.json) records source/copy hashes.
The reviewed runtime/wheel inputs are unchanged. Full sdist/source archives gain these review files and therefore acquire new input sets; do not claim complete sdist-input identity for this publication. I4-E1 remains open in the Author packet and is not silently resolved by this separate review.

## Independently executed results

Both actual SQLite 3.51.3 and 3.53.1 engines were verified:
- 15 / 15 reviewer-designed independent counterexamples PASSED.
- 29 / 29 I5 focused admission tests PASSED.
- 217 / 217 I4 focused SQL tests PASSED.
- 301 / 301 SQL diagnostic groups PASSED with 8 poison nodes restored.
- Broad regression suite: 3,137 collected, 3,058 passed, 59 call failures, 20 setup errors, exit 1.
- All 79 inherited baseline failures matched exactly (45 Transfer call, 20 Transfer setup, 14 I6 Wire call; 0 added, 0 resolved).

Fresh direct and sdist-derived wheels installed outside checkout on both engines pass 29/29 I5, 217/217 I4, and 15/15 counterexamples in all 4 combinations. Access smoke exits 1 at Transfer preflight; distribution orchestration exits 1. Both product Transfer fences remain active.

## Portable evidence

- [Evidence ZIP](independent-evidence.zip): **1,757,961 bytes**, SHA-256 `a8208c0cdb61ba7df1e59195af2c2e5005c34fbeb96e1f4ff3ff9513f866a0c9`.
- [Payload index](artifact-index.json): 124 indexed payload entries. Every length and hash reverified.
- [Artifact binding](artifacts.json): binds archive and report hashes.
- Frozen report SHA-256: `8fce9f19a2621e540dc709378dbc12268580c58bda363344091588b0a0d2db20`.

The ZIP contains exact reviewer scripts, counterexamples, runtime/source measurements, raw pytest/XML/journals, diagnostic receipts, installed-wheel logs, and build/exit evidence. Excluded bulky virtual environments and tarballs are explicitly indexed as omitted.

Transfer fences remain active in product DDL. I6 Wire admission, I7 Recovery reconciliation (including Task G G-R1), and I8 Query/Search remain separate mandatory obligations before Transfer operations can be integrated. This review PR authorizes no merge, release, deployment, P8, or real Provider/catalog operation.
