# I6-A secure Context admission — Author implementation evidence

This is Author verification, including supporting Author-side adversarial
analysis. It is not non-Author independent acceptance. Normal Transfer remains
staged. Both packaged SQL fences and all DDL/fingerprints remain unchanged.

Final outcome: focused **583 PASS**; installed direct wheel and sdist-derived
wheel **551 PASS each**; complete ordinary suite **5198 PASS / 324 FAIL /
419 ERROR** (5941 nodes, exit 1 overall, no skips/xfails). Full Author validation
is **INCOMPLETE**; non-Author independent acceptance is **NOT RUN**.

## Fixed ancestry and scope

Implementation starts directly from PR #141 commit
`dc6e663ea90e55210ed5674cae6c332f66a4ac18`, tree
`3d70218ecf98f751eb550e6a328a21f65069066f`, on
`impl/adr0031-i6a-secure-admission`. [Draft PR #143](https://github.com/TakashiSasaki/git-repo-db/pull/143)
has base `review/adr0031-i6-design-independent-20261023`. Design #134 is
`418ee68046fdfd03a0e84cc840e5d52fce176b81`, tree
`476d32923c9be5e3b60e4e17c8828e3646611c43`. Initial live GitHub
checks found no competing I6-A implementation PR among all 26 open PRs or
76 remote branches. Main was `cb532242c7aa86c6af5b6232b71c0906ea38f5c5`.

Task A's ADR 0033 minimal-sdist implementation/review/repair and PR #139's receipt
limit fix are absent from this ancestry. They were neither merged nor
cherry-picked. Later integration must reconcile those independent stacks; this
work does not claim their packaging/receipt improvements. No existing PR,
Accepted ADR, historic evidence, automation, release or deployment is changed.

## Implemented contracts

- R01/R08/R09: mandatory `ParentObservation(ParentReportKey, observed_at_us)`;
  independent Parent originals; total `ProviderEndpointDeclaration`; exact
  mandatory original endpoint tuple; no inferred or synthesized originals.
  Whole-unit selection withholds an incomplete report.
- R10/R11/R12/R14 (I6-A boundary): service-issued, exact-issued-object invocation
  contexts authenticated by trusted local composition; Resource, Repository,
  Source, positive-pair, claim, Disposition, Provider-registration and OID grants
  are checked separately from selection. Denial precedes local dependency lookup
  and replay shortcuts. Revocation is fenced by a serialized policy lease held
  through actual COMMIT; unsupported or unconnected policy paths refuse.
- R13 (I6-A dependency scope): pure bounded dependency/original validation;
  cumulative input/work charging; bounded current mapping scans and exact relevant
  Source-positive queries. General wire closure planning remains I6-B/C.
- R15: strict pre-affinity inputs and unchanged complete Parent/native-I7/Event
  SQL references, immutable guards/UDFs; atomic SAVEPOINT units and explicit
  rollback of failed outer COMMIT. Store-owned transactions verify exact packaged
  schema/connection profile and use the catalog writer gate for file-backed DBs.
- R16/R19: inspect both exact Transfer trigger definitions; partial, malformed,
  unreadable or absent ordinary schema refuses. Only an expiring, verified fresh
  in-memory synthetic fixture capability permits the two-fence-removed shape.
  Ordinary reopening and Store/Facade reject missing fences; ordinary Transfer
  remains staged even when both fences are healthy.

I5-A1/B1/C1 and I6-L1 have actual initial/replay and original-evidence
counterexamples. I5-D1 is supplemented by actual in-flight SQL and deferred
COMMIT probes. I5-F1 is corrected by both-trigger inspection. No I6-B/C, I7/I8,
normal Transfer activation, fence retirement or independent PASS is claimed.

## API and integration consequences

New domain/port: `context_admission.py`, `ports/context_authorization.py`.
Shared adapter guard: `adapters/sqlite/context_admission.py`. All external-input
mutators on `ContextStore` and `Context` accept keyword `admission`; an owned
transaction may bind that same issued invocation. Raw `ContextStore` uses
`admission_transaction`/`transaction`; the facade uses catalog-gated
`Context.transaction(..., authorization=...)` or trusted-connection
`Context.owned_transaction`. The corrected low-level coordinator now binds its authorization service at
construction and retains the explicit invocation's shared lease stack through
its actual outer Context COMMIT. `ContextStore(tx)` and `Context.for_transaction`
inherit only that exact expiring trusted capability. Unbound coordinator callers
still fail closed; Provider/Exchange wiring remains I6-C work. Raw SQL handles remain trusted infrastructure outside input APIs.

Provider Context intake and Context-bearing Exchange import/export are explicitly
unconnected until I6-C. Exchange refusal precedes progress/receipt duplicate
shortcuts; bounded parsing work already performed is still charged. Core-only
Exchange remains separate. No provisional allow-all context was added. Legacy
tests that depended on unauthenticated fixture mutations may now fail at this
earlier boundary; that is recorded as an actual changed failure, not erased by
skip/xfail or claimed as successful downstream behavior.

## Execution provenance

Selected environment: CPython 3.12.14 with its actual built-in SQLite 3.53.1,
source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No added SQLite library/binding, spoofing or second-engine matrix was used.

Frozen baseline #141 reproduced I4 **217 PASS**, I5 **29 PASS**, and the exact
3137-node historical broad cohort **3058 PASS / 59 FAIL / 20 ERROR**, with zero
skips/xfails. All 79 inherited unsuccessful nodes remain unsuccessful in the final
run, but this is not equivalent downstream behavior: 21 move from call failure to
setup error. The exact phase, causal exception, raw message, source frames and
reached assertion comparisons are retained in
`final-v3/inherited-79-node-phase-exception-assertion-map.json` (possibly gzip).

The dedicated implementation cohort passes all 217 I4 nodes, all 29 I5 nodes and
62 new admission integration nodes. The actual second-INSERT trigger observed one
Event and one endpoint before failure, then zero/zero after rollback. Deferred
COMMIT observed one Event/two endpoints with live policy leases and failed with
`SQLITE_CONSTRAINT_FOREIGNKEY`; explicit rollback cleared all new rows. Original
Parent time 51 and preexisting evidence remained unchanged. Initial raw traces:
[sql-admission-probes.json](raw/sql-admission-probes.json); final frozen-source
serial re-execution is under `final-v3/sql-probes/`.

The final executable freeze is `770e42d4828238cc0001c96663d078605ac44841`,
tree `9769a431eed95b841c9ac2d5a54a83ea248fc5be`. Clean detached source,
independent artifact lanes, exact-node/phase comparisons and hashes bind to that
freeze. Detailed commands, exits, timing and reconciliation are in
[VERIFICATION.md](VERIFICATION.md). The Draft PR body binds the later
evidence-only publication HEAD/tree externally; a Git tree cannot embed its own
final hash. Publication does not claim full Author acceptance.

## Independent review handoff

Freeze the final implementation HEAD/tree from the new Draft PR. Re-execute
foreign allow-all handle and forged principal attacks on initial admission and
exact replay before lookup; verify no foreign policy call/no row delta. Inspect
all public mutation carriers, including reserved field OIDs and scope Sources,
current mapping/Disposition reads, permission-before-selection precedence,
lease ownership through actual commit, input bounds and SQL failure traces.
Independently test both distribution forms outside checkout. Review the actual
full-suite delta and earlier failing phases; passing focused checks do not accept
unexecuted I6-B/C/I7/I8 behavior. Material corrections require a new freeze and
review. Independent acceptance remains NOT RUN.

Before claiming broad regression acceptance, review every remaining unbound
caller against the concrete per-node trace: synthetic callers need finite local
test authority without changing their original assertions; real application
callers need trusted composition at their assigned integration stage. Do not
solve either category by accepting a caller's principal/policy as authority.
Provider/Exchange connection requires separately scoped I6-C implementation;
this report requests no new owner design decision or redundant publication
permission. Existing deeper query/recovery/Exchange assertions that failed
earlier remain unverified.

## Corrective Author freeze after first broad execution

The first source freeze was executed honestly and retained: 5919 ordinary nodes,
5154 PASS / 341 FAIL / 424 ERROR, zero skips/xfails. This is a failed broad run,
not full Author acceptance. All 686 additional nonsuccesses were classified by
actual traceback and diagnostic exception events: 492 fixture migrations, 62
coordinator authorization-lifetime gaps, 127 actual explicit unconnected I6-C
guards, 2 exact-module audit regressions, and 3 additional ENOSPC failures. The
full initial run also encountered 5 environment-affected packaging nodes, some
already in the historical unsuccessful set. The first run remains unchanged.

Recoverable in-scope corrections were made before the new final freeze:
constructor-bound coordinator authority and commit-owned lease bridge; real
capability expiry, foreign-service refusal and export/write separation; guarded
cursor close; genuine `p1_coverage.CoverageClaim` dependency enumeration; exact
classification of the three new opt-in modules in the source ownership audit,
with additional import-detection and future-prefix negative controls. No
permissive fallback or Provider/Exchange route was enabled.

The existing coordinator fixture now supplies explicit finite Resource, Provider,
Repository and OID authority, including subprocesses and deliberate invalid-pair
fixtures. Its 24 test functions/parametrization and all 63 assertion ASTs are
unchanged; all 46 collected nodes pass, reaching their original cross-store,
crash/cut, rollback and Recovery Stop assertions. The combined corrected focused
run passed **577 nodes** (exit 0), including all 217 I4 and 29 I5 nodes, Parent
and new secure-admission/bridge tests, and source ownership audits.

Final full-suite and distribution executions bind their actual distinct commits
and retain their own outcomes. Initial direct and sdist-wheel distributions each
passed 488 tests outside checkout, but those earlier artifacts do not alone
accept the material coordinator correction. Full Author validation remains
INCOMPLETE because broad-suite failures remain; non-Author I6-A acceptance is
NOT RUN.

A final R12 counterexample found that an authorized/selected permanently
ineligible I8 Transfer with an unavailable Source returned `MISSING_DEPENDENCY`
before `QS10_PARENT_INELIGIBLE`. Two initial/replay cases failed, while the four
permission/selection precedence controls passed. The shared guard now checks pure
native eligibility after current authority/selection and before Source lookup;
all six cases pass without dependency lookup or mutation. A preliminary test
fixture with stale endpoint report references was corrected before this valid
counterexample; its failed output is preserved separately. The complete focused
source cohort is **583 PASS** (exit 0), with no skips or xfails. This material
final freeze has its own clean full-suite, SQL and distribution executions;
intermediate #143/cc6 evidence is not silently rebound to it.

Final direct-wheel and sdist-derived-wheel runtime cohorts each pass **551/551**
(exit 0, 35.131 / 35.268 seconds). Each has a separate venv and copied tests
outside checkout; product imports resolve to that venv's installed package, and
source-to-wheel and wheel-to-installed product hashes match. Both wheel bytes
have SHA-256 `83e9795875d58da753d7c9f76e9eb2c47e2eaafb70e079f581e59760ad5367c3`;
the inherited 84,133,424-byte sdist has SHA-256
`b5c7bac36796b73b9c3717881d5936706b8a01282a315aaf81f86b26db480de2`.
This is the inherited packaging contract, without ADR 0033 integration. Final
serial SQL rollback/revocation probes pass **3/3**. Ruff check and format checks
pass (435 files). Product/DDL/safety hashes are in
[final-product-safety-hashes.json](raw/final-product-safety-hashes.json);
all 156 measured product files match frozen Git bytes, while Accepted ADRs,
DDL/schema fingerprint inputs and historical I5/I6 evidence match the base.
Both installed lanes observe Context schema fingerprint
`924cc7557fb3da6211ea070185881f5fcaeff9bf52b6e237a361a238a2ea0c6e`,
the exact two packaged Transfer fence definitions, `integrity_check=ok` and no
foreign-key-check rows.

## Final broad-suite result

| Frozen source and scope | PASS | FAIL | ERROR | Exit |
| --- | ---: | ---: | ---: | ---: |
| #141 historical 3137 nodes | 3058 | 59 | 20 | 1 |
| #141 disjoint remaining 2605 ordinary nodes | 2605 | 0 | 0 | 0 |
| Initial `30888b6` ordinary 5919 nodes | 5154 | 341 | 424 | 1 overall |
| Final `770e42d` historical 3137 nodes | 2394 | 324 | 419 | 1 |
| Final `770e42d` disjoint remaining 2804 ordinary nodes | 2804 | 0 | 0 | 0 |
| Final `770e42d` complete ordinary 5941 nodes | 5198 | 324 | 419 | 1 overall |

The final historical and remaining executions took 130.274 and 470.607 seconds.
Dedicated focused/artifact/SQL cohorts overlap the ordinary inventory and are
not added to that aggregate. Two collected live/benchmark nodes are explicitly
unexecuted. All 79 inherited unsuccessful node IDs remain unsuccessful; 664
additional nodes remain unsuccessful. Initial-to-final comparison resolves 22
initial unsuccessful nodes and introduces no newly unsuccessful historical node:
18 coordinator cases, two module audits and two formerly ENOSPC-affected P4
distribution cases now pass. This comparison is node/phase/assertion based,
not a claim that failure counts alone prove compatibility.

The final clean source retains all 471 measured executable/configuration inputs
unchanged. Selected-node union, JUnit nodes and journal starts match exactly once.
Actual report-class sidecars reconcile every raw phase, all ordinary phases and
57 additional passing unittest subtests. The inherited helper's duplicate-call
predicate remains false for the remainder; its original output is not overwritten
or represented as strict phase PASS. Typed accounting is the separately measured
correction described in [README.md](README.md).

All five initially environment-affected packaging nodes were retried with safe
workspace capacity. Final execution has no ENOSPC failures. The remaining three
packaging nodes reached actual application/authorization failures (two were
already inherited nonsuccesses); an environment repair does not turn those
outcomes into passes. Initial bootstrap, interrupted and capacity-failed outputs
are retained separately and excluded from completed-run aggregates.

The final **664 additional unsuccessful nodes** are classified from their actual
raise frames, not file names or the `PERMISSION_DENIED` string:

| Category | Nodes | Concrete boundary / required work |
| --- | ---: | --- |
| Unbound direct Context/ContextStore callers | 490 (378 setup, 112 call) | Shared `authorized_write` rejects absent local service; e.g. `p1/test_coverage` reaches the old `p1/test_context.py` fixture setup. Review and migrate synthetic callers to finite issued authority while preserving original assertions; inspect real callers individually. |
| Coordinator callers missing explicit authority | 47 call | `PairCoordinator.admit` callers, including installed P6 query/CLI fixtures, do not bind constructor service and invocation. The corrected authorized API/lease bridge passes its 46 original coordination nodes; remaining callers still need explicit wiring. |
| Explicit unconnected I6-C routes | 127 call | `ProviderAcquisition._open_context`, Context-bearing Exchange import/export refuse. Examples include `test_provider_registration_is_explicit` and `test_core_first_context_second_and_failure_retry_convergence`; external trace-only repeats prove both caught errors originate at `_open_context:1111`. Real composition belongs to I6-C, not an allow-all fallback. |

There are **zero unclassified additional failures**, zero remaining
environment-only failures and zero remaining module-audit regressions in this
measured classification. That does not assert the 537 missing-authority callers
will pass after migration, or that their deeper Query, Recovery, SQL or Exchange
assertions ran. Concrete per-node frames/messages, first failure phases and
exceptions are under `final-v3/additional-failure-classification.json` (possibly
gzip); the two intentionally failing diagnostic repeats are separate under
`final-v3/caught-guard-traces/`. Final full Author acceptance requires disposition
and verification of these remaining callers/routes and all inherited failures.

## Hosted development CI checkpoint

On source `770e42d`, hosted `offline` and `sqlite-policy` pass; `registry-runtime`
fails. Its original I4 and I5 cohorts independently pass **217** and **29** nodes.
Its dynamic historical selection contains 3142 nodes and reports **2399 PASS /
324 FAIL / 419 ERROR**, exit 1, with strict selected/JUnit/journal reconciliation.
Those are separate hosted receipts, not the local frozen 3137-node cohort. The
inherited Access installed smoke scripts fail on unbound Context authorization,
despite the separate final 551-node installed lanes passing; neither outcome
replaces the other. Hosted Python is 3.12.15 with its actual SQLite 3.53.1.

The source CI merge commit is `c5ccec63adb3c5b5134458acc113024a1ea9abcb`.
[Checkpoint](raw/hosted-final-source-checkpoint.json) and
[line-numbered inspected log excerpt](raw/hosted-final-source-registry-excerpt.json)
retain source/runtime/result bindings. The connector fetched the complete remote
log. CLI persistence of its redirected download returned Forbidden and was not
retried; the receipt records that failure with temporary signed URLs redacted.
No complete raw hosted log or green runtime CI is claimed. Final evidence-only
publication checks are recorded separately in the PR body.
