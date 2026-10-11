# Preliminary Publication-independent consistency review

Reviewer: separate `design_consistency` subagent; model/effort not exposed.
Scope: pre-implementation, read-only source/DDL/caller review with two small
executable counterexamples. This is not post-implementation acceptance.

## Verdict

The accepted logical topology is coherent and production implementation can
begin using the coordinated interfaces below. The design does not need an
independent Publication to preserve atomic state, domain validity, bounded
enumeration, code targets, verified Git content, or Exchange staging. The
contracts relayed by the integration owner—typed current API state, direct
collection scope, `has_next` receipts, capture-bound child requirements,
list/ordinal code entries, intrinsic Git rows with decoder-specific derived
values, and per-record typed Exchange—address the major dependency gaps.

This verdict is conditional on preserving the mandatory invariants and tests
below. It does not approve a new default Git interpretation/ref winner,
provider trust, negative Source membership, retention, or an opaque provider
remainder. None of these residual choices blocks the independent settled work.

## Actual reviewed baseline

* Repository: `/workspace/git-repo-db`.
* Integrated feature commit: `6ca31eb95d2dca91adcf20af88fbb54387595375`.
* Tree: `7c3e1795162a2083f6df363a1afa53afa2e29333`.
* Runtime: Python 3.12.14, SQLite 3.53.1 through `.venv/bin/python`.
* Actual `schema_sql()` composition: `catalog3.sql`, `git_facts.sql`,
  `cas_integrity.sql`, `exchange.sql`, `identity_relations.sql`,
  `current_resources.sql`, `current_collections.sql`, `json_contracts.sql`.
* Schema 19 composed SHA-256:
  `d0fba8d577ffad700b17a7504f67228c375a00c16583e1d1c6a7eef7e12c9415`.
* In-memory composition produced 103 tables, 48 views, 498 triggers, and no fresh
  FK violations. These counts establish the inspected baseline only.

Read both complete reconstruction/implementation documents, root and Phase 2
AGENTS, accepted no-Publication ADR and decision register. Reused the existing
publication, acquisition-correction, completeness, Exchange and current typed
field reports; inspected their referenced production mechanisms. Historical
69-table candidate and seals are evidence, not implementation contracts.

## Shared implementation interface

| Workstream | Authoritative subjects and keys | Boundary consumed by other workstreams |
| --- | --- | --- |
| Schema/current state | Existing PR `change_request_id`; document `(PR, kind, provider document ID)`; thread `(PR, provider thread ID)`; Source association `(Source registration, repository)` | Typed normalized candidates; sparse-field merge; explicit presence; field evidence; resource-specific parent/conflict availability; savepoint-aware atomic admission; no fetch/result/profile owner |
| Acquisition/completeness | Exact typed enumeration scope with owner/family/query visibility/parent/target capture; stable membership and normalized terminal/child evidence | Resources admitted independently; proof answers one scope; operational cursor/progress refers to durable targets; rejected identified boundary retains actual clock without bytes; exact target anchor passed to Git/code |
| Git | Verified object `(object format, OID)`; intrinsic ordered parents/entries/tag target; acquisition refs/roots; actual snapshot/ref context; explicit decoder settings | Per-object install or explicit pending intrinsic state; raw bytes independently usable; exact root reachability predicate; decoder-specific derived values with no first/latest/version authority |
| Exchange/query/maintenance | Current resource keys, Git object keys, exact lists/scopes, normalized pending candidates | Closed wire vocabulary, typed dependencies, sparse current admission, resource-specific completeness validation; indexed closure; current search; domain byte verification and CAS-41; optional processing records never own facts |

Use a shared merge/evidence primitive or a typed family registry, not a generic
JSON row store. Extend the established current-resource algorithm rather than
writing unrelated latest-state engines. `resource_key()` currently knows only
Issue/review families: PR conversation `issue-comment` remains a document
natural key and must not accidentally use ordinary Issue/comment identity or
retention merely because its kind string matches.

Local revision advances once for the coherent outer write unit. A page's
members use the same pre-request revision/scope fence; incrementing revision
between sibling admissions would falsely invalidate the later members. The
counter is receiver-local and never travels as provider freshness.

## Concrete issues and required dispositions

### 1. Removing eligibility seals without replacing object transaction boundaries exposes partial Git structure

`adapters/git/parsing.py:65` (`staged_writes`) and `:92` (`write`) batch on row/byte
thresholds. `commit()` writes the commit before its parent sequence; `tree()`
writes entries individually. Today result publication hides interrupted prefixes.
With direct object readers, removing those joins alone would admit a half commit
or tree as complete.

Install the verified object's entire intrinsic structure in one object-scoped
transaction/savepoint, preventing threshold commits inside it. Large acquisition
may commit between independently valid objects. An object completion predicate
is justified only by parsing/checking that exact object's canonical bytes; it
cannot gate unrelated objects or serve as a renamed acquisition publication.
Exchange and full catalog validation must independently reject a truncated,
extra, reordered or mismatched intrinsic row set.

Existing `catalog3.sql:305–320` relations are also acquisition/result/repository
owned and require descendant object rows. Keep the verified owner bytes usable
when a descendant is absent. Either normalize intrinsic referenced OIDs with
checked optional resolved-object links, or leave intrinsic projection explicitly
pending until real dependencies arrive. Do not fabricate target Git objects.
Gitlinks legitimately name an external commit without requiring its bytes.

### 2. Nested admission can leak earlier writes if the caller catches failure

`adapters/sqlite/current_resources.py:190` simply yields when a transaction is
already open. `Store.transaction` at `store.py:171` does not implement nested
savepoints. SQLite statement ABORT does not roll back earlier statements.

Executed on the reviewed source:

```python
c = sqlite3.connect(':memory:', isolation_level=None)
c.execute('CREATE TABLE unit(value TEXT)')
c.execute('BEGIN IMMEDIATE')
try:
    with CurrentResources(c)._transaction():
        c.execute('INSERT INTO unit VALUES(?)', ('partial',))
        raise RuntimeError('evidence write failed')
except RuntimeError:
    pass
c.execute('COMMIT')
assert c.execute('SELECT * FROM unit').fetchall() == [('partial',)]
```

Use savepoints for nested coherent units and whole rollback for outer units,
including COMMIT failure. Preserve the original error if cleanup fails. A page
that rejects any required member must roll back that page's values/text/evidence
and revision; an independently justified partial-boundary write happens after
rollback under the same live job fence. Already committed earlier pages remain
usable. The small reproducer establishes the existing mechanical gap, not an
assertion that every current caller catches this exception.

### 3. Durable collection proof currently depends on operational and transport artifacts

`catalog3.sql:134` makes `fetch_collections.resume_scope_id` mandatory.
`current_collections.py:24–143` uses exact `next_cursor` values to interpret
terminal sequence. `Graph.current_baseline_requirements` at `exchange.py:1205`
walks operational `resume_scopes.request_context` to identify prior completion.
This would violate the new independent-domain boundary if copied unchanged.

Core scope carries the necessary owner/binding/query/visibility/target context
directly. Store normalized `has_next`/terminal meaning rather than HTTP cursor
tokens as validity prerequisites. Existing operational progress owns cursors.
Where incremental completeness really relies on a prior complete scope, retain
an explicit domain baseline relationship with exact comparable scope and
producer/field contract; never let disposal of jobs/cursors invalidate it.
Changing this representation does not choose a permanent new receipt retention
policy. Every retained evidence family needs a named completeness consumer.

### 4. Parent/child completeness needs immutable capture context despite mutable thread state

`GitHubCollector._thread` at `collector.py:1829` currently embeds comments'
IDs/pageInfo/completeness in result-owned thread payload. `_thread_documents`
admits current review comments separately. `pr_queries` child checks and
`Graph.historical_page_boundaries` at `exchange.py:1604` reach original root
inputs to prove the relationship.

Normalize the root's actual thread obligations while the response is in memory.
Bind each to the actual parent collection/capture, thread natural identity,
child scope and necessary exact target. An old child completion for thread T
cannot satisfy a new parent requirement merely because T's ID matches. Partial
GraphQL errors remain nonterminal/gapped even if advertised pageInfo is terminal.
Do not require an old mutable thread body to recompute the proof. Complete
thread roster with unfinished required replies remains incomplete tree.

### 5. Latest PR replacement must preserve only exact code anchors, not old full PR rows

`code_observations`, `root_origins` and query joins currently reference
`change_request_observation_id`; lists key items by fetch/result/page position.
`collector.py:1464` recovers merge/test-merge role presence from saved original
bytes. `query_service.py:392` binds current roots through selected PR observation.

Normalize actual merge-role null/unknown/OID while live input is in memory.
Code assessment/list keys bind exact PR, head/base format+OID, role and scope;
ordered entries use `(listing, global ordinal)` independent of pages. Preserve
minimal retained target evidence while its assessment/root needs it. Do not use
an arbitrary SHA-256 current-state fingerprint as a universal historical PR
owner, and do not retain old title/body/attributes to preserve that fingerprint.
Current-head B queries cannot borrow head A completeness. Explicit recorded A
queries may address the actual old code anchor.

### 6. Source current inventory must retain known associations and independent ownership

`collection_service.py:194–322` presently stores full provider repository
metadata in result-owned member observations and selects one Source root.
`identity_relations.sql:103–130` derives current members from that root.
`repository_identity.link_source:277` stamps local `now_us()` as first/last seen,
which is not the API response's actual observation instant.

Keep current Source association and typed metadata/evidence under Source plus
repository. Update R1 from a later partial R1 scan while retaining known R2;
store latest scan partialness separately from the known roster. Repository
registration/display metadata must not overwrite independent Source assertions.
For new evidence, use the actual captured observation time; keep a clearly
named local-registration timestamp separate if needed. Source is excluded from
the current one-repository exchange, so captured Source identifiers in resource
evidence must remain valid when detached and do not import a Source-wide roster.
No absent-member deletion, new Source provider ordering or UUID winner.

### 7. Ordinary resources and older collection attestations must not require old values

`Graph.current_page_requirements` at `exchange.py:1156` resolves stable current
keys and does not rehash today's values against historical receipt digests.
This is a usable established admitted-attestation boundary. Historical PR proof
instead uses full observations/results/originals in `aggregate_proof`,
`code_proof`, and `proof_requirements`; those references need coherent migration.

Extend stable-identity/attested-scope semantics to latest-only families. Validate
all retained exact values and bytes that actually exist, but do not reconstruct
old values from newer values or retain a hidden edit history. Missing stable
subjects/children stage completeness; independent admitted resources stay
readable. Internally consistent sender omission cannot be detected from a
digest/count alone; the old original itself was no provider-authentication
mechanism. Do not promise stronger truth or invent sender trust.

### 8. Exchange admission receipts must not retain every accepted current value

Existing `exchange_admissions.record_json` and generic immutable result barriers
would recreate accepted-value history if carried forward for mutable rows.
`exchange.py` discovers keys/FKs with PRAGMA, but also has special portable
columns, original authority, generated discriminator parents and JSON references.
Removing tables does not remove those implicit paths.

Persist only processing digest/identity/idempotency information for admitted
current data; actual pending/conflicting candidates may retain required values
and reasons. Treat candidate merge as the same typed domain admission on live
and wire paths. Validate foreign owner/parent and text/Git bytes before promotion;
reverse/repeated/reopen/onward export converges without receipt-order winners.
Unresolved parent conflicts must propagate resource availability and complete
scope qualification. Use indexed selected roots/children/dependencies rather
than repository-wide scans; test same-repository unselected growth.

### 9. Search, maintenance, generated guards and packaged CLI must retire the actual consumers

`index.py:40,117` obtains PR search inputs from all usable historical document
observations. New search selects eligible current document values and preserves
Issue/review semantics. Unreferenced shared text may remain physical bytes but
must not appear as supported history/search output.

`json_contracts.py` has categories, portable/local reference targets, recursive
dispatch and generated guards for old identities. Regenerate the packaged
SQL from the same new closed registry. Provider-shaped metadata is currently
explicitly opaque; copying that category to a renamed state payload does not
meet the reconstruction. `maintenance_service.py:500` audits dangling old
publications; parser CLI/service, certificates/scripts, Git query context and
byte-offset readers also need actual replacement, not dead imports.

Retain physical CAS/quarantine, true SHA-1/SHA-256 verification, exact text and
CAS-41 copied count. Remove `decoded_api` and legacy manual configuration
original stores only after those live producers/consumers are reexpressed.
Manual discovery uses normalized current settings, not a fake fetch/input.
Backup/restore readiness and no-overwrite file installation remain separate
physical catalog operations.

## Genuine residual semantics, without reopening the questionnaire

1. **Git decoder/current projection ambiguity.** Existing supported settings are
   utf-8/latin-1 plus strict/replace/backslashreplace metadata decoding. Executed
   example `b'caf\xe9'` yields `caf\\xe9` under utf-8/backslashreplace and `café`
   under latin-1. `query_service.py:1181,1244` reads selected profiles for byte
   offsets; `git_query_context.object_context` reports multiple eligible
   interpretations unresolved. Raw structural object facts have one intrinsic
   meaning, but decoded strings do not. Decoder-specific derived keys and actual
   capture/query context preserve supported decoding; an undisputed default
   among incomparable candidates cannot be selected by first insertion, latest
   parser, UUID or timestamp. Preserve unresolved/explicit addressing, or report
   the exact path needing a stronger owner choice. Ref/snapshot captures also
   remain domain history; a last-imported snapshot is no current-winner policy.
2. **Unknown provider-event/remainder meaning.** F08/F12/F20 and CI-11 inventories
   are not closed validation schemas. Current timeline accepts events without
   provider IDs and arbitrary provider-shaped objects. Retain modeled named
   event/actor/repository/list fields with justified meanings, exact presence
   and natural capture/event identity; actual timeline occurrences are domain
   events, not PR edit snapshots. If preserving an unknown event variant or
   arbitrary remainder is essential to a supported public contract, name its
   exact field and consumer. Neither opaque whole-response retention nor silently
   dropping supported modeled data is justified. This does not block closed
   known families and resource-independent work.
3. **Stronger remote truth.** A receiver cannot detect a coherent sender that
   omits a provider member from both declaration and digest. Preserve the
   existing admitted-attestation boundary and qualify incomplete/unprovable
   claims; do not assert cryptographic provider authenticity or auto-promote an
   unsupported complete claim. Stronger guarantees remain unselected.

No further owner policy is required merely to choose indexes, natural-key
columns, savepoints, bounded normalized domain scope representation, or closed
modeled fields that preserve accepted behavior. Do not turn the residuals into
an implementation stop for independent work.

## Minimum integrated counterexamples for later independent review

* Value/evidence/local revision rollback together, nested caught failure, and
  deferred-FK/COMMIT failure; all sibling page members use one live fence.
* PR/document/thread sparse v1/v2 field evidence; omitted/null/empty/type
  distinctions; older fill of unknown field; equal/incomparable conflicts.
* Complete100, identified partial200, stale terminal175, terminal300; same-time
  conflict; terminal empty versus missing terminal; partial/foreign child.
* Source R1/R2 then partial R1; no deletion, Source metadata overwrite or invented
  response time.
* PR head A retained exact code anchor followed by B; no old PR/body prerequisite
  and no borrowed completeness.
* Prefix of acquisition remains usable; incomplete single-object parents/tree
  never complete; missing descendant explicitly incomplete; external gitlink;
  both Git formats and decoder ambiguity/byte offsets.
* Parent missing then arrives, reversed/duplicate wire delivery, current drift
  versus old attestation, pending re-export/reopen and foreign owner evidence.
* Repeated current updates add no normalized accepted-value history, including
  exchange receipts/jobs/pending JSON; inspect shared unreferenced text separately.
* Optional logs/cursors/checkpoints lost without invalidating facts; fresh retry
  preserves actual clocks rather than generating a replay observation.
* Corrupted shared digest, real/fake Git descriptor, CAS-41 copied quarantine
  mismatch, atomic no-overwrite restore; current search excludes old texts.
* Same-repository unselected growth and selected-volume growth with indexed
  closure/statement or VM counts; no concurrent timing comparison.

Only the two small executable mechanics examples and fresh composed DDL check
were executed during this preliminary pass. The ordinary/package suites and
all redesigned behavioral scenarios remain post-implementation work. Required
fresh independent reviewers must inspect the corrected frozen integrated tree;
this review does not substitute for any of their four acceptance scopes.
