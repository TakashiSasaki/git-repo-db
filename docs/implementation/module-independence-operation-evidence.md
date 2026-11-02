# Module independence operation evidence (prototype)

This is the bounded OP-01–12 closeout under [ADR 0037](../adr/0037-operation-scoped-module-independence.md),
[ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md) and the
[operation contract](../architecture/module-independence-contract.md). It is not
release acceptance, a normal Schema21 transition, or a claim that every Python
surface is independently distributable. Exact final candidate/CI identities are
recorded in the PR; artifact source equality is distinct from execution commit
identity. Raw logs, synthetic catalogs and authentication data remain private.

## Ordered implementation stack

All entries remain Draft, unmerged and without formal GitHub approval. Each
child targets the immediately preceding branch. Main remains
`c0fadd6e7827ef30bbeb3c34e5af655eddf3add4`.

| PR | Head | Scope |
| --- | --- | --- |
| [245](https://github.com/TakashiSasaki/git-repo-db/pull/245) | `a9a834e1ddc11d4b616d90fb878e17d4621603e8` | Context Resource enumeration/pagination |
| [246](https://github.com/TakashiSasaki/git-repo-db/pull/246) | `047f8800846dbe1e016b00e1700372e6050bb978` | Context Provider/Source/Coverage reads |
| [247](https://github.com/TakashiSasaki/git-repo-db/pull/247) | `73f42b1b3bdc375d6786f776e47df0ded8efd618` | Paired Query |
| [248](https://github.com/TakashiSasaki/git-repo-db/pull/248) | `a02c9ffef8af64d1ce16064661bcf83bed17eaaa` | Core/Context Search combinations |
| [249](https://github.com/TakashiSasaki/git-repo-db/pull/249) | `3ea623ce0c35b1a488bdd37e99d75a9839eea20c` | Durable Operational ownership |
| [250](https://github.com/TakashiSasaki/git-repo-db/pull/250) | `eba5a99baf006d7c7f291542504c2a866f282136` | Local/Access-approved Git acquisition |
| [251](https://github.com/TakashiSasaki/git-repo-db/pull/251) | `681fbc557c80d53c664db3d233321cb38e45388a` | Selective Exchange export/reception |
| This PR | Recorded in PR metadata | Paired Recovery and this operation audit |

## Operation verdicts and evidence bindings

C/T/A/O/S/G/X mean Core/Context/Access/Operational/Search/Git acquisition/Exchange.
Counts include runtime/contracts where required; A remains one distribution with
zero runtime dependencies. Core includes Git-only Recovery. Paired Query and
paired Recovery are explicit integrations, not requirements of the basic stores.
“Demonstrated” below is limited to the selected operation and supported local
POSIX/process-crash contract. It does not imply host power-loss qualification.

| Operation | Actual required installation | Technical verdict / evidence | Maintenance verdict |
| --- | --- | --- | --- |
| OP-01 initialize/read Core | C + runtime/contracts (3) | Demonstrated: current direct/derived Core consumer delta passed; typed API/CLI, optional absence, persistent/completion stop | Canonical C factory, admission and Query; no new feature dependency |
| OP-02 Git-only complete Recovery | C + runtime/contracts (3) | Demonstrated: current direct/derived lifecycle delta passed after shared cleanup/accounting fixes; refuses paired input, preserves opaque coexisting evidence, no O/S initialization | Recovery stays in C; shared lifecycle and external accounting have one owner |
| OP-03 Context-only reads | T + runtime/contracts (3) | Demonstrated: current direct/derived reader delta passed; Resource/text/relations, enumeration, Provider/Source/Coverage; no concrete C | T owns snapshots and qualifications; no mirrored C fact authority |
| OP-04 paired Query | C+T+paired Query + runtime/contracts (5) | Demonstrated: current direct/derived delta passed for changed loaded T/runtime inputs; identities, references, snapshots and CLI | One explicit pair integration; no O/S/G/X requirement |
| OP-05 Core Search | C+S + runtime/contracts (4) | Demonstrated: current direct/derived delta passed; older Search receipt loaded pre-249 p1_schema; authority scan/index verification remain required | S owns search and C adapter; basic C has no search engine |
| OP-06 Context Search | T+S + runtime/contracts (4) | Demonstrated: current direct/derived delta passed for changed T/runtime inputs; no concrete C | S owns T adapter; no invented unavailable Core verification |
| OP-07 Access management/backup | A (1) | Demonstrated: current A-only direct/derived delta passed; no implementation changes | Single self-contained owner, no shared-product runtime dependency |
| OP-08 explicit local Git | C+G+O + runtime/contracts (5) | Demonstrated by reviewed #250 direct/derived artifacts; current audit verifies every loaded origin against retained wheel and current source, unchanged G/O and dependency edges | One G orchestrator and durable O; no T/A/S requirement |
| OP-09 Access-approved Git | A+C+G+O + runtime/contracts (6) | Same qualified #250 reuse, including exact Access scope, frozen intent, revocation/ABA and CLI; not a fresh final-head execution | A stays optional to G and dependency-free itself |
| OP-10 Core export | C+X + runtime/contracts (4) | Demonstrated by reviewed #251 direct/derived minima; every loaded origin still byte-equal; no O/T/A/S/G/pair implementation | One X owner; O is a lazy reception capability |
| OP-11 Core reception | C+O+X + runtime/contracts (5) | Same qualified #251 reuse, including all-supplied/coexisting Context capability refusal, work/resend/conflict/checkpoint/loss; not a fresh final-head execution | X reuses canonical C/O and optional T/pair composition |
| OP-12 paired Recovery | C+T+O+S+paired Recovery + runtime/contracts (7) | Current direct/derived minima passed: 10 groups each, real WAL preservation, exact-Claim Notes, typed merge/replay, final accounting, truthful O/S activation | Three canonical paired files over C lifecycle; no A/G/X/rich or paired Query dependency |

The current operation delta passed 16/16 cases in244.24seconds on local
`7b8c5dc93b728dfb20b7f13e96b72775bba1ae89`, tree
`7f4d0dfd8daae5215e9712f0ac980887e088c126`: Core4, Context/composed4,
paired Query2, Search4 and Access2. These are manually selected actual results;
ALL_PASSED_UNVERIFIED_SELECTION is not relabeled as automated selection proof.
The published product commit `a7f473756eff9a04a06ac763bb7ffbe395c5e339` has
exactly that tree and base681fbc55; API-generated commit metadata differs from the
local execution identity. Terminal latest-head CI is recorded separately in the
PR. The initial OP-12 source cohort passed 133 nodes,
including durable crash/loss/concurrency, all-family baseline preflight,
capability refusal, owned-cleanup fences and paired activation. Pre-commit
profiles retain their actual `681fbc55` plus dirty marker; frozen wheel/sdist
member comparison binds actual artifacts separately, without relabeling runs.

Qualified reuse is explicit: retained G/X wheels and recorded installed origins
are hash-checked, then each loaded namespace member is compared to its current
single source owner. All four G sets and all four X sets have zero changed loaded
members. Core's Recovery files changed and its whole wheel hash therefore changes;
those files were not loaded in these operation consumers. G's older runtime wheel
also predates a neutral transaction-guard addition that it does not import.
Dependency metadata and current namespace ownership are checked independently.
Neither an unchanged package version nor a freshness token proves this reuse.

The older Search receipts do load changed p1_schema/Context files. They are not
silently reused as final proof: the bounded delta reruns both Search combinations,
Context, paired Query, Core, Access and the composed reader. This is selected
operation verification, not a combinatorial module/release matrix.

## Current OP-12 wheel binding

Direct and sdist-derived minimum wheel bytes agree. Artifact hashes bind actual
build outputs, not issuer authenticity or authorization to release them.

| Wheel | SHA-256 |
| --- | --- |
| `repo_catalog_context-0.2.0-py3-none-any.whl` | `f0c6d939904c140a8c828eddc59cb22f09ec5f27277aeaaeadcc21296c3a8ee0` |
| `repo_catalog_contracts-0.2.0-py3-none-any.whl` | `54b3d2596e1f82d56f19b0ec5eccb9370f6eb96c47118d5fbcd013a1ca8d3b27` |
| `repo_catalog_core-0.2.0-py3-none-any.whl` | `a9d476425e2dea46a1d1a00e5d3b82862f562e3f610babeab63e0295b3cc19d6` |
| `repo_catalog_operational-0.2.0-py3-none-any.whl` | `3d46da58cb428d3193e5d043b3f0268a3d3b725c3647eaf3c8da10109ab967bb` |
| `repo_catalog_paired_recovery-0.2.0-py3-none-any.whl` | `5fb22e54bd647f61942650e053353d9f5443701cd2fc14f42a38d48421f9fd6c` |
| `repo_catalog_runtime-0.2.0-py3-none-any.whl` | `d643f9d7d2ffba1045d053604d56abc434453f9021c19f8f6fb31be3e933a1f8` |
| `repo_catalog_search-0.2.0-py3-none-any.whl` | `92ad0ddd064dcd4120fd8be7976d764dd4a2371d4d2abd110211e7d6b05657e3` |

## Boundaries, failures and remaining work

- Normal `repo-catalog` still uses implemented Schema21. The opt-in namespace
  extraction changes no schema/format/default topology. Global ownership and
  dependency DAG checks cover every product; no duplicate installed file owner
  or mandatory reverse dependency is permitted.
- Context reads do not grant Context initialization/mutation/Recovery. Provider
  acquisition remains composed. Transfer and Parent refusal stages retain their
  intentional unsupported boundaries. Context resource salvage without supported
  typed reconciliation remains a qualified observation, not recovered authority.
- The inherited Transfer fixture failure was reproduced on its original base
  during #251 and remains excluded from that unrelated Exchange cohort. P7's
  two stale NotesLimits test imports are mechanically corrected to their canonical
  contracts owner here so the affected crash-settlement tests actually execute.
- Initial paired consumer failures were harness errors: automatic Core Query
  correctly refused without paired Query, and sqlite3.Row cannot be compared
  directly to a tuple. The final probe requests core_only explicitly and verifies
  original identities using normalized values. Product guards were preserved.
- CLI GitHub authentication later returned HTTP401. The independently connected
  GitHub app confirmed repository push authority; no token was read/replaced,
  interactive login started, or denied private artifact retried. Source execution
  remains in the selected environment. API publication produced a different
  commit metadata identity; exact tree equality and both identities are recorded.
- Review source replay of parent modules is labeled separately from an actual
  parent artifact installation. Earlier failed records and source bindings remain
  intact. No full test suite, release acceptance, extra SQLite/CPU matrix, live
  acquisition, real catalog, merge, approval or deployment is inferred.

The scoped delta and independent candidate/artifact review are closed. The PR
records final documentation and terminal CI closeout, after which implementation
stops for owner review. Remaining unsupported surfaces are
listed rather than expanded into new Provider/Transfer/Context-only campaigns.

Independent closeout: eight strict source comparisons retain parent positive
controls; fourteen installed challenges cover both seven-product Recovery sets.
The artifact audit verifies78unique files/96loaded origins/seven sdists and
unchanged four-store DDL. G/X reuse independently verifies all eight original
sets and316loaded files. The existing source ownership audit enumerates the full
namespace, while metadata traversal rejects dependency cycles and duplicate owners.
The root composed consumer resolves twelve products and preserves its existing
API/CLI. No approval or merge follows from those checks.
