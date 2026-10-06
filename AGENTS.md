# Coding agent guide

This file applies repository-wide. Follow the user's latest explicit scope and any more specific instructions for a changed path. Write coding-agent prompts, task specifications, and handoff instructions in English; user-facing explanations may remain Japanese.

## Current state and working rules

- `repo-catalog` is an unreleased Python CLI for offline-queryable Git structure/content, GitHub PRs, and observation history. The normal application still uses **schema v2**.
- P1 provides the independent `repo-catalog/catalog3-p1` target, contracts and lifecycle tests. P2 implements synthetic-tested source sealing, typed archive, representative ID mappings, atomic batches, resume proofs and guards. P3A adds operational v2 source admission and a verified atomic P2-to-P3A phase receipt, tested on native and audited minimum SQLite. Change-aware CI is implemented. Full normalized conversion and new-runtime integration are not complete.
- P3A has reached its bounded synthetic acceptance boundary, with the affected P2/P3A closure passing on native and audited minimum SQLite; see the [English handoff](docs/schema-hardening/p3a-handoff.md) for exact evidence and limits. The next implementation slice for a subsequent task is **P3B: identity conversion**, below. Do not repeat P1/P2/P3A or reopen the CI optimization project without a concrete defect.
- P3A starting baseline: feature `1e052e4b666039704ad0b8ea3a1d7a752d561358`, historical substantive CI code `0d3ca4693a03d5daa8210e2fd3a44dd1e613cd09`, main `9a4110185d7e7abffc291f9cfd118ca71587f998`. Fetch and record actual HEAD/base/delta; these historical SHAs are not reset instructions or proof about later code.
- Continue on `design/schema-v2-hardening` / PR #1 unless the latest request or repository state establishes another target. Do not commit directly to main, auto-merge, overwrite user changes, or interpret this guide as permission to convert/cut over real data.
- Backward compatibility with old application/CLI/DB formats is unnecessary. **Acquired data must be preserved.** Prefer offline one-way conversion into a separate target; full GitHub re-download is not the normal migration strategy.

## Sources of truth

Start with [README](README.md) and [architecture](docs/architecture.md), then read the relevant documents:

| Concern | Sources |
|---|---|
| Target guarantees | [hardening overview](docs/schema-hardening/README.md), [invariants](docs/schema-hardening/invariants.md), [P1 design](docs/schema-hardening/p1-design.md), [lifecycle](docs/schema-hardening/p1-lifecycle.md) |
| Executable target contract | [complete DDL](docs/schema-hardening/target-schema.sql), [conversion contract](docs/schema-hardening/conversion-contract.json), [invariant contract](docs/schema-hardening/invariant-contract.json) |
| Conversion and roadmap | [P2 foundation](docs/schema-hardening/p2-foundation.md), [P3A handoff](docs/schema-hardening/p3a-handoff.md), [offline conversion](docs/schema-hardening/offline-conversion.md), [implementation plan](docs/schema-hardening/implementation-plan.md), [table mapping](docs/schema-hardening/table-conversion.md), [column mapping](docs/schema-hardening/column-conversion.csv) |
| Existing application | [data model](docs/data-model.md), [repository identity](docs/repository-identity.md), [CLI](docs/cli.md), [operations](docs/operations.md) |
| Validation | [testing](docs/testing.md), [change-aware CI](docs/change-aware-ci.md), [performance](docs/ci-performance.md), `.github/workflows/tests.yml`, `scripts/ci_dependencies.json` |

The complete SQL and machine-readable contracts are authoritative; generated CSV/Markdown/inventory are views. `proposal-core.sql` is a regression fixture, not the complete target. `source-access.json` is lexical analysis, not a complete call graph. `tests/support/p1_admission.py` demonstrates lifecycle behavior, not a production runtime. Read [implementation status](docs/implementation-status.md) as historical evidence.

## P3A boundary and next bounded slice: P3B

P3A admits the strict v2 core plus structurally and relationally recognized application FTS and capability-tested SQLite statistics. It retains complete physical/schema identities and per-object dispositions. Unknown objects remain fail-closed and classification rejection has a private local machine-readable report. Accepted core table values are typed archive input; indexes/triggers and derived search/statistics remain sealed bytes with explicit rebuild/exclusion.

The same-target phase model uses a second `conversion_runs` row with `p3a-handoff/1`. It independently verifies the complete P2 archive, mappings, diagnostics and output proofs, then atomically inserts a receipt under the writer lock. P2 evidence stays unchanged; restart/repeated handoff verifies the same committed transition, and P2 writes refuse the new owner before mutation. The receipt owns **only its own initialization INSERT**, not domain writes. Target lifecycle stays `building`; semantic blockers remain visible and activation is forbidden.

Current P3A phase/source fingerprints remain exact. Only the handoff verifier accepts the reviewed P2 predecessor at `1e052e4b666039704ad0b8ea3a1d7a752d561358` with its exact baseline seal and unchanged DDL/contract/parser. No global hash-ignore or force-resume option exists. Source capability probes on an older fixture interpreter do not relax the guarded operational SQLite >=3.46.1 requirement. Read the [handoff](docs/schema-hardening/p3a-handoff.md) before evolving this protocol.

For a subsequent P3B task, implement identity conversion only; do not attempt all remaining domain recipes at once.

### 1. Establish reviewed P3B write ownership and resume proof

- Verify the accepted P3A receipt and parent evidence before any domain mutation. Define a concrete P3B phase/protocol version, permitted tables/operations and phase-scoped committed output proofs.
- Preserve P2 archive, parent receipt, mapping and diagnostic facts. Any permitted enrichment of representative repository rows must have explicit ownership and a new proof; do not silently reuse their original P2 current-value hashes after changing them.
- Keep exact resume within each phase and explicitly reviewed predecessor verification. Use the existing writer lock, atomic commit boundary and stable allocation rules; test before/after-COMMIT failure, repeat invocation, restart and competing writers.
- Keep lifecycle `building`; neither successful identity conversion nor phase completion permits current-pointer publication, normal-runtime activation or real-data cutover.

### 2. Convert service/source/repository identity facts

- Implement service instances, sources, repositories, bindings, endpoints, name facts and source membership from preserved source values. Use explicit recipe/lookup/allocation/persistence, with typed ID maps where allocation is required.
- Preserve existing repository/local IDs. Distinguish repository UUID, provider-native identity, discovery source, URL and mount path. Shared OIDs, equivalent URLs or names do not authorize merging forks/mirrors.
- Retain original names, metadata, source/member time bounds and acquisition assertions. Report contradictory legacy identity columns, ambiguous binding/endpoint ownership and missing references instead of inventing values or selecting a convenient latest row.
- Enforce same-owner relations and valid scoped pointers, but do not populate final current/publication pointers prematurely. Preserve malformed, unknown and partial facts in the archive with explicit diagnostics.

### P3B acceptance and deliverables

Provide working identity recipes/maps, machine-readable phase ownership/output proofs, focused positive/negative/fault tests and an updated English handoff. Run a guarded synthetic source -> admitted seal -> complete archive -> verified P3A boundary -> P3B identity conversion -> restart comparison.

Compare IDs, typed bytes, source/service/binding/endpoint/member edges, original times and diagnostics. Include duplicate URL/name/shared-OID repositories that remain distinct; conflicting native identities; missing/ambiguous bindings; same-owner violations; existing representative maps; unknown/malformed/partial inputs; source/cache immutability; tampered parent/phase/output; and atomic/repeated/competing-writer behavior. Counts/FK checks alone are insufficient.

Update the dependency map and selectors for actual imports, file reads, fixtures and test collections. Keep P1/P2/P3A acceptance, audited minimum-runtime coverage, offline packaging and existing guards. Report fresh/reused/not-applicable coverage accurately. Do not use actual user DB/cache, acquisition APIs, normal sync/restore or activation.

### Later slices, not part of P3B

| Slice | Scope and completion evidence |
|---|---|
| P3C | Existing Git facts: objects/edges/content/digests/acquisitions/snapshots; compare bytes, IDs, ownership and order. Missing originals are not newly verified bytes. Git reconstruction is P4. |
| P3D | Saved API/PR history: payloads/pages/documents/versions/observations/reviews/events/unresolved data; preserve A->B->A, timestamps and partial scopes. |
| P3E | Integrated synthetic normalized conversion, restart and ID/byte/edge/pointer/diagnostic comparison; still not activation. |
| P4-P7 | Offline reanalysis; new runtime/first-sync reuse; explicitly scoped real-data dry-run; separately scoped cutover/rollback. |

## Architecture and preservation rules

- Keep dependencies `cli -> application -> domain/ports`; adapters implement application-facing boundaries. Do not make application services execute CLI/presentation code. PR queries live in `application/pr_queries.py`.
- SQLite connection/transaction/migration behavior belongs to `adapters/sqlite/store.py`; search to `index.py`; Git/API acquisition to their adapters; cache/leases/capacity to filesystem adapters. Packaged migrations/GraphQL/CLI schemas live in `resources/`. Dedicated conversion belongs to `scripts/conversion/` and `scripts/offline_convert.py`, not normal sync/restore.
- Use one writer/coordinator with an OS lock. Do not hold write transactions during HTTP/Git, hashing, waiting or stdout. SQLite files are local; enable FK on every connection and recursive triggers for the target. Current default is DELETE/EXTRA; preserve explicit WAL/runtime gates.
- Normal queries read the DB only: no network, Git execution, automatic migration or raw-content reacquisition. FTS is derived; preserve original-content checks and scan fallback. Do not activate the independent target in the normal migration runner before the runtime phase.
- Repository UUID, provider-native ID, URL, mount path and discovery source are different identities. Preserve existing IDs unless an explicit map is required. Shared OIDs/content do not authorize merging forks/mirrors. PR/MR numbering is binding/kind scoped.
- Enforce same-owner relations and scoped current pointers across child/parent updates, deletions, transactions, SAVEPOINTs, UPSERT and REPLACE. Completed listings remain sealed whether referenced or not; appending requires a partial marker; valid pre-commit rollback remains possible.
- Allow only verified monotonic enrichment: eligible NULL text -> exact known text, Git verified 0->1 after original-object verification, source-pair time bounds widening by min/max. Known bytes cannot be replaced/erased; aggregate bounds do not replace individual observations.
- Share body bytes only after exact comparison; never merge distinct versions/observations or erase A->B->A. Keep observation time separate from migration/reanalysis time. Preserve NULL, malformed values, unknown states/provenance and partial scopes with diagnostics; do not invent values or promote them to complete.
- Git OIDs include object format. Preserve raw path/ref/tree-name bytes and parent order. Git-object and raw-content hashes differ; missing originals are not empty content. Keep legacy verification assertions distinct from newly demonstrated verification.
- Preserve payloads/pages, pending resources, local objects and resume evidence as well as normalized rows. Keep completion/watermark/validator/cursor/principal/API/parser/profile scopes for later first-sync reuse; replay must not advance watermarks or trigger a blanket re-fetch.
- Counts/FK checks alone do not prove preservation. Compare typed bytes, IDs, edges, order, observations, coverage and scope. Multiple-DB merge, bidirectional sync and additional provider adapters are outside current scope.

## Guarded conversion limits

- Enter through the dedicated worker; component helpers are test boundaries, not unguarded operational alternatives. Never install irreversible seccomp/audit policy in the application or pytest parent.
- Verify source/copy/descriptor/cache fingerprints, target format/DDL/contract/converter identity and committed outputs on resume. Reviewed phase handoff is not permission to relax intra-phase checks.
- No acquisition network during conversion/reanalysis/index rebuilding/validation. Do not shortcut through sync, hydrate, restore or GC. P2 denies all child processes, including Git reads; later local Git reconstruction needs an explicit boundary, not guard removal.
- Preserve Linux/architecture/local-filesystem and audited SQLite >=3.46.1 requirements; unsupported bindings/platforms fail closed. Keep auditing active in every worker and the minimum-version lane.
- Source/cache symlinks, special files, unsupported remote filesystems and writable hardlink aliases remain unsupported. Writable regular files require link count one; path resolution alone does not establish inode isolation.
- Do not delete WAL/SHM/journal files to pass admission. Sealing requires stopped, consistent sidecar-free input, not converter-driven changes to the original. Target hot-journal recovery is separate.
- Networked dependency/repository preparation is a separate process. Never invoke preparation tools from the guarded converter/validator.

## Efficient development and change-aware CI

Use Python 3.12+, Git 2.43+ and the pinned uv/lock workflow. Inspect actual linked SQLite capabilities; native tests and guarded converter children may use different bindings.

1. Start with tests affected by changed code/imports/file reads/subprocess/fixture boundaries. Do not run full acceptance after every edit. Use `scripts/ci_dependencies.json` and the planner for final scope; update the map when dependencies change.
2. SQL, JSON contracts, CSV and generated schema Markdown are executable inputs even under `docs/`. Only explicitly classified prose/reports qualify for lightweight checks. Do not broadly ignore documentation directories.
3. Reuse only planner-verified full-acceptance evidence for compatible effective inputs, base/history, policy and runtime. Latest-commit paths, warm caches or a PR-body success claim are not proof. Unknown/shared inputs, incomplete history, expired/mismatched evidence expand validation safely.
4. Keep `tests / offline` and the always-running final gate. Collect expected selected IDs before execution; require exactly-once passed results and explicit unaffected reuse. Maintain the baseline-ID floor in `scripts/ci_required_baseline.json` **and** collect new tests. Review removals/renames rather than shrinking coverage to pass.
5. Small selections run sequentially; larger selections use the planner's fixed four workers. Packaging stays isolated/sequential. No `-n auto`, shared mutable test state, skipped/xfail required tests or retry-hidden failures.
6. Prepare dependencies, hash-verified wheels and audited minimum binding only for selected lanes. Keep offline packaging `--offline --no-index --find-links`. Preparation caches are not successful test evidence.
7. Workflow/policy/shared changes can require full acceptance; main/manual runs remain full. Otherwise run the smallest defensible dependency closure, not an unconditional full suite for every schema edit. Never use broad workflow path suppression or skip-CI commit messages to avoid the required gate.
8. Group report-only follow-ups where practical. Current evidence lookup is bounded and does not chain reuse-only anchors; repeated reports may therefore fall back to full. Do not weaken validation or repeatedly dispatch CI for a faster-looking number.
9. Report fresh/reused/not-applicable separately with SHA/run IDs. Retain timing/JUnit/selection artifacts, never DB/cache/payloads. Distinguish wall time, parallel aggregates and runner consumption; do not claim speedup from incomparable suites or one noisy sample.

Preparation and focused examples, not a mandatory full sequence for every change:

```bash
uv sync --locked --group dev
uv run --no-sync pytest tests/unit/test_conversion_protocol.py -q
uv run --no-sync pytest tests/integration/test_conversion_foundation.py -q -n 4
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
```

Use the current planner/runner prerequisites in `docs/change-aware-ci.md`; include new phase modules and test collections when implemented. Standard application tests use synthetic loopback APIs, dummy credentials and Git file transport; converters deny loopback acquisition too. Never disable parent/child guards. Live/pilot/benchmark runs need explicit scope, targets, capacity and request budget. Stateful CLI fixtures use an explicit `--state-dir`; global options precede subcommands. Never use default user state or leftover pilot data.

For schema changes, update the machine-readable contract first, regenerate with `scripts/schema_contract.py --generate` and the relevant design generator, and synchronize DDL hash/inventory/mappings/invariants/lifecycle/minimum-runtime tests. Do not hand-edit generated views. `schema_audit.py --fixture-schema` constructs disposable v2 state; read-only DB diagnosis is not migration. Synthetic index probes are not real-data estimates. The three `test_v2_hardening_reproductions.py` cases characterize existing collector bugs; passing them is not a fix. Add desired-invariant regressions when runtime behavior is actually corrected.

## Privacy and handoff

Do not commit/publish actual DBs, caches, API payloads, tokens, private repository content/identifiers, or credential-bearing headers/URLs/arguments. Use synthetic fixtures and dummy credentials. Ignored `artifacts/` can still contain private data; inspect staged paths and diffs.

Record decisions, actual SHAs, commands/runtime versions, selected/reused coverage, CI outcomes, admitted/rejected cases and limits. Distinguish code inspection, local synthetic tests, CI evidence, real-data read-only diagnosis, real-data conversion and cutover. Update this guide and the implementation plan when a milestone actually finishes; do not leave completed work as a standing instruction to repeat it.
