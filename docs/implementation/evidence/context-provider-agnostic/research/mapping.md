# Repository Mapping investigation (B)

Investigator artifact, not an independent review. Frozen product commit:
`efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`; tree:
`117d580b31098ecb8287281bd843894fdfad71fc`. Read on 2026-10-19 UTC.
The source links below pin that revision. No Provider API claims are derived
from these synthetic tests; the same numeric ID across GitHub/GitLab is an
intentional synthetic namespace counterexample.

## Result

The existing Context placement preserves Provider identity, permanent Repository
UUID, immutable conflicting mapping claims, and evidence-qualified disposition
semantics. Neither a new Mapping store nor moving these claims to Core is
necessary to support many Provider repositories per Core repository. The
existence of a qualified mapping candidate does **not** establish that Core is
present, that a Core repository/object has been acquired, or that Access permits
connecting. The typed API can be used on Context alone.

No Implementation Defect or Architectural Conflict was demonstrated in this
scope. The broad future annotation/relationship vocabulary may require separate
contracts; it does not establish a defect in the six approved Repository roles.
No change is proposed to those roles or to the no-Witness decision.

## What the eight relevant relations mean

| Authority / relation | Meaning and limits |
| --- | --- |
| Context `resources` | Provider ResourceKey `(service_instance_uuidv4, resource_kind, provider_resource_id)`; Provider Repository is kind `repository`. No repository UUID column and no URL/OID equality identity inference. |
| Context `repository_context` | Context-local registration of a UUID used by its FKs; registration/configuration is not a Provider mapping and not proof of a corresponding live Core row. |
| Context `resource_repository_relations` | Six finite roles; canonical target JSON directly in a claim key. Generated nullable UUID has a real FK to **Context-local** `repository_context`. |
| Context `repository_mapping_dispositions` | Immutable `dispute`, `withdraw`, `correct` reports addressing full MappingClaimKey; correction references a complete replacement claim for the same Provider Repository. |
| Context `resource_relations` | Provider-to-Provider relationships, including typed `provider_repository_roles`, preserve known Provider affiliation while Core mapping remains unresolved. |
| Context `source_repositories` | Known-positive membership of Source registration to UUID; neither a Source inventory nor a resource registration asserts `represents_repository`. |
| Core `repositories` | Permanent UUID identity; independent of Provider registration and Context availability. |
| Access `repository_locators` | Current `(scope_uuidv4, locator_text)` binding to UUID, without a cross-file Core FK. A mapping claim grants no approval, credential or connection configuration. |

Source: [Context DDL L2–41](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L2),
[relations L248–278](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L248),
[dispositions L360–410](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L360),
[Core L2](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/core.sql#L2),
[Access L7](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/access_ddl/connections.sql#L7).

## Typed lookup and qualification

| Question | Actual route and interpretation |
| --- | --- |
| Provider ID → UUID | Construct repository ResourceKey with the genuine service UUID and ID. `evaluate_provider_repository(key)` returns all active claim UUIDs and state. `repository_relations(key, 'represents_repository')` returns retained claims with support status. |
| UUID → Provider repositories | `relations_for_repository(uuid, 'represents_repository')`; return row resource keys, retaining multiple reports for one resource. Deduplicate only ResourceKeys for a listing, never erase underlying claim evidence. |
| Multiple Providers → one UUID | Separate service UUIDs permit the same Provider ID text. Two positive mapping claims coexist and reverse lookup returns both. |
| One Provider → conflicting UUIDs | Both immutable claims survive, including newer-clock arrivals. Evaluation is `conflict`; `active_repository_uuidv4s` includes both. Neither is a selected winner. |
| Unknown / unregistered | No claims yields `unmapped`. Provider affiliation may exist in `resource_relations` without any Core-target row. Missing affiliation, explicit-null role, and unresolved Provider-only affiliation remain separate. |
| Dispute / withdrawal / correction | Preserve the reports. No supplied evidence leaves withdrawal/correction unconfirmed; a dispute remains contested. Caller-supplied operation evidence may qualify withdrawal/correction for that read only. A correction retains both claims and identifies the old claim as corrected. |
| Available Core target | First inspect the mapping state/support status; separately open the appropriate Core snapshot and check its `repositories` / relevant typed OID. Finally resolve Access independently if execution is requested. |

The forward evaluator and reverse lookup are [adapter L469–692](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_context.py#L469);
production guarded APIs are [L831–949](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L831).
The operation-evidence contract and evaluator are [domain L1297–1497](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L1297).
`ResolvedRepositoryRelation.is_core_resolved_active` checks support status and
non-NULL UUID only ([L1577](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L1577)); it performs no Core lookup. This is a qualification property, not a proof of acquired Core content.
The query convenience UUID is emitted only for an Issue/PR with agreeing
single-candidate primary roles; the full alternatives remain in its view
([query L1084–1110](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/application/production_query.py#L1084)).

`MappingOperationEvidence` is an explicit trusted-caller input. These tests
construct synthetic evidence to exercise evaluator behavior, **not** to prove
issuer authenticity. The current application accepts it from its caller;
implementing a real verifier/operation integration would require preserving the
same qualified-evidence boundary, not inferring authority from `source='local'`,
issuer equality or Exchange digest. The existing I4 contract explicitly describes
this input: [I4 L31](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/implementation/adr0030-i4-query-search-backup.md#L31).

## All six roles and broader metadata

| Role | Subject / semantics |
| --- | --- |
| `represents_repository` | Provider Repository; positive non-NULL immutable mapping claim. No clock-based winner. |
| `owning_repository` | Issue only; current candidates, genuine NULL allowed. |
| `base_repository` | PR only; current candidates, genuine NULL allowed. |
| `head_repository` | PR only; current candidates, genuine NULL allowed. |
| `transfer_from_repository` | Issue-parented timeline-event comment; immutable actual-event endpoint report. |
| `transfer_to_repository` | Same event constraint; paired only in the same EventResourceKey/clock/provenance. |

DDL enforces role/resource compatibility; Transfer typed admission requires the
whole actual report rather than arbitrary generic endpoint insertion. Strictly
dominated comparable current candidates are pruned atomically; equal,
incomparable and unknown clocks retain alternatives. Reviews/comments inherit
neither implicit Repository membership nor extra mapping rows. A generic
annotation cannot use `owning_repository` simply because its target is a
repository: that would change an approved role's meaning. Broader annotation
associations belong in the audit of existing generic Resource relations or a
separately reviewed extension, not a fabricated seventh Repository role.
See [domain L259](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L259),
[adapter L108](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_context.py#L108),
[pruning DDL L334](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L334), and
[ADR 0030 ledger](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/0030-context-repository-relations-and-selective-exchange.md#L45).

## Placement alternatives (evaluation only)

| Criterion | A: retain Context (baseline) | B: place in Core | C: independent Mapping/Link store |
| --- | --- | --- | --- |
| Meaning / Provider independence | Provider-attributed contextual claims remain with Provider identities; service UUID namespace is already generic. | Provider schema/provenance enters Git authority; moving a table alone does not generalize its vocabulary. | Potential shared bridge authority, but purpose/trust/ownership must be defined before benefit is established. |
| Core independence / INSERT-only | Core needs no Context to remain valid; immutable claims/dispositions coexist with current Context data. | Claims could be append-only, but Provider dependencies must be duplicated into Core or become external obligations. Requires accepted boundary change. | Can preserve Core independence, but adds another authoritative dependency for consumers and another failure mode. |
| SQLite FKs | Real local FKs cover resources, registration, claims and dispositions. UUID→Core presence is a separate check, not a fictitious cross-file FK. | Core UUID FK improves only one endpoint; Provider Resource FK crosses the boundary unless Provider identity is duplicated. | Both Provider endpoint and Core endpoint cross files; no net referential-integrity win without duplicated registries. |
| Transactions / failures | Existing Context atomic units, Core-first paired admission, pinned snapshots; partial Core-only commit is honestly reportable. | Existing split-store graph changes; copying all Provider registration is not justified merely to remove one join. | Adds third authoritative commit/checkpoint/revalidation stage; interrupted partial commits need explicit behavior. |
| Backup / restore | Existing full Core+Context paired domain backup captures reports, dispositions, provenance and supporting claims. Access remains separate. | Core-only backup would contain contextual claims and dependency questions; existing scope contract must change. | Full backup becomes Core+Context+Link (or explicit independently coordinated snapshots); additional validation and activation protocol. |
| Selective Exchange | Existing exact claim/replacement dependency closure, bounded selection and honest omissions apply. No local evidence is imported as verification. | Serialization/selection/admission owner changes, requiring wire/dependency retesting. | New envelope section, selection policy, dependency and multi-store admission/failure contracts required. |
| Several Context stores | Exchange portable exact semantic claims into each Context; qualification can legitimately differ with locally available evidence. Context-only reads are supported, but arbitrary direct pairing with another catalog is not assumed. | Global shared Core would expose Provider claims to every Core reader and enlarge write trust boundary. | Central sharing is plausible only if concurrent writers, authorization, outage, retention, sharing and snapshot consistency requirements justify it. Not demonstrated by these tests. |
| Writes / trust | Context writers submit attributed reports; qualified operation evidence remains explicit; Access approval is independent. | Provider-report writers would need access to Core authority, increasing boundary complexity. | Requires new writer/reader permissions and trusted operation-evidence boundary; moving rows does not authenticate their issuers. |
| Future bridge relations | Generic Context relations may support extension without moving mapping authority. Six approved Repository roles remain unchanged. | Every new external bridge broadens Core's responsibility. | Could help genuinely independent many-domain bridge requirements, but speculative breadth is not evidence that a sixth store is needed now. |
| Search / validation cost | Existing rebuild/fallback and mapping-aware query evidence contract remain; tests extend at current boundaries. | Rework projections/fences and domain checks. | Additional snapshot fences, indexes, manifests, recovery/Exchange failure matrix and integration tests. |

Recommendation for designer consideration: retain A. First use the existing
mapping API; next extend Provider normalization and explicit operation-evidence
integration where needed. Consider typed read conveniences that name candidate
qualification and actual Core availability separately. Only evaluate B/C if a
concrete new durable sharing or authority requirement cannot preserve meaning in
A; either needs a separately accepted architecture decision. No option is adopted
by this audit.

Coordination evidence: [Core-first admission L544–589](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_coordination.py#L544),
[Context-only capability L252–301](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L252),
[paired validation L206–319](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_coordination.py#L206).
Pair identity validation checks the catalog identity; dependency validation checks
Core OIDs referenced by Context. It does not turn every Context UUID registration
into an assertion of a present Core repository. The low-level backup-candidate
helper [L733](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_coordination.py#L733)
explicitly does not claim power-loss-safe publication; do not mistake it for the
complete production recovery pipeline. Production backup/restore and selective
Exchange runtime evidence are handled in the collection/exchange investigation.
Selective Exchange retains a disposition only if its exact original and, for a
correction, replacement claim are retained ([L490–502](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/selective_exchange.py#L490)).

## Reproduction and classification

Run from repository root using the supported runtime:

```sh
.venv/bin/python -m pytest -c pyproject.toml docs/implementation/evidence/context-provider-agnostic/reproduction/test_mapping.py -q
```

Investigator's initial execution: Python 3.12.14 / SQLite 3.53.1, **9 passed**.
The audit's central runner provides durable machine-readable results. Fixtures
use fresh temporary Context databases, exact packaged DDL and the production
`Context.transaction` / `Context.snapshot` facade. No production state, live
Provider, credential, default runtime switch, product edits or ADR edits occur.

| Finding ID | Classification / severity | Reproduction and actual result | Expected meaning / impact / response | ADR change? |
| --- | --- | --- | --- | --- |
| MAP-N01 | Non-Issue / none | `test_mapping_forward_reverse_multi_provider_same_id`: two services with ID `42` map to R1; both returned forward/reverse. | Provider namespaces and many-to-one mappings already work. Retain ResourceKey and claims. | No |
| MAP-N02 | Non-Issue / none | `test_mapping_conflict_not_latest_winner_and_exact_replay`: two UUID claims survive reverse clock arrival, exact replay duplicates, changed original observation rejected. | Active alternatives are reports, not winner or acquisition proof. No rekey/merge; retain conflict state. | No |
| MAP-N03 | Non-Issue / none | Three disposition parameters: stored reports remain; absent evidence does not revoke; explicit synthetic evidence changes only current evaluation. | Correct ADR 0030 report/effect boundary. A real caller must supply genuine evidence; this test is not issuer verification. | No |
| MAP-N04 | Non-Issue / none | Unmapped Provider affiliation stored and queried without a Core UUID; later mapping resolves the view without rewriting the original role report. | Unknown mapping is not observed NULL. Existing representation suffices. | No |
| MAP-N05 | Non-Issue / none | Context-only qualified mapping exists with no Core/Access DB; unregistered Context UUID target fails its local FK. | Do not interpret `is_core_resolved_active` as Core presence or execution permission. Consumer documentation or an availability helper is an Extension Opportunity, not a demonstrated defect. | No |
| MAP-N06 | Non-Issue / none | Source positive membership and `resource(key, uuid)` precondition leave mapping `unmapped`. | Membership, registration and Provider→Core correspondence remain distinct. | No |
| MAP-N07 | Non-Issue / none | Disposition before original claim is rejected by FK, no stored row; after claim insertion admission succeeds and exact resend duplicates. | Missing dependencies require explicit retry, not staged fabricated claims. Exchange must report omitted units honestly. | No |

These are local B-scope IDs; the main findings register may cross-reference them
without counting them as defects. Source file/line links above identify each
behavior; all seven observations apply ADR 0029's independent Context/Access
boundary and ADR 0030 Q-S9–Q-S16 / Q-E6. No new blocking owner question was
identified by the mapping investigation.
