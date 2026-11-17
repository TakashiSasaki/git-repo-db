---
status: accepted
date: 2026-11-17
replaces: []
refines: ["0037-operation-scoped-module-independence.md", "0039-independent-filesystem-and-worktree-catalogs.md", "0040-scoped-machine-readable-model-validation.md"]
---

# ADR 0043: Separated persistence classes and source-derived table correspondence

- **Decision & Context:** Make the separated formats the sole future persistence target: P1 Core/Context/Operational/Search plus independent Access/Filesystem/Worktrees. Each responsibility domain owns its DB role; each concrete persistent entity, association, infrastructure row or projection class maps to exactly one table in that domain. The canonical assignment is [persistence-model.json](../architecture/persistence-model.json). Abstract classes, values, DTOs, aggregate inputs and query results are explicitly nonpersistent types, so not every Python class requires a table. Reuse current separated DDL as the initial design basis, recording gaps before redesigning it. Start future activation with fresh databases; backward compatibility and old-format conversion are unnecessary. This is an additive, design-first refinement, not ordinary CLI activation or retirement of the current normal implementation.
- **Constraints / Do NOT:** DDL remains the authority for fields, ordered composite keys and physical FKs. Derive them through the existing schema catalogue instead of maintaining another schema in JSON or Markdown. Qualify table identity by format/store/name and class identity by domain/name. Distinguish actual Python input/projection symbols from planned persistent classes and distinguish physical same-file FKs, optional qualified external references and query derivations. No seven-DB startup requirement, inferred cross-DB FK, invented Root table, ordinary file-body archive, retained-data mutation, migration command, new runtime dependency, semantic CI gate or web publication is introduced. Missing dedicated Python row types do not establish missing SQL capabilities. Structural checks and AST symbol presence prove neither serialization nor semantic correctness; runtime-created virtual/shadow tables and other unformalized catalogue semantics remain outside coverage.
- **Reason & Ref:** The owner wants responsibility boundaries to correspond to databases and persistent classes to tables, and explicitly chose “分離形式を目指します。後方互換性は不要です。” The owner then approved the design/mapping-first plan, using current separated DDL and fresh DBs, and instructed “Implement the proposed plan.” Level 2 Mini-ADR records that bounded design choice and its reversible tooling; it does not replace ADRs 0037–0040's operation, recovery, evidence or independent-catalogue obligations. Current normal startup remains Core Schema 21 plus Operational/Search, while P1 is opt-in. Implementation and executed verification of the new runtime are future work.

## Canonical mapping contract

The initial selected DDL has 72 product-table definitions across seven roles.
This is an observation, not a fixed expected count. The check derives its target
set from the actual registered separated DDL and requires one class per table,
including identities, coverage evidence, association rows and derivative Search
rows. Shared Contracts DDL does not become another store. Schema composition
entry-point ownership and definition-source ownership remain separate from
logical row responsibility.

Each row assignment records its kind, semantic note and an observed Python
`row-input`/`projection` binding, or explicitly no dedicated row type recorded.
Bindings may have nested values, derived columns or outer context: presence of
a source class is not evidence of a complete row encoder. Nonpersistent types
record their persistent sources/use without pretending that these are FKs.
The optional-reference section binds only the existing schema-catalogue registry;
it is not a complete model of all cross-domain references or preconditions.

Run from the product checkout with its verified environment:

```sh
scripts/local-run.sh python scripts/persistence_model.py --check
scripts/local-run.sh python scripts/persistence_model.py --format markdown
```

The first command checks assignment coverage, responsibility ownership, class
references, registered optional-reference bindings and Python class definition
presence against the complete source catalogue. The second performs the same
checks and prints a correspondence report with DDL-derived fields, ordered keys
and physical FK endpoints. Both use temporary in-memory schema extraction and
read source files only; neither opens retained DBs or writes generated files.
Do not check in a second editable copy of the generated table. The canonical
JSON is a repository design input, not a new public web-support allowlist entry.

## Bounded gaps and future sequence

Record normal/separated key differences explicitly: for example, normal
`git_objects` uses a surrogate PK while separated Core uses algorithm/OID;
normal `ref_observations` uses snapshot/name while separated Core uses
origin/observation IDs. Repository UUID identity already exists in both.
Filesystem Root is currently a path value in Scan, while `ScanResult` combines
several row responsibilities. `WorktreeEntry` receives observation identity
from its enclosing result/context; a future stand-alone row binding must carry
the full key. Context coverage is part of the model even where a website concept
group omits it. Website models remain derived and may catch up asynchronously
under ADR 0042; no web edit is required by this increment.

Follow the [operation contract](../architecture/module-independence-contract.md)
and the JSON roadmap in this order, assessing existing implementations rather
than claiming all of these capabilities absent:

1. Core/Context/Access foundations, including required Core-only and paired
   recovery (OP-01/02/03/04/07/12). Preserve ADR 0038's immediate corruption stop,
   read-only source preservation, typed salvage and fresh verified restore/merge.
   Carry ADR 0039's independent Filesystem/Worktrees raw-path, honest partial-scan,
   optional-link, EFU and DB-free Local obligations; those are outside OP-01–12.
2. Operational orchestration, acquisition, Exchange and derivative Search
   (OP-05/06/08/09/10/11), preserving cumulative actual work, durable reservations,
   package bindings, required checkpoints and honest state-loss behavior.
   Operational is not classified wholesale as disposable.
3. Ordinary CLI/initialization cutover after the relevant behavior and recovery
   prerequisites pass, with operation-scoped optional store initialization.
4. Normal-format code retirement after a named mapping from every affected test
   obligation/node to its separated replacement. Do not discard a regression
   merely because it previously used normal DDL. No old-data conversion or
   compatibility adapter is required; existing user DBs and historical evidence
   remain untouched.

This increment implements the mapping, structural checker/report and focused
regressions. It does not implement those four runtime phases, establish complete
formal consistency or change deployment/release/required-check settings.
