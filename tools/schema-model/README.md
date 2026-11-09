# Optional schema-model tooling

This is the first implementation increment of
[ADR 0040](../../docs/adr/0040-scoped-machine-readable-model-validation.md):
a versioned structural RDF projection of the existing source-bound inventory,
a deliberately limited SHACL profile, independent coverage checks and scoped
validation receipts. It does not extract retained catalog instances or replace
SQLite, product admission checks, or canonical DDL.

## Isolated environment and inputs

Keep this tooling environment separate from the product workspace. RDF/SHACL
libraries are not product runtime dependencies. Resolve the complete committed
lock without altering the product environment:

```sh
uv sync --project tools/schema-model --locked
```

First export the product IR through its verified environment. Use a fixed full
product commit, not a moving branch name:

```sh
scripts/local-run.sh python scripts/schema_inventory.py --profile all \
  --source "$(git rev-parse HEAD)" --output documentation/.build/inputs/all-formats
```

Run projection and validation together with a finite timeout:

```sh
uv run --project tools/schema-model --locked --offline python \
  tools/schema-model/model.py --input documentation/.build/inputs/all-formats \
  --output artifacts/schema-model/result --timeout 60
```

Dependency installation may initially need network access. The validation run
itself is offline; preload the complete lock into an accessible uv cache first.
Set `UV_CACHE_DIR` to an approved writable cache if the default cache is not
accessible. Cache locations are environment-specific, not repository contracts.

Keep `inventory.json` and `producer.json` together. The producer checks committed
source bytes and records source commit/tree, input hashes, IR digest and actual
Python/SQLite versions. A matching digest is consistency evidence, not a
signature or proof of trusted execution. See the
[inventory contract](../../documentation/schema-model-inventory.md).

The initial measured inventory has ten implemented schema definitions, seven
responsibility domains and fifteen distributions. These are source-bound
measurements, not universal constants or a count of live DB files. Keep normal,
P1 and independent formats distinct; Local owns no database.

## Projection and validation contract

- Version the vocabulary under `urn:git-repo-db:model:v1:`. Stable identities and
  graph digests must not depend on wall-clock time or random blank-node labels.
- Preserve ordered composite keys and FK bindings; declared omitted target
  columns differ from effective columns resolved from the target primary key.
- Keep source ownership, schema contributors and assemblers distinct. Multiple
  contributors are legitimate; mixed normal-format annotations do not establish
  per-table semantic ownership.
- Distinguish physical FKs, qualified external references, operation capability
  requirements, derivation and install requirements. Do not collapse them into
  one dependency relation.
- Retain SQL, fingerprints and extraction settings as evidence. SQL CHECK/NULL,
  triggers, UDF semantics and expression-index semantics are not translated into
  general logical guarantees.
- Determine expected targets from independent producer/IR inventory evidence,
  never from the generated RDF itself. Missing objects, missing required shapes,
  deactivated or unsupported checks, zero required targets and timeouts cannot
  become successful coverage.
- Ordinary validation is local and offline. The supported profile rejects
  external access, including SPARQL SERVICE, automatic imports and JavaScript.
  Unsupported features and unavailable checkers produce non-success results.
  A limited tested SHACL fragment is not full SHACL/OWL support.

[`encoding-contract.json`](encoding-contract.json) versions the **future**
Filesystem/Worktrees instance encoding contract. It does not claim that PR-A
implements instance extraction or validates instance behavior. In particular,
RowOccurrence identity stays separate from SemanticKey, bytes and native-time
lexemes are lossless, and legitimate incomplete scans or unresolved optional
references are not rejected merely for their absence.

## Interpret results narrowly

Keep four independent result families:

- `data_conformance`: submitted graph against selected constraints.
- `spec_satisfiability`: supported conceptual reasoning scope.
- `operation_invariants`: explicitly bounded state model.
- `implementation_conformance`: actual implementation/translation tests.

Use `pass`, `fail`, `undetermined`, `not_run` or `not_applicable` with scope and
reasons. There is no global `verified` flag. Bind receipts to product and tool
source, input/IR/mapping/shapes/lock digests, engine/version/profile, constraint
IDs, authority citations and raw diagnostics. Expected targets, selected targets,
completed invocations and engine-observed evaluation counts are different.
Unobservable engine counts remain null, not a copy of target counts.

Positive and deliberately broken fixtures establish bounded control evidence.
A correctly rejected negative fixture can pass its test while its data
conformance remains `fail`. A green structural result does not certify all SQL,
public API paths, real file bytes, concurrent executions or retained catalogs.

## Excluded follow-on work

PR-B adds real Filesystem/Worktrees instances and SQLite/API paired fixtures.
PR-C may add the optional request-local Open Ontologies adapter; ordinary
validation must continue without that service. PR-D adds a bounded operation
model. None of those increments, ontology publication, product dependency
changes, a mandatory CI gate, release qualification or deployment is introduced
by this tool. Open Ontologies capability claims require current controls;
previous experiments exposed large-integer comparison and proof-runner limits.

### Exact pilot limits

Raw SQL and complete original records are retained in `source-ir.json`, with its
own digest in the receipt; RDF nodes carry source-record digests and compact
scalar fields. This avoids replicating large SQL literals in each checker input.
Qualified external references have ordered `ReferenceBinding` nodes. The nine
baseline normal logical dependencies are explicit `LogicalAnnotation` records,
not current operation requirements: some descriptions predate accepted scoped
supersessions. `requiresCapability` and `derivedFrom` are not instantiated because
the input IR has no authoritative operation/derivation registry; these omissions
are reported as unformalized, rather than guessed from historical descriptions.

Required structural constraint classes must be nonempty. FK enumeration is also
checked against the separate extraction FK count before graph generation can
claim coverage. This is consistency validation, not authentication of a malicious
producer or a replacement for independently rerunning SQLite extraction.
