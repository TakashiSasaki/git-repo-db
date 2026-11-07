---
status: proposed
date: null
replaces: []
refines:
  - 0017-domain-keys-without-storage-surrogates.md
  - 0035-independent-documentation-workspace.md
  - 0037-operation-scoped-module-independence.md
  - 0039-independent-filesystem-and-worktree-catalogs.md
---

# ADR 0040: Scoped machine-readable models and validation evidence

## Decision

**Proposal for owner review, not an accepted guarantee or a new CI gate.** The
owner requested analysis, a work plan and progress on 2026-11-07. That authorizes
the bounded inventory work and this proposal; it is not recorded as acceptance
of the semantic-validation architecture. No retained instance is changed.

Build semantic validation on the existing source-bound SQLite schema IR. Keep
implementation facts, accepted design obligations and executed evidence distinct.
Use a versioned, optional RDF projection and SHACL constraints for a selected
scope; add small operation-state models separately. Neither an ontology service
nor a reasoner becomes a product/runtime dependency or the owner of product DDL.

The model distinguishes the following layers:

| Layer | Identity and meaning |
| --- | --- |
| Responsibility domain | Core, Context, Access, Operational, Search, Filesystem, Worktrees; this does not make Search authoritative or Operational wholly disposable |
| Implemented format | Source revision, schema family, store role, actual format/version representation and DDL fingerprint |
| Module / distribution / source | Code composition, canonical source-file ownership, mandatory and optional install requirements |
| Operation | Selected capability, input scope, required implementations/instances/identity checks and permitted partial outcomes |
| Instance / observation / claim | Qualified identities, selected observation interval, provenance and available validation scope |
| Constraint / evidence | Stable constraint ID, authority citation, implementation mapping, check type, result and unassessed scope |

Use different relations for physical same-file FKs, qualified external references,
operation preconditions, data derivation and code/install dependencies. Unique
source ownership does not require a single distribution to supply every part of a
composed schema. Do not introduce one generic `dependsOn` relation with all these
meanings. Treat authority, history retention, mutability and reconstructibility as
separate properties; the inventory alone does not derive them.

### Reference and observation contracts

1. Always check a supplied reference's own required components and representations.
2. Check its target only when the selected operation has the necessary target and
   scope. An unavailable optional Filesystem/Core instance yields `unresolved`,
   not corruption; an operation requiring that instance may instead refuse for
   missing capability. Record which case applies.
3. Preserve qualified composite keys and ordering. Encode raw path bytes losslessly
   with an explicit encoding; preserve UUID forms, units, NULL/missing distinctions
   and original observation scope. No Unicode normalization, case folding or
   cross-scan backfilling is implied by RDF conversion.
4. Keep revisions, schema families, observed times and attributed claims separate.
   Select explicit scopes before combining them. A named graph alone supplies no
   temporal meaning. Conflicting observations at different times are not, by
   themselves, logical inconsistency.
5. Preserve ADR 0039: a persisted Filesystem scan remains independently valid when
   execution stops before Worktrees records its link. No cross-DB transaction,
   required paired backup or automatic Core identity inference is added.

### Validation results

Maintain separate result types for data/shape conformance, specification
satisfiability, bounded operation invariants and implementation conformance.
Do not collapse them into a global `verified` flag. Design acceptance creates an
obligation, not implementation or execution evidence. Ordinary tests and agent
reviews do not constitute formal proofs.

Every result identifies source commit/tree, profile, schema/input/IR digests,
constraint IDs and authority citations, engine/version/profile, expected and actual
target counts, evaluated scope, skipped/unsupported constructs, timeouts and other
limitations. Model-check results additionally identify constants, assumptions,
explored states and bounds. A proof receipt identifies both its theorem/logic
scope and any unproved translation boundary.

A required check passes only with the expected extraction/constraint coverage and
a supported definitive result. Missing targets, skipped required constraints,
unsupported features and timeouts are not successes. Legitimately empty instance
data is declared explicitly; this never excuses missing schema/operation targets.
Validate both positive witnesses and intentionally broken cases. For an optional
external reference, unresolved target data is not a negative conformance result.

## Constraints / Do NOT

- Do not replace SQLite/admission checks with OWL keys or treat open-world absence
  as false. OWL name equality, SHACL counting and SQL uniqueness are distinct.
- Do not translate SQL CHECK to two-valued logic silently: SQLite permits NULL
  results. Retained SQL/triggers and registered UDFs remain unformalized until a
  supported translation and its limits are demonstrated.
- Do not infer complete OWL 2 DL reasoning, a proof or all possible executions
  from a partial reasoner, missing checker, successful plan trace or bounded test.
- Do not load repository/instance data into a shared ontology store as an implicit
  side effect of checks. Prefer local files or isolated request-scoped graphs.
- Do not change normal Schema 21 activation, seven-domain boundaries, independent
  packages, existing stop/recovery/budget obligations or public documentation
  selection through this tooling proposal.
- Do not add Windows, SQLite-version matrices or release gates to ordinary work.
  Use the environment's verified Python/loaded SQLite under ADR 0032; report the
  actual version, not a newly invented cross-environment pin.

## Context & Reason

Level 3 applies to the proposed long-lived, cross-module semantic/evidence
contract and future mandatory validation interpretation. It does not turn a
read-only inventory extension into a new product architecture decision. That
reversible engineering increment is independently reviewable in
[PR #256](https://github.com/TakashiSasaki/git-repo-db/pull/256).

The external assessment used main `573cd15`; the investigated main was
`071ba740b91edfabdef2884d1f371e0b9326bbb2`, after #245–253 and #255 merged.
The independent distributions are now integrated. There are seven responsibility
domains, fifteen distributions and ten implemented schema definitions, not seven
mandatory startup files. The normal renderer still covers three formats.

The first inventory commit, `9f0aea2f3c7d179a96060d375a75a1b0af8f42b5`, extracts
156 table definitions across those formats, preserves normal-profile output and
separates P1's Runtime assembler, domain DDL and Contracts coverage contribution.
Its [guide](../../documentation/schema-model-inventory.md) states the structural
checks and remaining semantic gaps. It does not implement this proposed ontology.

A request-scoped Open Ontologies experiment on that commit's ten composition
records produced: ten targets conforming; one deliberately duplicated composition
distribution rejected; zero targets reported as undetermined. Backend
`2.1.0+local.a74f122c8826`, adapter `0.2.0+local.ec346022ea8f` were observed.
The verified-SHACL call returned no verdict because its executable was missing.
These are bounded engineering observations, not a guarantee about future service
availability, all SHACL constructs, instance data or whole-repository consistency.
No shared ontology store was modified. Full local inputs/results are under the
task's ignored `artifacts/schema-catalog/`; this prose is a scope summary, not a
substitute for the raw execution receipts.

Direct SQLite import is not assumed available. Generate RDF from the existing IR
to retain composite ordering, source fingerprints and unsupported SQL evidence.
Avoid hand-maintaining a second DDL description. SHACL is appropriate for closed
submitted-data constraints; OWL is optional for explicitly supported conceptual
inference. A finite operation model explores transitions that a SHACL snapshot
cannot describe.

## Consequences and work plan

| Increment | Reviewable outcome | Dependency / acceptance condition |
| --- | --- | --- |
| Inventory foundation | All registered formats, ownership and structural counterexamples; source-bound JSON | PR #256, independent reversible work under existing contracts |
| Semantic model pilot | Versioned vocabulary and operation/format/domain mapping; RDF projection; FS/WT composite keys, hash states and optional-reference shapes | Accept this design; define executable projection/shape contract before expanding scope |
| Conformance fixtures | Valid empty initial catalogs, complete/partial/interrupted scans, malformed references, supplied/unsupplied targets, conflicting observations and SQL-vs-shape counterexamples | Pilot mapping; use real disposable SQLite fixtures and exact byte/time encodings |
| CI integration | Reproducible optional tool environment, local Linux checks, non-vacuous coverage gate, cached immutable inputs and compact result evidence | Pilot checks prove positive/negative/unsupported cases; select and pin a reproducible local SHACL runner before making it required |
| Operation model | Bounded Core-before-Context persistence, interruption and permitted partial completion; matching implementation tests | Accept design; map the exact selected acquisition/Exchange contract and source paths before specifying transitions |

The semantic pilot must map the seven responsibility areas and relevant operations,
while clearly labeling incomplete mappings. Start instance constraints with
Filesystem/Worktrees; do not claim all Core/Context behavior on that basis. Model
the loss of Operational and cumulative budgets as a later separate increment; a
partial-commit model does not prove request accounting. No new atomicity or resume
guarantee is inferred from either model.

Remaining engineering choices include RDF term names/encoding version, which
SHACL Core/SPARQL fragment is portable, the pinned local runner and the exact
finite state-model bounds. Public ontology publication, new services and new
runtime dependencies are outside this proposal. Open Ontologies can remain an
optional interrogation/validation adapter; service access must not be necessary
for deterministic ordinary CI. Acceptance is separate from implementation,
verification, merge and publication.

## References

- [ADR policy](policy.md), [ADR index](README.md)
- [Module and operation independence](0037-operation-scoped-module-independence.md)
- [Operation contract](../architecture/module-independence-contract.md)
- [Independent local catalogs](0039-independent-filesystem-and-worktree-catalogs.md)
- [Local operation contract](../architecture/local-catalog-contract.md)
- [Scoped recovery](0038-scoped-recovery-and-optional-initialization.md)
- [Cumulative request budgets](0025-cumulative-request-budgets-and-scoped-blockers.md)
- [Environment SQLite validation](0032-environment-sqlite-validation.md)
- [W3C SHACL](https://www.w3.org/TR/shacl/)
- [W3C OWL 2 direct semantics](https://www.w3.org/TR/owl2-direct-semantics/)
- [SQLite CHECK constraints](https://www.sqlite.org/lang_createtable.html#check_constraints)
- Owner request and supplied assessment in the 2026-11-07 task conversation; no acceptance recorded.
