# Phase 2 field meanings, provenance and retention boundaries

Status: **Proposed / Pending Owner Decision** for the new retained-field contract.
This investigation does not select historical lifecycles, make provider metadata
disposable, or alter production field semantics. References describe fetched main
`20e0f8d78b77c6c8d37826fd6d639819631e166b`, tree
`003d276a6aeb6a1479232a1d0a1857db371cb623`, Catalog3 schema 18.

The executed eight-resource production composition has **57 CHECK-backed JSON
columns**, including **nine opaque provider projection columns** and one decoded
Git-header column. The registry contains exactly those 57 JSON columns; no
CHECK-backed column is unclassified. In addition, `resume_scopes.request_context`
contains explicitly opaque `head`/`base` subtrees, `collection_progress.cursor`
can contain JSON without a JSON CHECK, and accepted historical API bytes in
`stored_bytes.body` can contain complete response JSON. Counting only columns
named `payload` therefore materially understates the remaining work.

The [machine-readable contract](../field-contract.json) identifies 20 coherent
field groups, every JSON column/shape/nullable contract, significant typed
columns, schema guards/views, AST SQL call sites, and public projection syntax.
Reproduce it with:

```sh
PYTHONPATH=src python scripts/audit_phase2_fields.py
PYTHONPATH=src python scripts/audit_phase2_fields.py --check
```

The tool executes `schema_sql()` in an in-memory catalog and calls the production
JSON registry audit. It parses Python ASTs and records SQL calls inside actual
functions. Those static call sites are leads; the reachable producer/consumer
chains below establish responsibility. Dynamic SQL and generic Exchange paths
still require manual tracing. The public key extraction includes nested literal
dictionaries and cannot infer dynamic keys; it is not an approved new CLI schema.
No authenticated collection, user catalog, real cached response or private data
is involved.

## Decision precedence and current boundaries

The latest [AGENTS.md](../../../AGENTS.md) applies explicit owner instructions,
then accepted ADRs/scoped supersessions, then current production contracts, then
historical receipts. The accepted transport-independent ADR has decision date
2026-10-10 and TP-01–TP-08. Its initial "not implemented" statement is an original
checkpoint; the [current implementation boundary](../../transport-independent-core-implementation.md)
and [Phase 1 implementation](../../phase1-api-original-retirement-implementation.md)
describe Schema 18. Phase 1 R1–R7, also dated 2026-10-10, supersedes older mandatory
API-original mechanisms only within the retired feature scope.

Repository/service/Source identities, signed int64 `_us` times, Coverage v2's
exact five-column claim/maximum-time candidate contract, natural document keys,
exact UTF-8 content, typed owners/parents, truthful per-field module/version,
missing/null/empty semantics, incomparable conflict handling, transferred Issue
capture and receiver-local checks remain accepted. CAS-41 remains selected.
The [decision status](../../model-integration-status.md) preserves D1–D38 and
CAS-1–CAS-75 traceability with explicit Phase 1 supersessions; it does not turn
the 18 historical parser objects into a DROP authorization. There is no separate
new numerical ADR version inferred by this workstream.

Already authorized: preserve actual domain text and raw Git content, truthful
provenance and distinctions, remove mandatory HTTP-original dependence after its
responsibilities migrate, and never replace it with opaque unmodeled response
JSON. Proposed: the exact F01–F19 retained property sets, actor/reference layouts,
event variants and named provider extensions. Historical resource lifecycles and
Git selection remain separate owner choices.

## Actual writers, readers and opaque public contracts

| Production object | Reachable producer | Retained meaning and real consumers | Consequence of simple deletion |
| --- | --- | --- | --- |
| `change_request_observations.payload` | `CollectionService.sync` → `GitHubCollector.sync_pr` → `ensure_pr` → `canonical(value)`; list and detail objects are retained | PR identity/number/title/body/state/actors/head/base/counts; `pr_state`, filters, code target planning/limits/stability, `pr list/show`; `Graph.aggregate_proof` compares list members to admitted observations; immutable fact/publication Exchange | PR list/show lose all metadata; author/draft/state filters and code assessment lose inputs; historical roster proof loses identity verification; publication bytes still remain through direct result/fetch FKs |
| `document_observations.metadata` | `ensure_pr` and `_document_normalizer` → `ApiFacts.document`: every key except body/title/user/author | PR title/body and conversation-comment observation attributes; typed author/url and exact body are separately stored; `pr documents`/search expose metadata, immutable fact membership and Exchange preserve it | Removes observable domain timestamps/reactions/associations and natural-key context; title/body documents currently duplicate almost every PR detail attribute, but unknown residual keys have not been approved for deletion |
| `change_request_events.payload` | `sync_pr` nested `event` normalizer stores entire timeline item | `pr timeline` exposes every event value; Exchange seals/exchanges exact immutable contents; many kinds have actor/label/milestone/assignment/review/rename/reference/commit meaning even without specialized filters | Deletes supported timeline semantics and content-bearing event variants; event native ID may be absent, so a replacement cannot invent one from page ordinal |
| `review_thread_observations.payload` | `threads` → `_thread`: all non-comments thread fields; comments reduced to native comment IDs, pageInfo and `observation_complete` | Thread identity/resolved/outdated state; `pr thread`, resolved/outdated filters; `_thread_comment_boundary_complete` checks saved children and continuation; Exchange/root proof; restart relates root and child collections | Cannot prove child membership or a terminal boundary; dropping pageInfo before normalized proof exists turns a truncated tree into an apparently complete thread |
| `code_commits.payload` | `sync_pr` nested `commit`: entire PR commit item; typed OID stored separately | PR commit membership/order; `pr show` returns objects; commit filters and code proof require typed OIDs/positions; provider actor/signature/message metadata is independently observed | Typed OIDs alone keep filters but silently remove provider metadata/output; provider signatures must not be confused with Git object integrity |
| `code_file_changes.payload` | `sync_pr` nested `file_item`: entire item; filename encoded to exact UTF-8 `raw_path` | PR file membership, status/rename/OID/statistics/patch availability; `pr show` returns full object, path filters use typed raw bytes, code proof uses listing membership | Path matching survives but patch/rename/status disappear; absence of a patch is not an empty diff or proof that Git has no change |
| `repository_inventory_observations.metadata_json` | `discover` → `GitHubCollector.inventory` → `CollectionService.discover`: entire repository item | Subject Repository attrs under a **Source-owned** result; provider ID binding/name/endpoint discovery, public/private count checks, `repos list/show`; current Source selection gates it; single-repository Exchange excludes Source-wide inventory | Removes real repository observations and discovery/completeness corroboration; moving them to mutable `repositories.metadata` would overwrite independent Source observations and local display/configuration |
| `issue_resources.metadata` | `sync_issues`/current collections → `current_parser.issue` or `issue_comment`: named outer keys, opaque inner provider objects | Current field evidence/merge/conflicts; Issue/comment output metadata; source shapes listed below; imported opaque metadata participates in semantic fingerprints | Dropping metadata loses fields and their proofs; dropping unknown nested properties changes state fingerprints and can erase genuine conflicts |
| `review_resources.metadata` | current REST/GraphQL collection → `current_parser.review` or `review_comment` | Review node/_links; comment lines/ranges/side/subject/created-time; current evidence, `review_position`, documents/thread output, selective Exchange | Stable typed target/parent columns do not replace comment range meaning; changing metadata without admission/evidence/fingerprint redesign breaks inherited per-field attribution |
| `commits.metadata` | Git acquisition → `GitParsing.commit` decodes non-tree/parent first-line headers to an object | Git object/target readers expose decoded author/committer/encoding/signature metadata; raw header/message/object bytes independently retain exact content; Exchange carries interpretation | Decoded output breaks; interpretation may later be recomputed from retained Git bytes, but selecting a decoder/current interpretation remains Q08 |

These paths are reachable application behavior, not dormant keyword hits. The
remaining original dependency is often beside the JSON projection: domain rows
still own a `parsed_result_uuidv4`, whose nonempty typed input manifest needs
saved HTTP input, while direct fetch FKs and completion proof require the same
original closure. Removing only JSON or only originals does not resolve both.

Public JSON is a genuine consumer. `pr list/show` expose PR `payload`; `pr show`
also exposes commits, file changes, code observation/links and observation
references. `pr timeline` exposes event `payload`; `pr documents` exposes exact
body, metadata, author/url and current or historical provenance. `pr thread`
exposes thread payload and review position. `issue list/show/comments` expose
metadata and actual current field evidence. `repos list/show` expose each selected
Source inventory metadata object. Git object/target queries expose raw bytes,
decoded text/headers and interpretation references. Query `_bounded` output and
CLI presentation may bound arrays, but that does not remove the persistent
consumer contract. The pre-release application permits changing those outputs;
the owner must still select the retained domain meaning instead of silently
deleting attributes.

## Retained-field contract proposal

F01–F20 in the JSON artifact carry producer, consumers, meaning, status and
decision dependencies. The following is the preferred **proposal**, with exact
column versus closed domain-JSON encoding implementation-dependent.

| Group | Proposed retained facts | Current shapes and exactness considerations |
| --- | --- | --- |
| F01–F02 PR identity/text | Canonical provider database ID; scoped request number and typed binding; exact title/body under unchanged natural document keys; optional explicitly modeled provider node locator | PR `id` identifies title/body documents, not a generated document surrogate. Title/body bytes are exact UTF-8. SQL NULL without presence evidence is unknown; explicit body null, omitted body and `""` differ |
| F03 workflow | State, draft, merged status, merged/closed instants, locked/lock reason, nullable merge readiness/rebaseability and maintainer modification observation | `merged` and `merged_at` currently drive `pr_state`; `mergeable:null` can mean pending provider computation, not false. None of these counts/flags becomes ordering authority |
| F04 actors | Service-scoped provider user/team identifiers, observed login/type, nullable author and typed assignment/requested-reviewer/team memberships | Login/name is mutable display metadata. Avatar/API endpoint bundles are not an actor's identity. Deleted/null actors need an explicit state; `{}` or `{id:1}` omits login instead of asserting login null |
| F05 targets | Object format/OID for head/base/merge, source/base ref strings and typed service-scoped donor repository reference | Deleted fork `head.repo:null` is distinct from an omitted repo field. Nested fork names/URLs do not register, merge or rekey Repository UUIDs. A later changed head/base cannot validate an earlier target acquisition |
| F06 labels/milestone/counts | Canonical label/milestone IDs and observed names/descriptions/color/state; provider creation/update/close instants; integer counts/diff statistics; named reaction summary and association | Collection arrays omitted/null/empty differ. Counts corroborate provider limits but never establish a member/terminal proof. Mutable endpoint metadata must not become an invented comparable clock |
| F07 PR conversation | Exact text, author/login, domain web URL, creation/update instants, association/reactions, typed PR parent; provider locator only if selected | The current residual metadata is nearly a whole PR detail snapshot for title/body documents and a comment snapshot for conversation comments. Removing duplicated PR subtrees is safe only after typed PR facts and independent document attribution replace their consumers |
| F08 timeline event union | Common event kind, nullable native event ID, actor and occurrence instant; tagged label/milestone/assignment/rename/review-dismissal/request/cross-reference/lock/commit/document-specific relationships and content | Timeline items are heterogeneous, including comment/review/commit content. A `renamed` event's old/new titles and a `review_dismissed` event's target/message are domain facts even when no specialized query exists. Unknown kinds require explicit supported-contract limitations; no `raw_event_json` fallback |
| F09 thread | Natural thread key, resolved/outdated value assertions; typed child-comment membership and normalized nested terminal evidence | Actual GraphQL query selects id/isResolved/isOutdated and comments with ID/body/update/author/parents/positions/targets/path/line/diff. `_thread` stores child IDs/pageInfo/partial-root flag; it does not store duplicate comment bodies. `endCursor` belongs to operational continuation, while terminal and members belong to checked domain evidence |
| F10 PR commit metadata | Typed OID/list order/parent-tree references, independently meaningful provider message, actor mapping and explicit signature-verification assertion | A provider `verification` result is an assertion with its own observation, never the receiver's SHA/OID check. Message text may differ from Git-decoded text; collapsing them would rewrite provenance |
| F11 changed files | Exact current/previous paths, status, optional blob OID, integer statistics and exact optional patch with explicit availability | `patch` absent/null/empty differ. Provider patch can be omitted/truncated. Git-derived diff is a new derived interpretation and does not fabricate the missing provider patch. Retain source URLs/text without fetching external bodies automatically |
| F12 inventory | Provider repository ID and observed names/owner, endpoint observations, visibility/private/archived/disabled/fork/default branch/descriptive attrs, typed parent/source provider refs; explicitly scoped permissions/capability/count assertions where selected | Source owns an observation whose subject is Repository. Two Sources can see different permissions/private scope. Neither source permission becomes the receiver's authentication/check. `has_*`, license/topics/language/security fields need named semantics; they are not automatically disposable |
| F13–F14 ordinary current Issue/comment | All presently retained Issue state/lock/label/assignee/milestone/count/reaction and comment created/reaction facts, normalized and typed | Actual live Issue outer keys: `state_reason`, `created_at`, `closed_at`, `locked`, `active_lock_reason`, `labels`, `assignees`, `milestone`, `comments`, `reactions`; Issue-comment: `created_at`, `reactions`. Their current shared-store lifecycle remains accepted; it does not apply to PR conversation comments |
| F15 review | Existing state, exact text/body-status, author/web URL, submitted instant, target OID; optional named node locator | Actual metadata keys are `node_id`, `_links`. Submission time has no last-update authority; unknown `updated_at` extensions are deliberately ignored. Model needed web links directly instead of persisting `_links` navigation blob |
| F16 review comment | Existing target/original-target OIDs, original/current positions, exact diff hunk/path, typed review/reply/thread parent; lines/ranges/side/subject and creation instant | Actual metadata: `line`, `original_line`, `side`, `start_line`, `original_start_line`, `start_side`, `subject_type`, `created_at`; GraphQL supplies only the selected subset. Missing range/parent fields preserve prior evidence; explicit null removes the field only with justified admission |
| F17 provenance | Original service/Source/Repository/binding/endpoint/principal capture, observation/parse/provider-clock facts and actual per-value module/version; receiver-local check separately | Existing capture snapshots can survive an Issue transfer without importing the old Repository or Source-wide inventory. No message hash, fetch identity, profile certificate or selected parser DAG is a domain eligibility dependency |
| F18 Git | Verified SHA-1/SHA-256 raw Git object bytes; raw refs/names/paths/header/message/tag bytes and decoded fields according to approved interpretation | Current metadata projection loses repeated nonstructural keys and folded header continuations; raw headers/object bytes preserve them. Preserve required decoding settings or a justified byte-offset method without preserving whole parser definitions as authority |
| F19 code assessment | Checked head/base version relationship, target set, complete commit/file listings, matching acquired Git roots, missing-role reasons and provider caps | Replace authored assertion flags with checked normalized references, not trusted sender booleans. Explicit null merge roles stay observed null; absent merge role remains unknown. A code-complete assessment requires every independently required input |
| F20 unknown extensions | **No unconditional deletion or persistence decision** | Historical whole-object/residual-object writers admit arbitrary keys; current live nested label/actor/reaction objects and Exchange metadata also admit arbitrary keys. Approve closed retained semantics or named closed extensions. Never preserve an unknown original response under a new generic metadata name |

Provider instants retained as domain fields become signed int64 `_us` values with
NULL for unknown, including zero/negative valid values. The current provider
metadata retains original time spellings; this is a transitional snapshot
behavior, not a recommendation for untyped timestamps in the final model. Raw
Git headers legitimately preserve original time strings as exact Git content.

Presence is not encoded by defaulting every property to NULL. A candidate with
omitted `labels` asserts no replacement. `labels=[]` asserts an observed empty
set. `labels=null` asserts explicit null and cannot prove a complete empty
membership. An omitted scalar keeps its original proof. Explicit null carries a
present-value proof. A known unchanged value can receive new genuine confirmation
without attributing unobserved sibling values to that capture. Array/object/boolean
and integer value types remain distinct (`true` does not equal `1`). The current
field-evidence guards, metadata ancestor proofs and conflict tests enforce much
of this already; the new closed contract must preserve it.

## Information-loss boundaries and independent repair

`ensure_pr` passes `"" if value.get("body") is None else value["body"]` to the
historical PR-body document. PR payload preserves null versus omission, so
deleting payload before replacing the body presence assertion would erase the
distinction. `_document_normalizer` does the same for PR conversation comments
and `ApiFacts.document` excludes body from metadata; those document rows already
cannot reconstruct that difference. A fresh schema can correct capture semantics,
but no future parser may recover the old unrecorded difference or pretend a new
fetch is an old observation. Historical body-status/layout belongs to the
approved field/publication/lifecycle stride.

An independently determined current-parser defect exists at `_common`:
top-level omitted user/author omits normalized author, but a nonnull object whose
`login` is omitted (`{}` or `{id:1}`) projects `author=None`. It therefore clears
an earlier known author and attaches new author-null evidence under a newer
comparable clock. This is distinguishable from `user:null` and
`user:{login:null}` and violates the already accepted omission/null rule. The
separate corrective implementation preserves known author/evidence for omitted
login and retains explicit-null behavior; it selects no new lifecycle or field
inventory. Its targeted regression and independent-review evidence belongs to
the implementation PR's exact receipt, not to this document's schema audit.

`GitParsing.commit` filters out continuation lines and uses a dictionary of
header name → decoded first-line value. Duplicate nonstructural keys overwrite
one another, and multiline signature text is not represented in that JSON.
`raw_headers`, `raw_message` and verified raw object bytes still preserve the
domain content. No wholesale JSON-to-column conversion may silently describe
that projection as lossless or delete the raw bytes. Q08 must decide interpretation
selection and actual decoder configuration. `QueryService` search code/commit
byte offsets currently retrieve `git_text_encoding`/`git_metadata_encoding`
through result → profile settings; simple profile deletion breaks valid readers.

## Every JSON column's lifecycle classification

This covers all 57 executed registry entries. Registry category is validation
behavior, **not** proof that a value is operational, transport-only or disposable.
Generated schema references and FK dependencies in the artifact are not a DROP
list.

| Exact columns / group | Classification and retained responsibility | Replacement decision/dependency |
| --- | --- | --- |
| Nine provider columns in the producer table | **Replace** opaque snapshots with approved typed domain meanings; keep until dependencies migrate | Q09 plus family lifecycle, Q04 publication and Q05/Q06 proof; retain actual content/conflicts |
| `commits.metadata` | **Replace or retain a closed interpretation**, preserve raw Git content | Q08/Q09; decoder attribution and byte offsets must remain correct |
| `issue_resources.acquisition_scope_json`, `review_resources.acquisition_scope_json`, both `field_evidence_json` | **Retain semantic responsibility**; physical typed/ref layout may change | Already accepted capture/per-field provenance, transfer and receiver checks; no profile/message gate |
| `current_collection_pages.members` | **Retain semantic responsibility** for checked typed membership/observation attribution | Existing archive-independent model is evidence; Q05 may integrate it, not automatically copy it for every family |
| `completion_markers.evidence`, `coverage_claims.details_json`, `incremental_scans.evidence`, `code_observations.details` | **Replace mixed proof/assessment structures** with chosen normalized domain evidence; exact Coverage claim remains five columns | Q04/Q05/Q06/Q08/Q10; maximum-time/no-fallback invariant and safe watermark remain |
| `git_acquisitions.request`, `git_acquisitions.roots_manifest`, `git_acquisition_publications.object_manifest_json`, `git_acquisition_publications.root_manifest_json` | **Retain domain acquisition/root/object membership**; operational request subset may move | Q08 and publication encoding; raw Git acquisition identity and sealed exact bytes cannot disappear |
| `service_instances.metadata`, `repositories.metadata`, `repository_bindings.metadata`, `repository_endpoints.metadata` | **Retain local registration/domain annotation responsibility**; presently authored, not provider snapshots | Do not replace local configuration with Source observations; concrete permitted fields may become closed under Q09 |
| `identity_relations.evidence_json`, `identity_relation_cancellations.evidence_json`, `repository_name_observations.provenance_json` | **Retain identity/name assertion responsibility**, replace historical result provenance references | Accepted independent UUID/names/equivalence/cancellation rules; Q04/Q03 publication for generated names |
| `resume_scopes.request_context`, `fetch_occurrences.request`, `source_input_observations.request_context_json` | **Replace and split** domain capture from HTTP envelope/query/ETag/cursor/body-reference data | Q04/Q05/Q06/Q07/Q03; head/base provider subtrees are explicitly opaque today |
| `inventory_observations.scope` | **Replace** Source completeness/capture contract despite current `operational` category | Q03/Q05/Q06; preserve owner/principal/expected count/private scope/terminal semantics without input payload |
| `parsed_results.derivation_json`, `parsed_results.input_manifest_json`, `parsed_result_publications.fact_manifest_json` | **Replace** actual publication/output-integrity responsibility; retire result interpretation machinery after migration | Q04/Q08/Q10; exact outputs, typed owners, missing-dependency staging and conflicts cannot be lost |
| `parser_profiles.definition_json`, both verification criteria/evidence JSON, local trust rationale; both parser/fact predecessor manifests and parser/fact selection staging record JSON | **Remove after dependency migration**; decoder/field provenance and unresolved domain candidate behavior separately survive | TP-04 settled retirement target; Q01/Q02/Q03/Q08 current/historical resolution must be accepted first |
| `jobs.request`, `job_attempts.checkpoint`, `sources.settings` | **Retain only as needed operationally**; physical placement/lifetime pending | Q06; frozen nonsecret Source settings/credential references remain accepted; do not delete pending work |
| `exchange_source_provenance.definition_json` | **Retain sender definition provenance responsibility**; not receiver configuration or identity merger | Q10; independent identity subset and mutable definitions distinction must survive |
| `exchange_admissions.record_json`, `exchange_staging.record_json`, `exchange_admissions.local_key_json`, `exchange_local_identities.local_key_json`, `identity_relation_staging.record_json` | **Retain bounded admitted/staged/conflicting identity/dependency responsibility**, replace wire-specific envelopes | Q10; generic opaque rows can contain legacy provider JSON, so final normalization must change encoders/admission/promotion together |
| `payload_admission_staging.context_json`, `unresolved_payloads.diagnostic_json` | **Retain Git rejected-byte/physical corruption diagnostic responsibility**; API rejected originals already retired | Accepted CAS/shared physical integrity, Q11 physical split; no automatic cleanup or retention duration |
| `search_documents.metadata` | **Retain only while the disposable search implementation uses it**, not domain source of truth | Existing writes are `{}`; indexes rebuild from eligible exact domain text. Any future removal must check schema/reader/package dependencies, not assume emptiness proves dead code |

JSON-without-CHECK locations are enumerated separately in the artifact. In
particular, root/child continuation JSON embeds cursor/thread/occurrence and merge
information. Replacing the provider thread payload or original bytes before
durable normalized child/target/checkpoint evidence exists would break a restart
after a committed prefix. Its retention duration/physical store belongs to Q06.

## P2-Q09: directly answerable field decision

**Question:** Approve retained meanings F01–F19, including exact optional patch,
typed timeline variants, Source attributes and scoped permissions, with explicit
unsupported-field behavior for F20; or approve a narrower explicitly enumerated
domain contract?

Accepted constraints: preserve exact text/raw Git, natural identities, typed
owners/parents, missing/null/empty, truthful evidence, provider clock comparability
and genuine conflicts. No generic response JSON, replay, retrospective extraction
or secret authenticated response retention. The owner has not selected all
historical/current property inventories.

| Alternative | Concrete behavior | Correctness, storage and performance | Product/Exchange/Coverage/backup/test effect |
| --- | --- | --- | --- |
| **A: typed broad named contract — recommended** | Persist F01–F19's modeled domain facts and type-specific child relationships; closed domain JSON only where its keys and semantics are defined | Preserves meaningful metadata visible today while eliminating actor/repository/API-object duplication. More joins/typed rows than a minimal projection; indexed parent/resource/time access, relational membership and shared exact text avoid reparsing and wide copies | New outputs show named domain fields; selective Exchange validates exact typed closure. Membership/terminal proofs remain independent from counts. Backup carries domain bytes. Test event variants, presence and scope/ownership per group |
| B: typed functional minimum | Preserve accepted invariant fields and the reviewed feature subset; explicitly retire unselected metadata/patch/timeline/inventory fields from supported output | Smaller storage and validation surface; irreversible loss of unselected semantics for future acquisitions, with no old-response recovery. Must not infer "unused means disposable" | Owner must approve each observable removal; unsupported-field/product limitations become explicit. Coverage promises cannot exceed capture capability. Exchange and backup carry fewer facts; absence tests distinguish unsupported versus unknown |
| C: typed core plus named extensions | Core invariant fields relational; approved provider-specific closed extension schemas for review location/reactions/verification/selected inventory details | Feasible when provider shapes differ substantially. Bounded nesting and known references retain semantics; schema-versioned named extensions avoid generic responses. More schema/version validators; index extracted frequently filtered values | Exchange validates approved extension kind/version/keys and references. Partial/unknown extension capture is explicit. Backup preserves exact domain text. Tests reject unrecognized keys/reference types and distinguish absent/null/empty |

A and C can share physical choices; the real decision is which named facts and
capture guarantees the product promises. Neither permits `provider_payload` with
arbitrary leftover keys. Unknown timeline kinds cannot silently masquerade as a
complete supported event inventory; the exact unavailable-kind policy must be
approved alongside the selected variants.

Examples that distinguish alternatives:

1. File `a.py` has `patch` omitted, then explicit null, then `""`. A retains all
   three availability assertions and exact text. B retires provider patches
   explicitly. C models them in an approved diff extension. None manufactures an
   empty Git diff from the omitted patch.
2. A timeline rename stores `{from:"before",to:"after"}`. A retains a typed
   rename. B must openly remove that event detail from the contract. C keeps a
   named rename extension. A generic original event object is not an alternative.
3. Source S1 and S2 observe R's private visibility/permissions under different
   principals. A/C preserve scoped observations; B can omit permissions from the
   product promise. None assigns either sender's check/authentication to the
   receiver or overwrites R's permanent identity.
4. A thread's known comments `[501]` with `hasNextPage=true` remains incomplete
   even though all currently listed IDs exist. All alternatives require chosen
   normalized child terminal/membership evidence before removing pageInfo.
5. Newer Issue input omits labels; prior label proof survives. `labels=[]`
   establishes observed empty membership only under the chosen field-set
   semantics. `labels=null` remains explicit null; it never fabricates empty
   complete coverage.

Dependencies: Q01/Q02/Q03 establish history/current lifecycles, Q04 publication
owner/member boundaries, Q05/Q06 normalized flat/nested completeness and restart,
Q08 Git interpretation/current selection. Q09 fixes meanings before Q10 can
finalize portable validators and exact closure. A field can be typed before its
retention duration is decided; no automatic deletion/GC policy is implied.
Q09 blocks wholesale projection replacement, not the audit tool, design probes,
or the accepted current-parser omission repair.

The implementation stride should cover writer, schema/guards, readers/filters,
public output, Exchange encoder/admission/promotion, backup validation, search
and meaningful tests together. An isolated DROP or a renamed snapshot does not
meet the target. Typed current-family projection work can run in parallel with
historical publication and Source/Git work after their interfaces and field
contracts are accepted; shared publication/proof/Exchange schema integration
remains one coherently reviewed tree.

## Verification and remaining regression needs

Executed design audit: fresh in-memory composed DDL, production registry coverage,
FK/integrity checks, deterministic generation and AST parse. This document is
not ordinary runtime acceptance and does not reuse Phase 1 passing counts.
The integrated PR receipt records exact checked revision/tree, environments and
later corrective implementation acceptance separately.

Existing regressions that must remain meaningful include:

- `test_current_resources.py`: body missing/null/empty, typed owners, parent
  staging and clocks; `test_current_projection_followup.py`: sparse field clocks
  and actual per-field parser producer.
- `test_current_state_independent_review.py` and
  `test_current_followup_adversarial.py`: nested inherited proofs, equal-clock
  contradictions, transfers, hidden conflicts and late arrivals;
  `test_current_boundaries_independent.py`: strict JSON value type distinctions.
- `test_catalog3_current_collection.py`,
  `test_current_collector_projection_followup.py` and
  `test_transport_independent_core.py`: real REST/GraphQL projections, no
  invented review update clock, omitted/null current fields and source attribution.
- `test_catalog3_document_identity.py`: natural document keys/exact UTF-8 including
  empty text, digest collisions and unresolved current selection.
- `test_catalog3_github_runtime.py`, `test_catalog3_review_coverage.py` and
  `test_catalog3_pr_scope_coverage.py`: partial GraphQL roots/children, exact
  head/base targets, restart and honest code/thread coverage.
- `test_catalog3_json_contracts.py`, `test_catalog3_exchange_integrity_audit.py`,
  `test_catalog3_selective_exchange.py` and Phase 1 exchange-retirement tests:
  opaque fields cannot become authored identity references or original carriers;
  complete proof requires exact dependencies, never only a subset of members.
- `test_catalog3_git_fact_contracts.py`, Git readers, CAS/maintenance and package
  tests: raw bytes/interpretation separation, exact formats/OIDs, physical
  corruption/quarantine and CAS-41.

After owner approval, missing tests must directly exercise typed field arrays and
event variants; malformed/unknown provider fields versus approved extension
capture; PR/comment body availability and exact patch bytes; actor login changes
without identity merging; Source-private/principal-scope contradictions; typed
donor repository references; duplicate/folded Git headers and decoder byte
offsets; and selective Exchange missing one field/member followed by late arrival.
These are contract/adversarial cases, not mechanical mirrors of a new schema.
