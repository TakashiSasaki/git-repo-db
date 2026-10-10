# Phase 2 owner decision register

**Every recommendation below is Proposed / Pending Owner Decision.** No option is
approved by creating this document/PR or by executing a prototype. TP-01–TP-08,
R1–R7 and the [unchanged invariants](README.md#accepted-invariants-unchanged) constrain
all options. The currently reachable schema is a correctness boundary until a
complete replacement is accepted and verified. No question asks to reapprove it.

The questions can be answered as named options, with explicit exceptions for
field groups or families. Recommendations aim to reduce coordinated implementation
choices. Different approved options remain feasible; no compatibility layer is
required for this unreleased project.

## P2-Q01 — PR state observation lifecycle

**Question:** Keep each admitted historical PR state observation, or keep one
accepted current state plus only the immutable receipt evidence required for
publication/completeness/conflicts?

- **A — recommended:** Retain domain PR observations, their exact retained fields,
  capture clocks/owners and publication membership. Shared text/content deduplicates
  independently; equal content does not merge different genuine observations.
- **B:** Current PR state plus explicitly defined confirmation/conflict/receipt
  records; older field values are unavailable after replacement. Completeness
  receipts cannot pretend to be reconstructible past PR values.

Example: PR #7 head A at provider clock 100, head B at 200, list L observed at 100.
A can exchange/recompute L's exact normalized A observation while current candidate
is B. B can retain L's attested A digest and identity, but cannot export past A
values unless separately retained. At equal clock, A versus B remains a conflict;
neither option authorizes last-received or parser-version order.

A uses O(observations × named fields), B O(resources + necessary receipts/conflicts).
Both avoid response envelopes and repeated nested provider objects. A simplifies
historical queries/receiver exact-value validation; B needs explicit unavailable
history outputs and Q10 receipt qualification. Backup carries only selected domain
history/text, never a mandatory response archive. Coverage's columns/time derivation
are unchanged. Test equal/incomparable clocks, sparse field origins, missing/null,
selective old observation exchange and changed PR head. Co-designed with Q04/Q09 and Q08
selection; blocks PR-state lifecycle replacement. See [publication](workstreams/publication.md).

## P2-Q02 — PR conversation and independent thread history

**Question:** Retain all domain observations of PR title/body/conversation comments
and independent thread states, or current-only values with immutable membership/
target receipts? This question does **not** reopen ordinary Issue/comment or
Review/comment latest-state contracts.

- **A — recommended:** Retain PR document observations and independent thread
  observations. Use natural document identity; a retained domain observation is
  not a new document surrogate/version identity. Current reviews/comments remain
  current rows; nested membership receipts attest observed digests/identities.
- **B:** Current values for the deferred PR-conversation/thread families, retaining
  exact required membership, parent/target and conflicting evidence separately.

Example: conversation comment C says “before” at 100, “after” at 200. A exposes both
texts with distinct provenance. B exposes “after” plus an old membership digest;
its old receipt cannot reconstruct “before”. A thread resolved=false at 100 and
resolved=true at 200 is similarly different from review-comment edit history.
An empty comments child is complete only with explicit terminal evidence.

A adds observation/text retention and historical search surfaces; B reduces value
storage but needs honest unavailable-history queries and Q10 qualification.
Publication, Coverage and backup retain exactly the approved domain lifecycle.
Tests must cover body missing/null/empty, duplicate natural document IDs across
kinds, independent thread state versus current review targets, old receipt/current
value drift and child completeness. Co-designed with Q04/Q05/Q06/Q09; influences Q10; blocks deleting
historical document/thread result and original FKs. Details in
[publication](workstreams/publication.md) and [fields](workstreams/fields.md).

## P2-Q03 — Source inventory scan lifecycle and identity

**Question:** Preserve each Source-scoped inventory enumeration/publication and its
observed repository members, or retain a current inventory roster plus receipt/
assessment evidence? How should current Source scan candidates be exposed?

- **A — recommended:** Independent Source publication and collection-observation
  UUIDs; retain actual scan observations/member facts. Present assessment candidates
  at the latest actual scoped scan observation time, with partial/unknown/conflict
  visible. This is a proposed Source assessment rule, not an automatic extension
  of repository Coverage or an ordering of unrelated provider attribute clocks.
- **B:** Current Source roster plus necessary owner/member/terminal/conflict
  receipts; remove historical value availability from public inventory queries.

Example: Source S authenticated as principal P sees repositories R1/R2 in complete
scan 100, then only R1 in interrupted scan 200. Neither option treats R2 as deleted
or calls 200 complete. A keeps both enumerations; B keeps current known roster and
honest newer partial evidence. Repository is the **subject**, Source the owner.
A second Source with the same URL/name remains a distinct identity. Provider
repository binding reuse must obey existing service/provider uniqueness, never
silently merge catalog repositories.

A stores O(scan members); B O(roster + proof/conflicts), with different historical
query/backup guarantees. Both can keep Source-wide inventory excluded from current
one-repository Exchange; exporting it requires a separate explicit scope/trust
choice, not Q10's assumed default. Tests cover principal/private scope, unsupported
owner, accepted prefix, expected count/terminal, Source-service mismatch and same
name/different UUID. Depends on Q04/Q05/Q09; blocks Source-original retirement.
See [publication](workstreams/publication.md)
and [completeness](workstreams/completeness.md).

## P2-Q04 — Atomic domain-publication identity

**Question:** Use an independent typed domain bundle/seal, or family-specific
publication seals without a shared publication identity?

- **A — recommended:** Separate `repository_publications` / `source_publications`
  UUIDv4 identities, direct typed ownership/output FKs and exact generated member
  seal. Optional typed domain dependencies bind code to PR/list/Git inputs. Each
  observation remains distinct; actual per-output/field parser attribution lives
  with the output, not parser-profile authority.
- **B:** Family-specific typed seals keyed to domain enumeration/assessment/Git
  acquisition; use explicit cross-family dependency links where code needs them.

Example: one PR-list response admits P1/P2 and their title/body values; an interrupted
later page does not erase that sealed partial bundle. Code for P1 combines prior
PR head, two list fragments and a Git acquisition. A groups these into independent
bundles without using HTTP IDs; B uses dedicated PR/list/code seals. Neither can
be implemented as a dummy fetch, empty parser input manifest or a renamed result
with profile/certificate prerequisites.

A adds bundle/member indexes but one consistent seal validator; B fewer shared
identities but more family-specific transaction/Exchange code. Both preserve exact
immutable output membership, typed owners and partial publication safety. A seal
is not collection completeness. Backup carries legitimate bundle/owner evidence;
Coverage refers to separate completion evidence. Tests reject changed sealed output,
wrong owner, missing member, mismatched digest and incomplete dependencies. Depends
on Q01/Q02/Q03/Q08 family boundaries and Q09 fields; **blocks the largest common
publication/profile retirement step**. Details: [publication](workstreams/publication.md).

## P2-Q05 — Normalized collection membership and terminal proof

**Question:** Retain admitted fragment/member/terminal evidence, or only a sealed
exact domain-member set plus an enumeration assessment?

- **A — recommended:** Typed repository/Source collection scope and observation,
  ordinal fragment receipts, exact typed member identities/digests, explicit
  terminal and independent completeness seal. No HTTP message hashes/cursors are
  core proof. Operational cursors stay separate.
- **B:** Exact domain set and one terminal/count/digest assessment; fragment
  continuation evidence is operational. Receiver proof strength must be qualified
  under Q10, and no automatic evidence deletion is implied.

Example: one admitted zero-member fragment ordinal 0 plus terminal 0 proves empty.
No terminal does not. Fragments 0/2, duplicated 1, member digest mismatch or missing
selected member cannot prove complete. A receiver can challenge those fragment
conditions; B receives an assertion about the final set and cannot reconstruct
fragment boundaries. Immutable-family members bind exact observations; current
Issue/review members retain the established receipt/identity responsibility.

A uses O(fragments+members), B O(members); both verify bounded indexed exact closure.
Counts alone cannot establish completeness. Coverage stays five columns/latest-time;
a newer partial or equal-time contradiction blocks older complete fallback.
Exchange/backup carry chosen evidence without originals. Tests cover every boundary
above, raw versus domain identity, inherited incremental baselines, missing owners,
subset/late arrival and same-time conflict. Implementation requires Q04/Q09; its evidence contract precedes Q10; blocks flat
proof retirement, not existing correctness hardening. See
[completeness alternatives](workstreams/completeness.md#p2-q05--what-durable-normalized-collection-evidence-is-required).

## P2-Q06 — Nested GraphQL obligations and code targets

**Question:** Model required child collections/target roles as explicit typed
obligations attached to exact parent observations, or parent-embedded closed
completion manifests?

- **A — recommended:** Typed root/thread member → required child-family obligation,
  normalized initial child members and explicit known-terminal/continue/unknown
  state; exact child seals discharge it. Persist head/base/merge/test-merge target
  presence/OID evidence independently of original roots.
- **B:** Closed parent domain manifest containing exact typed child completion
  identities/states, validated under a versioned semantic contract.

Example: root T1/T2 at 100 has complete empty child T1 and T2 prefix with errors.
Parent is partial until exact T2 child completes; a child for another same-repository
PR/thread cannot discharge it. A null merge OID is observed null, an omitted role
unknown. Code acquired for head A cannot become code proof for later head B.

A adds O(parents+obligations+child members) indexed rows and explicit retry targets;
B fewer tables but recursively validated closed manifest bytes and more complex
scoped querying. Both retain accepted prefix on restart and original clocks, never
reparse saved envelopes. Coverage and Exchange need the exact obligation set, not
sender booleans or only children that happened to arrive. Backup carries domain
obligations; transport continuation is Q12. Tests include error-bearing root,
missing obligation, wrong natural parent, stale retry and changed head/base.
Implementation requires Q02/Q04/Q05/Q09; its durable evidence contract precedes Q12 and Q10; blocks nested/root-original
retirement. See [completeness](workstreams/completeness.md) and
[acquisition](workstreams/acquisition.md).

## P2-Q07 — HTTP 304 ownership and reuse

**Question:** Disable conditional reuse for the first transport-independent core,
keep a disposable coherent operational cache, or confirm against normalized domain
version evidence without original body reuse?

- **A — recommended first implementation:** Unconditional 200 fetch/parsing; no
  core validator/cache origin. Higher bandwidth/rate cost, simplest correctness,
  cold restart and cache-loss behavior. Optional recording remains independent.
- **B:** Separate cache keyed by service/principal/endpoint/request shape/resource
  generation/validator and exact cached normalized target or response. On missing,
  corrupt, stale or mismatched entry, unconditional refetch. Cache may not publish
  retrospective observations or become a mandatory core backup/Exchange input.
- **C:** ETag bound to a normalized domain observation/retained field-contract
  revision; 304 confirms that exact identity/scope without body parsing. Requires
  a complete normalized reusable target, checked generation fence and invalidation
  on changed field contract. A digest alone is not reusable content.

Example: cache anchor A/ETag E, core later accepts B. A 304 cannot complete B using
A. Losing cache never makes A's already admitted domain facts unavailable.
A needs more requests; B more operational storage/coherence/recovery logic; C less
response storage but the strongest normalized completeness/fence preconditions.
None invents provider observation time or sends local validators via Exchange.
Tests: stale/missing cache, changed principal/query/field contract, race after
request, genuine 304, response parse failure and archive loss. Depends on Q04/Q09/
Q12; blocks 304-body retirement, can be decided independently. Full tradeoffs:
[acquisition](workstreams/acquisition.md#5-http-304-actual-safety-checks-and-three-feasible-replacements).

## P2-Q08 — Historical Git interpretation and PR/Git selection

Answer both subquestions explicitly: **Q08-S** selects evidence/candidate resolution;
**Q08-G** selects intrinsic decoder facts versus retained interpretations. They are
separate decisions, not a single implicit parser-version rule.

**Q08-S question:** Use family-specific evidence/maximal candidates with explicit
unresolved conflicts, or explicit domain resolution assertions (without parser
selection DAGs)? **Q08-G question:** Retain intrinsic Git object facts with decoder provenance,
or all normalized interpretations of the same verified raw objects?

- **Q08-S A — recommended:** Natural content/observation identity and actual module/version,
  decoder/byte-offset facts; only domain-established comparable clocks or exact
  snapshot scope semantics determine dominance. Expose incomparable maxima and
  interpretation contradictions. Default decoder version is not authority. Retain
  explicit raw acquisition/snapshot/ref/root membership independent of interpretation.
- **Q08-S B:** Allow typed owner-authored domain resolution assertions when
  necessary, preserving all disputed candidates until resolved. No parser verification,
  selected profile or predecessor DAG is required for ordinary admission/reading.
- **Q08-G A — recommended:** Intrinsic content facts with explicit actual decoder/
  byte-offset evidence; contradictions are recorded, not overwritten by parser version.
- **Q08-G B:** Retain every normalized Git interpretation with actual producer/decoder
  evidence; choose resolution separately under Q08-S. Raw bytes stay required in both.

Example: two PR heads A/B with incomparable endpoint clocks both remain candidates.
Git object G is decoded with UTF-8 versus Latin-1; raw G is unchanged, search byte
offsets need actual decoding evidence. Selecting parser v2 cannot silently make its
value or a ref snapshot current. A ref observation without a comparable provider
revision needs explicitly approved scope/snapshot selection semantics, not receipt
order. This register recommends disputed candidates until that semantic evidence
exists, not an invented total order.

Q08-G A is smaller/fewer joins but needs a precise deterministic fact/decoder contract;
Q08-G B stores interpretation candidates. Q08-S B adds resolution assertions; S-A
leaves disputes visible until genuine domain evidence establishes dominance. Both preserve exact
Git bytes, partial roots, natural parents, unavailable targets and contradictions.
Exchange carries exact verified domain dependencies, backup preserves bytes and
interpretations chosen by lifecycle. Tests include SHA1/SHA256, Gitlinks, repeated
headers, decoding offsets, partial acquisitions, incomparable PR/Git candidates
and module upgrades. Depends on Q01/Q04/Q09/Q10; blocks Git/profile current-reader
retirement. Details: [publication](workstreams/publication.md),
[fields](workstreams/fields.md).

## P2-Q09 — Retained domain-field contract

**Question:** Approve the named broad meanings F01–F19 in the field inventory,
a narrower explicit functional subset, or typed core plus named closed extensions?

- **A — recommended:** Broad typed named contract F01–F19, including exact text,
  optional patch, heterogeneous timeline event contents, scoped Source attributes,
  code targets and actual provenance. Model collection-valued relationships as
  typed memberships; closed domain JSON is allowed only with defined keys/types.
- **B:** Explicit functional minimum. The owner identifies each omitted field group
  and accepts its future unavailability; it cannot be recovered from core originals.
- **C:** Typed mandatory core plus registered, versioned, closed domain extension
  structures. Unknown unmodeled response objects remain outside persistence.

Example: labels omitted preserves prior labels/evidence, labels=[] is known empty,
labels=null is explicit null, a transport marker in an arbitrary provider key is
not a required domain property. A timeline comment event may contain genuine text;
retaining only event/id/time loses content. PR title/body metadata today duplicates
PR detail; selected meanings belong once to PR facts, with document-specific
provenance. Preserve raw Git headers even if decoded projection is lossy.

A more typed rows/indexes, B smaller storage/fewer query fields, C extension
validation/version cost. All avoid opaque originals and preserve body/attribute
presence/provenance. Public query/search/Exchange contracts and backup reflect
exact named meanings. Tests exercise each union/field type, per-field attribution,
transfers, null/missing/empty/unchanged, unknown extension rejection and decoder
content. Co-designed with Q01/Q02/Q03/Q08 lifecycle for availability; **blocks every opaque
provider-field deletion**, not independent omission repairs. Full row/path contract:
[field inventory](field-contract.json), [fields](workstreams/fields.md).

## P2-Q10 — Receiver-verifiable normalized Exchange evidence

**Question:** Require exact normalized-value closure for deferred historical-family proofs,
or allow qualified historical receipt attestations? Established current Issue/review
receipt/identity closure stays unchanged under every option.

- **A:** Deferred historical-family proofs carry all normalized historical values
  needed to recompute their state digests; feasible only where history is approved.
  Accepted current Issue/review families keep receipt/identity closure, without edit history.
- **B — recommended:** Exact normalized-value closure for retained immutable families;
  qualified historical receipt/identity closure for deferred families whose latest-only
  lifecycle is explicitly approved; established immutable receipt plus stable identity
  closure for accepted mutable current families. State digest attestation is described honestly. Missing closure
  stages and conflicting candidates remain barriers; sender hints do not grant authority.
- **C:** Sender assertion/digest with missing member closure remains staged or separately
  qualified evidence; it never alone gives receiver-verified complete Coverage.

Example: observed current Issue X at 100 later changes to Z. B transfers old receipt
X and current identity Z without pretending Z was observed at 100 or creating edit
history. Current Issue X history is not reopened by this question. A concerns approved
historical PR/thread/Source/Git families. A selective collection with O1/O2 but missing
O3 is incomplete for all receiver-verified alternatives. Reordered/repeated O3 late
arrival can promote exact closure idempotently.

A larger packages/history, B smaller current closure, C small partial units but
unavailable completeness. All use indexed O(V+E) selected dependency construction;
no repository-wide scans or quadratic per-member aggregate proof rebuild. Closure validation is structural consistency and admitted ingestion evidence, not
cryptographic provider authenticity. A fresh receiver cannot discover a provider member
omitted from both declaration and digest by a coherently dishonest sender. **Q10-T:**
approve structurally validated admitted domain attestations as imported evidence
(recommended at the existing provenance boundary), or hold their complete assertions
unavailable until a real new local/provider observation confirms them. The latter costs
requests and cannot pretend to reconstruct old provider state. No new trust policy is
accepted here. Exclude
operational cache/trust/quarantine/local checks/Source-wide inventory under current
one-repository scope. Git/text bytes and CAS validation remain required. Test tampered
normalized values, changed mutable values, bad manifests, portable key collisions,
missing/foreign owner, direct malformed staging, late dependencies and conflicts.
Depends on Q04/Q05/Q06/Q09 and affected lifecycle/Q08; blocks wire/trust changes.
See [Exchange alternatives](workstreams/exchange.md#p2-q10--what-exact-normalized-evidence-must-a-receiver-possess).

## P2-Q11 — Physical content separation and legacy quarantine

**Question:** Keep one domain physical CAS with typed legitimate consumers, or
separate Git and exact text/domain stores? No retention duration, deletion or GC
policy is requested by this question.

- **A — recommended:** Reuse shared physical `stored_bytes` for approved domain
  representations and exact text semantics; cache/archive has separate disposable
  ownership. Fresh schema stops admitting decoded API registrations after all
  legacy proof dependencies migrate.
- **B:** Separate Git byte store and exact-text/domain stores, with complete atomic
  integrity/backup/restore closure across every mandatory component.

Example: same bytes have Git and legacy HTTP references. HTTP retirement never
removes domain bytes or skips their quarantine. Existing API-only corruption stays
honestly diagnosed/backed up while its old runtime dependencies exist; API repair
through a fabricated Git descriptor stays forbidden. Fresh incompatible schema
is not permission to mutate retained user catalogs.

A preserves deduplication/current verifier transactions; B clearer physical ownership
but potentially duplicate bytes and additional backup/restore coordination. CAS-41
active physical count and prediagnosis manifest verification remain exact. Tests:
shared digest, physical corruption, genuine/forged Git repair, rollback, quarantine
count mismatch and source/copied verification. Depends on Q07/Q09 and dependency
retirement; storage layout can wait without blocking domain design if A is used.
Archive durations, automatic deletion and GC remain explicitly unchosen.
See [CAS alternatives](workstreams/exchange.md#p2-q11--where-do-retained-domain-bytes-and-their-physical-diagnoses-live).

## P2-Q12 — Durable checkpoint guarantee and placement

**Question:** Is an accepted normalized prefix atomically checkpointed in the same
catalog, acknowledged via a separate durable operational journal, or reconstructed
from domain evidence with a fresh scan after checkpoint loss?

- **A — recommended:** Small operational checkpoint section in the same SQLite
  transaction as the committed prefix, separate from domain eligibility, Exchange
  and parser authority. Lifetime remains explicit, with no automatic deletion chosen.
- **B:** Separate operational store; acknowledge committed domain prefix and reconcile
  on recovery. A local checkpoint cannot safely assume atomic cross-store commit.
- **C:** Reconstruct from durable normalized proof/targets and refetch from a safe
  boundary. More duplicate requests; original domain clocks remain unchanged.

Example: prefix ordinals 0/1 committed, process dies before cursor acknowledgement.
A restores cursor with the exact prefix; B reconciles its journal; C safely refetches.
An old attempt generation never publishes after a newer job fence, and partial work
never advances a complete watermark. Deleting optional recording changes none of these.

A cheap restarts/one transaction, B physically clean operations but recovery protocol,
C smallest operational dependency with network/rate costs. Frozen nonsecret job plans,
Source registration references, execution-time credentials, cancellation/fencing remain
accepted. Backup includes required checkpoint state only if its approved guarantee
requires it; domain restore remains valid without disposable transport cache. Tests
inject death before/after commit, stale retries, missing child cursor, cancellation
after terminal and duplicate re-fetch. Depends on Q04/Q05/Q06, separate from Q07;
blocks restart rewrite. Full options: [acquisition](workstreams/acquisition.md#6-minimum-normalized-restart-design-and-checkpoint-alternatives).

## Recommended decision order and implementation impact

1. **Largest common domain step:** Q04-A, Q05-A, Q06-A and Q09-A, with explicit
   Q01-A/Q02-A choices for the historical API families involved. These approve
   publication/proof/field meaning, not retention duration or GC.
2. **Acquisition boundary:** Q07-A and Q12-A, or explicit alternatives before
   writer/restart/cache replacement. No cache policy is inferred from archive retirement.
3. **Parallel families:** Q03-A Source scan design and the independently answered
   Q08-S-A candidate-selection / Q08-G-A intrinsic Git facts contracts can be
   reviewed independently, then implemented in parallel workstreams.
4. **Portable integration:** Q10-B and an explicit Q10-T attestation/trust answer
   after proof/lifecycle meanings are known. Q11-A
   is the lowest change physical option; broader storage or GC decisions can wait.

The core coordinated schema/writer/query/Exchange retirement cannot truthfully be
unblocked by Q04 alone. The smallest number of **approval bundles** is four:
API domain meanings, acquisition/restart, Source/Git family meanings, portable proof.
The twelve questions make those bundles concrete and allow exceptions. An owner can
approve the recommendations explicitly by ID; silence, CI success and documentation
merge are not approval. No reapproval is needed for accepted TP/R/identity/Coverage/CAS
contracts or for the independently determined implementation fixes.
