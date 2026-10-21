# D/E investigation: Collection, Coverage and end-to-end boundaries

Investigator report, **not independent review**. Frozen product commit:
`efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`; tree:
`117d580b31098ecb8287281bd843894fdfad71fc`. Investigation date:
2026-10-19 UTC. No product, DDL, accepted ADR or default-runtime changes.

The custom [probe](../reproduction/test_coverage_exchange.py) passed **10 nodes**
locally using Python 3.12.14 / SQLite 3.53.1. This is a supported newer SQLite,
not an exact 3.51.3 run. The root audit's consolidated execution receipt is the
machine-readable result and environment binding; these development runs are not
release qualification. All four Provider labels in the custom probe are
**synthetic normalized inputs**, not captured API responses or evidence of live
GitLab/Gerrit/Forgejo acquisition.

## Conclusions

The Collection/Coverage persistence, typed reads and Exchange paths are largely
Provider-independent for **already representable Resource kinds and correctly
partitioned semantic scopes**. The physically five-column Coverage Claim need
not change merely to add a collection kind. Correctly formed incomplete
deliveries withhold completeness rather than invent missing members. Exact
resend does not mint another observation or change its original time.

This does not make raw Provider normalization generic. The production acquisition
service imports GitHub normalizers, and the finite Resource/parent grammar still
limits which members can exist. Nor does generic JSON supply a registered
semantic contract for new collection kinds, permission scopes or incomparable
observation clocks. These are extension/engineering boundaries, not evidence of
an implementation violation of the accepted five-column model.

## D: capability matrix

| Requirement | Actual contract and limitation | Evidence |
| --- | --- | --- |
| Different Providers' lists | Provider service UUID is in every ResourceKey; arbitrary nonempty `collection_kind` is accepted. Four independently labeled synthetic batches survive typed Exchange. | Probe `test_generic_normalized_collection_typed_exchange_replay` (four parameters); [CollectionObservation](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/production_context.py#L227) |
| Lists directly on Repository resources | A Provider `repository` Resource can own `analysis_results` and assessment members without mapping to any Core repository. | Same probe; [collection admission](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L594) |
| Hierarchical Issue/Discussion/Review lists | The list structure is generic; named `reviews/comments/threads/documents` check member kind, service and encoded parent. A new collection name does not remove Resource DDL constraints: Review/Document require PR parent, Thread requires PR/Review. An Issue-owned arbitrary list is possible, but a genuine Issue-parented Thread cannot become valid by changing the list label. | [member check](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L520), [resource DDL](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L25) |
| Paging/partial acquisition | Membership and an immutable partial terminal do not prove complete coverage. A complete claim linked to the partial terminal is rejected and rolled back. No automatic union of pages into a complete terminal is demonstrated or implied. | `test_partial_members_cannot_prove_complete`; [proof FK/check](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L140) |
| Permission-dependent visibility | Scope JSON can describe visibility and provenance distinguishes original collections. An attempt to reuse one original collection key with another scope is rejected. Caller must supply genuine evidence/visibility coordinates; no credentials belong here. | `test_permission_and_clock_domains_use_distinct_provenance_scopes`; [scope binding](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L615) |
| Empty versus unobserved | Complete empty terminal + exact proof yields `known_empty`; missing claim returns unknown/None time/nonempty=false. | `test_empty_is_evidenced_and_missing_is_unknown` |
| No Provider completeness guarantee | Use partial/unknown, not complete based on presence of rows. The store validates evidence structure, not whether a Provider was truthful or its API exhaustive. | Partial test; [projection](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_context.py#L1048) |
| Later unknown observation | A newer unknown terminal invalidates an older complete proof's current qualification, while preserving the old claim/time. | `test_newer_unknown_terminal_invalidates_old_complete_without_rewrite` |
| Distinct clock domains | Coverage compares numeric `observed_at_us` within an owner; it has no FieldClock domain column. Distinct genuine collection provenance keys can keep incomparable observations separate. Same resource scope with 900 then 100 treats the second as stale even if the caller intended another clock domain. | `test_unpartitioned_resource_coverage_compares_numeric_times_only`; [claim admission](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_context.py#L1013) |
| Different Provider evidence | Service UUID is embedded in resource/collection scope; provenance is also embedded in collection owner. Source/service mismatches are rejected when those scope coordinates are present. Core Repository-level scopes intentionally lack provider provenance; adapters must not collapse incompatible scoped claims into them. | [CoverageScope](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L2371), collection admission above |
| New information type | New collection/coverage labels over existing allowed members need no new Coverage Claim columns. New Resource kinds/parent shapes need separate compatibility decisions and end-to-end validation. Arbitrary labels have no automatic typed semantic registry. | [five-column DDL](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/coverage.sql#L1) |

## E: stage-by-stage capability

| Stage | Established support | Boundary |
| --- | --- | --- |
| Provider input → normalization | Production GitHub REST/GraphQL normalizers retain typed IDs/clock/provenance. | Non-GitHub raw payload normalization is not implemented by merely selecting another `provider_kind`; [imports](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/application/acquisition.py#L21), [GitHub ID rules](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/github/production_intake.py#L50). |
| Already normalized input → Context admission | `ProviderIntakeBatch.observations/relations/collections/collection_proofs/coverage_claims/core_references` provide generic typed units. | Typed caller must provide genuine IDs, scope and evidence. Probe starts at this boundary for non-GitHub labels, [generic paths](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/application/acquisition.py#L1745). |
| Admission → SQLite | Production Context facade and composed product DDL used, including genuine FK/proof checks and five-column Coverage. | Resource vocabulary/parent restrictions apply; schema fingerprint is enforced by [P1 schema](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_schema.py#L109). |
| SQLite → typed read | `get_context_resource` returns field candidates, resolved text, arbitrary Resource relations, collections and typed Core dependencies; `get_context_coverage` evaluates evidence. | A preserved arbitrary JSON field or relation is not a specialized semantic query API. [Collection reconstruction](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/application/production_query.py#L1133). |
| Typed data → selective Exchange | Actual Resource parent/member/support edges expand within bounded selections; complete Coverage/proof/terminal units remain whole. | Repository selection does not implicitly select all its Provider resources; generic `annotates` edges are usable only through Resource selection/expansion, not invented Core membership. [Expansion](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/selective_exchange.py#L577). |
| Exchange → receiver → typed read | Custom tests preserve assessment object-valued fields, annotation text and multi-target relations, collection members/proofs, original times and exact replay. | Operational must be initialized; no Access settings or local trust authority are imported. Partial dependency delivery withholds the terminal/proof; available independent resources remain queryable. [Whole units](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/selective_exchange.py#L874). |
| Search | Current string field candidates and retained text are searchable independent of Resource kind; summaries recompute authoritative mapping qualifications. Missing/stale/damaged index falls back to authority. | Structured JSON object values are typed-readable but are not a generic structured/full-document search index. No implied graph/collection completeness query. [Extraction](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_search.py#L509), [fallback](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/application/production_query.py#L1461). |
| Paired backup/fresh restore | Actual SQLite snapshots cover all Context tables; shared catalog gate protects paired snapshot; domain/FK/fingerprint/manifest validation precedes fresh no-overwrite activation. | Access/Operational/Search excluded explicitly; backup does not establish Provider authenticity or new mapping qualification. [snapshot](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/recovery.py#L808), [exclusions](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/recovery.py#L980), [restore](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/recovery.py#L1949). |

The custom cases do not themselves claim to rerun every Search/backup scenario.
The root audit executes the existing I3/I23/I4 cohorts. Particularly relevant
I4 nodes are `test_search_rebuild_fallback_and_current_historical_summary`,
`test_paired_restore_preserves_all_keys_dependencies_and_excludes_other_stores`,
`test_paired_restore_coverage_source_text_and_git_only_boundary`, and
`test_forged_backup_with_valid_checksums_fails_semantic_restore`. These exercise
the actual product services, including disposable restore, not real catalogs.

## Findings proposed for the consolidated inventory

### CE-01 — non-GitHub raw normalization boundary

- **Classification:** Extension Opportunity; **severity:** Major relative to a
  claim of end-to-end support for all four Providers, not a release blocker for
  the existing GitHub adapter scope.
- **Condition/result:** inspect/call `ProviderAcquisition.admit_batch` raw issue,
  PR or repository paths: they dispatch to GitHub functions, while generic
  normalized units work for all four labels in the custom test.
- **Expected meaning:** a GitLab project IID, Gerrit composite identity and
  Forgejo repository-scoped payload must first be normalized by their own
  documented contracts; relabeling a GitHub payload does not provide that.
- **Source:** acquisition lines 21–32, 1568–1731, 1745–1785; GitHub intake line
  50. **ADRs:** 0029 Context responsibility, 0030 original Provider namespaces.
- **Impact:** non-GitHub raw intake; existing typed persistence/Exchange remains
  usable. **Option:** add Provider-specific normalization behind explicit typed
  input contracts, with golden identity/paging tests before broader typed API or
  schema changes. **Accepted specification change:** not inherently required;
  parent/kind limitations need separate decisions, not disguised normalization.

### CE-02 — collection visibility/clock scope contracts are caller-defined

- **Classification:** Engineering Contract Gap; **severity:** Major when a new
  adapter would collapse independent evidence into one owner key.
- **Condition/result:** same Resource CoverageScope, numeric time 900 partial
  then 100 unknown: second admission returns `stale`; no clock-domain field can
  tell the facade the observations are incomparable. By contrast, genuine
  distinct collection provenance keys preserve both scopes and their outcomes.
  Reusing one original collection key with altered scope is rejected.
- **Expected meaning:** completeness applies to the actual visibility/filter/
  hierarchy and comparison domain. A caller must not turn an API permissions
  subset into a universal claim or compare unrelated clocks.
- **Source:** CoverageScope lines 2371–2512; CoverageClaim lines 27–48;
  ContextStore admission/projection lines 1013–1058; Context collection lines
  594–633. **ADRs:** 0028 classified times; 0029 preserved Coverage;
  0030 unchanged five-column claims, original clocks and evidence.
- **Impact:** future adapters and generic Coverage writers; no demonstrated
  defect against the accepted numeric latest-observation policy. Generic
  resource/repository scopes lack collection provenance qualification, so they
  need especially conservative use.
- **Option:** specify per-Provider semantic collection keys, visibility/filter
  scope, original provenance and comparable observation-time contract; use
  distinct genuine collection identities for incomparable evidence and query
  them separately. Add typed validation/tests before considering any table
  change. Do not manufacture provenance to evade conflicts or invent comparable
  timestamps. **Accepted specification change:** none for safe scoped usage;
  a universal cross-clock aggregate is a separate design question, not approved.

### CE-N1 — partial/empty/replay and generic collection transport

**Non-Issue**, informational: tested generic normalized observations survive the
actual typed pipeline; partial terminal cannot prove complete, absent is not
empty, missing member delivery withholds completeness, and exact replay preserves
original identity/time. This is deliberately bounded to represented kinds and
explicit selections. DDL acceptance alone was not used as the success criterion.

## Improvement order and consequences (proposals only)

| Level | Assessment | Schema / Identity / Coverage | Exchange / Search / backup / verification |
| --- | --- | --- | --- |
| 1. Existing implementation | Preferred for existing kinds, fields, typed OIDs, arbitrary Resource relations and scoped collections already expressing the intended meaning. | No schema/identity change; keep exact original provenance and five columns. | Existing generic transport/reads and whole-store backup work; add scenario tests to prevent accidental completeness inflation. |
| 2. Provider normalization | First implementation extension for GitLab/Gerrit/Forgejo raw input. | Adapter must encode actual namespace and paging/visibility semantics, not use URL/number guesses. No Coverage DDL change needed for represented members. | Existing Exchange and backup stay usable; normalized text participates in Search. Golden specification-derived input tests are required; this audit's synthetic labels are insufficient. |
| 3. Typed APIs/contracts | Preferred place to standardize semantic collection names, scope validation, clock comparability and query qualifiers. | Keep physical columns; forbid unsafe aggregation by contract. Genuine source identities must remain stable. | Validate identical rules at admission, decode and typed read; verify replay/dependency cuts. Search structured-value capabilities would be a separate API/projection extension; backup bytes remain whole. |
| 4. Existing Context tables/relations | Relevant only if kind/parent vocabulary cannot express the actual resource. | A changed CHECK/parent contract changes DDL fingerprint, identity composition implications and member validation; five-column Coverage can remain. | Update Exchange typed decoders/closure and semantic restore validators together; test old/new schema compatibility explicitly. Search summaries require kind review. Higher verification cost than adapter-only work. |
| 5. New Context relation/entity | Justify only with an identity or relation that existing entities cannot preserve. | Define true semantic PK/FK, provenance and Coverage owner before choosing a table. Do not create a storage surrogate, Witness or Publication. | Requires new wire/dependency/whole-unit/restore validation and query/search projection tests; whole SQLite snapshots copy bytes but do not alone prove semantic restore support. |
| 6. Change Context responsibility | No D/E evidence requires this. | Moving Provider completeness authority would split existing source/resource/proof dependencies and weaken clarity of five-store boundaries unless a new decision resolves them. | Cross-store snapshot, admission, selection and restore responsibilities grow; requires architectural review rather than adapter repair. |
| 7. Independent store | No demonstrated D/E advantage over Context for collections or mapping-related evidence. | Adds identity ownership and cross-DB proof dependencies without solving Provider normalization or clock comparability. | Requires new transport/permission/backup/failure contracts; Search spans another authority. Highest verification cost; do not select absent a concrete otherwise unsatisfied requirement. |

These levels are an evaluation order, not an instruction to prioritize fewer
changes over preservation of meaning. For example, renaming a genuine
Issue Discussion to an unrelated allowed kind just to avoid a CHECK change is
not justified by the successful generic-list tests.

## Reproduction and interpretation

```sh
.venv/bin/python -m pytest -c pyproject.toml \
  docs/implementation/evidence/context-provider-agnostic/reproduction/test_coverage_exchange.py \
  -q --junitxml=/tmp/context-provider-coverage-exchange.xml
```

Run from the frozen checkout with the actual supported SQLite interpreter.
The missing-member test removes one Resource from a **synthetic exported
package**, recomputes its digest through the product encoder path, and verifies
that receiver admission withholds the complete terminal. It neither damages an
authoritative Catalog nor equates a received self-consistent digest with trust.
The partial-proof test expects SQLite's real constraint refusal and confirms
that prior valid partial evidence survives. The numeric-time case is a
characterization of an unsafe caller assumption, not a proposed new Coverage
algorithm or permission to change five columns.

No Implementation Defect or Architectural Conflict was established by this
investigation. Broader Resource kind/parent and Core annotation-reference gaps
belong to the companion identity/resource investigation. Independent review and
the consolidated severity counts are recorded by the root audit.
