---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0022-receiver-verified-notes-role-admission.md
  - 0014-history-and-notes-catalog-without-file-archive.md
  - 0019-monotonic-notes-capture-fact-admission.md
  - 0021-direct-semantic-notes-claim-group-keys.md
---

# ADR 0023: Configurable finite budgets for Git notes body admission and proof work

- **Decision ID:** B02-R02; **owner selected Option A**, accepted 2026-10-15.
- **Direct base:** [PR #63 / ADR 0022](https://github.com/TakashiSasaki/git-repo-db/pull/63), verified HEAD `8bf737152033902063eac7513840a210c06bbfbb`, branch `codex/adr-0022-verified-notes-role-admission`. Direct documentation-only successor; no implementation or merge.
- **Inherited:** ADR 0014–0022, KEY-P01, GCTX-M01–M09 and strictly append-only Git Core. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1, unchanged. Design acceptance is distinct from implementation, executed product verification and merge permission.

## 1. Binding choice: configurable, finite resource envelopes

Use **explicit finite defaults and configurable finite limits** for notes acquisition/admission, covering all three dimensions:

| Dimension | Required protection; details still open |
| --- | --- |
| Individual note body | A bound on the exact raw note body size, applicable to empty/binary notes without text normalization; exact numeric default/configuration contract remains open |
| Total bounded acquisition operation | A finite aggregate bytes/work envelope so many individually small notes cannot create unbounded work; operation scope, units and shared/replayed-content charging remain open |
| Notes-role proof traversal | Finite structural-proof exploration/work, including unsuccessful or incomplete searches; precise units/charging and numeric defaults remain open |

Configuration may deliberately raise a finite limit and permit retry under the revised finite envelope. A hard-coded product-wide size ceiling with no configurable increase (prior Option B) and an uncapped note-size mode relying only on streaming/system failure (prior Option C) are **not selected**. Streaming can be an implementation technique but cannot replace the selected bounds.

This decision fixes the **policy shape**, not numeric values, a settings format, zero/disabled semantics, resource counter storage or a new format version. Do not infer that an omitted setting, zero or a retry silently means unlimited. Exact configuration validation, effective-setting capture, operation/resume fences and resource accounting must be specified before implementation; no implementation may guess a bypass around finite limits.

The illustrative 8 MiB/128 MiB values in ADR 0022 were never adopted. No numeric default is adopted by this ADR either. A structurally valid oversized note is not an invalid Git object or an ordinary-file body merely because the configured budget prevents retention.

## 2. At a limit: exact content, honest availability and atomic units

At any applicable limit, withhold the oversize body, unproven body or unfinished atomic unit and report the actual resource stop/availability. Preserve **independently admissible metadata and already complete admissible atomic units**; resource exhaustion is not permission to alter their meaning.

- Never truncate a note and claim its original OID, retain only a prefix as if it were the exact annotation, invent a successful body check, or normalize binary bytes to make a body fit.
- A sender's reported size can support cautious planning only with its original qualification. It does not prove the actual byte length or validation result. A streaming stop must not fabricate the unobserved remainder, digest or verified size.
- Preserve GCTX-M03 atomic group visibility. An unfinished coherent group cannot appear as complete; do not split/re-key it arbitrarily, append into an earlier frozen group, or union accepted fragments into an unsupported complete listing.
- A stopped notes/ref/proof traversal proves neither absence nor an empty/complete inventory. Existing five-column/latest-observation Coverage and B03 evidence requirements remain binding.
- An unacquired/withheld body has no damaged retained instance. Do not create physical quarantine or lower/raise CAS-41 counts merely because a budget was exhausted. Actual loss/corruption of admitted bytes retains its physical meaning.
- Do not durably save an unproven/unfinished note body in pending Exchange, Operational retry state, Context text, Search, logs, quarantine, base64/compressed fields or long-lived caches. Bounded temporary-buffer lifetime/disposition remains part of the explicit acquisition protocol, not a new product archive.

The resource report can describe what work stopped and what was actually accepted without turning every failed/successful attempt into a permanent Core event. Operational owns work/progress/retry state. Core retains only its actual eligible immutable domain facts and indispensable admitted-byte/physical evidence; Search remains derived.

## 3. Retry and configuration changes do not rewrite Git facts

An explicit configuration increase permits a later attempt to satisfy the same immutable factual obligations; it does not guarantee success or waive B02-R01 structural role proof and exact body validation.

1. Preserve actual `(capture_origin_uuidv4,capture_uuidv4)`, original source/ref/root and semantic assertion/group identity. Retrying an existing Capture is not a new genuine observation. If the source is genuinely observed anew, use the established new-observation identity rules instead.
2. Previously accepted exact facts replay idempotently. Later eligible facts/evidence are new immutable units under ADR 0019–0021, never an UPDATE/DELETE/REPLACE, mutable `complete` flag or group extension.
3. Preserve the applicable effective settings/scope sufficiently for truthful work reporting under Operational's existing role. Detailed retry counter carry/reset/reuse accounting and resume fences are still open, not authority for silent budget resets or fake Capture IDs.
4. A later lower limit cannot delete admitted note/proof bytes, revoke historical checked structure, disguise retained-byte loss as intentional omission or trigger Core GC. New admission eligibility and existing historical preservation have distinct responsibilities.
5. The acquisition policy does not silently weaken backup/restore guarantees for data already admitted. If a backup/export/restore cannot satisfy its own required scope/resources, report that outcome honestly; never silently omit retained data and claim a complete backup.

No mutable Core configuration/counter, storage-only budget row ID, per-retry success ledger, universal admission seal or Publication is selected. Concrete settings/progress schemas remain future work under KEY-P01.

## 4. Worked examples

| Input and condition | Required result |
| --- | --- |
| Valid 20 MiB note; hypothetical configured raw-note limit is 8 MiB | Eligible metadata remains; no exact body admission or fake truncated note. These numbers are examples only |
| Explicitly raise that finite limit and retry with sufficient aggregate/proof budgets | Body may be admitted after all structural/body checks; exact earlier facts deduplicate and original Capture/group identity remains |
| 10,000 small proven notes individually fit, but aggregate operation budget is exhausted | Preserve complete admissible units and honest remaining availability; do not claim all bodies or all members were acquired |
| Notes proof traversal reaches its limit before the relevant mapping is established | Metadata remains useful; body withheld even if its standalone OID check could pass; no conclusion of missing/empty notes |
| One coherent group is unfinished when the work stops | No partial visibility as a complete group or arbitrary extension of a prior group |
| Same 2 MiB blob is referenced by 100 mappings or delivered again through Exchange | No duplicate nominal OID/domain fact solely for replay; precise budget charging is the next B02-R03 question, not fixed here |
| A previously retained 20 MiB note encounters a later 8 MiB setting | Keep historical admitted bytes/evidence; no deletion, false omission or quarantine reclassification |

## 5. Consistency with inherited decisions

| Decision | Preserved/refined consequence |
| --- | --- |
| ADR 0014 / GCTX-S01 | No ordinary file archive or hidden staging/search escape hatch; genuine notes remain purpose-bound, exact binary content |
| ADR 0015 / B01-R01 | Discovery includes all observable notes refs plus explicit additions; a resource-limited listing cannot imply global absence |
| ADR 0016/0018 / B01-R02/R03 | Genuine immutable observations remain distinct; retry preserves actual UUIDv4 pair and attribution |
| ADR 0017 / KEY-P01 | Semantic composite PK/FK; resource settings cannot invent a new authoritative surrogate |
| ADR 0019/0020/0021 / B01-R04/R05/R06 | Compatible append, exact replay, attributed alternatives, whole immutable group value and atomicity remain; no synthetic group split or winner |
| ADR 0022 / B02-R01 A | Both relevant receiver-verified structural role evidence and exact body checks remain mandatory; a larger budget is not permission |
| GCTX-M01/M02 | Core-only metadata needs no bodies, rehash or Context; common full typed OID never proves body presence/type/size |
| GCTX-M03/M04 | Typed atomic groups and truthful verified/report/conflict projections remain; no false closure or source/time winner |
| GCTX-M05/M06 | Core owns bounded immutable admission/physical evidence, Operational work; no per-attempt Core ledger |
| GCTX-M07–M09 | Check actual output bytes; preserve historical admission, immutable physical copies/diagnoses and evidence-derived candidates. Budget refusal is not physical corruption |
| Other fixed rules | Strict Core INSERT-only/no UPDATE/DELETE/REPLACE/GC, permanent repository UUIDv4, known-positive Source, Unix epoch microseconds, five-column/latest-observation Coverage, NO_INDEPENDENT_PUBLICATION, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, durable Context, paired full backup and ADR 0001 |

No prior accepted decision requires reversal. **B02-R02 A is accepted; resource units/counting and numeric defaults remain open.** Exact notes proof grammar, B03 completeness, origin trust, GCTX-M10 quarantine/count, settings/DDL/wire/fences/backup pairing and Context GC-03/04 remain unresolved. The implemented format is unchanged.

## 6. Future adversarial cases (NOT executed product tests)

1. Oversize valid binary/empty-note boundary cases preserve exact meaning, metadata and truthful availability; no truncated body/digest claim.
2. Many individually admissible notes hit the aggregate limit; no unsupported all-members/all-bodies completion claim.
3. A proof traversal stops before the mapping is established; verified blob bytes alone still cannot authorize retention.
4. Mid-group exhaustion/crash/retry never exposes a partial coherent group as complete or mutates the old group.
5. Higher finite settings allow explicit retry without a new Capture merely for replay, duplicate facts or relaxed body/role checks.
6. Lower settings preserve already admitted bytes/evidence, backup obligations and actual physical diagnoses; no Core GC or CAS-41 adjustment.
7. Reported size differs from observed bytes; do not fabricate verification or use claimed compression/size as a structural-role shortcut.
8. Resource stop leaves no durable unproven-body archive in retry/cache/Exchange/Context/Search paths.
9. Shared blobs and repeated deliveries preserve nominal identity, provenance and fact idempotency; test charging after B02-R03 is separately fixed.
10. Core-only metadata remains usable while Operational/Search are absent/rebuilt; no mandatory fetch, body or Context.
11. Budget exhaustion is distinct from actual retained-byte loss/corruption and source identity misuse.
12. Exact configuration/scope and retry accounting, once fixed, cannot be bypassed by silent resets, new fake capture keys or hidden unlimited settings.

## 7. Next owner blocker: B02-R03 resource measurement and shared/replay accounting (OPEN)

Before selecting numbers, **what does the aggregate budget count when one blob supports many mappings, proof dependencies are shared, or Exchange/retry repeats input?** Both options below retain B02-R02's finite configurable raw-note, aggregate-work and proof-traversal bounds. Neither is selected here.

Example: a 2 MiB N1 is attached to 100 targets. It may be read/checked once and reused, or arrive in 100 separate body-bearing messages. Both can represent 100 real mappings, but their actual byte-processing work differs. The same distinction applies to reused versus freshly read proof trees.

- **A — Charge actual bounded work (recommended):** aggregate byte/work counters reflect input actually read/decoded/checked and actual proof exploration. Sharing already checked data within the relevant coherent work scope does not pretend another full body read occurred; a newly read repeated body consumes work again even if its final Core insertion is idempotent. Keep an independent raw-note size limit. **Pros:** tracks resource cost, handles shared notes naturally, and does not treat SQL deduplication as free validation. **Cons:** exact work scope, units, reuse fences and retry carry/reset rules need precise definitions before numeric defaults.
- **B — Charge a conservative logical allowance for every mapping/delivery:** reserve a full relevant body/proof allowance for each reference/report even where implementation reuse avoids processing it again, while still bounding actual work. **Pros:** simpler conservative planning and less dependence on reuse optimizations. **Cons:** the single 2 MiB body may consume 200 MiB of logical allowance across 100 references; repeated metadata references can exhaust budgets despite little byte work, and proof-only work still needs explicit accounting.

Recommendation A chooses the basis of accounting, not free cross-operation trust or a complete counter protocol. Numeric defaults, precise counter units, parallel/resume boundaries, handling repeated independently attributable evidence and exact acquisition/proof grammar remain follow-up decisions. B03 and GCTX-M10 are not resolved by either option.

## 8. Authorization and verification boundary

The owner selected **B02-R02 A** after B02-R01 A. ADR 0022's B/C resource-policy alternatives are historical unselected choices. This is a documentation-only design PR, and the B02-R03 comparison is unaccepted.

No implementation, application source/SQL/DDL/schema labels, executable product tests, workflows/dependencies, live source acquisition, real catalog mutation/migration, deployment, release, merge or auto-merge is authorized. Static document checks and selected hosted development/documentation CI are distinct from product runtime/release acceptance. Future cases above are not executed tests. No independent review is implied; no new reusable skill is needed for this individual design choice.
