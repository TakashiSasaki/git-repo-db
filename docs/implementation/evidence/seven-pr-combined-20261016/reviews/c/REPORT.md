# Independent review C — combined-tree security and recovery

Decision: **APPROVED_FOR_OWNER_REVIEW within this scope; no new integration blocker**.

Reviewed synthetic commit: `388b824d1b3abe41c902759bf37a52c6ee5bcd2f`.
Exact effective tree: `ea006924152d2fc508c7eb21697ad3c376e373f6`.
Detached worktree: `/workspace/review-c`; clean tracked state throughout execution.
This reviewer authored no production code in the reviewed changes and modified
no source, feature branch or repository documentation.

## Scope and evidence inspected

Read repository AGENTS, the ADR index and relevant scoped decisions (especially
0003/0014, 0025–0028), the final-tree and three-store repository Skills, the P7
hardening evidence README and prior independent C report, and the Schema 21 final
evidence README. The P7 executable baseline is `178ddbaa8fa06f52aff4993730205c5a38da91f4`;
its historical failing full run and environmental limitations remain historical.
Documentation-only evidence commits are not additional executions.

Differential inspection found exactly one production file changed from the P7
executable baseline: `src/repo_catalog/adapters/sqlite/index.py` (17 added/8 removed
lines). All remaining 123 production inputs, including packaged P1 DDL, corruption
stops, request accounting, recovery admission/validation, coordination and WAL
preservation code, are unchanged. The complete P7 test subtree is unchanged.
`production-inputs.json` independently records every one of the 124 source/resource
input blobs and SHA-256 values at the reviewed combined commit.

## Security and integration findings

- Corruption stop: persistent stop and its completion fencing have no combined
  production delta. Regression coverage verifies normal operations remain stopped,
  reconstructible-store damage alone does not declare authority corrupt, and
  restart/lost Operational state does not reset authority. The independent probe
  deletes both derivatives after stopping and confirms ordinary backup refuses.
- Recovery budgets: the durable request/checkpoint/registry implementation is
  unchanged. Executed regression cases cover real SIGKILL reservation cuts,
  same-request process contention, lost/damaged accounting, fixed request contracts,
  typed versions and conservative settlement. No new reset or budget authority was
  added through Search.
- Typed replay: all captured identity/native bytes/notes-role and exact-evidence
  replay regressions in `test_exact_replay.py` pass. The independent combined-tree
  probe merges the stopped source into its fresh restored baseline: 3 candidates,
  0 admitted, 1 replayed and 2 qualified observations, with input complete.
  Context observations are not promoted into unsupported authority.
- WAL preservation: the existing process suite executes real uncheckpointed Core
  and Context WAL commits, proves actual units are absent from base-only immutable
  reads, and exercises forensic copying and writer gates. Its unchanged nodes pass
  against the combined tree. This is process/WAL evidence, not host-power-loss proof.
- Activation: P7 calls `p1_init` for reconstructible stores and reports
  `search_derivative_state="initialized_empty"`; it does not invoke the public
  Schema 21 `index.rebuild`. Independent probing replaced all three changed public
  Search entry points with functions that raise, then successfully executed paired
  backup, persistent stop, salvage, restore, replay and activation. Preexisting junk
  derivatives in the fresh target were replaced; the activated Search connection
  verified exact packaged P1 schema, passed integrity_check and had zero documents.
  The suspect source remained stopped and authority file hashes were unchanged by
  salvage. Activation publication fault-stage regressions also pass.
- Public Search changes modify disposable Search projection selection/pruning.
  They add no Core/Context writes, recovery bypass, implicit ATTACH, migration,
  receiver-local verification promotion or Publication authority. Schema 21 legacy
  quarantine behavior remains a separate public baseline; the combination does not
  silently wire that policy into opt-in P7.

## Executed validation

Own locked development/documentation environment: `/workspace/review-c/.venv`.
Python 3.12.14, SQLite 3.53.1, Linux 6.18.44 x86_64/glibc 2.41.
Temporary files used `/workspace/tmp-review-c` on workspace overlay (32 GiB,
approximately 30 GiB available before execution); the 8.8 GiB `/tmp` tmpfs was not
used. Exact commands and outcomes appear in `receipt.json` and dependencies in
`dependencies.json`; actual main-process import origins are in the probe receipt.

Focused execution: **84 passed / 0 failed / 0 errors / 0 skipped, exit 0**,
33.97 seconds under concurrent root work (not a comparative benchmark). This covers
`test_corruption_stop.py`, `test_exact_replay.py`, `test_durable_budget.py`,
`test_process_isolation.py`, and `test_safe_activation.py`.

Independent reconciliation establishes duplicate-free exact set equality among
84 collected IDs, 84 JUnit identities and 84 journal starts, with exactly one
successful setup/call/teardown record per node (252 phase records). The four
independent integration probes passed on attempt 4, exit 0.

Earlier probe attempts remain preserved: attempt 1 used an unsupported GitCore
context-manager protocol; attempt 2 used raw SQLite without required native UDFs;
attempt 3 incorrectly assumed P1 lacked a table named search_documents. These were
review-harness errors, not implementation defects. Each version and stderr is
retained; only the executed corrected attempt establishes the four probe results.

## Limits and authorization

This focused independent review does not substitute for the root complete suite,
all-255 P7 reconciliation, packaging verification or hosted receipts. It approves
no production code authored by this reviewer. Existing unsupported NFS/Windows,
privileged namespace mutation, malicious wholesale accounting removal and actual
host-power-loss cases are not newly verified. Full Context salvage, complete Search
projection rebuilding from empty P7 derivatives and public P8 activation remain
outside the implemented claim. No live catalog, real backup, production activation,
PR merge, release, tag or deployment was touched. Owner merge authorization remains
pending independently of this engineering conclusion.
