# ADR: Transport-independent core persistence and minimal parser provenance

- **Status:** Accepted target design; **not implemented** in the current runtime.
- **Decision date:** 2026-10-10.
- **Baseline:** `main` at `7a3596236cdbf2a9ac39c5d12101c8a54c03673d`, Catalog3 schema 16 (103 physical tables).
- **Scope of this ADR:** What the core must persist, what transport may optionally record, and how to identify the parser that produced normalized data.
- **Implementation scope of this PR:** Documentation only. The schema, application, CLI, tests and existing runtime contracts are unchanged.

This ADR freezes the choices explicitly reached in the design discussion. It **does not** choose new resource-history/current-state lifecycles, invent a current-winner policy, or assert that schema 16 already implements the target. Those decisions need separate review before a replacement schema is implemented.

## Terminology and boundary

| Term | Meaning | Core retention |
| --- | --- | --- |
| **Transport original** | Exact or decoded HTTP response bytes, original API response-shaped JSON, request/response envelope, headers, pagination cursors, ETags, retry records, and transport-only diagnostics | **Not persisted as transport evidence in the core** |
| **Domain data** | A resource's interpreted identity, title, body, state, author, relationships, code references and explicitly modeled domain attributes | Retain according to the domain's separately defined lifecycle |
| **Domain observation/evidence** | The asserted value(s), observation instant, applicable provider clock/scope, original ownership/capture context, and enough evidence for valid admission/coverage | Retain **only what the domain contract needs**; never require a transport-original record |
| **Parser provenance** | Name and version of the parser module that **actually produced** a normalized value/observation | Retain as simple provenance (no selected-profile authority) |
| **Domain content bytes** | The exact UTF-8 body or raw Git object bytes whose content is itself a cataloged object | Retain where the domain requires it; not a transport archive |
| **Optional transport record** | Debugging/investigation artifact outside the core, possibly including original response bytes | May exist or not exist; always disposable from the core's perspective |

A string or JSON body is **not** a transport original merely because it arrived over HTTP: an Issue body or Git blob that is itself a domain object may be stored. Conversely, copying an otherwise unmodeled API response into a generic `payload` or `metadata` column does **not** make it a domain fact. Provider-specific attributes may be stored where their meanings and consumers are explicitly defined; the detailed field inventory is deferred.

## Accepted decisions

### TP-01 — No mandatory API transport originals in the core

The target core database must not persist decoded API response bodies, unparsed provider response envelopes, or their exact byte-store registrations **for the purpose of transport replay, retrospective parsing, or HTTP debugging**. Transport metadata with no independent domain meaning also does not belong in the core.

A durable normalized record must be valid without any corresponding saved HTTP message, payload hash, fetch-occurrence row, archive reference, or message-replay manifest. No `FOREIGN KEY`, admission guard, publication precondition, eligibility view, completeness proof, exchange dependency, or restore condition may require a transport original.

Transport-only processing may use in-memory response bytes during an active collection. This decision is about *durable dependence*, not about forbidding transient buffering.

### TP-02 — Optional, isolated recording

Transport recording is optional and independent of domain persistence. It may write to files, a dedicated database, or another transport-owned store; the exact physical format is **not decided**. The existing `MessageRecorder` adapter is a useful starting boundary, not an obligation to retain its current file format.

A disabled, missing, unreadable, expired or deleted transport archive must not affect completed core data, queries, search, coverage, exchange, core backup, or restore. A supplementary recorder failure must not turn an otherwise valid domain acquisition into a domain failure. Ordinary transport, parsing, domain-validation, persistence and cancellation failures are **not** suppressed.

Optional capture is not a second required source of truth. It has no mandatory core-to-log foreign key, and its content is not included in the core portable exchange or mandatory core backup/restore closure.

### TP-03 — No retrospective API reparsing requirement

The core will not retain API transport originals to enable parsing old responses again after a module upgrade. Retrospective API reparse/replay is **not a supported core workflow**. An optional external diagnostic recorder may support manual inspection, but may not publish historical domain observations by pretending a new parse was an old remote observation.

Re-fetching the provider's current data is a **new observation**, not a reconstruction of an older response. Values absent from normalized storage cannot later be recovered from the core by changing the parser.

This does not require deleting normal domain-derived recomputation (for example, rebuilding a search index from stored domain text), nor does it settle the separately owned raw-Git-object case.

### TP-04 — Parser module name and version are sufficient provenance

For normalized facts retained in the core, record the **actual parser module name** and **actual parser module version** that generated the values. Additional timestamps and source/owner evidence already required for the domain retain their separate meanings.

The target design does **not** need:

- user-selectable parser/profile variants for one saved transport input;
- competing immutable parser interpretations and a chosen-interpretation DAG;
- core-stored whole-parser implementation/schema/capability verification certificates, receiver-local verification trust/invalidation, or profile/fact selection predecessor graphs as prerequisites for reading ordinary data.

Parser provenance is attribution, **not** a ranking, authorization, freshness signal, semantic value comparison, or immutable-code hash guarantee. An increase in parser version must not automatically outrank a provider clock or silently repair earlier values.

Where a current resource merges fields from different acquisitions/parses, attribution must remain truthful **for each retained value or group of values with shared evidence**. A single parser name/version on a mixed-provenance row is insufficient. The eventual physical layout (inline columns, evidence map or shared observation reference) is **not decided**.

### TP-05 — Preserve domain data, not opaque transport replicas

The target persists provider/resource identities, explicitly modeled domain properties, required body/text and Git content, meaningful relationships, necessary observation/provenance and consistency evidence.

Any current `payload`/`metadata` JSON column must be audited by *meaning*, not by name. Retain defined domain fields, possibly as typed domain JSON when justified. Remove or remodel undifferentiated provider response snapshots whose only purpose is wire replay or future speculative extraction. The exact subset of fields and the choice of normalized columns versus typed JSON are **deferred**, not implicitly decided here.

### TP-06 — Raw Git objects and domain text are not HTTP transport archives

Retain raw Git object bytes as cataloged Git content where required, including existing object-format/OID verification and corruption handling. Retain exact text bytes and SHA-256 semantics for required Issue/PR/comment bodies as domain values. Data exchange and backup may carry these **domain bytes** without carrying the API request/response that delivered them.

Do not remove `stored_bytes`, `payloads`, Git-content links, quarantine or CAS-41 wholesale: they currently serve both transport and retained domain-content paths. Separate their responsibilities first. Subsequent physical placement and representation of domain-content storage are implementation decisions.

### TP-07 — Preserve established independent invariants

This change does not reopen the existing permanent `repository_uuidv4` identity, natural document/resource identity decisions, signed int64 Unix epoch microseconds with `_us` suffixes, exact UTF-8 body identity, or coverage v2's five-column claim contract and maximum-observation-time candidate-set derivation.

Do not silently weaken typed owner/parent constraints, truth of observed/missing/explicit-null values, provider clock comparability, idempotency, conflict detection, cross-repository transfer capture provenance, independently received conflicting candidates, or the rule that a partial collection may not claim completeness.

Crucially, **the parser-selection DAG and the domain-current/conflict problem are different**. Removing the former does not authorize last-received-wins, greatest-parser-version-wins, or arbitrary current-fact selection. The replacement selection/resolution rules for historical PR/Git families remain **deferred**.

### TP-08 — Fresh incompatible development schema is acceptable

There is no release or backward-compatibility requirement. The implementation may introduce a fresh Catalog3 schema and remove retired tables, columns, views, guards, CLI functions and tests. No migration, compatibility facade, dual write or historical-data conversion is required unless separately requested. This ADR itself does not change `SCHEMA_VERSION`.

## Concrete change surface in schema 16

**This is an impact inventory, not an unconditional DROP list.** Some tables contain genuine domain facts or integrity guarantees even though their current schema includes a fetch or parsed-result reference.

| Area | Current objects / code | Required direction |
| --- | --- | --- |
| HTTP originals and reusable HTTP validators | `fetch_occurrences`, `source_input_observations`, `validators`; `adapters/github/persistence.py`, `collector.py` | Remove core transport-original persistence and references. Decide independently whether conditional HTTP caching belongs in a disposable operational store. |
| Mixed-purpose byte CAS | `payloads`, `stored_bytes`, `git_object_payloads`, `unresolved_payloads`, `payload_quarantine`; `adapters/sqlite/payloads.py`, `cas_integrity.py` | Remove `decoded_api` transport retention and its replay/repair assumptions; preserve domain Git bytes and required content verification. |
| Parser/profile infrastructure (18 dedicated tables) | `parser_profiles`, `parser_profile_capabilities`, `parser_profile_verifications`, `parser_profile_verification_invalidations`, `local_parser_profile_verification_trust`, `parsed_results`, `parsed_result_inputs`, `parsed_result_publications`, `parser_profile_selection_*` (5), `fact_selection_*` (5) | Retire profile verification, parser/fact selection DAGs and their requirement on ordinary readers. Replace only whatever minimal domain batch/publication ownership remains necessary; actual replacement objects deferred. |
| Historical PR/domain facts | `change_request_observations`, `document_observations`, `change_request_events`, `review_thread_observations`, `code_observations`, `code_commits`, `code_file_changes` | Remove `fetch_occurrence_id` and `parsed_result_uuidv4` dependencies from persistence identity/publication; preserve domain owner, observed facts and meaningful history **until lifecycle is decided separately**. Re-key code-list entries independently of HTTP page PKs. |
| Git decoded facts | `snapshots`, `commits`, `commit_parents`, `tree_entries`, `tag_objects`, `root_manifests`, `ref_observations`, `git_text_facts`; `adapters/git/importer.py`, `parsing.py` | Rework parsed-result ownership/eligibility without discarding immutable Git identity/content, partial-publication protections or existing snapshot semantics. |
| Current Issue/review state | `issue_resources`, `review_resources`, `field_evidence_json`, `acquisition_scope_json`; `adapters/sqlite/current_resources.py` | Replace exact profile UUID/trust dependencies with truthful module/version attribution. Preserve per-field clocks, missing/null distinctions, captured Source/endpoint and transfer/conflict rules. |
| Domain collection and coverage | `fetch_collections`, `collection_memberships`, `current_collection_pages`, `completion_markers`, `incremental_scans`, `coverage_claims`; `adapters/sqlite/current_collections.py`, `coverage.py` | Replace exact transport-page/replay closure with sufficiently checked normalized collection membership and terminal evidence. Keep five-column coverage and no unjustified complete state. Exact proof data model deferred. |
| Receiver/exchange state | `exchange_admissions`, `exchange_staging`, `exchange_blocked_results`, `exchange_selection_blocks`; `adapters/sqlite/exchange.py` | Export/import domain objects, capture evidence, completed collections and required domain bytes without HTTP originals or selection-DAG closures. Keep bounded missing-owner/dependency and unordered-value conflicts. Exchange wire format/version deferred. |
| Runtime state and replay | `resume_scopes`, `resume_cursors`, `collection_progress`, `jobs`; `application/collection_service.py`, `application/parsing_service.py` | Make restart/retry safe without retained HTTP messages; replay/reparse operations requiring core originals must be removed or re-scoped. Physical runtime-store split deferred. |
| Query, search and targets | `application/pr_queries.py`, `query_service.py`, `target_queries.py`, `adapters/sqlite/index.py` and existing eligible/current views | Replace joins to selected profiles/parsed results with domain-specific validity/resolution. Do not fabricate an undisputed current winner where evidence is incomplete. |
| Schema/CLI/evidence | `resources/catalog3.sql` and composed SQL, `adapters/sqlite/json_contracts.py`, generated SQL guards, `application/parser_service.py`, `cli/main.py`, `scripts/verify_builtin_parser.py`, `resources/builtin_parser_verification.json`, integration/packaging suites | Regenerate full DDL/JSON validations, remove retired parser-choice/replay UI and certificates, and replace behavioral acceptance tests; historical reports stay unchanged. |

Today, `ApiFacts.result()` requires a saved `fetch_occurrences` row; `parsed_results.input_manifest_json` requires a nonempty saved input; PR detail 304 handling rereads `stored_bytes`; and exchange completeness proof may reread saved PR list JSON. These are **known direct violations of TP-01/TP-03 in the current runtime**, not edge cases fixed by changing a configuration flag.

## Intentionally deferred design decisions

The following remain open. This ADR does **not** silently choose their answers:

1. **Resource lifecycles:** For each entity/family, retain all domain observations or only latest accepted state? How are historical PR/Git observations ordered, superseded or exposed once parser/fact selection is removed?
2. **Minimal domain observation/publication schema:** Which domain owner/batch identities, durable generation boundaries and atomic-completion records replace `parsed_results`? A parser execution, domain observation and Git acquisition are not automatically identical concepts.
3. **Collection completeness proof:** What normalized member identities, digests, owner/scope, timestamp and terminal assertions must remain to support honest coverage and partial exchange without original HTTP pages?
4. **Provider field inventory:** Which current opaque provider-JSON keys are first-class domain fields, allowed typed metadata or disposable transport artifacts?
5. **HTTP optimization and restart:** Disable 304/ETag initially, or use a disposable coherent cache? Which resume cursors/job checkpoints remain durable, and in which datastore?
6. **External recording implementation:** File versus separate SQLite database, bounded retention/deletion, security controls and cleanup policy.
7. **Physical content retention and GC:** How to reclaim unreferenced current-resource text safely while preserving Git objects, legitimate historical text and CAS corruption contracts.
8. **Portable exchange revision and trust boundary:** How to represent normalized collection/observation completeness and validate a sender without promising reparse of a nonexistent original; how to resolve cross-repository ownership forks.
9. **Concrete schema delta and parser-version representation:** Exact table/column/JSON layout and how module versions are assigned and validated, as opposed to additional unwanted code-hash/certification authority.

The current schema 16 resource lifecycles and conflict protections describe **the existing implementation**, not newly accepted answers to these questions. Until the relevant choices are made, avoid a destructive implementation PR that must invent semantics.

## Acceptance criteria for subsequent implementation

An implementation targeting this ADR must demonstrate, using **synthetic/disposable** data:

- A normal API acquisition persists normalized domain facts without inserting original API bytes, a mandatory core fetch row, or a corresponding `decoded_api` payload.
- There is no reference from durable core domain validity/eligibility, queries, coverage, exchange, backup or restore to a transport archive or saved message. Disabled/missing/deleted/failed supplementary recording does not change valid domain outcomes.
- Module name/version attribution matches the *actual* producer; partial updates can preserve older per-field attribution without falsely assigning the latest parser to inherited values.
- Parser/Profile/Fact selection DAGs, certificate/trust gates and mandatory retrospective HTTP reparse are not on any ordinary core read/write path.
- A new fetch under a changed parser is a new observation, not a retroactively edited old provider observation.
- Partial and out-of-order provider values, incomparable clocks, equal-clock contradictions, cross-repository transfers and staged competing candidates retain honest outcomes; parser version and arrival order do not decide disputes.
- Incomplete/truncated/missing-child collection sets cannot claim complete. Existing coverage v2 five-column shape and latest-time set derivation continue to pass.
- Full/selective export/import and backup/restore operate without optional transport artifacts and preserve required domain bytes and unresolved conflicts.
- Git object format/OID/raw-content verification, quarantine/repair where still applicable, and explicit domain-data publication/atomicity remain safe.
- The new complete packaged DDL/JSON guards, FK and integrity checks, all meaningful ordinary tests and installed wheel/sdist checks pass **on the submitted tree**. Report actual test results and unexecuted scope; do not reuse schema 16 acceptance as proof of new behavior.

## Scope and precedence

- This is **design authorization**, not authorization to merge, release, or silently choose deferred lifecycle policy.
- It supersedes the **future-target design** of mandatory transport-original retention and parser/profile/fact-selection DAGs in schema 16. It does **not** falsely amend today's functioning schema or historical validation reports.
- Existing repository identity, time, coverage and domain integrity contracts remain binding unless a separate decision explicitly changes them.
- Follow-on implementation PRs may be stacked. They should cite TP-01–TP-08, flag every deferred choice they need, and keep this ADR's accepted/deferred distinction intact.

Reference implementation baseline: [active schema](../src/repo_catalog/adapters/sqlite/schema.py), [data model](data-model.md), [transport recording](latest-state-transport.md), [current-state conflict boundary](current-state-boundaries.md), [schema 16 inventory](current-state-boundaries-inventory.json).
