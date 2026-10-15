# Implementation-boundary audit and executable architecture probes

**P1 executable successor:** [isolated four-store schemas and typed contracts](p1-schema-contracts.md), [complete physical reconciliation](p1-reconciliation.md), and independent [P2](p2-git-core-handoff.md)/[P3](p3-context-handoff.md) briefs. The historical PR #70 audit and prototype evidence below retain their original scope; P1 does not switch the Schema 21 runtime.

**Verdict: READY FOR IMPLEMENTATION STACK.** The boundary audit and executable
probes are complete; the four-store production runtime remains unimplemented.
This PR changes no packaged production schema or runtime, opens no user catalog,
performs no migration, and authorizes no merge/release/deployment. Remaining
owner-level architectural blockers identified: **0**.

Repository: <https://github.com/TakashiSasaki/git-repo-db>.
Fetched authoritative main: `57de60b65c2ef29420a885b0c2102dc90e11fa75`.
The initial checkout was older `b329efa`; all work was started on a new branch
from fetched `origin/main`, not that old checkout. PR #69's design integration and
ADR 0011/#52 acceptance are present. `gh pr list --state open` returned `[]` before
work. Accepted ADRs through 0027 and scoped supersessions govern the target.
No accepted ADR text or publication allowlist was changed.

## Reviewable artifacts

| Artifact | Purpose |
| --- | --- |
| [Table matrix](table-disposition.md) / [authored JSON](table-disposition.json) | Every product table/column, current PK/UNIQUE/FKs, mutation candidates, target ownership/key/disposition, retention concern, ADR/test and planned PR |
| [Complete generated inventory](schema-inventory.json) | Executed production composed SQL, full triggers/views/indexes/guards, fingerprints, ordered keys and source references |
| [Audit engineering notes](audit-notes.md) | High-risk mixed-column splits, physical five-column Coverage/key reconciliation, source/target distinction |
| [Call-site map](callsite-dependencies.md) / [JSON](callsite-dependencies.json) | 75 production Python/SQL inputs, 3,315 literal references, 98 revision/fence dependencies plus inspected dynamic integration paths |
| [Legacy violations](legacy-operations.md) | 20 concrete operation families requiring replacement, source locations, accepted successor, adversarial tests and PR owner |
| [Prototype A](prototype-a.md) | Append-only, metadata-only Git Core; semantic claim/group keys, conflict/replay and separately evidenced intrinsic checks |
| [Prototype B](prototype-b.md) | Independent WAL stores, subprocess COMMIT cuts, pinned pair reads, backup pairing and retry |
| [Prototype C](prototype-c.md) | Real SHA-1/SHA-256 Git notes proof, role-dependent body retention and cumulative finite work budgets |
| [Stack plan](implementation-stack.md) / [DAG JSON](implementation-stack.json) | P1–P8 dependencies, parallelism, deliverables and acceptance gates |
| [Independent review](independent-review.md) | Source/execution findings, reproductions, material corrections and rechecks |
| [Execution report](execution-report.md) / [receipt](execution-evidence.json) | Exact input binding, commands, passed/failed/skipped nodes, actual persisted crash states and limitations |

## Actual schema impact

Executed production DDL confirms **84 static product tables: 70 Core, 10 Operational,
4 Search**. Runtime FTS virtual/shadow tables are separately identified derivatives.
There are 20 Core views, 540 total triggers and 52 explicit indexes. All 84 tables
and all current product columns are classified: **48 replace, 16 split, 13 move,
4 eliminate, 3 retain; 0 unclassified**. These are dispositions of existing tables,
not a promised target table count. Semantic/FK redesign also applies to retained
components; a `retain` label never exempts a storage-only key.

Most consequential splits: nominal object identity versus attributed type/size
and receiver-local evidence; immutable whole-group commit/tree/tag observations
versus mutable pointer hydration; Git capture/ref/root evidence versus Source/PR
associations and Operational progress; permitted metadata/notes representations
versus excluded file content; Context alternatives versus disposable Exchange
receipts. `database_identity.local_revision` and every paging/acquisition/Search/
backup fence must change coherently. Coverage retains exactly five physical claim
columns while replacing storage-only scope/claim aliases with genuine semantic
coordinates; no extra observation UUID or six-column authority is accepted.

## Executed experiments

| Prototype | Tests | Result | Demonstrated boundary and remaining risk |
| --- | ---: | --- | --- |
| A | 43 | passed | Actual SQLite append-only supported API, metadata-only claims/groups, exact replay/conflict, transaction rollback/visibility, real commit verification. Narrow parser/encoding and privileged-SQL limits remain. |
| B | 14 | passed | Two separate persistent WAL files, real process death at four COMMIT cuts, identity-preserving retry, reader/backup gates and mismatched/invalid pair rejection. Power loss, durable installation and full recovery remain unimplemented. |
| C | 67 | passed | Actual SHA-1/SHA-256 Git objects; structural plus exact native/body/digest checks; all 15 requested cases and cumulative Operational work. Production parser scale, I/O crash-safe reservation and full integration remain. |
| Audit checker | 4 | passed | Missing tables/columns and stale inventory rejected; all production guards accounted for. Literal index is supplemented by inspected dynamic paths, not a general data-flow proof. |

Integrated direct pytest execution: **128 passed, 0 failed, 0 skipped**; an
independent reviewer also executed all 128. Ruff check and format-check passed
across `src tests scripts`. Both deterministic audit checkers passed.

Additional existing schema/visualization tests: **35 passed, 1 failed**. The failure
at `test_catalog3_schema.py:244` queries Operational `jobs` in a Core-only fixture.
It was reproduced at unchanged baseline main in a separate detached checkout;
no new code causes it. Preserve the resource-independence behavior while repairing
that stale cross-store assertion in future integration work. Full product/release
acceptance is **not** claimed. The focused profile wrapper also failed before
collection because `--journal` was registered twice; direct pytest with JUnit and
the existing journal hook produced the successful integrated evidence. Exact
commands, diagnosis and failure records are in the execution report.

Core/Context crash results are counts `(Core objects, Context units, links)`:
before Core commit `(0,0,0)`; after Core commit `(1,0,0)`; during Context `(1,0,0)`;
after Context commit/lost acknowledgement `(1,1,1)`. Every same-evidence retry ends
at `(1,1,1)` with exact duplicate replay unchanged. No mismatched full-pair backup
is certified. These are process-death properties, not hardware/power-loss proofs.

## Recommendations and next work

Fix P1's semantic ownership/key/admission/read contracts first. Then implement P2
Core and P3 Context in parallel; P4 notes extends Core independently of Context.
P5 acquisition/Exchange and P6 CLI/search integrate those stable interfaces, with
P7 paired backup/recovery depending on typed replay/admission. P8 independently
reviews the coherent runtime switch and installed schema. Detailed acceptance
gates and safe parallel opportunities are in the stack plan.

Recommended first coordination mechanism: Core-first independent admission plus a
cooperating OS gate; establish both authoritative read snapshots under that gate.
A valid committed Core fact survives absent Context. Context units commit atomically
and validate dependencies without implying Git closure. Full backups validate both
copied authorities before the final manifest and later activation. This is an
engineering recommendation demonstrated by probes, not a new domain Publication.

Per the owner's follow-up instructions, skills now distinguish current baseline
recipes from accepted target behavior; reusable review/debugging lessons are
recorded in existing skills. `AGENTS.md` records proactive skill reconciliation
and recurring verified learning, and corrects the stale ADR 0011/#52 sentence.
The review report includes these changes. Historical receipts remain historical.
