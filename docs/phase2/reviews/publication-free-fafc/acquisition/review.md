# Independent final-candidate review: scope 2 acquisition/completeness

Status: **scope 2 accepted on the exact frozen fafc candidate below**. All ten original acquisition findings were rechecked through the same independent counterexamples. The 50 preserved probes and 16 newly authored native-SQL counterexamples passed, with zero failures, errors or skips. No unresolved mandatory issue was found within this reviewed scope. Overall ordinary/package/hosted-CI and other-domain acceptance remain separate pending gates.

Reviewer: independent subagent `/root/review_acquisition`, not an author of the production changes. Model and reasoning effort: **not exposed**. No additional subagents were used. The initial failed receipt and accepted b86 receipt remain immutable historical evidence; this receipt supplies a new source binding.

## Exact source and runtime binding

- Clean isolated worktree: `/workspace/reviews/publication-free-acquisition-fafc`.
- Commit: `fafc1b2d4d2e1986768143cc71a0e55cba943ba3`.
- Tree: `6f566cb3e91e25facda60671c40108e0a9f8965b`.
- Imported packaged composed DDL SHA-256: `bf6deb09471a361918ab9d9e97ca1ba204060ffc78420972775a914357912f26`.
- Actual import: `/workspace/reviews/publication-free-acquisition-fafc/src/repo_catalog/__init__.py`.
- Shared interpreter: `/workspace/git-repo-db/.venv/bin/python`, Python 3.12.14; Python-linked SQLite 3.53.1.
- Independently executed native CLI: `/workspace/review-artifacts/schema-a1-b86/sqlite345/sqlite3`, SQLite 3.45.1, official-source version identifier `e876e51a0ed5c5b3126f52e532044363a014bc594cfefa87ffb5b82257cc467a`, 64-bit. Binary SHA-256 `d0ff9605f0080e55c0b33ad917a7beee285915dd6402ca284781b0845773d6a1`. This reviewer executed the already available compiled binary; did not claim to independently rebuild it.
- Generated `guard_sql()` exactly equals the packaged `resources/json_contracts.sql`; verified against this import and persisted in `binding.json`.
- Git status was empty before and after execution. No root source/history edits, retained-catalog changes or live authenticated requests. API/Git/SQLite state was disposable, with localhost synthetic API and dummy token only.

The prior scope-2 receipt remains `/workspace/review-artifacts/acquisition/corrected-review.md`, SHA-256 `52a0fc8ea47bb3e82871ef8d2760dbcb986d5322d1dd5ae10895704a6013f1f0`, bound to b86. That hash was independently rechecked unchanged. Original 41dbe failure evidence also remains preserved. The new artifacts are contained only in `/workspace/review-artifacts/acquisition/fafc-final/`.

## Review of affected changes

Re-read applicable root and Phase-2 AGENTS and the updated implementation handoff; design, ADR, decision register and implementation prompt were fully read in the original review and are unchanged between b86 and fafc. Inspected the b86-to-fafc correction inventory, current API/resource delta, shared JSON validation/native guard generator, affected staging owner update, composed pending SQL, updated map and Source/timestamp fixture ports. Acquisition collector/parser/persistence have no b86-to-fafc source differences.

New current candidate validation checks typed subjects, signed-int64 clocks, actual producer attribution, evidenced-value presence and internal capture correlations before missing parents may defer admission. Missing dependencies still do not fabricate a registration or invalidate an otherwise valid detached capture. Pending native guards independently validate each candidate/evidence/envelope instead of nesting a whole domain CASE expression. Metadata checks rebuild decoded parent/key paths, preventing escape spelling from bypassing known fields. The staging owner update keeps its repository selector consistent when an unresolved Issue candidate moves. The preserved detached-capture, inherited-origin, Source partial-inventory and receiver-fence probes all still pass.

The Source fixture ports assert actual Source assessments/known positive pairs in place of retired inventory observation tables; the timestamp fixture uses the whole composed schema and retains signed integer/range/storage assertions in surviving domain tables. These inspected fixture changes do not constitute independent execution credit in this receipt. Author-native-170 test claims are not used as independent acceptance evidence.

Shared Git decoding/query and Exchange closure/ref/replay changes were inspected at the dependency boundary only; their full semantic review belongs to the other scopes. This receipt makes no overall acceptance inference from their implementation or authored tests.

## Executed commands and results

All commands ran with CWD `/workspace/reviews/publication-free-acquisition-fafc`. The three preserved script copies are byte-identical to the accepted b86 probes; **no assertion adaptation was needed**.

```sh
PYTHONPATH=/workspace/reviews/publication-free-acquisition-fafc/src:/workspace/reviews/publication-free-acquisition-fafc:/workspace/review-artifacts/acquisition/fafc-final/probes PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python -m pytest -q /workspace/review-artifacts/acquisition/fafc-final/probes/test_independent_acquisition.py /workspace/review-artifacts/acquisition/fafc-final/probes/test_independent_invariants.py /workspace/review-artifacts/acquisition/fafc-final/probes/corrected-new-probes.py --tb=short --junitxml=/workspace/review-artifacts/acquisition/fafc-final/fafc-50-results.xml > /workspace/review-artifacts/acquisition/fafc-final/fafc-50-results.txt 2>&1

PYTHONPATH=/workspace/reviews/publication-free-acquisition-fafc/src:/workspace/reviews/publication-free-acquisition-fafc:/workspace/review-artifacts/acquisition/fafc-final/probes PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python -m pytest -q /workspace/review-artifacts/acquisition/fafc-final/test_native_pending_guards.py --tb=short --junitxml=/workspace/review-artifacts/acquisition/fafc-final/native-pending-results.xml > /workspace/review-artifacts/acquisition/fafc-final/native-pending-results.txt 2>&1
```

| Independently executed set | Nodes | Passed | Failures/errors | Skips | Reported elapsed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Preserved API/current/transaction/completeness probes, SQLite 3.53.1 | 50 | 50 | 0 | 0 | 149.98 s |
| New typed-pending probes, 8 SQLite 3.53.1 + 8 native CLI 3.45.1 | 16 | 16 | 0 | 0 | 117.93 s |
| Total | **66** | **66** | **0** | **0** | — |

The native 3.45.1 cases run SQL against their own disposable catalog backup, with foreign keys and recursive triggers enabled. This directly executes the installed pending guards rather than treating Python admission or author tests as evidence. The native and Python-linked variants reject foreign top-level capture parent, foreign field capture parent, body evidence whose body value was omitted, out-of-range observation integer, NULL required parsing time, boolean observation time, and a nested permissions-object replica using escaped `permi\u0073sions`. Each rejection preserves the original pending row. The positive control accepts observation `-9223372036854775808` and parsing time `0`, both in candidate and field origins; stricter guards do not invent positivity or chronological-order requirements.

Fresh native compilation also ran the exact imported composed DDL in `sqlite3 :memory:` through `fresh-native345-composed.sql`, with `.bail on`, foreign keys and recursive triggers enabled. Command:

```sh
/workspace/review-artifacts/schema-a1-b86/sqlite345/sqlite3 :memory: < /workspace/review-artifacts/acquisition/fafc-final/fresh-native345-composed.sql > /workspace/review-artifacts/acquisition/fafc-final/fresh-native345-compilation.txt 2>&1
```

Exit 0; output `3.45.1`, table count `84`, no foreign-key-check rows, integrity `ok`. This verifies actual fresh compilation on the bounded native parser; it does not claim populated full-check or all-view execution coverage. The SQL artifact contains only packaged schema and checks, no private data. Other acceptance workloads ran concurrently; elapsed times are not selected-scale or comparative benchmark evidence.

## All original findings rechecked

| Initial finding | Recheck on fafc |
| --- | --- |
| ACQ-01 capped commits block independent files | Pass: files are requested/admitted after the capped commits failure. |
| ACQ-02 partial commits listing ID lost to assessment | Pass: full synthetic sync links its actual durable partial listing ID. |
| ACQ-03 observed permissions omitted from field capture | Pass: direct context and actual `/user` OAuth scope header reach body field origin. |
| ACQ-04 sparse REST title rejected | Pass: omitted title inherits its value/origin while newer body changes; missing/null matrix remains active. |
| ACQ-05 verified redirect uses old or forged fence | Pass: final request uses its actual pre-request revision; a writer during response makes the unclocked response fail. |
| ACQ-06 foreign GraphQL owner completes local roster | Pass: foreign/missing/bool-number/contradictory identity reject; retained matching ID or typed matching requested number accepts. |
| ACQ-07 older175 overwrites complete300 assessment | Pass: same-target complete300 survives older175; head B cannot borrow A. |
| ACQ-08 escaped Issue body field-clock alias | Pass: native SQL rejects escaped semantic path alias. New decoded permissions-key attack also rejects on 3.45.1 and 3.53.1. |
| ACQ-09 code-check304 cache loss | Pass: real unconditional fresh-body fetch occurs; repeated detail304 produces reuse-unavailable. |
| ACQ-10 hidden current/pending response replicas | Pass: Python admission and direct SQL current/field/pending variants reject; new escaped nested original-bearing shape rejects on both native runtimes. |

The preserved 50 also recheck Store/shared nested body/statement/deferred COMMIT/cleanup rollback; value/presence/evidence/text/revision all-or-none; valid page resources after larger failures; sparse v1/v2 inherited producer/clock origins and explicit null; complete100 → partial200 → oldercomplete175 → complete300/equal/unknown Coverage; empty terminal versus absent terminal; exact thread roster/child obligations; Source partialR1 retaining R2; receiver-local checks and live revision/scope fences; detached captured IDs; cancellation/restart after cursor deletion; optional archive/warning failures; no write transaction over tested HTTP; and credential loss before acquisition producing no remote observation. These remain current-domain behavior assertions, not parser-profile/certificate/generic-batch gates.

## Scope and limits

Reviewed/executed scope remains current GitHub acquisition, current field/provenance admission, Source positive pairs, domain collection/completeness, receiver fences, operational cancellation/304/credential loss, shared atomic units and relevant current/staging JSON guards. Native SQL additions focus on pending document candidates; this is not an exhaustive native table/trigger campaign. SQLite 3.45.1 ran the new eight SQL cases and fresh composed DDL; the full 50 API probes ran on Python-linked SQLite 3.53.1.

Unexecuted here: complete ordinary 2128-node run, wheel/sdist package suites, hosted CI, full Git/Exchange/CAS/decoder semantics, every populated DDL guard/view, selected-scale workload, retention growth, real process kill/storage I/O faults and OS writer-lock concurrency. Those remain separate root/other-reviewer gates. No deletion-on-absence, GC/retention, provider-trust, total clock order, Source negative-membership, decoder ranking or generic batch policy was selected.

`artifact-sha256.json` binds this receipt, scripts, logs, JUnit, binding JSON and reviewed guard delta. Sign-off is scoped to the exact fafc SHA/tree/DDL above; subsequent affected source changes require renewed review.
