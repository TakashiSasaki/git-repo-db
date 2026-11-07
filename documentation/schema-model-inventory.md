# Implemented schema model inventory

The product-side `scripts/schema_inventory.py --profile all` extracts the ten
currently registered SQLite schema definitions into a single diagnostic JSON IR.
It covers the normal CLI's three formats, the four P1 formats, independent Access,
Filesystem and Worktrees. These are not ten authorities or ten required database
files. The seven accepted responsibility domains and the workspace's distribution
declarations are separate records. Local is an optional composition with no store.

This is a reversible tooling extension under ADRs [0035](../docs/adr/0035-independent-documentation-workspace.md),
[0037](../docs/adr/0037-operation-scoped-module-independence.md) and
[0039](../docs/adr/0039-independent-filesystem-and-worktree-catalogs.md).
It introduces no product schema, dependency, required runtime or new consistency
guarantee. The legacy renderer still consumes the default `normal` profile.
This guide and the diagnostic inputs are not added to the public site allowlist.

## Generate and inspect

Run with the repository's verified product Python; do not substitute system
Python/SQLite or the documentation environment for the producer.

```bash
# Development check of the current working files; not a committed-source receipt.
scripts/local-run.sh python scripts/schema_inventory.py --check --profile all

# Commit the producer inputs before exporting a source-bound inventory.
FULL_PRODUCT_SHA=$(git rev-parse HEAD)
scripts/local-run.sh python scripts/schema_inventory.py --profile all --source "$FULL_PRODUCT_SHA" --output documentation/.build/inputs/all-formats

# The old renderers use a separate normal-profile input directory.
scripts/local-run.sh python scripts/schema_inventory.py --profile normal --source "$FULL_PRODUCT_SHA" --output documentation/.build/inputs
```

Each export writes `inventory.json` and `producer.json`. The producer checks the
selected commit against working bytes before and after execution and binds the
IR digest, Git tree, input digests, executed local Python modules and actual
Python/SQLite versions. The all-format manifest also records `inventory_profile`.
These checks establish provenance consistency, not trusted execution or formal
correctness. Do not mix output profiles or revisions in one model.

## Representation

| IR field | Meaning |
| --- | --- |
| `stores` | Format-qualified keys such as `normal.core` and `p1.core`; actual SQLite tables, columns, ordered keys, physical FKs, indexes, triggers and SQL |
| `authority_domains` | Seven accepted responsibility areas and their independent implementation distributions |
| `configurations` | Schema families and optional compositions, not mandatory startup or backup sets |
| `distributions` | Names, versions and raw mandatory/optional dependency requirements read from workspace pyprojects |
| `source_ownership` | Unique owners of declared wheel-layout source paths; this does not replace installed-wheel tests |
| `composition_entrypoint` / `definition_sources` | The schema assembler and known contributing definition files, qualified by distribution |
| `extracted_objects` / `column_count` | Separate SQLite enumeration used to detect omissions in the structured projection |
| `extraction_connection` | Observed in-memory PRAGMAs and non-built-in SQL function names/arities/flags, including extension functions; not a complete runtime requirements specification |
| `optional_references` | The two explicit Worktrees external-reference contracts, separate from physical FKs |
| `normal_logical_dependencies` | Existing normal-profile annotations, with format-qualified endpoints |
| `scope.unformalized` | SQL behavior, Python checks, operation preconditions and other guarantees this inventory does not evaluate |

P1's assembler belongs to Runtime, its domain DDL to the respective independent
distribution, and shared coverage DDL to Contracts. A single format may therefore
have several contributing distributions. Do not turn unique ownership of each
source file into a rule that every composed format must have one contributing
package. The mixed normal catalog's broad domain mapping is not a per-column
semantic ownership claim or evidence that the CLI uses the independent layout.

Version representation follows the product: P1 and Worktrees expose a format ID
without a separate integer schema-version API; Filesystem exposes a schema version
without a format-ID API. Missing fields remain JSON `null`. Do not parse a suffix
and invent a version or identity that the product does not declare. SQLite's
actual `STRICT` and `WITHOUT ROWID` flags are introspected for this profile.

Worktrees' Filesystem reference contains namespace and scan UUID. Its physical
foreign key points only to the local Worktrees observation. An external Repository
UUID is an explicit domain claim; it is not an inference from a filesystem path,
remote URL or matching HEAD. Missing target **instance data** remains unresolved;
missing target **schema definitions** within the explicitly complete extraction
profile is a coverage error. No catalog instances are opened by this tool.

## Checks and limits

The checker requires every registered format/domain/configuration, checks source
ownership and rejects duplicate installed source paths. It checks object/column
coverage, physical FK endpoints and the local reference's complete target key.
P1 also checks its declared fingerprint manifest against actual composed DDL.
The registry must be explicitly extended when a new format is implemented.

These are structural checks, not an arbitrary-JSON security boundary. The export
producer binds bytes and sources; the checker does not prove a malicious author
cannot forge internally consistent evidence. Definition-file annotations identify
known contributors; the broader producer input closure, not that annotation list,
binds all product/control sources. SQL text and UDF registration are preserved as
evidence, not translated into logic. In particular, SQLite CHECK/NULL semantics,
Python admission, history preservation, instance identities and crash recovery
have not been formally verified. Runtime-created FTS tables are outside this
static profile. Paths are column types here; no retained paths are decoded.

Focused checks include real packaged schemas plus deliberately removed formats,
tables, columns and triggers, broken FK endpoints, duplicate namespace source
paths, incomplete references and wrong owners. An empty extraction is not success.
Use a pytest base directory outside every Git worktree:

```bash
scripts/local-run.sh python -m pytest tests/unit/test_schema_catalog.py tests/unit/test_schema_inventory.py tests/unit/test_schema_inventory_structure.py
```

Subsequent semantic-model work can consume this IR without making ontology tools
product dependencies. It must separately define operation contracts, constraint
coverage, data scope, unsupported features and bounded state-transition models.
