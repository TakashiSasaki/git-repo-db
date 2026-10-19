# Selective multi-Repository Exchange: accepted boundary and implementation contract

Decision authority: [ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md),
Exchange Q-E1--Q-E10. Context keys/roles:
[Context Repository relations](context-repository-relations.md).
Baseline is PR #103 commit `1134e200eb4ac9ec45bf3fae3be695e2bb786a8d`.
This document defines the next design target, not features already present in v3.

## 1. Independent selections and bounded effective closure

Use distinct logical sets (wire names below are conceptual):

- R: explicitly selected permanent Repository UUIDs;
- O: explicitly selected `(object_format, full_oid)` pairs;
- C: explicitly selected Context Source/Resource/other supported typed subjects.

R, O and C are independent roots. For example, R={R1}, O={commit C}, and
C={PR P} is valid even where PR P has a head Repository other than R1. An empty
set is not the same as omitted/unrestricted selection; the wire version must
encode that distinction and require explicit opt-in before treating omission as
all. Do not silently export the entire Provider or every registered Repository.

Q-E4=C allows typed Git **metadata graph expansion**, not just nominal-OID
padding. Q-E5=C independently permits bounded Context expansion. A finite policy
specifies allowed edge kinds, directions, depths, units/bytes and actual-work
budget. Record requested roots, the effective included sets, reasons for closure
additions, reached limits and unadmitted/omitted scopes so a receiver can validate
what was sent. The particular ordering/default numbers are engineering choices;
use deterministic, cycle-safe traversal without a claim of unbounded closure.

Deduplicate nominal OIDs by their full typed key, never by raw hex alone. Keep
separately keyed attributed claims, complete relation groups, capture facts,
physical-copy identities and provenance. Two Repositories referring to one OID
are not one Repository. Adding a nominal OID does not prove possession of bytes,
Repository membership or complete history. Metadata-only Exchange is still valid.
Q-E4 does not authorize ordinary-file blob archival or auto-fetching unavailable
objects; allowed retained representations/Notes still require their established
receiver-local byte/structure checks.

## 2. Select facts without changing their meaning

| Domain unit | Selection and closure obligation |
| --- | --- |
| Repository registrations/claims | R and expressly permitted typed dependencies; keep original UUID and provenance |
| Capture/Git Observation | Actual Repository and Capture identity; selecting an OID does not manufacture an observation in R |
| Attributed OID scalar/group metadata | O plus admitted graph expansion, retaining original report boundaries and alternatives |
| Notes | Actual Capture/root/target/note and role-proof contract; never combine incompatible reports into a complete group |
| Coverage | Preserve original scope/time/state and exact proof/terminal/membership meaning; do not shrink a complete set while retaining complete |
| Provider/Source | Minimum valid registrations and selected Source scope, not every resource behind a shared Provider |
| Source membership | Selected positive pairs; omitted pairs are not negative membership evidence |
| Resources/relations | Selected C plus genuine required parents and allowed relation expansion; no fabricated parent resource |
| Resource--Repository relations | Six typed roles with exact keys/clocks/provenance; resolve dependencies only within permitted Repository scope |
| Mapping Dispositions | Exact target ClaimKey and, for correction, replacement ClaimKey; references must exist in receiver or admitted closure |
| Core reference | Preserve typed OID and provenance even where availability is unresolved under its actual contract; not Repository ownership proof |

A Source inventory originally complete for {R1,R2} cannot become complete for
{R1} because the caller selected only R1. A Provider registration shared by two
Sources does not automatically include both Source inventories. A PR referencing
an R2 Issue does not grant permission to register R2. Follow only typed, explicitly
allowed relations; arbitrary URLs/prose/JSON strings are not expansion edges.

For Transfer reports, the original one-sided/explicit-null/two-sided scope must
survive selection. Selecting only one endpoint from an inseparable two-sided
report does not turn it into an originally one-sided report. Include the legal
unit in full or report that unit unadmitted/omitted; retain independent valid data.
Source, OID group and Coverage completeness are distinct from package completion.

## 3. Receiver identity and registration

A receiver with initial seed R3 may import permitted R1/R2 using those UUIDs.
Do not rewrite its seed, `catalog_instance_uuidv4`, existing Core registrations,
Capture identities or Source memberships. Receiver Core/Context/Operational
pairing still must be checked; a cross-seed sender is not a broken receiver pair.
Context-local FK registrations and cross-file Core validation remain separate.

The receiver fixes an explicit permitted Repository set and all material request
semantics. A dependency edge is not permission to grow that set. Unknown permitted
UUIDs may be registered without minting replacements. Unpermitted references do
not trigger registration or Access approval. Unknown/unsupported input formats,
invalid original bindings, malformed data, digest failures and stored corruption
are not ordinary partial-dependency success.

## 4. Immutable package identity and canonical content

Q-E7=A uses:

```
PackageKey = (sender_catalog_instance_uuidv4, package_id)
PackageKey -> one canonical-content digest_sha256
```

Both are transport-envelope coordinates, not claim/Capture/Resource identity and
not sender authentication. Versioned canonical UTF-8 content includes envelope
metadata, selections and sections, excluding only the digest field itself as
specified by that version. Preserve canonical embedded `_json` values exactly;
JSON serialization escaping is not permission to alter their meaning or key.
Changes to package ID, export time, selection or body mean changed hashed input.
The hash is not merely a bag-of-domain-facts deduplication identifier.

| Presentation | Receiver meaning |
| --- | --- |
| Same PackageKey and same recomputed canonical digest | Exact package resend; eligible missing units may be retried |
| Known PackageKey with different digest | Reject content replacement, even if changed body is otherwise valid |
| Changed canonical content | Sender must issue a new package ID |
| Same domain fact in another package | Deduplicate/check using its actual semantic key and immutable payload |

Hash matches do not authenticate the origin, establish notes eligibility or
replace typed checks. A new package ID is not an automatic new work budget.
Do not introduce HMAC, PKI or signatures for this work.

## 5. Partial admission and stage receipts

Q-E6=B admits independent coherent units. A missing required FK withholds that
unit; a legitimate unresolved CoreReference may be retained only under the
separately supported reference contract. Never manufacture a Provider Resource
or change immutable group membership to satisfy an FK. Current candidates that
are stale by genuine source clocks are normally non-inserting outcomes, not
source corruption. Preserve equal/incomparable alternatives.

No durable staging store of unadmitted domain payloads is introduced. A result
can identify an unadmitted unit/reason for a later resend, but is not permission
to retain hidden full Provider responses or unproven Notes bodies. Dependency
ordering and retries are bounded, use original keys and consume actual work.

Record distinct outcomes such as committed, existing-validated, stale, missing
reference, outside permission, and unprocessed/interrupted. Outcome names are
engineering wire detail; none means Coverage complete or verified issuer.
Stage summaries must identify actual committed scopes and enough unit references
for an honest partial result. This is not a permanent per-fact audit subsystem.

Q-E9=B sequence:

```
validate bounded package and fixed receiver request
  -> atomically check/bind PackageKey and digest in Operational
  -> admit Core coherent units / commit
  -> record actual Core stage result
  -> admit Context coherent units / commit
  -> record actual Context stage result and partial/completed summary
```

No unrecorded package binding may be represented as recorded. Concurrency must
reject conflicting bindings atomically. Preflight/check work is still budgeted.
Core, Context and Operational do not gain a cross-file atomic transaction from
this sequence. On a crash between a domain commit and its checkpoint, inspect the
actual stored semantic facts; absence of a receipt does not prove absence of a
commit. Checkpoints never authorize deletion/rollback of committed Core facts.
Missing references may resolve later, so partial is not permanently unprocessable.

## 6. Operational absence, loss and explicit new requests

Q-E8=A deliberately limits persistence of PackageKey/digest history to Operational.
There is no extra durable Exchange Witness. The existing P5 request-issuance
witness mechanism remains distinct and must not be deleted or repurposed.

| Receiver condition | Permitted reception |
| --- | --- |
| Operational not initialized | No ordinary reception; explicit initialization is required |
| Operational healthy, old request binding/accounting intact | Resume only the exact frozen request and remaining cumulative budget |
| Operational lost/reconstructed | Old request cannot be continued as though its consumed work were zero |
| Explicitly reinitialized Operational and genuinely new request | May receive the same unchanged package against intact domain facts under a newly explicit finite budget |
| Old/incomplete Operational backup | Do not claim complete former accounting or package-binding history |
| Core/Context persistent recovery stop | Recreating Operational never bypasses the stop |

Q-E10=B selects explicit reinitialization, not automatic creation on reception.
A `new_request` boolean cannot reissue the old RequestIdentity. Restored/imported
old receipt flags do not authenticate facts. Strong historical ID-reuse detection
cannot be promised after the only package-binding records are lost. State that
limit explicitly instead of silently adding another durable store.

Charge actual decode/hash/check/relation work again when actually repeated,
even when domain insertion deduplicates or rolls back. Reuse may avoid work only
where it truly avoids it. Explicit new requests are deliberate new operations,
not automatic retries to evade exhaustion. Preserve all existing cancellation,
final-dispatch/completion, recovery and actual-work boundaries.

## 7. Original provenance, local effect and backup

Claims and Dispositions preserve their full semantic key, original observed time,
claimed issuer and replacement references on A -> B -> C forwarding. Sender and
receiver names, receipt times and local checks must not be appended to original
provenance. Exact replay compares payload as well as PK. A different genuine
report has a different genuine provenance; relay alone is not independent evidence.

There is **no Witness section** and no confirmation-history JSON hidden in another
section. B can re-evaluate a received withdrawal only with genuine evidence
actually available to B. A's prior evaluation, `source=local`, a shared Catalog
UUID, a checksum or an Access grant does not become B's local confirmation.
A source's original reported verification wording, where legitimately preserved,
remains attributed wording and not local authority.

Paired Core+Context backups include the two new durable tables and all their
required existing domain dependencies. Git-only backup makes no Context promise.
Operational/Search remain reconstructible and excluded from that domain backup;
Access retains its independent backup/approval contract. No aggregate five-store
atomic backup or copied approval is implied. With no Witness audit requirement,
restoration does not promise to recover unstored past check actions. A cloned
UUID or validated file hash alone does not authenticate local operations.

## 8. Engineering acceptance boundary

The implementation must specify its wire version, deterministic order, missing
versus empty filters, finite traversal policy, legal unit boundaries, full-domain
preflight and stage receipt encoding. It must integrate the new relation/Disposition
keys without weakening old byte/Notes/group/recovery checks. The baseline v3
`repository_candidates` format and single-seed receiver check are not evidence
that this contract is already implemented.

Do not infer additional policy decisions from placeholders in this document.
The staged work and required adversarial cases are in the
[implementation handoff](../implementation/context-exchange-design-handoff.md).
