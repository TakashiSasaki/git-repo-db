# Reviewer A — combined architecture and Git DAG

Verdict: **APPROVED_FOR_OWNER_REVIEW** for this review scope. New integration blockers: **0**. This is an independent engineering review, not merge authorization or Full Release Acceptance.

- Exact source commit: `388b824d1b3abe41c902759bf37a52c6ee5bcd2f`.
- Exact effective tree: `ea006924152d2fc508c7eb21697ad3c376e373f6`.
- Detached review worktree: `/workspace/review-a`.
- Reviewer authored none of the production changes under review, made no reviewed-tree edits, and did not merge, retarget, push, migrate, activate, release, or deploy anything.
- Read AGENTS, ADR index and scoped accepted boundaries, the required CI-final-tree and three-store skills, frozen P7 and Schema 21 evidence, current CI/testing contracts, and applicable recovery/identity/notes/time ADR decisions. Accepted target and implemented public Schema 21 were treated separately.

## Independent merge reconstruction

For every stage I independently ran `git merge-tree --write-tree <target> <feature>`, independently read the synthetic commit's actual ordered parents and tree, and compared to the supplied chain and previous reference trees. All seven invocations exited zero without conflicts. All second-parent feature heads are ancestors of the final synthetic commit, without flattening stacked histories.

| PR | Merge base | Effective tree |
| --- | --- | --- |
| #89 | `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c` | `ed80623514a5e574d1e24e908b95504f60b815db` |
| #87 | `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c` | `6ebd07cf4d6846e7d964c1be571c8507c037b9be` |
| #88 | `c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75` | `e250fe0ad801013fb9c59e929cfc7f875fabb5b8` |
| #93 | `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c` | `d4bf2253eed2ea7df26336c681c5a5241dd36bf6` |
| #91 | `7dc31256907aff4412170bc3f3ce3069b2ad89f2` | `f749d63fb1162520b21512a0690bf2015441ba91` |
| #92 | `1700ed37e82a6028cfa40c86b35db7621dd50404` | `1e5b150613d1ccf15285c5724498744fb4d883fa` |
| #90 | `e956cd50b1f25bd95427301cced4741bb68e24f8` | `ea006924152d2fc508c7eb21697ad3c376e373f6` |

`independent-dag.json` records full target/feature SHA, actual parent order, recomputed merge-tree output/exit, source delta, and diff-stat. Independent GitHub REST observation in `pr-state-independent.json` found all seven PRs open and non-draft at exactly the pinned heads. Their current bases match the intended stacks. The list-pulls endpoint does not return mergeability; its null mergeability values are not evidence of either conflicts or readiness. The first unsupported gh JSON-field attempt is preserved separately.

## Architecture and isolation

The production delta from main is precisely the seven P7-related files plus the public Search `adapters/sqlite/index.py` correction, recorded with Git blob IDs in `additional-bindings.json`. Public packaged DDL, public schema version/composer, public CLI, existing public persistence and acquisition modules are unchanged. No runtime migration or P7 public activation is introduced.

Against frozen P7 source `178ddbaa8fa06f52aff4993730205c5a38da91f4`, **the only production-source difference is the public Search index module**. All P7/opt-in executable source is identical. Against frozen Schema 21 source `74f90adae40ae60076dca33629fa2edbf5763474`, the source differences are the P7 files and the already reviewed bounded native-header parser change. Evidence-only feature-head commits were not treated as rerun receipts.

The Search diff keeps old-generation derivatives until replacement, selects new-generation membership from the pinned Core snapshot's actual current keys, advances beyond stale-only batches, checks the current-key count, and prunes unreferenced Search derivatives after promotion. It introduces no Core write, surrogate authority, ATTACH, compatibility view, new domain tables, Publication gate, or dependency on P7. Fine-grained runtime validation of Search and recovery belongs to reviewers B/C and the combined execution.

I independently executed all packaged schemas in memory and inspected their physical tables, foreign keys, views and Core immutable guards. Baseline counts remain Core/Operational/Search **70/10/4**. Opt-in counts remain Core/Context/Operational/Search **18/17/8/3**. Opt-in Core contains no jobs, request work/progress, Search derivatives or Context resources/text; has no views; each table has UPDATE/DELETE guards; and every Core FK targets a table in the same Core. Direct static baseline imports into the explicit opt-in module set are absent. This is static import/DDL evidence, not a proof about arbitrary future dynamic loading or hostile privileged writers.

Permanent repository/Capture identity and append-only Git Core schema/guards remain unchanged from frozen P7. The public Schema 21 baseline's historical mutable Core semantics were not incorrectly represented as opt-in append-only semantics. No Publication machinery, duplicated Operational Core tables, compatibility aliases, implicit ATTACH or unauthorized public migration is introduced by the combination.

`independent-boundary-probe.json` preserves the inspected table/FK/trigger inventory, fingerprints, source identity and static import result. These independent checks supplement rather than replace the supported audits.

## Authoritative checks and focused execution

All executed on the exact combined commit using this worktree's own locked `uv` environment. Python **3.12.14**, SQLite **3.53.1**. Actual interpreter/import origins are in `check-0.log`.

The following all exit zero, with separate raw logs and commands in `check-execution.json`:

```sh
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync python scripts/audit_publication_free.py --check
uv run --no-sync python scripts/schema_viz.py --check
```

Independent focused tests: **49 passed / 0 failed / 0 errors / 0 skipped**, exit zero, 7.99s. Selection covers P1 physical schemas and disposition/guard adversaries, public Schema 21 physical-store/split-write contract, and the still-supported historical audit helper functions.

```sh
uv sync --locked --group dev --group docs
TMPDIR=/workspace/integration-acceptance/reviews/a/tmp uv run --no-sync pytest \
  tests/integration/p1/test_schema.py \
  tests/integration/p1/test_disposition.py \
  tests/integration/test_schema21_runtime_contract.py \
  tests/unit/test_phase2_dependency_audit.py -q \
  --basetemp /workspace/integration-acceptance/reviews/a/pytest-temp \
  -o junit_family=xunit1 \
  --junitxml /workspace/integration-acceptance/reviews/a/focused.xml \
  --journal /workspace/integration-acceptance/reviews/a/focused.jsonl
```

`focused-collection.txt`, JUnit, journal, stdout, exit receipt and `focused-reconciliation.json` bind 49 duplicate-free collected IDs to exactly the same 49 JUnit identities and journal starts, with exactly one passing setup/call/teardown per node (**147 phase records**). Collection was independently repeated on the unchanged clean source after execution.

## Historical optional audit disposition

I reproduced the complete old `scripts/audit_phase2_dependencies.py --output ...` entrypoint failure: exit **1**, `AttributeError` at `build_report()` line 492, retired `exchange.EXCLUDED`. Raw traceback is preserved in `check-7.log`; it is not a passing audit.

This is **not an authoritative current acceptance gate**:

- `.github/workflows/tests.yml` invokes the current publication-free audit, not the old Phase 2 entrypoint.
- `docs/testing.md`, `docs/change-aware-ci.md` and `scripts/ci_dependencies.json` describe current acceptance and do not require the old entrypoint. The policy classifies historical phase exports as evidence, not acceptance gates.
- `docs/phase2/verification.md:33` explicitly binds those reproduction commands to PR A's **Schema 18** checkout; `docs/phase2/implementation.md` is explicitly **Schema 19**; `docs/phase2/workstreams/fields.md` identifies its investigation as **Schema 18**.
- Earlier publication-free architecture reviews already disclose the full entrypoint failure as historical, while using functioning helpers. Current unit tests still exercise these usable helpers and all passed in my focused run.
- The helper, field-helper importer and production exchange blobs are identical between main and this combined tree (`additional-bindings.json`). No seven-PR integration regression introduced the failure.

Disposition: retain historical code/evidence, accurately label the obsolete full entrypoint as unsupported for current Schema 21 acceptance, and use the current boundary/callsite/publication/P1 audits. No architecture rewrite, weakened check, production correction or remediation PR is warranted for this unused historical entrypoint.

## Limits and owner gate

This scoped approval does not claim complete combined pytest, installed distributions, actual Mermaid rendering, hosted full release acceptance, production activation or platform guarantees; independent reviewers and root receipts address those distinct scopes. Linux cooperative-process/local-filesystem recovery limits and deferred P8 integration remain unchanged. No NFS/Windows/host-power-loss claim follows from static guards or subprocess tests.

Owner procedure must retain **#89 → #87 → #88 → #93 → #91 → #92 → #90**, use merge commits, retarget stacked children only after their parent is merged, verify unchanged feature heads and recompute each actual effective tree before merge. Actual merge commits are not predictable from synthetic SHAs. Check current main/heads/checks/rules again at execution; abort on an unexpected head/tree/conflict/check failure. This review authorizes none of the merges.
