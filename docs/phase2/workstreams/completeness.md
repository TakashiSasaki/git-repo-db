# Phase 2 workstream B: collection evidence, Coverage and receiver verification

Status: **investigated current behavior; replacement designs Proposed / Pending Owner Decision**.
Baseline: fetched `main` `20e0f8d78b77c6c8d37826fd6d639819631e166b`, production Catalog3 schema 18,
complete DDL SHA-256 `16110944d4b6a0942657644fe80383394210af1218a3e7111e331a1651fa211e`.
No collection/publication/lifecycle/cache policy is accepted by this document.
The transport-independent ADR, Phase 1 retirement decision and current `AGENTS.md`
establish the boundary. Existing Coverage v2 is preserved verbatim.

## Eight concepts with different responsibilities

| Concept | Current live representation and admission | Meaning a replacement must preserve |
| --- | --- | --- |
| 1. Valid individual resource | `rest_item`, `current_parser`, typed facts/current resources, natural keys and ownership FKs | Valid member A does not prove that B was obtained, an endpoint ended, or a child was enumerated. Resource admission can survive a failed collection. |
| 2. Parsed/admitted fragment | Historical `fetch_occurrences` plus sealed `parsed_results`; current `current_collection_pages` in the resource-admission transaction | The interpreted portion was admitted with truthful parser/capture evidence. An accepted partial GraphQL root may contain valid resources and errors simultaneously. |
| 3. Known full membership of one fragment | Current receipt's typed `members` and immutable state digests; historical PR lists require comparing original arrays with complete observation objects | Successful individual parses do not prove no list members were skipped. Missing outputs must invalidate the relevant proof, without retracting independent valid facts. |
| 4. Explicit terminal boundary | `next_cursor`, `graphql_connection`'s `hasNextPage`/`endCursor`, `completion_markers` | Empty is established by an admitted empty terminal fragment; zero requests/zero members alone means unknown. Transport cursors are continuation inputs, not domain object identities. |
| 5. Required child completeness | Root thread observation `comments.nodes/pageInfo/observation_complete`, child `thread-comments` scope with exact root/thread parent | Root terminal does not imply terminal comments. Completion from another root, Source or thread cannot discharge a child obligation. |
| 6. Complete domain publication | Historical parsed-result input/output seals are independent of collection completion; PR code has explicit role/listing/target assessment | A page publication can be valid while the whole collection/code assessment remains partial. Publication atomicity and collection completeness must not share one lifecycle by assumption. |
| 7. Coverage Claim | Exactly `(coverage_claim_id, coverage_scope_id, coverage_state, observed_at_us, details_json)` | A scope/time/state assertion is distinct from its supporting completion identities. Current state considers every candidate at the maximum time; advisory proof/detail never breaks a tie. |
| 8. Receiver-verifiable completeness | `Graph.proof_requirements`, `aggregate_proof`, `code_proof`, exact dependency equality and blocked-claim state | An asserted complete state is portable only when the receiver can validate the full exact scoped proof. Presence of unrelated rows, envelope `requires`, or a member subset is insufficient. |

Code anchors:
[`CurrentCollectionProof`](../../../src/repo_catalog/adapters/sqlite/current_collections.py#L17),
[`current_collection`](../../../src/repo_catalog/adapters/github/collector.py#L97),
[`collection`](../../../src/repo_catalog/adapters/github/collector.py#L670),
[`graphql_connection`](../../../src/repo_catalog/adapters/github/collector.py#L1410),
[`proof_requirements`](../../../src/repo_catalog/adapters/sqlite/exchange.py#L1604).

## Current producer/store/consumer chains

### Flat REST pages and historical PR lists

`sync pr/all` and `jobs resume` reach `GitHubCollector.collection` through
`CollectionService._sync`. `ApiFacts.begin` freezes Source/repository/CR and
request scope; it reuses the same job collection or an explicitly reusable
completed listing. Each historical page writes decoded API CAS bytes and
`fetch_occurrences`; each resource normalizer produces owned immutable facts,
and `choose_page`/`publish` seal the result before the transaction commits.
The next URL and admission advance together. A committed terminal page interrupted
before `finish` is locally completed on resume without acquiring a new page.

`ApiFacts.finish` writes a complete marker with the exact **set of fetch UUIDs**,
plus root and child collection IDs where applicable. The marker timestamp uses
accepted fetch/page receipts, excluding newer rejected partial markers.
`collection_coverage` evaluates the collection at its actual observation
boundary. `freeze_complete_proof` binds a complete claim to exact marker UUIDs,
not whatever marker the receiving catalog happens to have later.

Historical PR-list proof remains original-dependent:
[`Graph.aggregate_proof`](../../../src/repo_catalog/adapters/sqlite/exchange.py#L1481)
loads every listed fetch's `stored_bytes.body`, decodes its array, and requires
exact equality with one `change_request_observations.payload` per provider item.
It then requires each listed CR to be included in the assessment's requested set
and checks required subordinate collection kinds. For `pr`, those include
timeline, commits/files and one complete code result per request; `pr-documents`
has its own established narrower kinds.

Simply deleting originals removes the current test for an omitted PR-list
member. Keeping only the CR IDs the normalizer happened to emit also loses that
responsibility: the emitter could have silently skipped B. A replacement needs
an explicit admitted fragment member contract and exact observation/output
membership. It must bind PR A to this list/scope/observation, not an unrelated
historical A from the same repository. Publication identity and lifecycle choices
block a production replacement; existing completeness validation can be hardened
independently.

Exact anchors:
[`ApiFacts.begin/page/finish`](../../../src/repo_catalog/adapters/github/persistence.py#L289),
[`freeze_complete_proof`](../../../src/repo_catalog/adapters/sqlite/coverage.py#L18),
[`summary_collection_ids`](../../../src/repo_catalog/adapters/github/collector.py#L313).

### Archive-independent current-resource receipts

`current_collection` admits mutable resources and one immutable page receipt in
the same transaction. Each member is an exact five-key typed object: Issue
members contain service/kind/provider ID/digest; review members contain CR/kind/
provider document ID/digest. Actual normalizer module/version are persisted.
The page key is `(fetch_collection_id, ordinal)`; positive decimal provider IDs,
canonical digest form, within-page duplicate identity, scoped binding/service/CR
ownership and post-seal insertion are guarded by generated SQL and Python.
Mutable current rows are not immutable parser outputs.

`CurrentCollectionProof.evidence` requires a nonempty exact `0..N` fragment
sequence, nonterminal intermediate receipts and a terminal final receipt.
`current_collection_completion_valid` independently checks the same boundary
and exact maximum receipt time for direct SQL. Thus an observed empty list is
one empty page and a terminal marker, while no page produces no complete proof.
[`current_collections.sql`](../../../src/repo_catalog/resources/current_collections.sql#L4)
and [`JSON generator`](../../../src/repo_catalog/adapters/sqlite/json_contracts.py#L1777)
are active production composition, not historical snapshots.

The receipt state digest intentionally does **not** reference a mutable current
body. `Graph.current_page_requirements` requires the independently usable member
identity, page receipts and relevant incremental baseline, not a current row
whose later contents hash to the old digest. This preserves historical receipt
meaning after A is edited. It also limits receiver validation: current code
validates digest syntax/identity/closure, not recomputation of every historical
member value from an immutable observation. The proposed immutable-member
prototype below tests stronger recomputation for the narrow historical design;
it must not be advertised as the existing current-state guarantee. New wire/trust
policy remains P2-Q10, and keeping an immutable full current-value snapshot would
be a new lifecycle choice, not an automatic extension of this pattern.

### Incremental scans and watermark inheritance

[`current_incremental_url`](../../../src/repo_catalog/adapters/github/collector.py#L49)
selects a proven completed baseline with the same repository, Source, principal,
permission set, endpoint/API/parser/preservation settings and actual current
normalizer attribution. It resumes the original job's bounded endpoint instead
of recomputing `since`; a later scan overlaps the original scan-start boundary
by five minutes. `Graph.current_baseline_requirements` walks exact baseline
completion UUIDs iteratively, checks fixed scope context/owner/module sets,
rejects cycles, and carries only the relevant baseline chain.

Historical incremental PR conversation comments separately persist a stable
scope, actual since-specific scope, original scan start and `safe_watermark_us`.
`incremental_scans` is inserted only after collection terminal success. Ordinary
Issue comments are independently refreshed for every stored accessible parent;
a parent's provider update clock does not order its comment edits. Completing
one child cannot advance another child's watermark. The inherited baseline
assertion is domain coverage evidence; request URL/cursor, retry state and credential
reference are operational inputs. Their durable lifetime and physical placement
remain owner choices, detailed in workstream C.

Anchors:
[`incremental_comments`](../../../src/repo_catalog/adapters/github/collector.py#L1149),
[`current_incremental_reviews`](../../../src/repo_catalog/adapters/github/collector.py#L1274),
[`current_baseline_requirements`](../../../src/repo_catalog/adapters/sqlite/exchange.py#L1206).

### Nested GraphQL roots, independent threads and current comments

The root transaction commits actual root bytes, immutable thread interpretations,
current review-comment values and their digest receipt, plus a pending
`{cursor, occurrence}` continuation. This is an accepted prefix, even if later
child acquisition fails. Resume reads the exact committed root and its original
clock, then resumes children before advancing the root cursor. A root containing
errors may admit valid resources but cannot complete. Its raw fetch may advertise
`next_cursor=NULL` while its current receipt deliberately retains a retry cursor.
These are acquisition occurrences versus interpreted completeness boundaries;
they cannot be validated with one blanket raw-cursor rule.

`review_thread_observations.payload` already strips most comment bodies, retaining
comment database IDs, initial pageInfo and `observation_complete`; thread domain
attributes remain provider-shaped. Child continuations use current receipts
without historical HTTP CAS. Child scopes name exact `parent_fetch_collection_id`
and thread natural identity. `thread_collection_ids` and `thread_observed_at_us`
include previous resumes' children rather than only the current process list.

Ordinary selected-thread queries evaluate the latest actually observed root or
that selected thread's children. Unrelated child failure can leave T1 complete
while T2 is partial. A new T1 root requiring children cannot borrow T1's old-root
terminal child. Error-only attempts without resource data do not create remote
evidence; a newer admitted incomplete root/child supersedes older complete proof,
and equal-time contradictory candidates cannot hide behind an older terminal.
Those semantics are exercised by the current review-coverage tests.

Exact anchors:
[`threads`](../../../src/repo_catalog/adapters/github/collector.py#L1472),
[`_thread`](../../../src/repo_catalog/adapters/github/collector.py#L1799),
[`_thread_children`](../../../src/repo_catalog/adapters/github/collector.py#L1897),
[`_thread_listing_complete/_thread_comment_boundary_complete`](../../../src/repo_catalog/application/pr_queries.py#L579),
[`thread_observed_at_us`](../../../src/repo_catalog/adapters/github/persistence.py#L562).

Removing root bytes currently loses child IDs/continuations and observed merge
targets. Keeping only completed child collections loses **which children were
required**. The minimum normalized replacement is exact root/member identity,
initial member evidence and terminal/nonterminal/unknown status, child obligations,
actual observation clocks and code-role evidence; an operational checkpoint may
separately own the transient provider cursor/query. P2-Q06 chooses its layout.

### Code lists and target completeness

`code_listings` fixes CR, kind, scope and head/base object format/OIDs. Its
`code_listing_progress` is operational/local completion state; received catalogs
instead use exact immutable terminal/listing proof. Commits/files are parsed
members with direct result and fetch provenance. Successful terminal API pages
remain insufficient at known provider truncation caps: 250 commits/3,000 changed
files, or fewer obtained records than a reported count, yield `API_CAP` partial.
Changed reported count changes the reuse scope even if head/base are unchanged.

Before and after PR evidence must show stable head/base for the same assessment.
Merge/test-merge and review-target roles must be explicitly known, including
observed null versus missing. Each nonnull required role must link to a published,
same-repository, verified exact Git OID/root with real required raw bytes.
`Graph.code_proof` requires exact role set, complete listings, owned inputs and
published acquisitions; removing result/fetch identities without normalized
replacement can silently turn an unobserved target into an empty target set.

Anchors:
[`listing cap enforcement`](../../../src/repo_catalog/adapters/github/collector.py#L780),
[`before/after and code assessment`](../../../src/repo_catalog/adapters/github/collector.py#L2510),
[`saved_thread_code_input`](../../../src/repo_catalog/adapters/github/collector.py#L1430),
[`Graph.code_proof`](../../../src/repo_catalog/adapters/sqlite/exchange.py#L1359),
[`code_complete_insert`](../../../src/repo_catalog/resources/catalog3.sql#L584).

### Source Inventory has a different owner and proof

Source Inventory uses Source-owned `source_input_observations`, inventory
interpretations and immutable publications, not repository `fetch_collections`.
It first verifies authenticated principal/declared owner scope, admits supported
organization identity or authenticated-user owner scope, then validates all
accepted repository members. Explicit included repositories define a narrower
scope. Terminal page traversal can still be partial when known public/private
counts do not match, privacy visibility is unknown, or full inventory scope
cannot be established. Discovery deduplicates provider IDs and binds explicit
service identity; names/URLs never merge repository or Source identities.

`inventory_observations.scope.response_evidence` retains input UUID/payload,
URLs, actual response times, ETag and next URL. If a later request fails, accepted
Source inputs are sealed into a partial inventory result. Current Source inventory
requires historical publication/selection; single-repository Exchange excludes
Source-wide inventory. Source inventory is **not** represented by a fabricated
repository Coverage v2 scope: owner/type/aggregate semantics belong to P2-Q03.
Current aggregate `inventory_observations.observed_at_us` is run start, while
inputs have response clocks; the replacement must distinguish scan start from
actual domain assessment boundary rather than silently copying one clock.

Anchors:
[`inventory_input/inventory`](../../../src/repo_catalog/adapters/github/collector.py#L470),
[`CollectionService._discover`](../../../src/repo_catalog/application/collection_service.py#L120),
[`_publish_inventory`](../../../src/repo_catalog/application/collection_service.py#L394),
[`inventory owner guards`](../../../src/repo_catalog/resources/identity_relations.sql#L86).

### Selective Exchange and late proof eligibility

Complete markers name exact fetch/current-page collection sets. Complete claims
name exact marker UUIDs, acquisition/result evidence and relevant domain scope.
`Graph.proof_requirements` checks owner/kind/source/root context, actual maximum
observation time and recursive proof closure. Current baseline inheritance is
iterative. `aggregate_proof` requires each PR and family; `code_proof` requires
exact targets. Export of one fetch cannot accidentally expand through a shared
repository/document identity into sibling acquisition history. A selected subset
can carry valid resource facts, but its broader complete claim is omitted unless
every exact dependency is present. Missing dependencies stage and can promote on
late arrival; conflict evidence blocks disputed completeness without deleting
independent facts or inventing sender/receiver order.

304 is a separate validation boundary with no new fetch/member observation. It
requires the exact previous PR observation/result/fetch/payload and compatible
scope. New transport-independent proof must distinguish revalidation from a new
observed member set. P2-Q07 decides cache ownership/reuse; B does not choose it.

## Schema 18 object classification and deletion dependencies

These classifications are conditional mappings, not a DROP list. All have live
consumers. Counts/DDL/FKs/generated contracts come from complete packaged schema
composition; field inventory and publication workstreams own their final names.

| Existing object / key | Producer and readers | Proposed responsibility / status | What simple deletion breaks; dependency order |
| --- | --- | --- | --- |
| `fetch_collections`; PK collection ID, composite owner/CR keys; repository, Source, scope, kind, observed time | `ApiFacts.begin`; restart, query, Exchange | **Replace / pending Q04–Q06** with scoped domain collection observation and separate operational run | Loses exact parent/scope/baseline identity. First establish typed scope and publication/collection linkage. |
| `fetch_occurrences`; portable UUID, local ID; payload FK, ordinal, request/cursor/times | `ApiFacts.page`; historical outputs, membership proof, resume, 304, code proof | **Remove after dependency migration** for API; retain acquisition distinction needed for Git separately | Breaks direct historical FKs, PR roster exactness, root restart, cache origin. Migrate domain membership, ownership, continuation and revalidation evidence together. |
| `collection_memberships`; PK collection + natural document key; ordinal; natural document FK | `ApiFacts.document`; scoped document/query/Exchange | **Replace / pending** typed observation memberships, possibly retain domain logical membership responsibility | Only historical document identity roster; neither full fragment roster nor terminal/nested proof. Replacement cannot use this limited roster as universal completeness. |
| `current_collection_pages`; PK collection/ordinal; members JSON, clock, continuation, module/version | Current REST and GraphQL comment admission; CurrentCollectionProof, readers, Exchange | **Retain pending Q05/Q06; established independent evidence** | Durable receipt digests/terminal evidence and incremental baselines would disappear. Removing the transport cursor alone requires independent restart ownership; do not discard members. |
| `completion_markers`; portable UUID/local key, collection/scope FKs, state/evidence/clock | `ApiFacts.finish/partial`; Coverage and all relevant query/Exchange paths | **Replace / pending** exact domain completion/revalidation assertion and reason-only partial evidence | Deletion falsely reverts to operational progress or old complete state. Migrate max-time partial candidates, exact marker linkage and receiver conflicts first. |
| `coverage_scopes`; repository/optional CR typed owner; unique repository-kind or CR-kind | `Store.coverage`; queries, CLI, Exchange | **Retain accepted contract** | Keep natural scope uniqueness, owner FKs and existing meaning. Source Inventory extension is a separate decision. |
| `coverage_claims`; exact five columns, unique scope/time/state | Atomic `admit_claim`; view/read/Exchange | **Retain accepted contract**; proof linkage may be typed external relation plus advisory identifiers | No sixth column or replacement total-order winner. Preserve all maximum-time candidates and blocked-proof conflicts. |
| `current_coverage` | Reads immutable maximal-time candidate set and receiver proof blocks | **Retain accepted derivation** | New partial/unknown/conflict must not fall back to older complete. Details/UUID/parser version are not tie-breakers. |
| `incremental_scans`, `resume_cursors`, `collection_progress`, `resume_scopes` | Acquisition/job plan/fence/restart and baseline/proof joins | **Retain only while Q05–Q07/checkpoint decision pending**; split domain baseline evidence from operational state | Loses frozen resume fence, safe watermark and exact parent association. Placement/lifetime policy is not chosen here. |
| `code_listings`, `code_listing_progress`, code observations/roles | GitHub code writer, Git importer, code/query/Exchange | **Retain domain targets; replace proof/result/operational attachments after Q04/Q08/Q09** | Listing completeness must remain tied to exact head/base/role evidence and Git bytes, not row counts alone. |
| Source input/inventory observations and repository inventory members | Discovery, current inventory views | **Replace after Q03/Q04/Q09**; retain actual inventory domain facts | Source owner cannot be replaced by a repository owner or erased; acquisition inputs cannot disappear before scope/count/member evidence migrates. |

Important indexes today: `fetch_occurrences_fk_1(fetch_collection_id)`,
`completion_markers_fk_0(fetch_collection_id)`, collection owner/scope/source
indexes, natural collection/member primary keys, `collection_memberships_document_fk`,
and the coverage unique `(scope,time,state)` index. Current page scans use the
leading collection PK. Membership/terminal/obligation replacements should provide
`(collection,fragment ordinal)`, `(collection,fragment,member ordinal)`, unique
typed member/observation keys, `(parent collection,parent member)` child access,
and receiver dependency-key indexes. A bounded proof can visit O(fragments +
members + required children + code roles), with O(log N) indexed lookup per
identity. Never discover closure by repeatedly scanning the whole repository or
rebuilding one identical aggregate proof once per member.

## P2-Q05 — What durable normalized collection evidence is required?

**Precise question:** For a terminal scope enumeration, should the domain retain
admitted fragment membership and terminal sequence, or retain a sealed exact
domain-member set/terminal assessment while fragment continuation is operational?

Accepted constraints: no mandatory originals; truthful ownership/module/version;
partial is not complete; exact scoped receiver proof; Coverage v2 unchanged;
missing/null/empty and ambiguous ordering remain distinct. No retention/GC policy
is inferred. Publication identity, field inventory and receiver trust stay pending.

| Alternative | Concrete normalized representation | Correctness, storage and runtime consequences |
| --- | --- | --- |
| A. Durable fragment receipts (**recommended**) | Integrated candidate `repository_collection_scopes/observations/fragments`, typed PR/document/thread member tables, `repository_collection_terminals/seals`, `collection_child_obligations`; analogous Source-owned tables and inventory members. Fragment carries collection/ordinal/actual clock/membership completeness/terminal/module/version. | Directly distinguishes empty/missing-terminal/gaps/incomplete fragment. Receiver checks exact normalized observation/membership closure. O(F+M) rows and verification; hashes must cover explicit modeled member semantics, never original-byte hashes. Cursors/URLs need not be core columns. Durable domain fragment identity must be explicit, not a renamed HTTP fetch. |
| B. Sealed domain set plus enumeration assessment | Exact typed collection members and one seal `(expected member count, normalized member digest, terminal assessment, actual observation boundary)`; fragment receipt/checkpoint is operational until completion | Fewer final domain objects and simpler scans. Receiver can check exact set/count/digest but cannot reconstruct fragment boundary integrity from the final set; whether a terminal assessment assertion alone is sufficient is P2-Q10. Restart still needs durable normalized accepted prefix and child obligations outside original bodies. No automatic deletion of committed evidence is authorized. |

Recommendation A exposes enough evidence to challenge skipped membership and
nested obligations using ordinary typed rows, supports scoped offline readers,
and follows the established independent receipt approach without forcing its
current JSON layout onto every domain. A completion record must seal exact
fragments/members/obligations; membership observations may refer to immutable
historical facts or defined current-resource receipts according to approved
lifecycles. It must not require full edit history for an accepted current family.

Example: L has `fragment 0 @100: [PR A] nonterminal`, `fragment 1 @175: [] terminal`.
A complete assessment at 175 has both fragments and A. Empty L instead has
`fragment 0 @100: [] terminal`. L with only first fragment is partial regardless
of whether A is independently valid. Missing fragment 1 cannot be hidden by
renaming fragment 2 to terminal or by a set digest containing A alone. If a
partial observation at 200 exists, the old/new terminal assessment at 175 does
not make current coverage complete; same-time 200 complete and partial conflict.

Exchange must carry the selected proof closure or omit broad completeness;
backup/restore includes domain evidence and required text/Git bytes, excluding
optional transport caches. Testing needs direct SQL/admission attacks, fragment
omission, late membership, reordered records and immutable observation integrity.
Dependencies: Q04 publication/identity, Q09 fields/lifecycles for member evidence,
Q06 nesting and Q10 portable proof validation. **Blocks** production removal of
historical collection originals; does not block independent baseline integrity
checks or executable proposals.

## P2-Q06 — How do nested roots define and discharge child obligations?

**Precise question:** Should each observed parent enumerate normalized typed child
obligations as independently addressable rows, or embed exact child seals in the
parent publication and retain separate continuation only while a child is pending?

Accepted constraints: partial roots may preserve valid resources; no missing
child can establish complete; thread identity/CR ownership remain typed; original
observation clocks survive resume; selected-thread completeness is independent
of unrelated child failures; errors/retries cannot manufacture a current winner.

| Alternative | Representation | Correctness, cost and restart implications |
| --- | --- | --- |
| A. Explicit child obligations (**recommended**) | Typed `(root observation, parent thread/member, child family)` obligation; initial embedded member receipt; explicit `known-terminal/needs-continuation/unknown` status; exact subsequent child fragments and completion identity | Parent membership names every required child, including empty terminal children. Indexed per-thread queries and bounded closure. O(parents+child fragments+members) rows; root commits normalized facts/obligations/operational cursor atomically. Resume can reconstruct targets after deleting optional archives. |
| B. Parent-embedded child seals | Each immutable normalized thread/parent observation contains a typed child receipt with initial members, terminal status and completed-child membership seal; pending continuation separately references exact parent | Fewer independent identities for fully embedded terminal children. Repeated parent observations copy child seal structure; completed child publication must remain bound to exact parent. Reader/exchange must compare structured member sets without treating an unmodeled GraphQL subtree as a domain blob. |

Recommendation A makes missing obligations, wrong-parent completion and
selective proof visible as relational integrity failures. Core initial membership
and known boundary are independent of transient `endCursor`. Retry cursor,
query, credential reference and fence may live in a separate durable operational
checkpoint; permanent checkpoint placement/lifetime is not chosen. Accepted
partial roots need a representation for valid resource observations **and** an
incomplete connection interpretation. A retry of the same provider cursor is not
automatically a duplicate domain observation or proof of a new total order.

Example: root R1 @100 lists threads T1/T2 and is terminal. T1 embeds zero comments
with an explicit terminal child. T2 embeds C1 plus `needs-continuation`; child C2
at 150 terminates. T1 can be queried complete at R1's actual boundary even before
C2 arrives. Whole R1 cannot complete before C2. Root R2 @200 lists T2 with missing
child boundary; R1's completed T2 child cannot discharge R2. If R2 has errors,
valid T2/C1 facts can be retained while R2 coverage remains partial. A stale child
retry @175 cannot erase R2 partial @200; equal-time terminal/partial candidates
remain conflict.

Exchange requires parent observation, initial receipt, all named obligations and
the exact completions for the requested scope. Partial selective exchange can
still admit T1 or C1 without asserting whole-R completeness. Backup must preserve
normalized committed prefixes and domain evidence; cache/continuation backup
depends on the separately chosen operational-store policy. Tests need empty
children, omission of one obligation, wrong thread/root/Source, accepted errors
and repeated cursors, close/reopen after prefix, stale retry, selective child proof
and O(N) closure. Dependencies: Q04/Q05 identity/evidence, Q09 target/field contract,
Q07/checkpoint physical placement and Q10 Exchange. **Blocks** normalized root
restart/whole-thread proof implementation; flat collection hardening is independent.

## Executable evidence and independent challenges

Run in this checkout with no live collection:

```sh
uv run --no-sync python docs/phase2/prototypes/completeness_probe.py --threads 10000 --output artifacts/completeness-results.json
uv run --no-sync ruff check docs/phase2/prototypes/completeness_probe.py
uv run --no-sync pytest -q tests/integration/test_catalog3_coverage.py tests/integration/test_catalog3_current_collection.py tests/integration/test_catalog3_review_coverage.py tests/integration/test_catalog3_selective_exchange.py tests/integration/test_catalog3_remaining_adversarial.py tests/integration/test_phase1_retirement.py
```

The [disposable DDL](../prototypes/completeness.sql) and
[probe](../prototypes/completeness_probe.py) use fresh synthetic SQLite only.
[Executed result](../prototypes/completeness-results.json) records production
fingerprint, actual Python/SQLite and per-scenario output. A missing/null probe
varies only status on the same observation/resource identity; the prefix-restart
probe closes and reopens an actual disposable SQLite file. Digest corruption,
missing terminal, ordinal gap, early terminal, missing nested child, member subset,
late exact arrival, Source absence and repository mismatch are independently
challenged. Accepted Coverage max-time/contradiction/stale-terminal outcomes are
tested using the production domain resolver.

Limitations are explicit: this narrow proposal fixture uses a single synthetic
member family union in place of the integrated design's typed membership tables.
It does not enforce every domain-family compatibility/natural thread-parent
constraint, portable UUID representation, production immutability/publication
seals, provider authenticity, wire policies or cache lifetime. It is designed to
disprove some incorrect proposals, not certify the whole target schema. Those
properties require the integrated prototype and future vertical tests.

At 10,000 child collections, it visits 10,001 collections and verifies exact
closure with 60,005 SQL statements; member enumeration uses the leading collection
PK and does not scan the repository. SQLite size was 1,569 pages × 4,096 bytes
before later minor fixture adjustments. Timing is a single-process
characterization while other agents may be active, **not a clean comparative
benchmark**. The checked-in receipt is the actual run and is authoritative for
its concrete timings/size.

Baseline focused verification passed **294 cases in 128.72 seconds** on the
unmodified baseline application tree. The first command had a nonexistent test
filename and exited 4 without executing tests; the corrected command above
passed. This is focused behavioral evidence, not full production acceptance of
a redesign. Ruff passed for the probe; fresh FK/integrity checks pass within it.

Independent review found two misleading probe claims before submission: identity
differences could explain an old missing/null digest test, and the old restart
test had not reopened a database. Both were corrected; the narrow fixture's
family/parent-binding limitations are recorded above.

## Already-determined hardening and remaining tests

The baseline probe demonstrates an objective current historical-proof gap:
`Graph.proof_requirements` accepts exact manifest plus `terminal:true` even when
the only flat historical page has ordinal 2, or ordinal 0 retains a continuation.
FK checks pass. CurrentCollectionProof rejects the corresponding cases.
Requiring exact page sequence/true terminal for the **existing flat contract**
does not choose P2-Q05. An independently reviewed correction is tracked as a
separate implementation commit; nested GraphQL current receipts must govern
error/retry boundaries, and 304 with zero new fetches must stay valid. Historical
raw occurrences are not universally normalized fragments.

Existing meaningful cases are in:

| Suite | Retained contract |
| --- | --- |
| `test_catalog3_coverage.py` | Full same-time truth table, newer unknown/conflict, int64 extremes, atomic duplicate/stale admission and rollback |
| `test_catalog3_current_collection.py` / `test_transport_independent_core.py` | No mandatory archives/profiles, incomplete pagination, current receipt/module evidence, restart and changed-normalizer full rescan |
| `test_catalog3_review_coverage.py` | Partial/error roots and children, original root reuse, newer observed gap, selected-thread independence, no old-root child borrowing |
| `test_catalog3_rest_boundaries.py` / `test_phase1_retirement.py` | Accepted prefix/rejected response clocks, safe cursors, body-free rejection, detail validation and original-time 304 semantics |
| `test_catalog3_selective_exchange.py` | Fetch subset lacks broad completion, exact manifests, 304 origin, reordered/repeated records, conflicts and bounded selective closure |
| `test_catalog3_remaining_adversarial.py` | Manifest subset, unrelated proof, incomplete code listing, Source owner attacks, newer/tied partial collection without fallback |

Future normalized subsystem tests must additionally cover: source-wide empty
inventory versus unverified scope; family-specific complete roster membership;
omitted obligation versus terminal empty child; before/after PR head/base race;
inconsistent normalized member digest on receive/promote; partial graph errors
with repeated cursor interpreted without originals; exact late closure without
receiver-local checks; conflict candidate sets without comparable provider
clocks; query completeness independent of result pagination; and proof operation
counts for large nested trees/selective units. These are required responsibilities,
not authority to implement an unapproved production model.

## Dependency order for a coherent implementation stride

1. Accept Q04 domain publication/identity with Q01–Q03/Q08 lifecycle boundaries
   and Q09 retained field semantics; preserve existing Coverage contract.
2. Accept Q05 fragment/set evidence and Q06 child obligations, then Q10 exact
   portable proof validation. Decide Q07/checkpoint placement for durable restart.
3. Implement one integrated vertical collection/publication unit: typed scopes,
   normalized writers, immutable members/terminal/partial evidence, query
   predicates, nested/code target checks, bounded Exchange closure and maintenance
   dependencies. No dual schema or compatibility layer is needed.
4. Once all consumers migrate, remove API-only fetch/input/original attachments
   and parser-profile eligibility paths coherently. Content/quarantine deletion,
   GC and durations remain separately deferred; no DROP list is authorized here.

Publication/field normalization and operational acquisition/cache work can be
developed in parallel after their contracts are accepted. The collection/Exchange
proof definitions must be shared before either implementation is declared complete.
