# I6-A secure Context admission — Author implementation evidence

This is Author verification, including supporting Author-side adversarial
analysis. It is not non-Author independent acceptance. Normal Transfer remains
staged. Both packaged SQL fences and all DDL/fingerprints remain unchanged.

## Fixed ancestry and scope

Implementation starts directly from PR #141 commit
`dc6e663ea90e55210ed5674cae6c332f66a4ac18`, tree
`3d70218ecf98f751eb550e6a328a21f65069066f`, on
`impl/adr0031-i6a-secure-admission`. The new Draft PR's base must be
`review/adr0031-i6-design-independent-20261023`. Design #134 is
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
  Normal reopening, Store/Facade and Transfer routes remain refused.

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
`Context.owned_transaction`. Caller-owned coordinator transactions cannot retain
leases through their outer COMMIT yet, so writes through those unwired paths
fail closed. Raw SQL handles remain trusted infrastructure outside input APIs.

Provider Context intake and Context-bearing Exchange import/export are explicitly
unconnected until I6-C. Exchange refusal precedes progress/receipt duplicate
shortcuts; bounded parsing work already performed is still charged. Core-only
Exchange remains separate. No provisional allow-all context was added. Legacy
tests that depended on unauthenticated fixture mutations may now fail at this
earlier boundary; that is recorded as an actual changed failure, not erased by
skip/xfail or claimed as successful downstream behavior.

## Executed checkpoints and pending final receipts

Selected environment: CPython 3.12.14 with its actual built-in SQLite 3.53.1,
source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No added SQLite library/binding, spoofing or second-engine matrix was used.

Frozen baseline #141 reproduced I4 **217 PASS**, I5 **29 PASS**, and the exact
3137-node historical broad cohort **3058 PASS / 59 FAIL / 20 ERROR**, with zero
skips/xfails. Historical unsuccessful node IDs, phases, causal exceptions and
reached assertions are being compared with final execution separately.

The current dedicated implementation checkpoint passed all 29 I5 nodes and 62
new admission integration nodes. The actual second-INSERT trigger observed one
Event and one endpoint before failure, then zero/zero after rollback. Deferred
COMMIT observed one Event/two endpoints with live policy leases and failed with
`SQLITE_CONSTRAINT_FOREIGNKEY`; explicit rollback cleared all new rows. Original
Parent time 51 and preexisting evidence remained unchanged. Raw traces and
observations: [sql-admission-probes.json](raw/sql-admission-probes.json).

Full final source, artifact, node/phase comparison, exact source/DDL/fingerprint
hashes and publication bindings are separate receipts added after this source
freeze. These scopes are not yet declared complete in this checkpoint. The Draft
PR body binds actual tested source commit and final evidence HEAD/tree externally,
since a Git tree cannot embed its own final hash.

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
