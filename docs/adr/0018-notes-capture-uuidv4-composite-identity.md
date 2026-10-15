---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0016-immutable-notes-ref-capture-observations.md
  - 0017-domain-keys-without-storage-surrogates.md
  - 0015-automatic-git-notes-ref-discovery.md
---

# ADR 0018: Origin UUIDv4 and capture UUIDv4 as the direct notes-capture key

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

**Current refinement:** [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) accepts direct semantic composite claim/group keys using the actual Capture UUIDv4 pair, typed slot, asserted value and genuine provenance, without surrogates. B02-R01 structural role-evidence strength is fixed by [ADR 0022](0022-receiver-verified-notes-role-admission.md); B02-R02 configurable finite budget policy is fixed by [ADR 0023](0023-configurable-finite-notes-resource-budgets.md); B02-R03 actual-work accounting is fixed by [ADR 0024](0024-actual-notes-resource-work-accounting.md); [ADR 0025 / B02-R04 A](0025-cumulative-request-budgets-and-scoped-blockers.md) fixes cumulative work within one explicit acquisition request across continuation/resume/retry. Counter units, defaults and resume mechanics are agent-owned engineering work, not further owner blockers. Other proof/completeness/trust/DDL work remains separately scoped; GCTX-M10 recovery is fixed by ADR 0026; detailed implementation remains work under that policy. Earlier alternatives below retain their historical scope.

- **Decision ID:** B01-R03.
- **Owner decision:** **D-1** — one stable issuer/`capture_origin_uuidv4` and one independent `capture_uuidv4` per genuine Git notes-ref observation, directly forming the composite domain primary key; **no receiver-local surrogate**. Both UUIDs are version 4.
- **Decision date:** 2026-10-15. Owner-selected architectural target; no production DDL, runtime code, migration or actual ingestion is changed.
- **Direct predecessor:** Unmerged [PR #58 / ADR 0017 / KEY-P01](https://github.com/TakashiSasaki/git-repo-db/pull/58), HEAD `c3cb94b367777b4a31d9dcf9644e253a69eef74a`. Earlier dependencies include B01-R02 / ADR 0016, B01-R01 / ADR 0015, product scope ADR 0014 and GCTX-M01–M09.
- **Concurrent unrelated proposal:** [PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52) reserves ADR 0011 for still-proposed governance and is not accepted or integrated by this decision.
- **Implementation baseline:** Three-Store Catalog3 Core Schema 21, Operational Schema 1 and Search Schema 1. These are not the accepted final schema.

## 1. Binding capture-key structure

The permanent notes-ref observation identity is **exactly the pair**:

`(capture_origin_uuidv4, capture_uuidv4)`

- `capture_origin_uuidv4`: a version-4 UUID identifying the **capture-ID issuing authority** as a genuine domain producer/origin. It MUST remain stable across observations made by that same origin and across authentic forwarding/backup of those observations, and MUST be distinct for an independent origin in the identity contract.
- `capture_uuidv4`: an independent version-4 UUID minted **once for each genuinely new observation/capture** by that origin. A separately observed identical notes ref/root gets a **new** capture UUID; an exact retransmission of the earlier observation retains **both** original UUIDs.
- These two UUIDs are the capture's **actual portable composite primary key**, and every dependent notes mapping/group FK uses their complete pair. Do not substitute a single auto-increment ID, a receiver-local capture row UUID, a content fingerprint, a timestamp, a Git OID or a second UUID that exists only for storage.
- Both components must satisfy UUIDv4 syntax/version/variant and byte-identity validation at ingress; the choice between canonical string/16-byte SQL storage and detailed UUID representation constraints is left to physical schema design. Value equality and normalization must be unambiguous across Exchange/backup.
- No multi-ref generic event key, implicit current-ref state, generic Publication or sender-authoritative validation status is created.

**Conceptual DDL only (NOT production):**

~~~sql
CREATE TABLE notes_ref_captures (
  capture_origin_uuidv4 TEXT NOT NULL,
  capture_uuidv4        TEXT NOT NULL,
  repository_uuidv4     TEXT NOT NULL,
  raw_ref_name          BLOB NOT NULL,
  PRIMARY KEY (capture_origin_uuidv4, capture_uuidv4)
) STRICT, WITHOUT ROWID;

-- The child mapping uses both primary-key components:
-- FOREIGN KEY (capture_origin_uuidv4, capture_uuidv4)
--   REFERENCES notes_ref_captures(capture_origin_uuidv4, capture_uuidv4)
~~~

This minimal example intentionally omits the final UUID CHECK guards, immutable provenance/group/evidence tables, byte admission constraints, exact ref/root claims, appropriate FK targets and transaction protocol; it is NOT a complete schema or authorization to implement.

## 2. Issuance, provenance and receiver behavior

**Local observation.** When a capture producer first makes a genuinely new notes-ref observation, it uses its persistent `capture_origin_uuidv4` and mints one fresh `capture_uuidv4`. Both identify that capture for all future partial deliveries or transfers of the *same capture*. A re-observation, including one yielding the identical ref/root and note members, is an independently created capture with a new UUID.

**Exchange/import.** An intermediary catalog MUST forward a preserved, evidenced original capture key with the original capture provenance. It must not mint its own `capture_uuidv4` merely because the receiver allocates a new SQLite row or the same capture arrives via a different transfer path. The receiver may independently verify the origin/key claim and related facts; a matching key is a **candidate for idempotent replay**, never authority to trust a claimed root/Provider/physical checksum. Do not relabel another origin's capture as locally observed.

**Input sources that do not issue capture UUIDs.** A real local capture adapter may be the capture producer, even when it reads Git or receives a Provider API response with no native capture-event ID. It creates its own persistent origin and UUIDv4 for the actual observation, retaining the underlying remote/source attribution **separately**. Merely loading metadata with no established capture identity is not a license to arbitrarily relabel separate observations as identical. Precise first-admission/restart semantics and imported-origin authentication remain later protocol work; do not require the external Provider itself to issue UUIDv4.

**Origin is not repository identity or Source ID.** `capture_origin_uuidv4` is NOT by default `repository_uuidv4`, Git `(object_format,oid)`, a Context `source_id`/provider registration, a service instance's mutable URL or the remote notes-ref name. Repositories and external sources may be observed by multiple independent capture origins. Context must not be required to create/read Core-only captures. The exact relationship to any pre-existing persistent service instance UUID is not silently equated here.

**Clone/fork and collision safety.** The origin identity must not be accidentally duplicated by separately administered independent issuers that claim to be distinct origins. If a cloned catalog produces further independent captures, the origin/issuer semantics and stable UUIDv4 generation must avoid key reuse and wrong attribution. The exact clone/fork reassignment protocol, access control and issuer authentication are not fixed by D-1; a UUID is a uniqueness device, **not a signature** or proof of an observation. UUIDv4 collisions, reused IDs, spoofed origin IDs and protocol violations must fail closed or surface typed conflicts rather than overwrite old Core facts.

**No time-based identity.** Unix epoch microsecond times, UUID issuance order, root OID order, receive order, local row/transaction number and notes decoder are not substitutes for either UUID and are not canonical Git read winners. Missing observed root/type/member data remain truly missing and can be recorded within the accepted typed observation contract; the root and members are NOT components of the composite capture key.

## 3. Separate stable identity from the not-yet-decided replay protocol

This ADR **does** decide:

- Which two UUIDv4 components identify a notes-ref capture and how the child composite FK refers to it.
- A genuine **new** capture is minted once, and different captures of exactly the same notes ref/root remain distinct.
- A genuine **retransmission of the same** capture retains both original UUIDs, including when forwarded via multiple catalogs and when parts are delivered at different times.
- An incoming equal capture key cannot overwrite accepted immutable Core repository/ref/root/provenance/notes evidence or be treated as intrinsically trusted.
- Whether a note body was acquired and byte-verified is independent of the capture UUID, and never authorizes ordinary file-blob archival.

**Subsequently fixed by [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md), not by the original B01-R03 selection:** independent compatible, source-attributed immutable facts and separately atomic coherent relation groups can be appended under the same Capture; exact repeated typed facts are idempotent. Existing groups are never mutated, and partial groups are not silently merged into a complete list.

**Subsequent refinements and remaining open work:**

- **B01-R05 is now fixed by [ADR 0020](0020-immutable-competing-notes-member-claims.md):** eligible conflicting member reports become separately attributed immutable alternatives with derived conflict. Forged capture identity still fails closed; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A.
- **B03:** exact complete/partial/known-empty group/list evidence and whether/when a separately supported complete-scope claim can be admitted; no generic mutable completeness promotion.
- Direct semantic identity/equality is fixed by ADR 0021 / B01-R06 A; concrete member/group grammar, origin authentication/registry, producer takeover/clone security, Exchange wire serialization, schema constraints, locking/read fences and transaction protocols.
- **B02-R01:** role-evidence strength fixed by ADR 0022; **B02-R02:** configurable finite budget policy fixed by ADR 0023; proof grammar remains open; **GCTX-M10:** active physical quarantine/disposition predicate.

## 4. Worked cross-catalog example

Consider origin P, whose UUID is `OP`, observing repository R and ref `refs/notes/review`:

| Event | Origin key | Capture key | Root | Correct treatment |
| --- | --- | --- | --- | --- |
| First actual observation | OP | K1 (fresh UUIDv4) | A | Insert immutable capture reference for K1 |
| Same capture K1 resent via another Exchange path | OP | K1 unchanged | A | Recognize same capture; do not create a new capture |
| Independent second observation of same root A | OP | K2 (fresh UUIDv4) | A | Distinct capture K2 despite equal ref/root |
| Third observation after ref moves | OP | K3 (fresh UUIDv4) | B | Distinct capture K3; do not mutate K1/K2 |
| Independent origin Q observes A | OQ | K4 | A | Distinct capture; same root does not merge the observations |
| Sender supplies OP/K1 but ref or root inconsistent with accepted immutable claim | OP | K1 reused | B | Refuse silent overwrite/trust; handle per later conflict protocol |

One DB may use different physical index layout than another, but both can refer directly to the same domain pair `(OP,K1)`. No mapping by receiver-local surrogate is needed.

If K1 was only partly delivered on the first transaction and the next message supplies another K1 member, this ADR **does not decide the acceptance rule**. The key still denotes K1, and the protocol must preserve the difference between a newly supplied part of one capture and a genuinely distinct observation K2.

## 5. Consistency with all accepted invariants

| Existing decision | Reconciliation |
| --- | --- |
| **ADR 0014 / GCTX-S01** | Ordinary file body archival excluded; retained commit/tree/tag and evidenced Git note content unchanged. Capture ID not a note-content authority |
| **ADR 0015 / B01-R01** | All observable `refs/notes/*` and explicitly nominated additional refs can be observed; neither ref discovery nor UUID assignment proves all notes were listed |
| **ADR 0016 / B01-R02** | Every independently genuine notes-ref observation has an immutable distinct capture identity, including repeated equal root. Same-capture replay does not create an invented observation |
| **ADR 0017 / KEY-P01** | **Direct semantic composite primary/foreign key; no additional receiver-local surrogate.** Issued UUIDv4 identifies real origin/capture occurrence and is not an arbitrary database-row convenience |
| **GCTX-M01** | Metadata-only Core works without Git object bytes, mandatory Context, hidden fetching or fake ref-root proof |
| **GCTX-M02** | Common Git nominal `(object_format, full_oid)` does not change; origin UUID and capture UUID are a different domain of identity |
| **GCTX-M03** | Typed scalar claims, capture-scoped ordered relation groups and unknown/partial/known-empty distinctions remain intact, no false grouping by root or transfer order |
| **GCTX-M04** | Receiver-verified canonical field interpretation remains distinct from source-reported/conflicting alternatives. UUID equality proves no field |
| **GCTX-M05** | Local Git verification and required capture provenance in Core; Provider assessment in Context, disposable retries in Operational |
| **GCTX-M06–M07** | Bounded verified representation admission and operation-scoped actual byte checks for retained allowed bodies; capture token alone proves no CAS or Git OID |
| **GCTX-M08–M09** | Independent immutable physical copies and evidence-derived eligible-set selection unaffected; capture pair is never the physical CAS instance key |
| **ADR 0003 / CAS-41** | INSERT-only Git Core; no UPDATE/DELETE/REPLACE/GC; actual retained byte faults still follow CAS-41 active quarantine rules; metadata absence not corruption |
| **Other invariants** | Permanent repository UUIDv4, Source known-positive, Coverage five-column/latest-observation semantics, Unix epoch microseconds `_us`, NO_INDEPENDENT_PUBLICATION, Context durability, Core-only metadata backup, paired Core+Context full backups, ADR 0001 |
| **GCTX-M10** | Quarantine retirement/active count still unselected, unrelated to capture UUID generation |

This is a **capture-specific UUIDv4 issuance rule**, not an authorization to add issued UUID columns as surrogate keys to every Git, Context or Operational table. The general KEY-P01 prohibition remains repository-wide.

## 6. Future acceptance counterexamples (NOT executed)

1. Insert OP/K1 as a genuine notes-ref observation and reference it by a child table's two-column FK; no duplicate `notes_capture_id` integer/UUID exists.
2. Observe ref/root A twice independently with OP/K1 and OP/K2: preserve two immutable captures, not one content/root dedup.
3. Forward OP/K1 through catalogs X→Y→Z, resend via Z→X: same original portable capture key remains stable and no new capture appears solely due to retransmission.
4. Observe same ref/root under independently established OQ/K4: preserve an independent capture, and do not equate OQ with OP merely because names or endpoints match.
5. Reject or explicitly diagnose non-v4 UUIDs, invalid variant/length/encoding and mismatched canonical serialization under the eventual physical schema.
6. Supply OP/K1 with a different repository or ref/root from the previously accepted immutable K1. No UPDATE, REPLACE, silent coalescing, false successful replay or trusted sender marker.
7. Present a self-proclaimed verified Provider root with correct UUID pair but no bytes; retain only appropriately qualified report, not byte-verified canonical truth.
8. Let a local Git-only adapter originate captures with no Context or registered remote Provider IDs; the issued origin/capture pair and provenance remain Core-owned.
9. Recreate Operational/Search or restore a metadata-only Core: identities and valid accepted capture observations remain intact.
10. Crash/retry after generating an origin/capture token but before a durable accepted capture is established; do not silently fabricate a duplicate accepted observation on retry. ADR 0019 fixes monotonic immutable fact/group retries; precise first-admission and transaction fencing still require implementation design.
11. Attempt to use UUID sorting/receipt ordering to declare the current notes-ref root. This violates established provenance/read policy.
12. Inject a copied catalog with accidentally shared issuer state: independent captures must not be mislabeled as the same actual capture when conflicting keys appear. Exact clone-origin policy remains a separate implementation contract.
13. Supply partial mapping K1 and later more K1 members: ADR 0019 / B01-R04 admits compatible new typed immutable facts/groups under K1, deduplicates exact replay, and never modifies an already accepted group or invents K2.
14. Feed a note-to-file relation referencing a normal blob: no file-body archival occurs just because the note capture has a valid UUID pair.
15. Independently validated Git note bytes remain under CAS-41/physical instance checks; UUIDv4 is not a digest or a physical-health certificate.
16. Confirm capture identity does not choose resource defaults/counter mechanics, B03 exact completion evidence or GCTX-M10. Apply accepted B02-R01–R04 policy; resource implementation details are engineering work under ADR 0025.

## 7. Subsequent owner decisions: B01-R04 A, B01-R05 A and B01-R06 A accepted; B02-R04 A accepted by ADR 0025

[ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md) accepts **Option A**: compatible, source-attributed typed facts/coherent new immutable groups can be appended under the original capture UUIDv4 pair; exact repeated accepted facts are idempotent. Do not modify previously accepted groups, infer complete coverage by union, or replace conflicting claims. ADR 0020 / B01-R05 fixes separately attributed immutable competing member reports and derived conflicts; direct semantic keys are fixed by [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md). The original A/B/C comparison below is historical, not an unselected B01-R04 question.

**How should multiple partial deliveries, replay of accepted fragments and conflicting facts for the *same* `(origin_uuidv4, capture_uuidv4)` be admitted to append-only Core?**

- **A — Monotonic typed facts attached to one capture (recommended candidate).** Accept new compatible immutable member/evidence facts under the stable capture pair, deduplicate exact same facts, never rewrite previously accepted facts. Reject or explicitly surface incompatible claims; verify true capture provenance. Completeness is a separately justified scope-specific claim under B03, not a generic batch/Publication. Benefits: partial/out-of-order support and minimal new domain ID; costs: per-member semantic equality/conflict, read snapshot and late-input consistency protocols.
- **B — Single atomic frozen capture snapshot.** Stage incomplete messages outside authoritative Core and admit one fixed capture representation only when final/ready (or admit a deliberately partial frozen result and refuse later extension under the same key). Benefits: simple once-admitted immutability and dedup; costs: delayed partial Core usability and potentially rejecting genuine late-arriving same-capture evidence, contrary to the spirit of metadata-only acceptance.
- **C — Immutable named fragments within the same capture.** Each separately issued genuine fragment has its own domain-level identity/evidence under the parent capture, with out-of-order/idempotent fragment handling. Benefits: explicit transfer chunk boundaries and provenance; costs: additional justified domain identities, fragmentation/consistency and completion interpretation complexity. Fragments must not become a generic Publication or a storage-only surrogate.

ADR 0019 fixes B01-R04 Option A. Retain a stable capture identity across compatible partial deliveries; never mutate prior coherent groups, fabricate an independent capture for retry, silently overwrite contradictory evidence or use a generic successful batch seal. ADR 0020 / B01-R05 fixes conflicting member reports as immutable attributed alternatives; ADR 0021 / B01-R06 A fixes their direct semantic keys; B03 determines precise completeness evidence; ADR 0022 / B02-R01 fixes required structural role-evidence strength; B02-R02 configurable finite budget policy is fixed by ADR 0023; proof grammar remains open.

## 8. Design-only permissions and references

- Repository: https://github.com/TakashiSasaki/git-repo-db
- Owner choice: B01-R03 **D-1** in this conversation, succeeding ADR 0017's key policy and ADR 0016's immutable capture-per-observation requirement.
- ADR 0011 governance PR #52 remains proposed/unadopted.
- The full application-level Core remains append-only; no code, DDL, schema version, migration, owned runtime catalog, CLI, deployment, release or PR merge is authorized. The future examples are proposed acceptance criteria, not executed tests.
