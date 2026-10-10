# Phase 2 Workstream E — Exchange, CAS and physical retention

Status: investigation and **Proposed / Pending Owner Decision**. The baseline
below is fetched `main` `20e0f8d78b77c6c8d37826fd6d639819631e166b`, production
Catalog3 schema 18. This document neither defines a new wire version nor approves
new trust, retention, garbage collection or API repair behavior. The accepted
transport-independent ADR and Phase 1 R1–R7 retirement remain binding.

## Current live graph and responsibilities

The supported entry points are `exchange export/import/staging` in
[`cli/main.py`](../../../src/repo_catalog/cli/main.py), routed to
[`ExchangeService`](../../../src/repo_catalog/application/exchange_service.py).
Export takes the existing writer lock and a transaction, creates a single
repository unit, persists portable identities, and creates the output with
exclusive file creation. Import takes the same lock and commits intake,
promotion and publication revision together. An original-only import has no
domain publication effect. No acquisition runs during import.

[`Graph.__init__`](../../../src/repo_catalog/adapters/sqlite/exchange.py)
discovers actual composed production tables, writable columns, primary keys and
grouped composite FKs. Generated current-family discriminator columns are not
portable writable fields; SQL still enforces their parent types. `key`,
`portable_columns`, `record`, `validate_record`, `resolve` and `_existing` form the
identity/admission boundary:

* Service, repository and Source registration UUIDs stay separate; labels and
  URLs do not merge them. Sender Source local IDs and settings do not cross as
  authority. Source registration provenance is recorded separately.
* SQLite integer-only IDs receive persistent random portable identities where
  no natural key exists. Git objects use `(object_format, oid)`, physical bytes
  use SHA-256, logical payloads use `(representation, sha256)`, and documents use
  their accepted natural identity. Composite FK groups become typed `$ref`
  fields, never coincidentally equal local integers.
* Exact body hashes are checked before intake. `text_bodies` hashes exact UTF-8;
  `stored_bytes` checks physical SHA-256 and length. `git_object_payloads` also
  checks format/OID/type/size against the actual Git object bytes. A digest alone
  establishes content identity; it does not establish ownership or completeness.
* Mutable current resources have natural identity mappings and shared
  `CurrentResources.admit` semantics. They are never sealed in immutable
  `exchange_admissions`. `last_checked_at_us` is omitted from sender output;
  import cannot manufacture a receiver-local live check.

The exact production closure also includes embedded authored references from
[`json_contracts.py`](../../../src/repo_catalog/adapters/sqlite/json_contracts.py).
`JSON_REGISTRY`, `REFERENCE_TARGETS`, `REFERENCE_LISTS`, `_walk`, `_owner`,
`validate_record` and generated SQL are part of the dependency graph. They check
the reference type, owner, actual membership and missing dependencies. Provider
projection JSON is deliberately opaque; its survival does not imply approval to
keep a full original response in the final model. Authored evidence has a typed
reference vocabulary; unknown identity-looking keys and local-ID references
fail closed. A purported payload reference must have actual acquisition
ownership under its repository or Source. Changing only this registry without
regenerating its SQL would leave contradictory admission paths.

| Live producer → store → consumer | Retained semantic responsibility | What deletion breaks | Minimum replacement decisions |
| --- | --- | --- | --- |
| `ApiFacts.page/result/publish` → `fetch_occurrences` → `payloads(decoded_api, sha256)` → `stored_bytes`; historical domain rows → `parsed_results`/inputs/publication → `Graph.record/_export/_admit` | Historical domain rows have typed owner/input membership and a sealed exact output set; a valid delayed fact may stage while its dependencies arrive | Direct FKs, input manifests, output publication and receiver admission fail; weakening them admits a partial interpretation | Q04 publication boundary, Q01/Q02/Q08 lifecycle and selection; exact field contract Q09 |
| PR-list pages → `aggregate_proof` → immutable complete Coverage proof | Every listed PR must have exactly one published observation whose stored `payload` equals the saved provider object; listed requests must be accounted for; required child collections/code proof must exist | Saved bytes are parsed here, even after acquisition. Dropping bodies removes the only implemented normalized-set reconstruction; dropping the verifier allows selective/partial lists to establish complete Coverage | Q05 normalized listed membership/terminal evidence, Q04 output seals, Q10 portable closure |
| PR code collection → `code_observations.details`, code listings, result inputs, code/acquisition links → `code_proof` | Exactly one complete code observation; stable API head/base; explicit expected roles and no missing roles; listings in the correct PR/kind; published Git roots and acquisition publications match each role/OID | Omitting listed-input/target evidence can label code from an obsolete PR head as complete. Git raw bytes are legitimate content, not disposable transport proof | Q06 durable target/child obligations, Q08 Git publication/selection, Q05 list proof |
| `ApiFacts.complete` and current page proof → `completion_markers` → `proof_requirements` → `coverage_claims` | Immutable exact fetch/current-page manifests; same Source/repository/PR; child scope compatibility; max actual observation time; terminal evidence; independently verifiable required set | FK-only validation cannot establish missing pages, children or terminal boundaries. Exact transport closure currently remains required for historical markers | Q05/Q06 normalized sequence/tree proof, Q10 receiving predicates |
| PR-detail conditional reuse → exact 304 marker → `proof_requirements/_admit` | Marker anchors the original observation/result/fetch/payload under the same repository and PR; the 304 is not a new resource observation | Arbitrary validator or cached bytes could otherwise attach old content A to current B. Deleting the anchor invents observation/completion evidence | Q07 conditional policy; Q04/Q05 normalized observation/revalidation anchor; Q10 transfer policy |
| Git importer → verified `git_objects`/`git_object_payloads`/`repository_object_sources` → content closure and `git_acquisition_publications` | Format+OID identity, correct raw bytes and captured repository/acquisition membership; immutable object/root manifest | Raw Git repair/exchange/integrity becomes impossible; removing interpretation selection separately must not erase Git facts | Git bytes already authorized; Q08 interpretation selection and acquisition publication replacement |
| Source inventory → `source_input_observations`, Source-owned results, inventory/name observations | Actual Source ownership remains distinct even when an output mentions a repository | Importing the Source result through an inventory-derived repository name leaks other repositories' inventory. Treating it as repository-owned changes provenance | Q03/Q04 Source publication; Q10 only if new Source-wide or reduced name assertion exchange is wanted |
| Full verification → all physical `stored_bytes` → `unresolved_payloads` and `payload_quarantine` → backup/restore | Digest/length integrity and physical quarantine remain shared across logical representations; CAS-41 records active physical quarantine | Ignoring `decoded_api` labels can hide corruption of the same digest used by a Git object. Dropping diagnostics/count weakens accepted backup guarantees | Q11 physical separation; no retention-duration/GC authorization |

These are live dependencies, not conclusions from string matches. The probe and
listed integration tests execute export/intake/promotion with production DDL;
the methods above consume the identified rows and manifests in those executions.

## Exact completeness and admission behavior

`aggregate_proof(scope, details, collection_rows)` reopens `stored_bytes.body`,
decodes a PR-list array, and compares each complete provider object to
`change_request_observations.payload` under its origin fetch. This is both a
saved-original dependency and a current opaque-field dependency. The final
replacement must persist the intended resource identity and normalized domain
observation membership during intake. Replacing this with only a list of PR
numbers loses the identity/observation/publication connection. The method also
checks each requested PR's required collection kinds and a unique matching
`code_proof` for aggregate `pr` completeness. An empty list is a meaningful
complete empty set only with actual terminal evidence.

`code_proof` binds one complete code output to its result/publication, the
commit/file listing collections included as result inputs, and all expected
Git acquisition roles. It verifies the exact head/base OIDs against the code
observation and published roots. This target binding must survive API-original
retirement. A collection of valid commits is not evidence that they were
acquired for the presently asserted PR head/base.

`proof_requirements` derives dependencies from local typed facts, not an incoming
`requires` envelope. For a historical completion marker it checks the complete
fetch UUID set across parent/child collections, equivalent child capture scopes,
exact current-page collection manifests where present, maximum non-NULL actual
observation time and the terminal assertion. For 304 it requires the original
observation/result/fetch/payload anchor under the same repository and PR. For a
complete Coverage Claim it verifies matching exact complete marker identities,
scope kind, collection ownership, Git acquisitions/publications, code/aggregate
proof and the maximum underlying observation time. The 304 claim's resource
observation time comes from the original observation, not the validation receipt.
Coverage retains its accepted five-column claim shape and latest-time candidate
set; neither sender checks nor parsing/receipt time can establish ordering.

The baseline's historical branch checks exact UUID-set equality and
`terminal:true` but does not independently check contiguous flat-page ordinals
or the final page's actual cursor. A fresh-schema counterexample with only
ordinal 2, or ordinal 0 carrying a continuation cursor, is being characterized
and hardened by Workstream B. This is a correctness defect in the existing
completeness contract, not permission to select a new permanent proof schema.
GraphQL partial roots and child continuation need family-aware treatment;
flat-list ordinal assumptions must not be blindly imposed on every fragment.

Current-resource pages are already archive-independent. `CurrentCollectionProof`
verifies immutable normalized member receipts, explicit continuation/terminal
boundaries and a sealed completion marker. `current_page_requirements` and
`current_baseline_requirements` require typed member identities and stable owner
dependencies, allowing a current resource's value to change without making an
old collection receipt an immutable current-state snapshot. This is evidence
that original-free proof is feasible, not approval to use its exact JSON layout
or historical-value semantics for every family.

## Original-retirement, staging and conflict protections to preserve

Phase 1 intentionally retains only originals in legitimate typed domain/proof
closure. `ORIGINAL_RECORDS` and `ORIGINAL_PROOF_TABLES`,
`original_dependencies`, `original_root`, `required_original_keys`,
`_constraint_valid_unresolved`, `git_original_status` and
`_preflight_original_roots` enforce that boundary. Input/fact/Git manifests and
exact terminal/304 identities own dependencies. A generic metadata/request
`payload` annotation, selected parser profile, forged `requires`, malformed
publication, invalid owner, disconnected empty publication or partial reason
marker cannot authorize API bytes.

Preflight uses a rolled-back repository-scoped savepoint overlay. Incoming
dependencies are admitted through ordinary validators, then actual domain roots
are derived from that state. Missing API-body placeholders exist only inside
the savepoint, are always rolled back and are never receipts or retained
evidence. Known-invalid/conflicting inputs cannot become roots through staged
descendants. A valid missing dependency remains stageable; a body must match a
declared Git format/OID even if the full Git descriptor arrives later. Removing
API-body preflight in the replacement requires normalized proof checks, not a
less strict interpretation of envelope hints.

`receive` validates every byte before staging. Digest-invalid bytes and their
dependents are rejected; rejected API body envelopes do not remain in JSON
staging. `_admit` resolves only admitted typed references, checks incoming
`requires` against independently derived proof, applies same-owner JSON guards
and SQL constraints, and uses shared current-resource admission. `_promote`
iterates durable staged dependencies with per-record savepoints. Genuine Git
content can remain pending for explicit repair, unlike rejected API originals.
Unexpected failures roll back the outer service transaction. Known missing
dependencies are distinct from permanently invalid/conflicting evidence.

Repeated exact immutable records are idempotent. Competing variants of an
immutable identity stage without an arrival-order winner. Conflicts seed local
`exchange_blocked_results`, `exchange_selection_blocks` and
`exchange_blocked_coverage_claims`; `refresh_resolution_blocks` propagates the
actual FK/registered-JSON closure once with adjacency sets and a queue. A
domain-member conflict also blocks its owning parsed result, preserving atomic
output eligibility. Parser selection/trust is transitional; these underlying
conflict and incomplete-publication protections are independent and must move
to domain-owned predicates when the DAG tables disappear.

One-repository Exchange excludes Source-wide inventory, operational validators,
job/resume state, local parser trust, quarantine, diagnostics and rejected-byte
staging. Source-owned observations are excluded even if they mention the chosen
repository. New normalized proof must retain this exclusion until Q10 approves
any different exchange scope. A sender's truth about its observation is separate
from the receiver's structural validation and its receiver-local live checks.

## Portable normalized design — alternatives, not accepted wire policy

The integrated proposal uses separately typed repository and Source publication
owners, typed domain observations, normalized collection member/fragment/terminal
and child-obligation evidence, and Git acquisitions/content. See the publication
and completeness workstreams for the exact proposed names. The Exchange graph
must follow those domain edges without any mandatory fetch, HTTP message,
decoded original, parser profile, verification certificate or selection DAG.

The following receiver predicates are the recommended candidate contract,
**pending Q04/Q05/Q06/Q09/Q10**:

1. Each record has a typed portable identity and a canonical normalized semantic
   digest. Owner and parent edges are typed FKs, including Source versus
   repository boundaries. Omitted, explicit NULL and empty values are preserved
   in the canonical digest and field-presence evidence.
2. A sealed publication descriptor identifies the exact normalized output
   members (identity, kind and semantic digest), owner and actual parser
   module/version. All required members/dependencies must be present before the
   publication is usable. Normalized dependency membership is not saved API
   input membership.
3. A collection seal binds normalized members, explicit terminal boundary,
   admitted fragment sequence and required child obligations under one capture
   scope. A zero-member terminal collection can complete. Missing/skipped/
   conflicting fragments, an inconsistent digest or a required incomplete child
   cannot. A selective unit containing 2 of 3 members remains incomplete.
4. Coverage is admitted from the exact domain proof closure and genuine times.
   A newer partial observation at 200 still defeats an older complete 100;
   complete and partial candidates at the same time remain a conflict. A later
   message/UUID/parser version cannot select a winner.
5. Code completeness binds the acquisition's exact expected role/OID set to the
   asserted PR observation. An acquisition for head A followed by PR head B
   cannot satisfy B's code proof. Git bytes retain independent object verification.
6. Receive stages typed missing dependencies and contradictory evidence;
   dependency arrival promotes the same immutable seal without inventing remote
   observation times or receiver checks. Reordered/repeated records converge to
   the same usable/conflicted graph.

No digest can prove that an untrusted provider or sender did not omit a remote
item. A normalized receipt proves structural consistency with the collector's
declared observation and capture contract. Saved HTTP bytes likewise do not
authenticate a provider simply because the bytes parse. Any new attestation,
signature, live-revalidation or sender-trust requirement is a separate Q10 owner
choice, not an assumed consequence of normalizing the schema.

### P2-Q10 — What exact normalized evidence must a receiver possess?

**Question:** For a portable complete publication/collection assertion, which
members and observation values must be carried, and what can the receiver
independently validate? Do one-repository units continue excluding Source-wide
inventory and local trust?

**Accepted constraints:** typed portable owner/parent identities; exact text and
Git bytes; no originals or parser authority in target closure; truthful five-column
Coverage; no partial complete assertion; conflicts/staging/receiver-local checks
remain independent. New wire version/trust is unapproved.

| Feasible alternative | Concrete consequence | Integrity, storage and runtime effects |
| --- | --- | --- |
| A. Exact normalized observation closure for every seal | Collection C observed at 100 names observation O1/value X and O2/value Y. To admit complete C, the receiver obtains O1/O2 and recomputes their canonical digests, even if current resources now contain Z | Strong reproducible historical value closure; requires retained normalized history for mutable families or explicitly modeled snapshot members. More rows/bytes; linear manifest hashing and indexed closure. Depends on Q01/Q02/Q09 |
| B. Identity-and-receipt closure for mutable families, exact observation closure for immutable families | C retains typed members plus observed value digests; receiver obtains current identities, receipt and seal. Current X→Z does not rewrite C's observed digest or pretend Z was observed at 100 | Matches the established current receipt responsibility. Receiver validates structure/identity and the immutable receipt, not reconstructible past values. Avoids secretly choosing universal history; proof strength must be described honestly. Depends on Q05/Q09 |
| C. Carry only a sender completion assertion and member digest without member closure | Sender asserts C contains 3 members but sends only O1/O2; receiver records sender evidence while local complete eligibility waits for the missing closure | Feasible only as staged or separately qualified evidence; the digest/assertion alone cannot establish receiver-verified complete Coverage. Smaller partial units; requires an explicit trust/qualification policy if exposed as anything stronger |

**Recommendation (pending):** B with exact normalized closure for retained
historical families and stable identity/receipt closure for settled mutable
current families; keep one-repository scope and local trust exclusion. A is a
feasible owner choice if those families are approved to retain reconstructible
domain history. C remains unavailable/staged evidence unless a separate owner
decision defines additional authority. Preserve exact manifested dependencies
and independently recompute usable completeness; never accept an advisory
envelope as proof.

**Effects:** Coverage columns and maximum-time semantics stay unchanged. Backup
includes retained normalized seals and domain bytes; optional recording is
outside closure. Tests must challenge changed mutable values, missing members,
bad digest, repeated/reordered late dependencies, wrong Source/repository,
incomparable conflicting observations and malicious sender hints. Export is
O(V+E) for the selected graph using keyed adjacency/membership, not a whole
catalog scan or all-pairs manifest construction. Admission should resolve
dependencies with keyed pending queues; a generic sorted retry sweep may require
multiple passes on deep dependency chains and is not a permanent performance
target.

**Dependencies/implementation impact:** Q04 publication identity, Q05 member/
terminal proof and Q06 child/target contract must precede final wire DDL/encoder.
Q01/Q02/Q09 determine whether A or B applies to each mutable family; Q08 determines
historical Git eligibility. This blocks production format/trust changes but
does not block schema audits, characterization tests or objective implementation
defects. The smallest useful approval is the publication+normalized proof+portable
closure bundle, with explicit family history choices only where A is required.

### P2-Q11 — Where do retained domain bytes and their physical diagnoses live?

**Question:** After historical API proof replacement, should legitimate Git/domain
content keep one core physical CAS, or use dedicated domain stores? How are
existing API-only quarantine records represented while the old runtime remains?

**Accepted constraints:** raw Git SHA-1/SHA-256 verification and exact UTF-8 text
identity; CAS-41 active physical quarantine manifest count checked against the
verified copied database before restore diagnosis; no API repair/replay revival;
optional recording disposable; no new duration/GC/deletion authorization.

| Feasible alternative | Concrete difference | Storage, correctness and operational consequences |
| --- | --- | --- |
| A. One core `stored_bytes` physical CAS for required domain representations; optional cache/archive has separate ownership/store | Git blob bytes happen to equal a historical HTTP body's bytes. The core digest still has one physical domain object; removing the HTTP registration does not remove the Git object or its quarantine | Reuses existing physical verification/quarantine/repair transaction guarantees and deduplication. Typed logical consumers must retain meaning. Fresh target schema admits only approved domain representations; operational cache has no core validity FK |
| B. Dedicated Git byte store plus separate exact-text/domain stores | The same byte string can appear in more than one physical content namespace | Clear ownership boundaries, possible duplicate bytes and more verifier/backup components. CAS-41 must still describe all active retained physical quarantines accurately; publication/restore must be atomic for every required component |

**Recommendation (pending):** A as the minimum coherent storage change, preserving
the existing exact-text table and independent physical CAS checks for Git/domain
bytes. Existing old-runtime API-only corrupt bytes remain diagnosed and backed
up with the active physical count until their dependencies are retired under an
approved schema change. API-only corruption is not repaired through a fabricated
Git descriptor. A fresh incompatible schema does not require salvaging retired
API originals, but that does not authorize mutating or deleting retained user
catalogs. No automatic deletion, retention duration or collector cache format is
selected here.

**Effects:** Git mappings and diagnostic history survive; explicit repair clears
active quarantine atomically but retains prior diagnosis. Backup checks source
and copy; restore validates manifest hash/schema/catalog/count before diagnosing
and uses a fresh retained stage and no-overwrite publication. Tests must include
shared digests, API-only corruption while old paths remain, true/false Git repair,
manifest count mismatch, unexplained copied corruption, failure rollback and
process death. Q07 cache placement and Q09 domain content inventory affect final
physical boundaries. GC/lifecycle remains a separate owner decision; it does not
block normalized publication/proof work.

## Old-to-new impact and dependency order

This classification is conditional on complete dependency migration; it is not
an unconditional DROP list.

| Schema 18 objects | Classification and retained responsibility |
| --- | --- |
| `repositories`, `service_instances`, `sources`, bindings, typed domain identities, `text_bodies`, verified Git objects/content/mappings | Retain as final domain identity/content; eliminate transport-owned edges without merging identities or changing exact content |
| Historical observations, code listings/entries/targets, Git facts/snapshots, repository/name inventory facts | Replace publication/provenance/field representation where needed; retain legitimate attributes and history while Q01/Q02/Q03/Q08/Q09 are pending |
| `parsed_results`, `parsed_result_inputs`, `parsed_result_publications` | Replace with owner-approved normalized domain publication membership/seals. Their atomic ownership and incomplete-output guards are real responsibilities; API input/interpretation identity is transitional |
| Parser profiles/capabilities/certificates/invalidation/local trust and profile/fact selection DAG families | Remove after publication/reader/conflict/selection migration; do not replace with ordinary parser-version authority |
| `fetch_collections`, `collection_memberships`, `current_collection_pages`, `completion_markers` | Replace with approved normalized sequence/tree evidence; current receipts are a reusable correctness example. Keep old fields only until writers/restart/readers/exchange consume replacement |
| `fetch_occurrences`, `source_input_observations`, `payloads(decoded_api,...)`, mandatory original body/hash registrations | Remove after publication/proof/304/restart and field migration. No independent original export survives Phase 1 |
| `resume_scopes`, cursors/progress/incremental scan state, validators/jobs | Retain only while restart/cache decisions are pending. Separate durable domain target evidence from operational continuation; not core publication identity |
| `coverage_scopes`, five-column `coverage_claims`, current maximum-time view | Retain accepted contract; replace details/proof dependencies and conflict barriers coherently |
| `exchange_local_identities`, admissions/staging/source provenance | Retain their domain responsibilities, adapt to approved normalized portable graph and owner boundaries; wire representation and indexes implementation-dependent |
| `exchange_blocked_results`, `exchange_selection_blocks`, blocked Coverage | Replace result/DAG barriers with domain publication/observation conflict predicates; preserve Coverage conflict propagation |
| `stored_bytes`, approved logical domain representations, `unresolved_payloads`, `payload_quarantine`, Git-only rejected-byte staging | Retain physical content/integrity; Q11 decides final placement. No automatic deletion or API-only repair is inferred |

Shortest coherent implementation dependencies after approval:

```text
Q04 normalized owner/publication + Q05 member/terminal + Q06 children/targets
        + required Q01/Q02/Q03/Q08/Q09 family contracts
                    |
    domain writers/schema/readers/eligibility/restart migration
                    |
    Q10 normalized export/receive/selective closure + conflicts + Coverage
                    |
    remove originals, profiles/DAGs, obsolete JSON refs/CLI/certificates
                    |
    Q11 physical-store refinement, preserving CAS-41

Parallel preparation: schema audit/characterization;
                    Git raw-content verifier/backup review;
                    Q07 cache alternatives;
                    field inventory and Source publication design.
```

Code-bearing strides need integrated writer/schema/reader/Exchange/maintenance
tests and frozen-source certificate regeneration while the old certificate
mechanism is reachable. No migration or compatibility layer is necessary for
this unreleased project. Partial runtime interfaces that disagree on publication
identity are not useful intermediate deliverables.

## Executable evidence and safe implementation candidate

[`exchange_probe.py`](../prototypes/exchange_probe.py) executes the complete
packaged DDL and production Graph/CAS on disposable synthetic catalogs. It
requires an explicit synthetic state directory and reports source/schema
fingerprints. The baseline receipt is
[`exchange-baseline.json`](../prototypes/exchange-baseline.json).

```sh
python docs/phase2/prototypes/exchange_probe.py \
  --state-dir /tmp/git-repo-db-p2-exchange-example --sizes 0 256 1024 4096
```

Baseline Python 3.12.14 / SQLite 3.53.1: SHA-1 and SHA-256 blobs sharing one
physical body export 11 records. Reversed intake admits all 11; repeated intake
adds zero; removing the body stages 3 records; its later delivery admits 4
records and clears staging. Physical corruption yields one quarantine; verified
Git repair clears active quarantine and keeps one historical diagnostic. Fresh
FK and integrity checks pass. CAS-41 service backup/restore is separately
covered by the production cases listed below; the standalone probe does not
claim to execute that service lifecycle.

The operation-count probe preserves the Phase 1 export-scoping guarantee:
selected empty-repository export stays at 223 statements and approximately
4,000 SQLite VM opcodes as unrelated verified blobs grow 0→256→1024→4,096.
It also demonstrates a safe optimization opportunity: conflict-free
`refresh_resolution_blocks` currently performs 75→1,611→6,219→24,651 statements
and approximately 0→31,000→125,600→503,200 opcodes. It materializes every product
table and builds dependency edges even when the conflict seed set is empty.
The three old barrier tables must still be cleared, and pending selection
scope barriers must still be recomputed. After those steps, an empty seed set
cannot traverse any dependency edges. An early return at that exact boundary
preserves all domain semantics and avoids the unnecessary global walk. This
fix is independent of every deferred Phase 2 policy and belongs in a separate
implementation commit/PR with positive-conflict and pending-scope regressions.

These are operation counts, not clean timing benchmarks; other agents may run
tests concurrently. The VM progress callback is invoked every 100 opcodes, so
each measurement has that granularity. No wall-time comparison is claimed.

Existing regression contracts executed for this workstream:

* `test_catalog3_exchange.py`: portable remapping, typed ownership, byte integrity,
  missing parents, immutable content conflicts and local parser trust separation.
* `test_catalog3_selective_exchange.py`: reordered/repeated acquisition units,
  exact selective closure, 304 anchors, multi-input/output publication, partial
  member sets, conflicting completion, incomplete selection heads and production
  nested-thread completeness with 1/101 replies.
* `test_catalog3_exchange_integrity_audit.py`: Source-wide exclusion, quarantine
  exclusion, shared byte deduplication, permutation convergence and 304 identity.
* `test_phase1_exchange_retirement.py`: original-only and malformed/forged root
  attacks, missing-late dependencies, valid SHA-1/SHA-256 repair staging, and
  grouped promotion preflight.
* `test_phase1_exchange_scaling.py`: selected export independent of 4,096 unrelated
  blobs and intake independent of 12,000 unrelated admission receipts.
* `test_catalog3_cas_integrity.py` and `test_backup.py`: true/forged Git identities,
  physical diagnosis/explicit repair, rollback, process death, CAS-41 count and
  backup/restore publication/failure invariants.

The final integrated verification ledger records actual node counts and tested
feature revisions. This workstream's documentation/probe checks are not a claim
that the unapproved replacement architecture passed runtime acceptance.

The focused baseline characterization executed 131 cases without bootstrap;
one additional CLI backup fixture had a setup error because `repo-catalog` was
absent from PATH. With the environment's `venv/bin` added to PATH, that isolated
backup case passed. Both runs and JUnit hashes are recorded in
[`exchange-characterization.json`](../prototypes/exchange-characterization.json).
The first run is explicitly a failed invocation, not a 132-case success receipt.
Ruff lint/format, Python compilation, JSON parsing and whitespace checks passed
for these design/probe artifacts. Packaging/full-runtime acceptance is performed
for the integrated code-bearing PR rather than inferred from these focused runs.
