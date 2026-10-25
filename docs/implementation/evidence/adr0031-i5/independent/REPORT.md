# ADR 0031 I5 independent product review

**限定I5独立レビューPASS — bounded I5 typed admission only.** No Critical or High
I5 product defect exists in the runtime implementation. Product implementation
findings: **0**.
Three **Medium** boundary contract findings are identified and assigned to I6 Wire:
- **I5-A1**: Store admission lacks caller authorization checks (deferred to I6 Selective Exchange).
- **I5-B1**: Implicit parent evidence completion synthesizes event clock and causes false dependency failures.
- **I5-C1**: Endpoint declaration auto-synthesis masks wire truncation, admitting truncated events as genuine 1-sided transfers.

Two **Low** test/operational findings were independently evaluated:
- **I5-D1**: Author atomicity test only verified pre-flight checks; independent in-flight SQL trigger counterexample verified genuine SAVEPOINT rollback (**PASS**).
- **I5-F1**: `has_transfer_fence()` inspects only one trigger; mitigated by `Context._validate_schema()` checking full schema (**PASS**).

Two carryovers remain open:
- **I4-E1 (Low)**: Complete sdist inputs differ between Author execution tree and public tree due to post-execution evidence additions.
- **Task G G-R1 (Medium)**: Candidate global/scoped identity exposure deferred to ADR 0031 I7.

This review does not accept ADR 0031 as a whole, enable Transfer, drop Transfer fences
in product DDL, accept I6–I8, resolve G-R1, or authorize merge, publication, release or deployment.

## Fixed references and independence

Reviewed on 2026-10-22 UTC by an independent review agent separate from the implementation Author.
GitHub was confirmed prior to runtime testing and remained consistent at completion.
PR #129, base PR #128, and their respective branches remained open and unmerged at the specified heads.

| Reference | Commit | Tree |
| --- | --- | --- |
| Base #128 | `2003a9ee4f25907bcf96a634980b8caffc133c4e` | `7a662517644541c3c321a111b9325e97ea5667a8` |
| Author execution | `3a749541fe4c41eb72e7ded9f36528f0abeb05ff` | `6a494efb510713dbfb3cebf6ef5ff85e703e0d18` |
| Public HEAD & independent execution | `99e40c9af91f9ea36dd3d4ba97eccad46f6c6e14` | `d2d69b3094c8e07e375fc357e979ed8131bf39c5` |

Execution used a clean, detached worktree on branch `review/adr0031-i5-independent-20261022`
at public HEAD. No reviewed product code, test, branch, or PR was modified. Reviewer probes,
counterexamples, and test harnesses lived outside the checkout and are archived in
`independent-evidence.zip`. There was no real Provider, catalog, merge, release, or deployment
operation and no GitHub write.

### Blob comparison between Author executed tree and Public tree
Actual Git blob comparison between Author executed tree (`6a494efb510713dbfb3cebf6ef5ff85e703e0d18`)
and public tree (`d2d69b3094c8e07e375fc357e979ed8131bf39c5`) confirmed:
- Exactly 6 files differ (all in `docs/implementation/evidence/adr0031-i5/`).
- Exactly 445 runtime code, DDL, tests, and build inputs are bit-for-bit blob identical.
- As with I4-E1, the full sdist scope differs (77,620,267 bytes Author executed vs 80,846,880 bytes public tree) due to post-execution evidence additions, while runtime wheels are bit-identical (762,725 bytes, SHA-256 `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`).

## Author evidence independently checked

The published Author evidence ZIP at `docs/implementation/evidence/adr0031-i5/author-evidence.zip`
was independently inspected:
- Size: **3,305,637 bytes**
- SHA-256: `c83f97e6276ad9134adee02f7f73fd0af2df49db32414410a502e049aaf67f9b`
- Member entries: **138** payload entries matching `artifact-index.json`.
- All 138 member sizes and SHA-256 digests in `artifact-index.json` were reverified against the physical ZIP members with 0 discrepancies.

## Actual engines and newly executed cohorts

Two SQLite dynamic library engines were loaded and verified:

| Property | SQLite 3.51.3 | SQLite 3.53.1 |
| --- | --- | --- |
| Library Path | `/home/ubuntu/.local/share/git-repo-db-sqlite-3510300/lib/libsqlite3.so` | `/home/ubuntu/.local/share/git-repo-db-sqlite-3530100/lib/libsqlite3.so` |
| `sqlite_version()` | `3.51.3` | `3.53.1` |
| `sqlite_source_id()` | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |
| Context DDL Fingerprint | `924cc7557fb3da6211ea070185881f5fcaeff9bf52b6e237a361a238a2ea0c6e` | `924cc7557fb3da6211ea070185881f5fcaeff9bf52b6e237a361a238a2ea0c6e` |
| Deterministic UDFs | `validate_json`, `validate_resource_key_json`, `validate_resource_provenance_json` registered | Registered |

### Newly executed cohorts on each engine
On both engines, identical results were achieved:
- **I5 Focused Suite**: 29 / 29 passed.
- **I4 Focused Suite**: 217 / 217 passed.
- **Independent Counterexamples**: 15 / 15 passed.
- **SQL Diagnostic Groups**: 301 / 301 passed.
- **Broad Regression Suite**: 3,137 collected, 3,058 passed, 59 failed, 20 errors, exit 1.
- **Inherited 79 Baseline Failures**: Exactly preserved (45 Transfer call, 20 Transfer setup, 14 I6 Wire call; 0 added, 0 resolved).

## Focused疑義の検証 (Points A–F) and Independent Counterexamples

A dedicated test suite `test_independent_counterexamples.py` (15 tests) was constructed
and executed outside the checkout to evaluate the 6 focus areas:

### Point A: Selection / Permission & Trust Boundary (Finding I5-A1)
- **Investigation**: Inspected `admit_transfer_event(report)` in `p1_context.py`. The method validates structural integrity (`selection_truncated` and `omitted_roles`), but does not accept `selected_resources` or `permitted` callbacks, unlike `Context.relation()`.
- **Finding (I5-A1, Medium)**: An untrusted caller can submit a transfer report containing resources or repositories outside their permitted boundary. If DB dependencies exist, store admission accepts the report and inserts relations. Furthermore, exact replay returns `"duplicate"` without permission re-evaluation.
- **Boundary Contract**: Store admission is strictly a database invariant and dependency enforcer. Caller authorization and scope filtering MUST be performed by the caller (I6 Wire / Selective Exchange) before invoking store admission.

### Point B: Parent Evidence Implicit Completion & Clock Mismatch (Finding I5-B1)
- **Investigation**: `TransferEventReport.__post_init__()` synthesizes missing parent coordinates when `parent_report` is omitted, borrowing the event's `clock` and `provenance`.
- **Finding (I5-B1, Medium)**: If a legitimate parent report exists in `resource_relations` with an independent clock (e.g. Issue clock at 50, Event clock at 100), the synthesized scope query fails to locate the parent report in `resource_relations`, raising `ValueError: Missing dependency: eligible Parent report not found` despite the parent report's presence in the database.
- **Obligation**: I6 Wire and Acquisition layers must explicitly provide `parent_report` or exact parent coordinates rather than relying on implicit synthesis.

### Point C: Endpoint Declaration Auto-synthesis & Wire Truncation (Finding I5-C1)
- **Investigation**: When `endpoints=None`, `TransferEventReport` automatically synthesizes endpoint declarations from the passed `relations`.
- **Finding (I5-C1, Medium)**: If a 2-sided transfer loses one endpoint on the wire prior to constructing `TransferEventReport`, passing `endpoints=None` causes the object to declare only the 1 surviving endpoint. Store admission compares declared endpoints against relation endpoints; finding both equal to 1, it admits the truncated event as a legitimate 1-sided transfer.
- **Obligation**: The I6 Wire protocol must carry the provider's original declared endpoints explicitly and pass them as `endpoints=...` to `TransferEventReport`.

### Point D: In-Flight SQL SAVEPOINT Rollback & Atomicity (Finding I5-D1)
- **Investigation**: Author's test `test_atomicity_second_endpoint_failure_rolls_back` passed an unregistered repository UUID, which failed during Python pre-flight validation before `SAVEPOINT p1_transfer_event` and before any SQL statement was executed.
- **Independent Counterexample**: Injected a disposable `BEFORE INSERT` trigger on `resource_repository_relations` designed to fail only on the second endpoint insertion.
- **Result (PASS)**: Verified that the first endpoint was inserted, the second endpoint failed with `SQLITE_CONSTRAINT`, and the entire event cleanly rolled back to `p1_transfer_event`. 0 partial writes remained in `resource_relations` or `resource_repository_relations`.

### Point E: Provider Semantics & Staged Refusal Integration
- **Investigation**: Verified how `ContextStore.admit_transfer_event()` interacts with provider strings and whether stage fences protect ordinary access.
- **Result (PASS)**: Verified that non-transferred events are rejected with `ValueError`. When fences are active, ordinary access paths fail closed with `RuntimeError: Context transfer operations are staged and refused until ADR 0031 I5`.

### Point F: Asymmetric Fence Inspection (Finding I5-F1)
- **Investigation**: `has_transfer_fence(db)` only checks for `i2_transfer_stage_fence`, ignoring `i2_transfer_report_stage_fence`.
- **Result (PASS - Mitigated)**: Counterexample proved that if only `i2_transfer_stage_fence` is dropped, `has_transfer_fence()` returns `False`. However, `Context._validate_schema()` validates the full DDL against `expected_schema('context')`, detecting any dropped trigger with `UNSUPPORTED_SCHEMA`. Both triggers remain active in product code.

## Accepted ADR invariant audit

The 15 independent counterexamples verified key ADR 0031 invariants:
1. **U3=C' (Unique Semantic Parent Authority)**: Verified that parent relationship is determined strictly through `resource_relations` where `predicate = 'parent'`.
2. **U4=B (Child Independent Admission)**: Child resources can be admitted before parent resources, provided parent reports are admitted prior to transfer event support.
3. **B3 (Identity vs Semantic Parent Separation)**: Native resource identity remains independent of parent report references.
4. **G3=A & Permanent Disqualification of I8 Parent Reports**: An I8 parent report in `resource_relations` is permanently disqualified from serving as parent support for I7-native Transfer events. Attempting to use it raises `ValueError: Missing dependency: eligible Parent report not found`.
5. **Absence vs Dependency Error**: Missing parent report is cleanly reported as missing dependency (`ValueError`), distinguished from permission or malformed syntax.
6. **No Automatic Regeneration on Parent Arrival**: Admitting a parent report after a child transfer event has been rejected does not automatically admit or replay the rejected event.
7. **Preservation of Original Metadata**: Original `members`, `scope`, `clock`, `provenance`, and `observed_at_us` are preserved verbatim without truncation or alteration.
8. **Multiple Parents, Global/Scoped Documents**: Non-leaf documents and multiple parent references are handled cleanly without collision.
9. **Exact Replay vs Modified Payload**: Exact replay returns `"duplicate"` with 0 rows inserted; modified payload with identical key is rejected with `IntegrityError` / `UNIQUE constraint failed`.
10. **Pre-affinity Type Handling**: SQLite string/int/float/bool boundaries in JSON attributes were verified to preserve exact types across round-trips.

## Poison fixtures and 301 SQL diagnostic groups

The 301 diagnostic test groups from ADR 0031 I4 were re-executed against both SQLite 3.51.3 and 3.53.1:
- 301 / 301 passed on both engines.
- The 8 corruption / poison node guards were confirmed intact and properly restored after diagnostic execution.

## All 79 inherited first failures reconciliation

The broad regression suite was run on both engines (3,137 tests collected, 3,058 passed, 59 failed, 20 errors, exit 1).
Comparing the 79 failures against the final I4 baseline:
- **Retained**: Exactly 79.
- **Additional Failures**: 0.
- **Resolved Failures**: 0.
- **Breakdown**:
  - 45 Transfer call failures (`Context transfer operations are staged and refused`).
  - 20 Transfer setup errors (`Context transfer operations are staged and refused`).
  - 14 I6 Wire call failures (`'Context' object has no attribute 'transfer_summary'`).
- All 79 failure nodes, execution phases, and refusal exceptions match the baseline with 100% fidelity.

## Independent distribution execution and isolated verification

Wheels and source distributions were built and tested in 4 isolated virtual environments outside the repository checkout:

### Artifact Digests
- **Direct wheel**: 762,725 bytes, SHA-256 `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842` (bit-identical to Author wheel).
- **Sdist-derived wheel**: 762,725 bytes, SHA-256 `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842` (bit-identical to direct wheel).
- **Sdist archive**: 80,846,880 bytes, SHA-256 `009632d416c385e44f859341c4af0dd98dc7da5312fa36af902338b133ff7a02`.

### Isolated Environment Execution
In all 4 environments (direct wheel on 3.51.3 & 3.53.1, sdist wheel on 3.51.3 & 3.53.1):
- `tests/integration/p3/test_transfer_admission.py`: 29 / 29 passed.
- `tests/integration/p3/test_transfer_sql.py`: 217 / 217 passed.
- `test_independent_counterexamples.py`: 15 / 15 passed.
- I2 probe exited 0; I3 probe exited 0.
- Product Access smoke exited 1 (refused by stage fence at preflight).
- Distribution orchestration exited 1.

## Open Findings and Carryover Status

```
+-----------+----------+----------------------------------------------------------------------------------------+------------------------------------+
| ID        | Severity | Summary                                                                                | Status                             |
+-----------+----------+----------------------------------------------------------------------------------------+------------------------------------+
| I5-A1     | Medium   | Store admission lacks caller authorization checks; deferred to I6 Wire                 | OPEN_BOUNDARY_CONTRACT (I6 Wire)   |
| I5-B1     | Medium   | Implicit parent evidence completion synthesizes event clock and causes false dep error | OPEN_BOUNDARY_CONTRACT (I6 Wire)   |
| I5-C1     | Medium   | Endpoint declaration auto-synthesis masks wire truncation                              | OPEN_BOUNDARY_CONTRACT (I6 Wire)   |
| I5-D1     | Low      | Author atomicity test tested preflight check rather than SQL rollback                  | VERIFIED_PASS_BY_COUNTEREXAMPLE    |
| I5-F1     | Low      | Asymmetric fence trigger inspection in has_transfer_fence()                            | VERIFIED_MITIGATED_BY_FACADE       |
| I4-E1     | Low      | Complete sdist inputs differ between Author execution tree and public tree             | OPEN_CARRYOVER (Documentation)     |
| Task G    | Medium   | Candidate identity scoping deferred to ADR 0031 I7                                     | OPEN_CARRYOVER (ADR 0031 I7)       |
+-----------+----------+----------------------------------------------------------------------------------------+------------------------------------+
```

## Transfer Gate Entry Conditions and Subsequent Mandatory Work (I6 / I7 / I8)

### Gate Entry Conditions for Transfer Integrated Admission
1. Both product Transfer stage fences (`i2_transfer_stage_fence` and `i2_transfer_report_stage_fence`) MUST remain active until I6 Wire admission and I7 Recovery reconciliation are completed.
2. I6 Wire protocol must enforce selective caller authorization, explicit parent report conveyance, and explicit declared endpoints before invoking `admit_transfer_event()`.

### Mandatory Work Remaining
- **I6 Wire**: Wire protocol definition, selective transfer exchange authorization, explicit parent/endpoint transport.
- **I7 Recovery**: Task G G-R1 candidate scoping reconciliation, full journal recovery, rollback and backup invariants.
- **I8 Query / Search**: End-to-end multi-store query and faceted search integration.

## Evidence and reproduction

All test logs, receipts, XML reports, raw outputs, build logs, and counterexamples are permanently
archived in `independent-evidence.zip`:
- Size: **1,757,961 bytes**
- SHA-256: `a8208c0cdb61ba7df1e59195af2c2e5005c34fbeb96e1f4ff3ff9513f866a0c9`
- 124 indexed payload entries matching `artifact-index.json`.
