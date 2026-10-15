# P3 executable Context implementation brief

Status: depends on owner review of the P1 stacked PR. P1 depends on PR #70 at
`eb84be9b2061b026ad82b780cc95e062928f838a`. Use the PR's exact accepted P1 feature
SHA/tree, fingerprints and review/evidence binding. P3 can implement independently
of P2 once those contracts are accepted. This brief authorizes no merge, catalog
migration, release or P8 production initializer switch.

## Stable inputs and first commands

Read [P1 contracts](p1-schema-contracts.md), [the physical disposition ledger](p1-disposition.json),
`p1_ddl/context.sql`, shared `coverage.sql` and the composed schema identity/guards
in `p1_schema.py`. The packaged fingerprint manifest identifies actual target DDL
and executed SQLite constraints.

```sh
uv sync --locked --group dev
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync pytest tests/integration/p1/test_context.py tests/integration/p1/test_coverage.py tests/integration/p1/test_coordination.py tests/integration/p1/test_derivatives.py -q
```

Use only disposable synthetic data. This is focused development validation, not
release acceptance. Stateful CLI experiments require a disposable `--state-dir`.

## Contracts and implementation work

`domain/p1_context.py` defines `ResourceKey`, `FieldClock`, `FieldCandidate` and
Context `CoverageScope`. Shared Coverage claim/projection value types have neutral
ownership. `domain/ports/p1_context.py::ContextAdmission` fixes `resource`, `text`,
field admission/candidate reads, current repository membership, scope, Coverage
admission/read and portable Core linking. `adapters/sqlite/p1_context.py::ContextStore`
is the executable reference. Context methods participate in a caller-owned local
transaction; internal savepoints keep candidate-set replacement and reads coherent.
They do not commit the coordinator's outer transaction or acquire Git closure.

Implement Provider, Source, PR, Issue, review/thread/document and related current
Context behavior against that schema. Provider IDs retain their real service
namespace. Ordinary Issue identity is independent of repository membership and
Source registration; detached resources are valid. Reviews/documents use actual
parent PR, kind and provider document identity with normalized local ownership
checks. Text uses exact UTF-8 SHA-256 identity with collision equality checks.

Keep each current field's actual original clock/provenance/observation. Missing
is absent evidence; explicit null is a candidate. Comparable newer clocks replace
only dominated current candidates; equal or incomparable clocks retain alternatives.
Never substitute local processing time or a receiver verification conclusion for
a genuine source observation. Repository transfers change current evidence,
preserve Issue identity and do not rewrite original captures. Do not recreate a
full normalized Provider edit history or retain API originals as pending state.

Source associations are durable known-positive pairs. Partial or empty inventory
cannot delete or rebind an existing pair. An empty Source inventory has actual
source/scope/terminal evidence without a fabricated repository or Provider resource.
Coverage uses exactly five physical authoritative claim columns and the full
semantic owner/time/state key. Details are advisory. Use the latest observation's
entire candidate set; unknown/partial never borrow an older complete result.
Real complete empty terminals differ from no terminal. Child, collection, field,
Source and exact head/base scope proof must match the requested coordinates.

## Portable Core references and partial availability

Context references use full typed OIDs plus real resource/role/provenance, with
local FKs for Context ownership and explicit cross-store dependency validation.
Never import a sender's verified flag as local Git authority. Standalone Context
remains durable without Core; a read requiring absent Core reports that dependency
unavailable. Core remains valid without Context. Losing Context is never treated
as disposable reconstruction.

Use `PairCoordinator` for Core-first/Context-second admission, explicit partial
success after a committed Core unit and identity-preserving retry. Bind typed
Context operations to its caller transaction. Paired reads use both pinned
snapshots; no ATTACH atomicity assumption, mutable Core revision or append-only
counter history. Search tokens bind actual snapshot content and instances;
missing/stale/corrupt Search falls back to direct Context or paired authority reads.
Operational loss cannot erase candidates, Source positives or Coverage; lost old
request accounting fails closed instead of resetting cumulative work.

Catalog-wide corruption stop survives Operational/Search loss. P7 owns fresh
verified restore, untrusted typed salvage/merge and activation; P3 does not clear
stops, repair Core bytes in place, add quarantine counts or claim recovery is
implemented by Context restart.

## File ownership and review

P3 owns new production Context/Provider adapter modules, `domain/p1_context.py`,
`domain/ports/p1_context.py`, `adapters/sqlite/p1_context.py`, Context DDL and focused
Context/Coverage tests. P2 owns Core modules/DDL/tests. Both consume the frozen
neutral Coverage, schema/fingerprint and coordination contracts described in the
[P2 ownership brief](p2-git-core-handoff.md). Neither stage independently edits
shared `coverage.sql`, schema composition/fingerprints or coordination interfaces.
Necessary shared changes are a coordinated dependency commit with affected
contracts rerun. P5 composes acquisition/Exchange; P6 public query/Search; P7
backup/recovery; P8 initializer and complete runtime switch.

Retain P1 regressions and add production cases for field-level inherited evidence,
null/missing, incomparable/equal clocks, transfer/detachment, exact parent document
ownership, current-set rollback/restart, source-positive partial scans, latest
Coverage including unknown/conflict/known-empty, nested/head/base proof, reverse/
repeat transfer, actual paired commit cuts and derivative loss/reconstruction.

Independent read-only review subagents should inspect both source and actual
executed evidence. They must not modify or approve their own implementation.
Correct material findings and obtain independent revalidation on the exact
feature SHA/tree. Submission is for owner review, without auto-merge or release.
