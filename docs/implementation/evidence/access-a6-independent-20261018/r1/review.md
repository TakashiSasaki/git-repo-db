# R1 independent Access identity, SQL, time and history review

Status: independent static review and runtime matrix complete. No defect was reproduced in the reviewed R1 scope and no product source was changed.

Reviewer: R1, a separately invoked read-only reviewer, not the author of the reviewed implementation. Start: 2026-10-18 12:35:33 JST. End: 2026-10-18 12:39:32 JST.

Reviewed checkout: `/workspace/access-review-ro`, commit `f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60`, tree `a7b4521fb7fa6562c8e0bf67e2766743e0b82c5b`. Initial `git status --short` was empty. The review covers the cumulative Access registry/settings/backup implementation, not merely PR #102's final delta. Remote PR/ancestry/CI pinning is owned by the coordinator and is not independently claimed by this report.

## Scope and authority

Read the repository-wide `AGENTS.md`, ADR index/policy, the full ADR 0003, ADRs 0017/0028/0029, Access design, A1 contract, A1a/A1b/A2a/A5/A6 implementation reports and ADR replacement ledger. Used repo-local skills `three-store-invariants`, `ci-final-tree-verification`, `adr-workflow`, `lessons-to-skills`, including the Access consent, expiry and backup references. These are procedures, not additional approval authority.

The analysis distinguishes the default Catalog3 Schema 21 runtime from explicit Access schema 2. The reviewed Linux implementation stores SSH/HTTPS settings but does not implement remote execution. Core Repository UUIDs, Access Scope UUIDs, registration facts, current controls and local permissions retain different meanings.

## Static disposition and source references

No defect was reproduced in the R1 scope. The following source assertions were also exercised by the independent runtime matrix where described below:

| Concern | Source | Semantic assessment |
| --- | --- | --- |
| All ten table PKs and composite references | `src/repo_catalog/adapters/sqlite/access_ddl/registry.sql:2`, `connections.sql:2` | Scope and repository bindings use the required domain identities; controls/grants refer to the full registration triple. There is no storage-only registration surrogate, separate history or mutable current-route pointer. |
| Same scoped repository locator | `connections.sql:7`, `access_connections.py:151` | PK `(scope_uuidv4,locator_text)` permits one current Repository UUID. API creation conflicts rather than silently rebinding; explicit CAS rebinding removes the former preference before UPDATE. |
| Original-time replay/history | `access_registry.py:196`, `access_registry.py:233` | Exact replay returns before touching controls; new registrations preserve caller coordinates. History keyset is descending original time then ascending URI. Multi-call pages do not promise a pinned snapshot. |
| Rank before permission | `registry.sql:27`, `access_connections.py:290` | MAX is computed over all registrations. Same-time alternatives are retained or refused by an explicit result bound; default selection reports ambiguity before evaluating controls/grants. |
| Clock regression/type/range | `domain/access_registry.py:43`, `access_registry.py:202` | API requires exact positive Python `int` within int64; a lower original time is retained with `precedes_latest`. SQL affinity validates stored values, not the original Python/JSON input type. |
| ABA permission invalidation | `connections.sql:98`, `access_connections.py:151` | Material scope-context/profile/binding/assignment/control changes delete affected grants in the same transaction. No-op/label edits are distinct controls. |
| Full local-grant subject/content | `connections.sql:43`, `connections.sql:135`, `access_connections.py:367` | Assignment/purpose, actual Repository binding and full registration key are matched, with exact canonical options/context. SQL validity does not prove a human approved. |
| Read validation before joins | `access_connections.py:81`, `access_schema.py:143` | Complete snapshot domain/FK validation precedes selection, preventing a dangling parent from silently disappearing in an inner join. |
| Inactive restore/history continuity | `access_backup.py:547` | Original rows are retained; grant rows are forbidden in artifacts and restore disables route controls before publication. Restore does not register historical URIs at receipt time. |
| Independent Scope fork | `access_backup.py:590`, `application/access_maintenance.py:31` | New explicit registration only, copied current settings disabled, original history untouched; normal application measures a genuinely new time. Explicit typed adapter administration is not an old-data migration tool. |

## Independent reproduction packet

`independent_matrix.py` was written outside the checkout without importing any existing test fixture/helper. It exercises real typed APIs and trusted infrastructure SQL against synthetic data only. Each matrix entry writes its actual observations into `independent-matrix.json` and binds interpreter, source import path, SQLite version/source ID, commit/tree and dirty state.

The prepared matrix covers direct PK/FK inspection, A10/B20/A30 plus lower-time insertion and a same-time alternative, one-row history pagination, disabled newest/no fallback, exact replay after lost controls, CAS rebinding R0→R1→R0 and independent S2 binding, eight grant ABA targets, no-op/label preservation, direct SQL immutability/FK/preference attacks, concurrent replay, coherent Access backup/restore, inactive restore replay and fresh-Scope fork history. Invalid API times include NULL, bool, float, numeric text, zero, negative and overflow with positive int64 endpoint controls.

Actual execution at 2026-10-18 12:39:09 JST passed all **9 matrix groups**, with exit status 0, empty stderr and no skips. These are independent script groups, not pytest test-case counts. The reviewed source remained clean before and after. Python 3.13.5 loaded the reviewed `access_schema.py` from `/workspace/access-review-ro/src/` and actual SQLite **3.51.3** with source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`. The coordinator owns the official SQLite source-build/hash-verification evidence; this script independently queried the loaded runtime.

Reproduction command, from `/workspace/access-review-ro`:

```sh
env LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 /workspace/access-review-ro/.venv-minimum/bin/python /workspace/access-review-evidence/r1/independent_matrix.py
```

Result evidence: `independent-matrix.json`, `independent-matrix.stdout.txt`, `independent-matrix.stderr.txt`. The JSON preserves all ten table PKs and actual FK rows, observed history/default states, every ABA outcome, direct SQL rejection messages, concurrent replay results, unchanged source and restored/fork history, invalid-time controls and script SHA-256. No minimum-runtime spoofing, product monkeypatch, network-guard change or existing test helper was used.

The matrix is not a substitute for the coordinator's full focused cohort, installed distributions or CI. No original user repository, real catalog, backup or credential is an input.

## Gate disposition and limits

Implementation consistency and independent review within the bounded R1 scope pass, subject to the explicit unexecuted boundaries below. This is not approval of the whole Access stack. Whole ADR 0003 replacement acceptance, merge permission and release eligibility are distinct owner gates; this review does not accept or delete any ADR, switch the normal CLI/P8, merge or deploy.

Other reviewers own Git command/FD boundaries, Context/Exchange multi-repository semantics, packaging/CI and the 26-item assertion map. This reviewer has not performed a power-loss test, hostile privileged-writer test, distributed fencing check or real-data extraction/migration.

## Reusable skills

Existing Access skill references already explain composite registration replay, ABA revocation, rank-before-permission and restore/fork history. No new verified general lesson is yet established; no skill edit is recommended merely to duplicate those procedures. The coordinator may add a lesson if independent runtime work exposes a new generalizable failure.
