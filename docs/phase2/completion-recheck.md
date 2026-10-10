# Phase 2 completion recheck

This is a corrective evidence audit of the original Phase 2 assignment and the
later test-efficiency work. The integrated replacement design remains **Proposed /
Pending Owner Decision**. This recheck does not approve a lifecycle, publication
identity, completeness schema, cache/checkpoint policy, retained-field vocabulary,
Exchange trust rule, retention period or deletion policy.

## Rechecked baseline

Main was fetched again on 2026-10-10 and remains
`20e0f8d78b77c6c8d37826fd6d639819631e166b` (Schema 18).
The open, unmerged stack is:

| PR | Base | Submitted head | Actual hosted acceptance |
| --- | --- | --- | --- |
| [#22](https://github.com/TakashiSasaki/git-repo-db/pull/22) investigation/proposal | main | `e5f7ff386b77627490a400f0a7e29d3989a9a532` | [38038819100](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38038819100): 1,724 ordinary + 2 package cases |
| [#23](https://github.com/TakashiSasaki/git-repo-db/pull/23) determined corrections | #22 | `162581dfcfb501311d4993e90cdd160fb64d6e35` | [38039756971](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38039756971): 1,921 ordinary + 2 package cases |
| [#24](https://github.com/TakashiSasaki/git-repo-db/pull/24) test efficiency | #23 | `52a36cab26f2287591ff9296cac151fe135cc55a` | [38042315927](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38042315927): 1,941 ordinary + 2 package cases |

Each run completed successfully and reconciled selected tests without missing or
excluded files. PR #24's actual checkout is the synthetic merge
`1878f9112f1e152996931476f7e82d628e6134d3`, with the same effective tree
`5cb8c86f91c8a7c9a05b34e88df857cb3d1b618b` as its feature head.
The corrective runtime remains Schema 19: 103 tables, 665 columns, 226 FK
constraints, 48 views, 498 triggers and 113 explicit indexes. Schema 18 proposal
snapshots remain historical inputs, not the active Schema 19 fingerprint.

## Genuine omissions found and corrected

Passing the earlier checks did not establish that the investigation was complete.
Independent reviewers found these additional gaps:

1. **SQL reader inventory.** Both AST inventories recognized `execute`,
   `executemany` and `executescript` but omitted SQL supplied to `Store.one` and
   `Store.all`. That hid actual Issue eligibility, Source and decoder readers.
   The audit now includes these helper call sites, with regression coverage.
   Compilation and static references remain labeled separately from runtime
   reachability; dynamic SQL still requires the traced production paths.
2. **Typed current-field groups.** The 57 JSON columns were enumerated, but the
   current Issue/comment scalar identity, title/body/link, clock, ownership and
   capture groups lacked an explicit contract. The
   [typed current-field supplement](current-typed-field-contract.md) fills this
   gap and identifies actual producers, consumers, exactness and origins.
   Unknown provider remainders and event variants remain open Q09 work; the
   retained-field vocabulary is not described as closed or accepted.
3. **Large selected Exchange closure.** The earlier 4,096/12,000-object probes
   grew unrelated data while exporting an empty selected repository. Those prove
   isolation from unrelated growth, but do not measure a large selected closure.
   The new production-Graph probe grows selected domain/Git dependencies and
   checks full/selective transfer, reversed/repeated records and late dependency
   convergence. It records operation counts rather than concurrent wall times.
4. **Candidate assertion and receipt precision.** The newer-partial case now
   checks partial state before adding an equal-time contradiction. Presence
   checks use actual modeled cells/digests. Restart preserves a nonempty committed
   prefix with FK/recursive-trigger enforcement after reopen. New exact-file
   evidence supplements older candidate receipts; old fingerprints are preserved
   as historical checkpoints rather than presented as current checks.
5. **Current reproduction guidance.** A default field `--check` on Schema 19
   compared against the frozen Schema 18 artifact and failed. Current commands
   now generate/check a separate output; diagnostic guidance does not suggest
   overwriting the historical proposal inventory.

The acquisition reviewer found no missing promised restart implementation or
demonstrated runtime defect. Four additional saved merge/test-merge role cases
strengthen omission-versus-null evidence across catalog reopen: root observation
100 survives a child observation at 300, only the child is requested, and role
presence/completeness stays unchanged. This is additional path-specific coverage,
not evidence that the earlier real-prefix restart scenario was absent.

## Original scope disposition

| Original requirements | Rechecked deliverable and remaining boundary |
| --- | --- |
| §§1–5 mission, latest baseline, authority, target and invariants | Fresh remote main/guide, accepted ADRs and explicit proposal status; no identity/Coverage/CAS decision reopened |
| §6 A historical publication | [Publication trace](workstreams/publication.md), typed ownership/output responsibilities, concrete alternatives; production replacement waits for affected lifecycle/publication/selection decisions |
| §6 B completeness | [Completeness trace](workstreams/completeness.md), flat/nested prototypes, current receipt and selective closure cases; no partial collection proves complete |
| §6 C restart/304 | [Acquisition trace](workstreams/acquisition.md), real-prefix/root reopen, stale retries, conditional reuse and fencing/watermark cases; permanent cache/checkpoint ownership remains proposed |
| §6 D fields | Original JSON registry/20 groups plus typed current-field supplement and expanded readers; unknown provider/event vocabulary remains explicitly undecided |
| §6 E Exchange/CAS | [Exchange trace](workstreams/exchange.md), Git SHA-1/SHA-256, physical corruption/quarantine/CAS-41 and small/selective convergence; selected-volume evidence added by this correction |
| §7 machine dependency inventory | Exact composed schema/native keys/generated columns/SQL objects, JSON registries, CLI and AST inventories, conditional table dispositions; SQL helper omissions corrected, unresolved dynamic edges retained |
| §8 decisions | [Twelve concrete questions](decision-register.md), examples, alternatives, effects, dependencies, implementation blockers and four approval bundles |
| §9 integrated design | Tagged 69-table illustrative DDL, old/new responsibilities, reader predicates, transaction/restart boundaries and coordinated retirement graph; no unconditional DROP list |
| §10 independent review/prototypes | Separate worktrees, adversarial counterexamples and executable scenario evidence; candidate validator limitations remain explicit, selected-volume and final-receipt gaps corrected |
| §11 determined implementation | Schema 19 presence/clock/proof/Exchange/index fixes and test efficiency; this correction adds audits/characterization without new production semantics |
| §§12–14 PRs, verification, handoff | Explicit #22→#23→#24→supplement stack and actual source/tree/run evidence; complete final supplement acceptance belongs to its PR body |
| §15 completion standard | Substantial integrated proposal and independent safe implementation are delivered; complete transport-original retirement is a post-decision stride |
| Later test-efficiency request | [Actual measurements and isolation](../test-suite-efficiency.md), original behavioral coverage retained, two package processes, work stealing and native-Git fixture deduplication; single-pair measurements are not universal speed guarantees |

## Remaining owner decisions and implementation

The [decision register](decision-register.md#recommended-decision-order-and-implementation-impact)
still governs the shortest coherent post-approval sequence. The first substantial
domain step needs Q04 publication, Q05 membership/terminal proof, Q06 child/target
obligations, Q09 retained fields and explicit Q01/Q02 history choices for affected
families. Q07/Q12 decide acquisition/cache/restart. Q03 Source and Q08 Git/selection
can progress in parallel after their contracts are approved. Q10 determines
portable proof and attestation; Q11 covers physical layout without authorizing GC.

Removing the historical publication/profile/DAG machinery and mandatory HTTP
proof inputs before these choices would delete real facts, lose restart targets,
or grant false completeness. Those production strides remain pending. Missing
publication/current/Source/code/Git validators in the disposable sketch are stated
implementation limits; they are not silently called successful checks or accepted
semantics. A production-ready replacement prototype was not an original deliverable.

No merge, release, deployment, authenticated production collection, retained
catalog mutation or automatic retention/deletion is performed by this recheck.
Final corrective source SHA/tree, focused evidence, independent review and hosted
acceptance are recorded after execution in the supplement PR and its receipts.
