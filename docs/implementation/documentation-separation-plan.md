# Documentation separation: SEP0 checkpoint

Status: proposed design, no files moved and no CI/environment behavior changed.
Baseline: `e868805bfc1dc564ec2ce07f88e02fea04fe34e4`, tree `1a94f483b6a465ffc4a1e11fa8f3139b001b6b3d`.
ADR allocation checked index, reachable history and all 130 fetched origin refs: highest existing ID 0034; allocate 0035.

## Concrete coupling and retained authority

`audit_implementation_boundary.py` imports `introspect_all` from `schema_viz`; it consumes mechanical IR and DDL evidence. The renderer has no MkDocs import. Root runtime dependencies already exclude MkDocs, but local setup and Access install the docs group; Access also runs the docs build. Root `mkdocs.yml`, `overrides/**` and `docs/site/**` are CI shared inputs. Unknown paths conservatively remain product inputs. ADR0034 additionally fingerprints root regular files and actual backend configuration; do not add documentation exceptions to hide real build inputs.

The ledger enumerates exact move candidates and explicit boundary/machine files with source hashes, plus retained scopes. Its role is not permission to relocate whole directories. Contracts, ADRs, implementation/phase2 machine JSON and historical evidence stay put. Schema outputs are derived but some are consumed as product verification evidence: retain their current locations until all consumers are mapped. Existing public allowlist stays unchanged.

## Dependency-aware PRs

1. SEP0: this small Draft design/role/node-ledger PR. Proposed policy only; independent design review and explicit adoption remain separate.
2. SEP1: neutral `scripts/schema_inventory.py` extraction, product audit imports and structural safety tests. Preserve IR and byte-level generated evidence; no renderer moves in parallel.
3. SEP2: isolated `documentation/` project, own lock/environment/build outputs, pinned source/IR provenance and existing allowlist. Initially additive; do not edit/move SEP1-owned files concurrently.
4. SEP3: after both prerequisites, move renderer/site tooling and designated tests, switch collection, imports, environment groups and existing Pages/Access paths. Explicit docs-only classification leaves unknown/root/machine changes conservative. Preserve producer input fingerprints and efficient equal-input reuse. Product integration must not wait on docs; full release accounting reports the union of old obligations in separately named scopes. Final receipt/label semantics require design review before this cutover, never silently shrink complete release acceptance.
5. SEP4: parent-assigned independent adversarial review at a frozen commit: broken MkDocs/rendering/missing docs dependencies leave product verification functional; real SQL/contract/fingerprint faults still fail; docs-only changes avoid product rebuilding without cache bypass; old/new node accounting is exact, including split mixed tests. Strict 43 inherited Transfer non-successes remain non-successes, with zero unexplained node/outcome changes.

## Evidence and limits

Baseline targeted collection collected 28 nodes; no tests executed by collection. Proposed node targets are a design, not an executed migration. Mixed structural/rendering tests split rather than losing either assertion set; their exact assertion coverage must be reviewed during SEP1/SEP3. No broad suite, install or deployment in SEP0.

Main protection GET previously returned HTTP403 `Resource not accessible by integration`; no retry or bypass. Branch metadata reported unprotected and rulesets empty, which do not prove all required-check settings are known. No setting changes are authorized. No new owner product-semantics decision is requested; proposed ADR adoption and explicit full-release receipt semantics are the remaining workflow decisions before cutover.

## Review corrections: explicit producer/consumer obligations

The ledger now lists producer, consumer and cutover action for root `mkdocs.yml`, the SQLite-policy scanner, Development workflow, release executor and broad offline verifier. Root MkDocs configuration is currently a real root build/CI input; move its responsibility into the nested documentation project only at coordinated cutover, without weakening the backend-input fingerprint. The policy scanner explicitly includes `docs/site/development/index.md`: relocate that allowlisted scan target with the page and prove forbidden SQLite instructions remain detectable. Neither a moved page nor a relocated test may disappear from policy coverage.

`tests.yml` drives product planning, collection, execution, schema-map comparison and receipt generation through `ci_execute.py`. Its product-scoped success cannot silently acquire complete-release meaning after removing documentation nodes. `verify_i5_offline.py` currently collects documentation tests among broad cohorts and requires dev+docs dependencies; split its scope explicitly with exact old/new accounting, preserving strict43 Transfer reconciliation and distinguishing I5 evidence from release approval. No change to these executables is made in SEP0.

### Neutral inventory boundary

Retain complete SQL and fingerprints for tables/views/triggers/indexes, composite FK sequence, generated-column classification, partial-unique predicates and present three-store coverage. SQL-null autoindexes retain their existing meaning. Presentation annotations may remain for compatibility, but HTML's truncated deep copy is never the neutral source. Structural tests run against the neutral producer without importing renderer/MkDocs/YAML; renderer tests consume an unchanged complete IR.

### Proposed complete-release semantics

Ordinary product checks/merges are independent of rendering. Complete release acceptance is the conjunction of independently executed local/hosted product and documentation obligations, exact node replacement and matching selected product source/IR provenance. Product-only green is reportable while docs are unavailable, but never sets `full_acceptance=true`. Documentation source SHA/tree, selected product SHA/tree and neutral IR digest are separate fields, with input/artifact hashes and execution evidence. Differing documentation/product commits are expected; missing/mismatching selected-source or IR provenance fails the aggregate. New labels and receipt changes await owner adoption before SEP3.

### Planned boundary and release tests (not executed here)

- Scan the relocated development page with prohibited SQLite download/swap instructions; require the same policy rejection. Missing required live policy input must fail rather than silently reduce coverage.
- Break MkDocs config, renderer or docs imports: product audit/SQL tests and ordinary product CI stay executable; documentation checks fail independently.
- Mutate SQL/contract/fingerprint inputs: neutral inventory and product gates reject; docs-only classification must not conceal them.
- Compare exact pre/post node multisets including one-to-many splits; every old structural and rendering assertion has a destination. Offline broad scope retains43 known non-successes and zero unexplained outcome/node gaps.
- Product-only pass plus absent/failed/skipped documentation locally or hosted never yields complete/full acceptance. All required local/hosted obligations with matching provenance may satisfy the aggregate; one missing context does not.
- Reject changed IR digest, selected product tree mismatch, missing artifact hash or reused stale evidence, even when docs source commit is valid. Accept distinct docs/product source identities only with verified matching selection.
- Docs-only edits avoid unnecessary product rebuilds; genuine root/backend/machine/unknown changes still invalidate/select product verification. Check producer inventory remains complete after HTML generation.
