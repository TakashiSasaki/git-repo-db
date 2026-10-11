# Phase 2 evidence ledger

This ledger separates the investigated baseline, proposed-model checks, focused
development receipts and submitted-tree acceptance. No proposal is accepted by a
successful probe, documentation PR, test run or merge of unrelated work.

## Baseline and scope

Latest main was fetched before investigation:
`20e0f8d78b77c6c8d37826fd6d639819631e166b`, tree
`003d276a6aeb6a1479232a1d0a1857db371cb623`. There were no open PRs. The accepted
transport-independent ADR and Phase 1 retirement decision are dated 2026-10-10;
main includes the decision-authority guide from PR #21. The actual composed
Schema 18 fingerprint is
`16110944d4b6a0942657644fe80383394210af1218a3e7111e331a1651fa211e`.

Python 3.12.14, SQLite 3.53.1 and uv 0.12.19 were measured locally. The inventory
executes complete packaged schema composition in memory, prepares all 48 views
and 309 table mutation shapes under SQLite authorizer observation, checks
generated JSON guards, and records FK/integrity results. Its production table
counts are 103 tables, 665 columns, 226 FK constraints, 498 triggers and 106
explicit indexes. Static AST references are labeled candidates, not live call
proof. Dynamic SQL and unresolved call edges are retained as limitations.

Every production table has a conditional semantic disposition and typed-FK
dependency map. Native dependent SQL objects and audited source sites are
machine-linked. The compressed source inventory has an uncompressed SHA-256;
`audit_phase2_design.py --check` validates that binding and all table coverage.
Generated artifact revision metadata describes the actual generation checkout,
including dirty status; it is not a clean submitted-tree acceptance receipt.

## Reproducible design checks

Run from PR A's checkout after `uv sync --locked --group dev`:

```sh
uv run --no-sync python scripts/audit_phase2_dependencies.py --output artifacts/dependency-inventory.json --source-output artifacts/dependency-source.json.gz
uv run --no-sync python scripts/audit_phase2_fields.py --check
uv run --no-sync python scripts/audit_phase2_design.py --check
uv run --no-sync python docs/phase2/prototypes/candidate_probe.py
uv run --no-sync python docs/phase2/prototypes/independent_schema_attacks.py --ddl docs/phase2/prototypes/candidate.sql
uv run --no-sync python docs/phase2/prototypes/independent_candidate_validation.py --prototype-dir docs/phase2/prototypes
uv run --no-sync python docs/phase2/prototypes/independent_counterexamples.py --prototype-dir docs/phase2/prototypes
uv run --no-sync python docs/phase2/prototypes/completeness_probe.py --threads 10000 --output artifacts/completeness.json
uv run --no-sync python -m pytest docs/phase2/prototypes/test_acquisition_characterization.py
uv run --no-sync ruff check src tests scripts docs/phase2/prototypes
uv run --no-sync ruff format --check src tests scripts docs/phase2/prototypes
```

Use `--help` for publication and Exchange production probes: both require an
explicit **new disposable** `--state-dir`. They create synthetic catalogs and
must never be pointed at retained user state. The acquisition pytest fixture
blocks external traffic, uses loopback HTTP and synthetic Source registrations.
`python -m pytest` is intentional: a failed earlier invocation of the `pytest`
entry point could not import the checkout's `tests` package and ran zero cases.
That setup error is not passing evidence.

The integrated candidate is a 69-table STRICT SQLite sketch. The current probe
has 17 grouped adversarial scenarios; its receipt records exact SQL/probe hashes,
actual table counts, FK/integrity, and limitations. SQL/probe changes invalidate
older fingerprints, which remain labeled historical review checkpoints.
Independent scripts construct their own ownership, timestamp, identity, scalar,
field-origin and digest attacks. The generic completeness fixture deliberately
admits unmodeled wrong-family/natural-parent substitutions; independent probes
record those counterexamples rather than hiding them. The integrated typed
collection validator corrects those modeled bindings.

The integrated sketch does **not** implement exact publication-seal admission and
immutability, full current-resource admission and all current lists, Source/code/
Git family validators, final parser/field vocabulary or normalized Exchange trust.
The independent validator reproduces the unimplemented publication-seal boundary.
These are requirements for eventual production implementation, not successful
checks or an approved production replacement.

## Focused production correction evidence

[Independent review](independent-review.md) and its JSON receipts bind each
development test to its actual source revision, tree, fingerprints, node IDs,
bootstrap flag and outcome. Focused counts overlap; they must not be added into
an asserted unique acceptance total. The untouched baseline independently passed
301 cases without bootstrap.

| Determined change | Source revision | Focused evidence and limit |
| --- | --- | --- |
| Conflict-free Exchange refresh | `c8180e79acced221f9b7c3f3717388b7fb022721` | Independent 40 no-bootstrap cases; two changed-definition fixture failures then two explicit-bootstrap passes. Operation counts: 4 refresh statements at 0/256/1024/4096 unrelated objects; selected export remains 223. |
| Omitted author fields | `c6a54666688b2d72888686efca5f1b10b9efca86` | 70 new actor-presence cases; explicit NULL remains distinct from missing login. |
| Omitted nested parent/target fields | `835b3309f6eff1c7192376ec7147c63983e7470e` | 72 new nested-presence cases; independent combined fields/projection/conflicts 176 pass without bootstrap. |
| Partial acquisition clocks and restart fences | `6edc217ec4f673fbf10056e2e4436507c8a1a5d2` | Independent 22 new cases without bootstrap; 196 broader cases with development bootstrap. Rejected known resource200, stale retry175, equal200 and valid300 remain distinct. |
| Historical collection proof boundaries | `b5fa28e42ab04a15a135c651f9dab3fdaaa6f057` | 26 new adversarial cases; independent 24 static cases without bootstrap and all 54 focused cases with bootstrap. Legitimate accepted-error GraphQL retry, typed rawless children and separate 304 proof survive. |
| Result-led publication indexes | `a94dd50906a7918f84e66f2623dcef977cd93b76` | Independent eight cases without bootstrap; actual publication sealing uses 1,088 VM steps at both 100 and 2,000 unrelated histories, versus 3,329/45,151 after removing only seven indexes. |

The nested completeness fixture uses 60,005 indexed verification statements for
10,000 children. These are operation-count characterizations. Concurrent wall
times and unrelated workload setups are not clean comparative benchmarks.

## Submitted-tree acceptance

PR A includes executable audit tools, four meaningful ordinary audit tests and
disposable prototypes; its production Schema 18 remains unchanged. PR B integrates
only the independently settled corrections, updates the active schema fingerprint
for seven indexes, and regenerates the still-required historical built-in
certificate from a frozen definition and successful synthetic capability tests.
Certificate retention here does not approve it as a permanent architecture.

For each submitted code-bearing tree, complete applicable acceptance means fresh
schema/JSON/FK/integrity and view/trigger tests, Ruff, ordinary offline integration
and end-to-end tests, Coverage/collection/Exchange/CAS adversarial tests, sequential
isolated wheel/sdist installs, and CI selection/result reconciliation. Final
acceptance must run without `REPO_CATALOG_TEST_BOOTSTRAP`.

The PR bodies and hosted `ci-profile` artifacts record the **actual final feature
SHA, effective tested tree, selected/executed counts, gate result and hosted run
URL**. They are populated only after execution. This ledger's design/development
receipts do not claim that outstanding final acceptance or hosted CI already
passed. Appending test claims before execution would be false evidence.

No authenticated production collection, retained catalog mutation, private data,
new retention/deletion policy, PR merge, release or deployment occurred.
