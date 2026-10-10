# Phase 2 Workstream C: acquisition, restart and conditional reuse

**Status:** investigated implementation at main
`20e0f8d78b77c6c8d37826fd6d639819631e166b`, Catalog3 schema 18.
Recommendations below are **Proposed / Pending Owner Decision**. No permanent
cache, checkpoint, publication or resource-history policy is chosen here.
The transport-independent core ADR (TP-01 through TP-08) and Phase 1 R1–R7
retirement remain accepted. The line anchors describe this exact baseline.

## 1. The acquisition/restart state is not one object

| Concept | Schema 18 producer and store | Actual reader or gate | Retained responsibility; deletion consequence |
| --- | --- | --- | --- |
| Frozen job request | `CollectionService.sync` at [`collection_service.py:410`](../../../src/repo_catalog/application/collection_service.py#L410), `discover:80`; `jobs.request` | `CollectionService.resume:508`, `_sync:520`, `_discover:119`; `job_plans.activate:98` | Stable Source registration set, repository targets, endpoint URL and nonsecret acquisition settings. Deleting it makes restart silently use different owner/scope/configuration. It is an operational plan, not provider evidence. |
| Attempt fence | `JobService.create/resume/update`, [`job_service.py:13`](../../../src/repo_catalog/application/job_service.py#L13); `jobs.current_attempt`, `job_attempts` | `ApiFacts.fence`, [`persistence.py:224`](../../../src/repo_catalog/adapters/github/persistence.py#L224), Git importer publication fence | Only the current running attempt may publish. Attempt number cannot rank observations. Removing it admits obsolete foreground work after resume/cancellation. |
| Exact acquisition scope | `ApiFacts.scope:240`; `resume_scopes` | `ApiFacts.begin:289`, incremental lookup, code-listing reuse, `completed_pr:2046`, Exchange ownership/proof | Captures repository/binding/Source, principal, API version, endpoint, request context, parser and preservation configuration, permissions and provider counts/OIDs where applicable. Some values belong to durable domain capture evidence; query text/page sizes/cursors belong to operations. Keeping the existing opaque row forever is not the accepted target. |
| Collection instance | `ApiFacts.begin:289`; `fetch_collections` | Page writers, completeness/coverage, child linking and Exchange | Identifies a particular bounded enumeration and owner. A scope can have multiple acquisitions. It currently also carries job-independent local start time. Its permanent identity is Q04/Q05. |
| Mutable continuation | `ApiFacts.page:358`; `collection_progress.cursor`; root pending JSON | Historical REST reads last accepted `fetch_occurrences.next_cursor`; current REST/GraphQL children read last `current_collection_pages.next_cursor`; GraphQL root reads pending `{cursor, occurrence}` | Retry location and current attempt status. It must not be confused with terminal proof or a domain observation. Its durable lifetime and placement are Q12. |
| Accepted historical page | `ApiFacts.page:358`; `fetch_occurrences`, `payloads(decoded_api)`, `stored_bytes`, result inputs | PR/title/body/comment/event/listing publication, saved thread-root restart, 304 and Exchange proof | One accepted input may contain many domain objects. The original is still required by the implemented publication/proof boundary. Simple deletion makes the result/FK/proof graph invalid. Normalized admission and membership must replace its separate roles. |
| Accepted current page | `current_collection:104`, `_thread_documents:1850`, `_thread_children:1893`; `current_collection_pages` and current resources | `CurrentCollectionProof`, resumed current enumeration, Exchange, coverage | An immutable receipt records member natural keys, state digests, parser module/version, observation time and next/terminal boundary without original bytes. Current values can change after the receipt. It is an established pattern, not a decision to copy the same JSON format to every family. |
| Unsuccessful observed boundary | `partial_rest_collection:816`, `threads:1733`, `_thread_children:2023`; reason-only partial completion marker | `ApiFacts.observed_at_us/thread_observed_at_us`, coverage and summary | A known observed incomplete resource/collection must retain its actual time even when its malformed body is discarded. It grants no membership, terminal proof or fabricated original. Error-only responses with no domain resource are operational failure. The current REST path has a demonstrated gap (§8). |
| Domain target evidence | `saved_thread_code_input:1430`, PR detail fields, current review targets | PR code construction and `completed_pr`; raw root reread | Distinguishes omitted merge/test-merge from explicit null and verified OID. Necessary domain evidence must outlive a job; opaque root JSON is an implementation dependency to replace. |
| Successful watermark | `incremental_comments:1155`, `current_incremental_reviews:1272`; `incremental_scans`, or verified current terminal marker | Next job's `since` query | A completed bounded scan permits an overlapping update scan from its original start. An interrupted scan or resume time cannot advance it. It is a reusable scan optimization whose lost state must cause extra acquisition, never invented complete coverage. |
| Conditional validator/cache | `detail:1020`; `validators` points to retained `decoded_api` payload | Detail HTTP 304 handling | Currently binds ETag to exact saved representation under resume scope. Validator is excluded from Exchange; bytes/304 proof remain domain dependencies. Q07 must replace this without assuming an ETag alone proves a normalized row's origin. |

`resume_cursors` appears in production DDL, FK/index/JSON guards and Exchange's
excluded-table set. There is **no current Python application writer or query
reader** of its rows. The live cursor paths above use `collection_progress` and
accepted page receipts. This is evidence for further exact schema audit, not an
unconditional permission to drop a table or its generated SQL.

## 2. Transactions, committed prefixes and failures

[`Store.transaction:171`](../../../src/repo_catalog/adapters/sqlite/store.py#L171)
uses `BEGIN IMMEDIATE` (ordinary `BEGIN` for read snapshots), commits on success,
and rolls back for any `BaseException`. Publication revision increments occur
inside the owning transaction. `CollectionService.sync/resume` holds
`locks/writer.lock` throughout execution; HTTP requests happen outside page
transactions, so an in-flight response cannot partially commit domain output.

### REST historical and current pages

Historical `collection:670` begins/reuses an exact scope/collection and code
listing, then acquires one page outside a transaction. Within the next
transaction it fences, stores the accepted original, creates the page's result,
normalizes every member, publishes the sealed result/selections, updates cursor
and listing page count, and commits. A failed member rolls back the **entire
page**, including raw bytes and any earlier members in that page. Earlier
successfully committed pages survive. A known rejected response has only its
live retry URL and a reason/time partial boundary, through
`partial_rest_collection:816`; API-original rejection staging stays retired.

On restart, a historical page's stored `next_cursor` selects the next URL; the
last accepted terminal page with NULL cursor causes **local finish without a
new GET**. `collection_progress.cursor` may record a rejected retry URL, but the
reader deliberately derives continuation from the last accepted page. A
terminal page committed before `finish` is not an incomplete remote collection;
a cancellation between those commits adds no coverage claim or remote clock.
A subsequent local finish uses the original accepted receipt time. The existing
`test_terminal_page_resume_has_one_original_coverage_observation` proves this.

Current `current_collection:104` follows the same page transaction structure,
but admits current candidates and an immutable member receipt without adding
`fetch_occurrences`, `payloads` or `stored_bytes`. The pre-request
`Store.revision()` and `candidate_context` fence receiver-local checks. Its
restart ordinal and URL derive from the last accepted normalized receipt.
`current_members_unresolved:230` checks members from **all** receipts, including
a previous attempt, before completing. A terminal prefix containing a staged or
unordered member cannot become complete merely by skipping HTTP on resume.
See `test_unresolved_terminal_receipt_does_not_become_complete_on_resume`.

Code listings additionally retain the exact head/base context and reported
count. `collection:690` puts `reported_count` into the scope, so a changed count
invalidates reuse even if head/base are unchanged. `API_CAP` guards commit lists
at 250 and file lists at 3,000, and treats a collected count below the provider
reported count as incomplete. Page termination alone does not establish code
listing completeness. A failed listing retains its identity/accepted prefix;
completed matching listings may be reused across jobs.

### Nested GraphQL roots and children

`threads:1477` reads a fixed root query from `resources/pr_threads.graphql`.
A successful root transaction commits together:

1. The accepted root original and its actual response time.
2. Every embedded current review comment and immutable member receipt.
3. Thread natural identities and historical thread observations.
4. A pending root checkpoint `{cursor: previous_root_cursor, occurrence: local_fetch_id}`.
5. Historical result publication/selection and catalog revision.

It commits **before** requesting additional child comments. Root cursor advances
only after all required children of that root have completed. If the process
stops before a child request, `threads:1540` rereads the saved root through
`fetch_occurrences -> payloads -> stored_bytes`, recovering its original child
cursors and observation clock; it does not create a new root response or clock.
The new characterization probe (§8) proves one root POST before interruption,
one child POST after restart, 100 original root comments at time 100, one child
comment at time 300, and thread completion at 300. A root-shaped JSON blob must
be replaced by normalized child obligations and target evidence before deleting
this dependency.

`_thread_children:1893` already has no retained child-response body. Each child
page transaction admits current comments, records member digests/time and retry
or terminal cursor, and publishes. Parent/root identity, thread natural key,
query and `parent_fetch_collection_id` separate child scopes. A resume uses the
last child receipt. Completing a child does not independently prove the root
has enumerated all threads.

`graphql_connection:1413` requires an actual `nodes` array of objects, a boolean
`hasNextPage`, and a nonempty string `endCursor` when another page is required.
An empty array with `hasNextPage=false` is an explicit empty terminal collection.
Missing pageInfo or a truthy nonboolean value is not terminal proof.

`graphql_errors:1381` treats `RATE_LIMITED` as retry/backoff before ordinary data
processing. Error-only/null resource envelopes become operational
`GRAPHQL_PARTIAL`; no domain resource or original is retained. A well-formed
root containing data **and errors** is admitted as partial domain evidence:
thread observation says incomplete, current member receipt retains a nonterminal
retry marker, and root continuation does not advance. It keeps the original
accepted root under today's historical result/restart contract. The root cursor
is retried live after `GRAPHQL_PARTIAL`; no API reparse capability is introduced.
A partial child page can likewise admit valid current comments and a retry
receipt but cannot complete the child. Malformed identified child resources at a
newer time retain a reason/time partial boundary without original bytes.

If malformed embedded child connection data requires a fresh root,
`refresh_root` drops the saved local occurrence from the checkpoint and retries
the original root cursor. It never labels the old root with a later clock.
`thread_collection_ids:354` and `thread_observed_at_us:562` include exact children
from earlier resumed attempts, and exclude another root's children. Required
nested completion needs **normalized root-owned obligations** (Q06); a flat
terminal page-count check alone is insufficient.

### Source inventory

Inventory has a different restart structure. `inventory:502` retains each
accepted, validated identity/list page as `source_input_observations`, separately
committed before a later page fails. `_discover:119` publishes a Source-owned
partial inventory result if accepted prefix input exists. On resume it reuses
the frozen Source plan but **enumerates anew**; it has no `fetch_collections` or
persisted page-cursor resume path. Retained prefix originals are publication
inputs, not a restart optimization.

Inventory list members are validated before accepting their input: valid
nonempty login, allowed authenticated User/Organization scope, provider ID,
owner/repository name and effective nonempty clone URL. Known public/private
counts and per-member `private` booleans determine uncertainty. Merely reaching
a terminal list can leave `INVENTORY_SCOPE_UNVERIFIED` or
`INVENTORY_COUNT_MISMATCH`. Selected repository discovery has separate explicit
scope. A request with no accepted input becomes only a job outcome.

`_discover:166` labels inventory/name observations with pre-request run-start
`now_us()`, whereas `source_input_observations` use actual response clocks. The
proposal must separately model `scan_started_at_us` and the aggregate
observation/publication boundary. Choosing the aggregate boundary/interval is
part of Q03; this report does not silently recast the existing timestamp as a
remote response time.

## 3. Code-target evidence and races

[`saved_thread_code_input:1430`](../../../src/repo_catalog/adapters/github/collector.py#L1430)
reads the latest accepted root for observed merge/test-merge roles even when
thread collection failed. For each role:

- Missing property: unobserved; the target set is incomplete.
- Explicit null: observed absence of that role.
- Valid SHA-1/SHA-256 OID: observed required Git target.
- Wrong type/invalid OID: no valid target; incomplete.
- Any root errors: available role values remain evidence, but the complete target
  inventory cannot be asserted.

A quarantined/unreadable root returns unavailable target evidence, not an empty
complete set. A completed `threads` call separately rereads the latest root to
return merge roles. Replace both reads with typed role/value/presence evidence
under the exact PR observation/collection, truthful parser module/version and
actual response time. Do not allow "no HTTP request on this retry" to revoke a
prior saved role, or infer null from omission.

`sync:2450` acquires commit/file lists under the pre-listing detail's head/base,
then `code_check:2952` unconditionally requests detail again. A changed head/base
marks `PR_CODE_RACE` and keeps code partial. A matching after-check supplies the
new PR observation anchor. Expected roles include head, base, observed merge,
test-merge and every current review-target OID. Published Git acquisitions can
be reused only with matching repository, object format, exact OID and role,
verified commit content and a published preservation obligation. A failed
refresh cannot erase an already preserved matching role.

A code publication currently combines all relevant accepted API inputs, reused
listing inputs, the exact PR origin input and Git acquisition inputs into one
`parsed_result` (`sync:2717`). Its details carry stable head/base,
`code_inputs_complete`, expected/missing roles and provider limits. Complete
requires stable before/after context, full observed target inventory, complete
listings and all target acquisitions. `completed_pr:2046` uses eligibility, exact
job/Source/principal/API/parser/preservation/permissions scope and complete child
kinds, then checks every expected role link. Simply dropping that fetch scope
join permits an unrelated/incomplete job to skip unfinished work.

The normalized proposal needs typed code assessment inputs referring to domain
PR observation, listing set, target requirement and verified Git acquisition.
Selection of historical PR/Git states remains Q01/Q08; parser version, attempt
and receipt order may not decide a domain winner.

## 4. Jobs, cancellation, restart and watermarks

`job_plans.freeze_source:14` saves Source registrations and credential
**references**, never credential values. `freeze_config:90` freezes collection
and preservation settings. `activate:98` restores these but does not replace
receiver-local DB/cache policy. `check_registration:108` rejects deleted/rebound
Source registrations and resolves current credential availability. A frozen
endpoint URL is checked again before sync. Adding a Source or changing settings
after job creation cannot silently retarget the job.

`JobService.resume:27` refuses complete/cancelled/legacy jobs, enforces
`not_before_us`, interrupts a prior running attempt, increments the attempt and
drops old cache leases/space reservations in one transaction. `_sync:526` pins
`expected_attempt`; every API page/publication fence checks it against the
current running attempt. `JobService.cancel:83` requires SIGINT for a foreground
running job; queued/waiting/failed/interrupted jobs can be cancelled. Domain
observation clocks never derive from resume or cancellation time.

`_sync` marks acquisition failures waiting, Source unavailability skipped, and
cancellation interrupted. Database/I/O failures mark failed if a metadata update
is still possible; a full database can leave the durable job ID with an old
running state so a later resume must fence and recover it. Valid earlier page
transactions remain. Recorder callback/warning failures are nonfatal to domain
acquisition and only the latest 100 sanitized diagnostics are retained;
transport, parser, catalog and cancellation failures keep their own semantics.

Historical PR conversation incremental comments have a stable scope distinct
from their `since` URL. Only terminal successful enumeration inserts an
`incremental_scans` row with `safe_watermark_us = original scan start`, and the
next query overlaps by 300,000,000 microseconds. A resume keeps its original URL
and original scan start. Current review incremental scans similarly wait for
terminal proof before recording a watermark. Current Issue/comments derive the
next overlapping `since` boundary from a verified complete current marker and
its collection start; they validate parser module/version and permission scope.
Neither a more recent failed child scan nor completing a different parent
advances that child's watermark.

Losing operational watermark/checkpoint state can safely cause a full/repeated
scan. It cannot authorize a new coverage claim or choose a current value.
Whether a restart guarantees no redundant requests, rather than safe repeated
admission, is a new policy choice (Q12), not an accepted requirement to keep API
originals.

## 5. HTTP 304: actual safety checks and three feasible replacements

Baseline [`detail:1020`](../../../src/repo_catalog/adapters/github/collector.py#L1020)
loads the exact scope's validator and sends its ETag. On 304 it requires
nonquarantined saved bytes and JSON equality with the **currently selected PR
observation**. Cached A may not be attached to newer selected B. Mismatch/missing
content causes an unconditional GET; another 304 fails `API_SCHEMA`. A matching
304 creates no PR/document/page occurrence. Instead it creates a completion
marker at actual validation time, anchored to the original PR observation,
result/fetch and payload; validator `validated_at_us` advances. The original
observation clock remains unchanged. Operational validators are not exchanged,
but this historical completion closure presently carries originals.

| Alternative (all Proposed / Pending Q07) | Correctness and required evidence | Performance/restart/failure implications | Exchange/Coverage/backup implications |
| --- | --- | --- | --- |
| **A. Disable conditional detail reuse; GET actual content. Recommended for first transport-independent implementation.** | Never send If-None-Match. Project/admit every actual response as a new observation under existing clock/conflict rules. An unexpected 304 cannot establish observed values and must refetch/fail. No saved HTTP cache is required. | One response body per requested detail. More bandwidth/provider quota than successful 304; simple restart after loss of operations. Complete same-job domain proof can still skip already completed work. Preserve before/after head checks. | Exchange needs ordinary normalized observations/proofs only. New observation time belongs to the actual response. Core backup excludes disposable optional transport logs. Choosing A is not authorization to delete domain content/history. |
| **B. Separate disposable operational cache. Feasible performance extension.** | Cache owns validator and representation **together**, keyed by service/binding/Source/principal/permissions/API projection/query scope. Never keep a usable ETag detached from its corresponding accepted normalized anchor and representation. Cache response is admitted only by an authoritative live 304 with exact scope and domain revision/content comparison; otherwise actual GET. | Successful 304 avoids body transfer. Cache loss/expiry/corruption produces a cache miss and actual GET, never a failed core query/backup. External cache/domain commits cannot be one SQLite transaction: use publish-before-cache or a reconciliation protocol; a cache entry may refer to a committed domain observation, never the reverse. No core FK to cache. | Durable revalidation, if the owner wants it as domain evidence, references the original normalized observation and scope/time, not cache bytes/ETag. It cannot be trusted as a receiver-local check or invented new value observation. Core Exchange and backup do not carry the operational cache. |
| **C. Conditional revalidation of complete normalized endpoint evidence. Feasible only with explicit retained-field/presence and revalidation contract.** | Bind ETag in disposable operations to an immutable normalized endpoint projection with a presence mask, all retained fields/relationships/body identities and exact owner/scope. A mutable merged current row is insufficient: it may combine omitted inherited fields from different clocks. Check projection contract/parser producer and undisputed anchor before treating 304 as validation of those facts. Changed current state or incomplete projection forces actual GET. | Avoids retaining/caching original API body. Smaller cache, potentially cheaper restart when normalized anchor remains. Changing the retained-field contract or projection cannot extract omitted old fields; unconditional fetch is required. Recovery reconciles cache anchor with committed core identity. | Define what a portable domain revalidation asserts, if anything, and how receiver verifies the anchor/scope. It must not require original hash registration, replay, or sender check fabrication. Q09/Q10 needed before portable normalized revalidation. |

Example distinguishing A/B/C: PR observation O1 at 100 says head H1, body exact
text T1. Cache E1 was obtained for O1. A later unconditional code check produces
O2 at 200 with head H2. Server returns 304 for E1 at 300. B/C must reject the
cache-to-current association and perform an actual GET; they may not label O2
as H1, or attach H1's Git closure to H2. A requests actual content initially.
If O1's normalized body contains only known fields and a new projection version
requires a previously absent field, C cannot satisfy it from E1; neither parser
version nor a 304 supplies missing content. If the cache file disappears after
O1 commits, all three can still query/exchange/backup O1; B/C incur a GET.

A successful 304 proves the selected HTTP representation has not changed under
a particular conditional request. It does not independently prove unknown child
collections complete, choose an incomparable winner, or establish what data a
receiver had checked. No implementation of B/C is authorized by this proposal.

## 6. Minimum normalized restart design and checkpoint alternatives

The following are **semantic requirements already authorized**, with physical
objects **Proposed / Pending Q04/Q05/Q06/Q09/Q12**:

| Domain evidence required after an accepted prefix | Possible typed representation; not production DDL | Operational-only material |
| --- | --- | --- |
| Exact provider owner/capture and actual response observation | Repository/binding/Source FK plus captured endpoint scope; per-field or observation module/version and clock | Credential reference resolution, job/attempt and fetch retry count |
| Root's complete set of admitted thread identities in each fragment | Root-owned fragment/member relation using thread `(change_request_id, provider_resource_id)` | Static GraphQL query text/hash, page size and root end cursor |
| Required child enumeration and initial embedded members | Root-owned child obligation with thread key, initial fragment membership, observed terminal/nonterminal state and time | Child provider cursor and retry location |
| Child accepted prefix and explicit terminal boundary | Immutable scoped fragments/member digest/terminal evidence; membership does not point to mutable current row | Next-request URI/token |
| Merge/test-merge presence, known null or OID | Typed target observation: role + presence state + object format/OID when known + exact PR/root owner and time | JSON envelope, GraphQL errors text, response ETag |
| Before/after PR context and code targets | Typed stable-context check and code requirements tied to exact domain observations/listings/verified Git acquisitions | The HTTP method/status/envelope that acquired them |
| Newer identified incomplete boundary | Reason-limited partial assessment at actual observed time; no admitted members/terminal assertion | Retry deadline, transport/server/network error without resource |

**P2-Q12 — Which restart guarantee and physical placement should the first
replacement provide?**

- Accepted constraints: committed facts/proofs survive process failure; missing
  optional HTTP recordings never affect them; stale attempts cannot publish;
  restart cannot manufacture observation clocks or completeness. No checkpoint
  retention/GC period is authorized.
- Alternative 1 (**recommended**): keep a small operational checkpoint section
  in the same SQLite file initially, excluded from portable Exchange. Commit
  cursor acknowledgement atomically with admitted normalized fragment/proof.
  Core domain validity must not FK to it; losing/deleting it triggers proof-based
  reconciliation or safe restart/full acquisition. This minimizes crash states
  and lets database backup include optional local progress without requiring it
  for restored domain correctness. Lifetime/cleanup remains undecided.
- Alternative 2: separate operations database/journal. Domain proof commits
  first; operations acknowledgement references committed domain IDs. Restart
  checks current core proof rather than trusting an ahead checkpoint. If core
  commit succeeds and journal fails, repeat a request/admission or derive the
  next boundary; if journal is ahead of core, ignore/rewind it. Extra I/O and
  cross-store reconciliation are necessary. Back up operations optionally.
- Alternative 3: no durable provider cursors; restart by new bounded scan and
  idempotent natural-key admission. Lowest durable transport state, most repeated
  requests and longest restart on large nested trees. A new response is a new
  observation; it cannot be silently appended to an older publication as if an
  atomic provider snapshot. Domain-publication/coverage rules must describe
  separate assessments or truthful multi-fragment intervals.
- Concrete crash difference: root fragment F1/member set commits at 100, before
  child cursor C1 acknowledgement. Alternative 1 preserves F1+C1 together;
  Alternative 2 must reconcile missing C1 against F1; Alternative 3 rerequests
  the root and cannot relabel the later response at 100. In each case F1 remains
  legitimate historical evidence if its lifecycle retains it, never complete
  merely because a retry had no saved token.
- Dependencies/impact: Q04 batch identity and Q06 child obligations precede exact
  checkpoint references. A/B placement is independent of Q07 cache choice.
  Selected contract needs crash-before/after-commit, stale-attempt, lost-journal,
  restored-core-only and fixed-original-watermark tests. No new wire trust policy
  or cleanup duration follows from this choice.

## 7. Large implementation boundary and unresolved decisions

The shortest coherent acquisition stride after owner decisions is:

1. Q01/Q03/Q04 define retained historical resources, Source/repository publication
   owner and atomic identity; Q09 freezes actual field/presence/target contracts.
2. Q05/Q06 define normalized flat membership/terminal and exact nested obligations.
3. Q07 selects unconditional acquisition or a separately owned cache; Q12 selects
   checkpoint semantics/placement. No cache is needed to unblock option A.
4. Implement writers, receipts, root/target restart and readers against those
   domain facts in one vertical change; retire historical API `page/source_input`
   storage dependencies and raw-root readers only after new equivalents exist.
5. Q08 replaces historical Git/PR selection independently of parser DAG authority;
   Q10 Exchange uses normalized closure and receiver completeness predicates.
   Exchange/maintenance cannot claim final original independence before this step.

Safe work before those choices includes machine-checkable inventories, the
characterization probes, and repair of the demonstrated current-resource
rejection clock gap. It does not authorize a new publication subsystem, global
field dropping, original garbage collection or permanent cache policy.

## 8. Executable evidence and independent findings

New disposable characterization:

```sh
uv sync --locked --group dev
uv run --no-sync python -m pytest docs/phase2/prototypes/test_acquisition_characterization.py -q
```

On the baseline source tree with the proposal-only probe added: **6 passed in
3.39s**, Python 3.12.14. The existing restart/cache/watermark/retirement selection additionally passed
**18 cases, 111 deselected in 24.32s**, without bootstrap on the same source
tree; the selection and JUnit receipt were recorded locally. These tests use
independent Git-plumbing/local HTTP
fixtures, an offline network guard, fresh temporary catalogs and actual SQLite
writers/readers. The probes prove current normalized prefix restart, saved root
reread/original clock preservation, 304 stale-head fallback, and a matching 304
that changes no PR/fetch observation. No authenticated provider or retained
catalog was used. This is scoped characterization, **not full runtime
acceptance** and not evidence that the proposed architecture is implemented.
The first invocation via the `pytest` executable failed collection because the
checkout's `tests` package was absent from that entry point's path; using
`python -m pytest` resolves it. No probe ran in that failed invocation.

**Objective current REST clock gap, reproduced:** a current review collection
commits an empty nonterminal page at 150, then receives review ID 2 with malformed
body at 200. Its whole second page correctly rolls back without storing bytes,
but `current_collection:224` calls `ApiFacts.partial` with no observation clock.
The catalog retains only `partial@150`. A terminal retry at 175 then reports
`complete@175`; an equal retry at 200 reports complete rather than contradictory
maximum-time candidates. The known newer incomplete boundary at 200 was lost.
The three parameterized characterization cases expose the current outputs; they
are deliberately labeled as a gap, not a recommended behavioral contract.
A separate authorized correctness change should retain only known identified
resource/collection rejection clocks, leave raw/error-only/nonresource responses
without fabricated domain observations, include truthful partial boundaries in
Issue summary clocks, and keep terminal-marker time tied to actual accepted
receipts. It must add proper regression expectations before final acceptance.

Existing behavioral contracts to retain, with source anchors:

- [`test_catalog3_github_runtime.py:353`](../../../tests/integration/test_catalog3_github_runtime.py#L353): terminal commit/local finish and transport-only failure preserving coverage.
- `:860`, `:980`: prefix/listing reuse after another newer job and successful child watermark boundaries.
- `:1043`, `:1181`, `:1333`, `:1595`: nested pages, root-scoped earlier children, malformed cursors and connection shapes.
- `:1085`, `:640`, `:734`, `:801`: 304 stale-head association, before/after code checks, partial observed merge targets and interrupted changed heads.
- [`test_phase1_retirement.py:524`](../../../tests/integration/test_phase1_retirement.py#L524), `:645`: newer rejected GraphQL boundaries, stale/equal/later 150/200/300 retries and complete clocks.
- [`test_catalog3_current_collection.py:34`](../../../tests/integration/test_catalog3_current_collection.py#L34), `:119`, `:423`: archive-free current state, unresolved terminal resume and parser-version rescan.
- [`test_catalog3_job_plans.py:30`](../../../tests/integration/test_catalog3_job_plans.py#L30), `:79`, `:159`: frozen Source/settings, credential references and interruption.
- [`test_current_collector_projection_followup.py:183`](../../../tests/integration/test_current_collector_projection_followup.py#L183), `:274`, `:319`: field omission/null/clock/contradiction behavior across REST/GraphQL.

Missing replacement tests: loss of optional normalized-cache acknowledgement,
core-only restore with no checkpoint/cache, normalized root child obligations
without saved JSON, retained-field-contract invalidation during 304, selective
normalized target exchange and conflicting unclocked historical observations.
Their expected outcomes depend on the pending decisions above.
