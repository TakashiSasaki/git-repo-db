# Current Issue/comment field contract supplement

This supplement describes the production **Schema 19** tree
`52a36cab26f2287591ff9296cac151fe135cc55a`, with DDL SHA-256
`d0fba8d577ffad700b17a7504f67228c375a00c16583e1d1c6a7eef7e12c9415`.
It adds the typed current Issue/comment fields omitted from F13–F14's metadata
inventory in the original [Schema 18 field contract](field-contract.json).
The original JSON and receipts remain historical evidence.

**Accepted** below means an already settled identity, content, ownership,
presence, provenance, ordering or receiver-local invariant. **Implemented** means
the current production field/reader contract that must remain correct while
reachable. **Proposed / Pending Q09** identifies new normalized vocabulary or
additional retained properties. A listed production column does not approve a
new physical layout, a historical lifecycle, automatic deletion or an Exchange
trust policy. The [guide](../../AGENTS.md) and
[transport-independent ADR](../transport-independent-core-adr.md) take precedence.

## Producers and consumers

`CollectionService.sync` → `GitHubCollector.sync_issues` / current REST collection
→ [`current_parser.issue` / `issue_comment`](../../src/repo_catalog/adapters/github/current_parser.py)
produces a present-field projection. `ApiFacts.current_context` resolves the
typed binding/service/Source and captures its nonsecret scope;
[`CurrentResources.admit`](../../src/repo_catalog/adapters/sqlite/current_resources.py)
validates, stages or transactionally updates it. A malformed resource, wrong
owner, missing parent or unfenced live update cannot acquire invented authority.
Imports use the same domain validation and preserve original per-field evidence.

[`issue_queries._scope`, `_eligible`, `_fields`, `issue_query`, `_project`](../../src/repo_catalog/application/issue_queries.py)
read identity, owner, workflow, exact text and evidence for `issue list/show/comments`
and `search issue`. `_eligible` uses `Store.one` to join text and current eligibility;
the eligibility view reads actual conflict/parent dependencies. State/author and
document-author filters consume state/login; search and
[`index.refresh_documents`](../../src/repo_catalog/adapters/sqlite/index.py)
consume exact title/body. Public output is a real consumer of metadata and evidence.

[`Graph` export/admission/promotion](../../src/repo_catalog/adapters/sqlite/exchange.py)
carries typed current values and exact domain text, checks portable owner/parent
dependencies and preserves disputes and late arrival. Sender checks never become
receiver checks. Maintenance/backup verifies required exact text independently
of optional recording. Current Issue/comment values are not sealed historical
parsed-result members and do not require saved HTTP, parser profiles or certificates.

## Complete current column and meaning map

The following groups account for every `issue_resources` column, including the
generated parent discriminator, plus the exact text reached by its content FK.
Producer abbreviations: **P** = the live provider parser; **A** = typed context and
CurrentResources admission; **D** = SQLite derived/constraint state. Every mutable
value uses the original retained field evidence described in CI-09, rather than
automatically inheriting the newest row-level provenance.

| Group and production fields | Meaning, producer and source | Consumers and exactness/presence | Status and retention boundary |
| --- | --- | --- | --- |
| **CI-01 identity:** `service_instance_uuidv4`, `kind`, `provider_resource_id` | A supplies the independently registered service; P takes the canonical positive GitHub database `id`. `kind` distinguishes Issue from comment. Natural key is `(service_instance_uuidv4, kind, provider_resource_id)` | Current admission, parent/receipt keys, query lookup and Exchange. Canonical decimal TEXT is identity; login, URL, repository name and Issue number cannot rekey or merge it. Missing/invalid identity rejects, not an unknown/null resource | **Accepted** identity separation; **Implemented** two-kind physical key. Retain this identity responsibility through any replacement. It does not select actor identity expansion or historical PR/comment policy |
| **CI-02 current membership and parent:** `repository_uuidv4`, `repository_binding_id`, `provider_issue_number`, `parent_provider_resource_id`, generated `parent_kind` | A resolves the current typed repository/binding. P supplies Issue `number`; comment endpoint context supplies parent provider ID/number. D derives `'issue'` for a comment parent and NULL for an Issue | Owner/FK guards, current-number lookup, comments, Coverage scope, transfer propagation and Exchange. Number is positive signed-int64 SQLite INTEGER. Issue parent is NULL by kind; comment parent is required canonical ID under the same service. Unknown parent stages; wrong parent/owner rejects. `parent_kind` is an implementation discriminator, not a provider assertion | **Accepted** typed ownership/parent and permanent repository UUID. **Implemented** current membership can transfer without changing CI-01 or original capture. Physical discriminator/layout is implementation-dependent; no URL/name-based merging |
| **CI-03 title/workflow:** `title`, `state` | P reads exact `title` and Issue `state` (`open`/`closed`). Live ordinary Issue requires them; comment rows have NULL title/state by typed shape | Public title/state, title search/indexing and state filters. Title is exact UTF-8 text, including empty string, without trimming or normalization. SQL NULL in a partially known/imported Issue is interpreted with its evidence; comment NULL is a kind constraint. A partial field omission preserves its previous value/proof | **Accepted** exact text and presence; **Implemented** Issue field inventory and comment restrictions. Retain while current readers exist. New workflow enums or wider provider state vocabulary are **Proposed / Pending Q09**, not silently accepted |
| **CI-04 exact body and availability:** `text_body_sha256`, `body_status`, referenced `text_bodies.body`, `text_bodies.byte_length` | P distinguishes omitted `body`, explicit null and present string. A interns exact UTF-8 text and computes SHA-256/byte length. State vocabulary is `present`, `provider-null`, `missing`, `inaccessible` | Text validation, public body/status/hash, search/index, Coverage body-availability reasons, Exchange and backup. `present` requires a content FK; `""` is a real zero-byte body with its own digest. Explicit null has `provider-null`, not an empty body. Omission in a newer partial capture preserves previous body/status/evidence. `missing` and `inaccessible` do not fabricate text or an HTTP outcome | **Accepted** exact content and missing/null/empty distinction; **Implemented** availability vocabulary. No HTTP-original hash or raw response is needed. Content retention duration/GC and external body fetching remain unapproved; no edit-history table is introduced |
| **CI-05 author and domain locator:** `author`, `url` | P reads `user.login` and `html_url`. A present user object without `login` omits the author assertion; `user:null` or `login:null` explicitly asserts null. Empty login/string remains exact | Author/document-author filters, public output, semantic fingerprints/conflicts and Exchange. Omitted author/URL preserves previous value/proof; explicit null is distinct from unknown with no proof. URL is an observed domain web locator, not repository identity, HTTP envelope or authorization to fetch it | **Accepted** presence/provenance and no identity merging by names/URLs; **Implemented** retained login/web URL. Provider user/team IDs, actor type, node locator and selected extra links are **Proposed / Pending Q09**. Existing login alone must not be claimed as a durable actor resource identity |
| **CI-06 confirmed deletion state:** `deleted` | A accepts an explicit typed domain deletion assertion; D retains the row and disallows physical deletion through the existing trigger. Current GitHub parser does not infer deletion from a missing list member or sparse object | Eligibility, ordinary reader/index exclusion, semantic conflict handling and Exchange. Logical false/true is a typed flag; absence from a partial or complete scan alone is not a confirmed deletion assertion. Resource identity and capture survive a tombstone | **Implemented** current tombstone/physical-retention contract, protected by accepted truthful-evidence rules. Broader deletion propagation, automatic cleanup, duration and GC remain unapproved |
| **CI-07 comparable provider evidence:** `provider_updated_at_us`, `provider_clock_scope` | P parses REST `updated_at` for Issues/comments to signed-int64 Unix epoch microseconds; declared scopes are `github-issue-updated-at` / `github-issue-comment-updated-at` | CurrentResources dominance/field merge, staging/conflict resolution, query timestamp and receipt/Exchange evidence. NULL is unknown; zero and negative values are valid. Clocks compare only within the justified resource/endpoint scope. Parse/receipt time, UUID or parser version never orders different values | **Accepted** time units, comparability and unresolved contradictions; **Implemented** these two endpoint scopes. Adding another comparable clock is not authorized. Provider creation/closure times inside metadata do not acquire ordering authority |
| **CI-08 row capture and producer:** `observed_at_us`, `parsed_at_us`, `parser_module`, `parser_version`, `acquisition_scope_json` | A records actual observation/parse times and nonsecret captured scope; P supplies its actual module/version (`repo_catalog.adapters.github.current_parser`, version `2` at this baseline). Scope records captured service/repository/binding/Source registration, endpoint, principal reference, API version and preservation profile as applicable | Scope fences/guards, field evidence, transfer preservation, public provenance, current staging and Exchange. Times are signed-int64 `_us`; required row times cannot be NULL. Capture is not an HTTP request/response envelope or parser profile. Detached original capture IDs can survive transfer/import; validate existing captured registrations when present. The latest row attribution does not relabel inherited fields | **Accepted** genuine origin, Source independence and transfer provenance; **Implemented** captured-scope vocabulary. Normalized physical references and any additional capture fields are **Proposed / Pending Q09/Q12**. Source-wide inventory is not automatically imported with a capture snapshot |
| **CI-09 retained-value provenance:** `field_evidence_json` | A keeps evidence keyed by canonical field path, including original provider clock/scope, capture, observation/parse time and actual module/version. Imported evidence remains sender capture, never receiver confirmation | Field merge, genuine conflicts, scope validation, public `field_evidence`, current fingerprints and Exchange. Body/status form one field. Metadata objects have ancestor/child path evidence; arrays are currently observed field values, not automatically typed member proofs. Evidence cannot describe an absent candidate field. Omission keeps origin; a genuinely confirmed unchanged field can receive confirmation without asserting its omitted siblings | **Accepted** per-field truthful attribution, missing/null/empty/unchanged and type distinction. Preserve version `1` on inherited/imported fields when version `2` updates another value. Closed typed field paths/array-member provenance layout are **Proposed / Pending Q09**, not a new ordinary eligibility DAG |
| **CI-10 receiver-local check:** `last_checked_at_us` | A advances it only for accepted authoritative live acquisition with the matching pre-request revision and scope fence | Local public check timestamp and fencing/confirmation logic. NULL is no local check; signed-int64 zero/negative values are valid. Imported sender `last_checked_at_us` cannot advance the receiver. It is excluded from portable wire columns | **Accepted** receiver-locality and genuine live authority. No cache reuse, parsing time or repeated Exchange record manufactures a check. Final operational placement/lifetime remains Q12 |
| **CI-11 named provider metadata:** `metadata` | P keeps ten named outer Issue keys and two Issue-comment keys, detailed below. A keeps their known paths/proofs; current imported provider metadata may include additional arbitrary keys | Public metadata, semantic fingerprint/current conflict, evidence guards and opaque-provider Exchange. Omitted key differs from null, empty object/array/string and unchanged observed value. `true` and `1` remain distinct. Current opaque inner objects are not approved normalized original replicas | **Implemented** selected outer-key inventory; **Proposed / Pending Q09** inner vocabulary, types and typed memberships. Unknown fields are not disposable merely because no specialized filter reads them. Until consumers migrate, deleting them changes real current state/output/conflicts |

Deleting any CI-01–CI-10 responsibility breaks the listed domain identity,
content, ownership, field-origin, query, conflict or Exchange contract. Replacing
a physical column can be correct only when those consumers and their integrity
checks consume its accepted replacement together. The current-family lifecycle
retains distinct resources at latest accepted state; it does not choose historical
PR observations, PR conversation comments, independent thread history or Git selection.

## CI-11 metadata meanings and the remaining field decision

All outer keys below are read verbatim by the live parser when present. Their
original timestamp spellings and opaque inner provider objects are current
implementation boundaries, not the target normalized timestamp/field contract.

| Outer key/group | Current domain meaning and exactness | Provenance and proposed normalization |
| --- | --- | --- |
| Issue `state_reason` | Provider explanation for current open/closed state; omitted and explicit null differ. It is not a comparable update clock | Retained path proof under CI-09. **Proposed Q09:** approve a named state-reason vocabulary and unknown-value behavior, without changing accepted ordering |
| Issue `created_at`, `closed_at`; comment `created_at` | Provider creation/closure instant assertions; explicit null closure differs from omission. They are stored as provider JSON values today | Retained path proof. Signed-int64 epoch `_us` normalization is the accepted target format for retained instants; exact retained inventory and normalization layout remain **Pending Q09**. No creation/closure time becomes an update clock |
| Issue `locked`, `active_lock_reason` | Lock state and provider reason; omitted lock is not false, null reason is not empty text | Retained individual path proof. **Proposed Q09:** named typed flag/reason fields and explicit unsupported reason handling |
| Issue `labels`, `assignees`, `milestone` | Observed descriptive/membership attributes. `labels=[]` is known empty field value; omitted preserves previous evidence; null is explicit null, not a complete empty collection. Inner objects can contain IDs, mutable names/logins and locators | Current arrays are atomic field observations and objects have path proofs. **Proposed Q09/Q05:** approved label/actor/milestone identities and descriptive fields, typed memberships and separate completeness obligations where promised. No login/name/URL identity merging |
| Issue `comments` | Provider count assertion, distinct from an enumerated comment roster | Retained count path proof. **Proposed Q09:** typed nonnegative count/availability contract. A count cannot establish member or terminal completeness under accepted Coverage rules |
| Issue/comment `reactions` | Provider reaction-summary attributes/counts; provider locators and extra nested keys remain opaque. Summary is not a complete list of reacting actors | Retained object/child path proofs. **Proposed Q09:** closed named summary meanings/types and selected locators, or explicitly retire unselected properties. No generic leftover-response carrier |

Q09 still needs a concrete approved inner actor/label/milestone/reaction and
extension vocabulary. Feasible alternatives remain the original broad typed
domain contract, an explicitly enumerated functional subset, or named closed
extensions. This supplement recommends preserving currently observable meanings
with typed or closed named fields, while marking unsupported/unknown capture
honestly. It does not select which unknown properties to discard or retain.

The historical F08 timeline union, F12 Source repository attributes and F20
provider remainder are also **not closed validation schemas**. Naming broad
groups, hashing them or passing an audit is not their approval. Variant-specific
event keys/types/null rules, nested repository/actor meanings and unknown-kind
behavior still require a reviewed proposal and owner decision before production
replacement. A new unmodeled `domain_payload` is not a feasible alternative.

## Public projection, Exchange and storage implications

`issue_queries._fields` emits the identity/parent/number and current owner fields,
title/state/author/URL, exact body/status/hex digest, observation/provider/check/parse
times, actual module/version, evidence and metadata. It also emits local display
`repository`, `resource_kind=kind` and `resource_lifecycle="current"`; these are
presentation mappings, not new provider observations or portable identity keys.
`search issue` adds `field` (`title`/`body`) and exact matching `text`.
`deleted` and `provider_clock_scope` are consumed by eligibility/order even though
they are not separate ordinary `_fields` keys. Capture is visible through actual
per-field evidence; a public NULL alone cannot prove that a provider asserted null.

Exact body deduplication remains by UTF-8 SHA-256. Search/index rows are derived
and rebuildable; field evidence/current conflicts are domain correctness data.
Typing closed metadata can reduce repeated actor/label snapshots and add joins/
indexes; final storage/runtime costs depend on approved membership and vocabulary.
Removing a field can reduce bytes while also losing supported output/filter or
conflict semantics, so savings are not deletion authority. No duration or GC policy
is selected, and backup/CAS-41 responsibilities do not change.

Selective Exchange must preserve the accepted current natural key, typed present
owner/parent, exact text and truthful retained field origins; missing dependencies
stage and late arrival can promote. It cannot certify a past receipt by comparing
only today's mutable value, import a sender's local check or silently choose one
incomparable candidate. The permanent normalized collection proof and wire/trust
policies remain Q05/Q06/Q10, separate from this inventory.

## Regression and dependency-audit coverage

| Responsibility | Existing concrete regression evidence | Remaining replacement tests |
| --- | --- | --- |
| CI-01/02 independent identity, parent and transfer | `test_current_resources.py::test_issue_membership_transfer_preserves_natural_identity_and_children`, missing-parent restart/promotion; `test_current_state_independent_review.py::test_issue_parent_constraints_resist_direct_sql_bypass`; `test_issue_transfer_followup.py` | Chosen typed metadata references must also reject wrong service/owner and late mismatched actor/label parents |
| CI-03/04 exact text and availability | `test_current_resources.py::test_partial_and_provider_null_are_distinct_from_empty_and_missing`; `test_current_state_independent_review.py::test_sparse_update_preserves_exact_body_and_nested_known_fields`; current query/index/Exchange tests | Closed field migration must preserve exact title/body/null/empty and byte/hash/search consistency; no parser replay recovery |
| CI-05 sparse actor | `test_current_author_presence.py` across all five current parser families, including old-version origin and explicit null/empty login | If actor IDs are approved, test mutable login without identity merging and deleted/unknown actor distinction |
| CI-06/07 deletion and clocks | `test_current_boundaries_independent.py::test_equivalent_typed_deleted_flag_does_not_create_json_conflict`; current conflict tests; `test_current_state_independent_review.py::test_missing_clock_does_not_become_zero_or_use_large_observation_time` | Any new provider clock requires genuine comparability evidence and contradictory/equal/incomparable cases |
| CI-08/09 original capture and field origin | `test_issue_transfer_followup.py`; `test_current_projection_followup.py::test_partial_fields_keep_actual_parser_when_another_version_updates_row`; sparse author/nested version-1→2 tests | Proposed field/member layouts must preserve ancestor/child provenance, explicit null and repeated/late Exchange without origin fabrication |
| CI-10 receiver-local check | `test_current_projection_followup.py::test_imported_sender_check_is_not_a_receiver_local_check`, live scope/revision-fence tests | Proposed cache/checkpoint confirmation must satisfy the same authority predicate, not just presence of a matching validator |
| CI-11 nested/type distinctions | `test_current_boundaries_independent.py::test_equal_proof_retention_preserves_distinct_json_types` and equal-clock conflict variants; field-evidence JSON guards | Closed reaction/label/actor schemas, missing/null/empty memberships and unsupported/unknown extensions depend on Q09 |

The supplemental audit regressions in `tests/unit/test_phase2_dependency_audit.py`
compile actual Issue eligibility, Source inventory completeness and Git decoder
queries, including `Store.one/all`, plus CurrentResources/ParserModel/GitParsing
SQL-forwarding helpers. They prove prepared SQLite column/view/trigger dependency
access **without executing the statements**. Field-audit regressions ensure default
Schema 18-versus-19 mismatch explains both fingerprints and directs separate
current output; historical JSON is not rewritten. These focused audit checks are
not ordinary runtime acceptance or performance measurements.

The dependency auditor previously omitted `one/all`. The original field auditor
already recognized those two methods; its additional gaps were local SQL wrappers,
`executescript`, CTEs and async function attribution. Both now share the same SQL
interface/forwarder recognition, with their separate compilation/token evidence.

The audit's AST labels remain explicit: a receiver name or forwarded SQL argument
does not prove live dispatch; dynamic table names, argument aliases, custom/external
interfaces, and failed preparation remain unproven. The public literal-key extract
does not describe all dynamic `dict(row)` outputs. Full per-object error/rollback,
test/migration responsibility mapping and the remaining closed provider/event
vocabulary cannot be claimed complete from AST compilation alone.
