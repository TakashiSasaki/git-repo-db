---
status: proposed
date: null
replaces:
  - 0026-stop-salvage-restore-merge-after-corruption.md
refines: []
---

# ADR 0038: Scoped recovery completion and optional-store initialization

## Decision

**Proposed complete successor to ADR 0026, pending preservation review and explicit
owner acceptance.** `replaces` declares the intended transition, not an already
retired predecessor. ADR 0026 remains accepted and unchanged on this review branch.
The owner selected M-01/M-04 in the 2026-10-31 task; that selects Git-only availability
and deferred optional initialization, not approval of this complete successor text.

GCTX-M10 continues to mean stop, preserve, salvage read-only, restore a suitable
verified backup into a fresh destination, merge only receiver-validated typed
candidates, validate and safely activate. Only Git-only completion and O/S
initialization timing change in R5 and R6.9. All retained clauses below are intended
successor obligations, subject to the pending acceptance; later accepted ADR 0036
already governs observation/Claim/Notes semantics. The clause map identifies each
retained/changed family and all ten concrete verification cases.

## Constraints / Do NOT

Do not weaken any retained R1–R6 safeguard to satisfy installation independence.
Do not clear the original stop, repair/overwrite original evidence, omit necessary
WAL/journal state, reset work on continuation, treat salvage as a trusted baseline,
claim unavailable Context recovery, or apply Git-only optional-initialization to
paired recovery. Missing required validation capability means refusal, not omitted
validation or a diagnosis of corruption solely from missing code. No whole
Operational implementation is hidden in Core by this decision.

## Context & Reason

ADR 0026 §5 unconditionally says Search/Operational are rebuilt, and §6.9 includes
that obligation in activation verification. M-04 substantively changes those
obligations for Git-only recovery, so this is **replacement**, not additive
`refines`. Full ADR/Level 3 applies: availability, durable recovery safety and
activation guarantees cross module boundaries. The reason for the limited change
is to permit a complete safe Git-only lifecycle in the basic Core installation,
while retaining all authority/evidence safeguards and established paired scope.

[ADR 0037](0037-operation-scoped-module-independence.md) owns the module decisions;
the [operation contract](../architecture/module-independence-contract.md) owns
operation-level dependencies. Recovery obligations are carried here from ADR 0026
at `c2ae058b6402e0f5055c864fba1ed4ec7992a8aa`, with scoped updates already required by
ADR 0036. Historical alternatives, old authorization statements and provisional
blocker counts are not current rules. The old stale claim that ADR 0011 was
unadopted is not carried; current governance is accepted.

## Surviving recovery obligations

### R1. Failure scope and the operation that stops

The operating distinction is **ordinary operation → recovery mode** when authoritative corruption is detected. Do not first persist or manage an object/payload quarantine state, keep ordinary service running beside it, or require a quarantine INSERT to enter recovery. Recovery progress may have engineering substeps; there is no product/domain quarantine flag, active set/count, release or retirement lifecycle.

Detected corruption of retained authoritative data makes the **affected catalog suspect**. A mismatching stored body does not prove its stored digest, OID association, metadata, diagnosis rows, sibling copies or the rest of that database are intact. Successful SQL queries or a SQLite structural check do not establish all application content as trustworthy. Multiple BLOB rows in one database do not establish independent fault isolation.

Trigger the recovery workflow on a confirmed integrity failure of persisted Git Core or Context data, a database structural failure, or an authoritative-storage fault that prevents establishing the required integrity. Stop routine use of that catalog, including normal query/export success, writes, acquisition, Exchange admission/output, background workers and normal backup completion. A metadata-only query exemption is valid for a catalog in ordinary operation, not a way to continue serving a catalog after this stop condition.

Rejected malformed incoming data, attributed conflicting reports, intentional nonacquisition and resource-limit stops do not themselves diagnose damage in the authoritative database. Search/Operational failures retain their reconstructible-store treatment when the authoritative stores remain sound. Other independent catalogs are outside the affected catalog's stop scope.

The implementation must fence concurrent/in-flight users before claiming the catalog is frozen; do not publish unchecked results or keep committing after detecting the fault. Do not require a successful diagnostic INSERT into the suspect Core/Context to stop it. Preserve the observed failure and stop condition outside the suspect write path, with honest limits on the observation. Restarting the app, deleting Operational state or finding a usable sibling must not silently clear the stop. Precise coordination/restart mechanics are constrained engineering work, not another owner-option chain or a generic Publication authority.

Keep the actual detection/diagnostic evidence for investigation and truthful salvage reporting. Evidence that a fault was observed is not a mutable isolation status or permission to use the rest of the database. Recovery resumes service only by validating and activating the fresh restored/merged catalog; the old source remains preserved in recovery, without an "unquarantine" action.

### R2. Recovery sequence and admission boundaries

| Step | Binding behavior |
| --- | --- |
| 1. Stop and preserve | Take the affected catalog out of ordinary service. Preserve the source and incident evidence; do not repair, overwrite or purge it |
| 2. Read-only salvage | Permit explicit diagnostic/salvage reads of the frozen source or a preserved working copy. Serialize recoverable typed candidates and report unreadable/rejected/unknown scope |
| 3. Restore a baseline | Restore a suitable previously verified backup into a fresh destination/stage. Revalidate its actual contents and required Core/Context pairing before using it as the merge target |
| 4. Merge rescued candidates | Revalidate salvage input at the receiving domain boundary; admit only independently admissible facts, exact allowed bodies and complete atomic units, with existing replay/conflict rules |
| 5. Validate and resume | Validate the resulting candidate catalog and its truthful recovery scope; activate it consistently. Keep the original suspect source preserved and stopped |

Read-only means no application-authoritative changes to the original suspect database: no in-place repair, trigger bypass, diagnostic append, schema migration, revision change, checkpoint/VACUUM cleanup or repair-driven content replacement. The freeze/capture protocol must account for SQLite connection shutdown and journal/WAL effects rather than assuming a read-only SQL flag freezes every file. Preserve a coherent necessary database/journal/WAL set; copying only the main database can omit committed state. If an extraction technique requires changes, run it on a disposable copy of preserved evidence. Do not use `immutable=1` to pretend a live/mutable source is frozen. These requirements select no specific recovery tool or filesystem layout. See [SQLite WAL state and read-only access](https://www.sqlite.org/wal.html#the_wal_file).

Serialization is best effort. A failed page/table/range does not erase already rescued independent candidates, but missing or uninspectable scope stays explicitly unknown/incomplete. An unreadable database can yield no recoverable candidates; this does not permit fabricating an export. No working backup means this workflow cannot claim a restored operational catalog; preserve evidence and report the blocker rather than start normal operation from unverified recovered rows.

A fresh filename alone does not resolve an ongoing storage, memory or application fault. Use a suitable recovery environment and address continuing faults before activation; report unresolved integrity failures rather than repeatedly promoting newly damaged targets. Exact diagnosis and coordination techniques remain engineering work.

### R3. A salvage export is untrusted input

Keep a forensic preservation copy, a typed salvage serialization, and a normal verified backup distinguishable. A forensic image may contain damaged bytes and prior incident state; it is not a healthy restore baseline. A salvage serialization is a carrier of candidate domain data and recovery observations, not an authoritative success seal. Do not execute recovered SQL/schema/triggers as the destination's production definition or restore suspect internal tables wholesale.

SQLite recovery may lose, alter, resurrect or misplace records and violate constraints; a readable exported row is not sufficient admission evidence. [SQLite's recovery limitations](https://www.sqlite.org/recovery.html#limitations) support treating extracted data as candidates. The serializer/format must preserve its actual scope, typed values, provenance qualifications, dependencies and errors; exact wire spelling/tool selection remains engineering work.

| Candidate | Required receiving treatment |
| --- | --- |
| Nominal Git OID or metadata-only report | Validate typed identity and the claim's actual supported provenance; maintain reported/unknown/conflict qualifications. Parseability cannot authenticate its source or make it canonical |
| Retained commit/tree/tag representation | Recompute actual CAS and Git format/OID/type/size, parse intrinsic structure and install the justified facts atomically; do not import stored `verified` flags |
| Note body | Also re-establish ADR 0022's relevant structural notes-role proof; neither rescue origin nor a standalone matching body digest authorizes arbitrary file retention |
| RefObservation, original Claim or relation group; shared NotesMapping content | Apply ADR 0036: observation-scoped original Claims/Groups preserve their original origin UUIDv4 / observation UUIDv7 references, exact observation-result claim, immutable subject and full semantic evidence/group coordinates. Shared NotesMapping content retains its own full semantic identity (typed root, grammar/scope and mapping coordinates), not an observation-owned identity. Exact replay compares full payload. Retain genuinely distinct attributable comparable contradictions with derived conflict; reject reused immutable coordinates with incompatible values or subjects. Shared content never substitutes for exact-Claim proof |
| Context resources/text/associations | Apply existing identity, text digest, provenance, latest-state/conflict, known-positive Source and five-column Coverage rules. Missing rescue data is not a deletion or an empty complete inventory |
| Old success checks, local IDs/revisions, diagnoses or source-membership assertions | Do not promote them to receiver-local authority solely because they were recovered. Use only the independently supported domain meaning; uncertain evidence remains outside authoritative admission |
| Corrupt, incomplete or unproven body/unit | Exclude it from active-domain admission; preserve the source/forensic evidence and report the omission or rejection honestly |

The source of an uncertainty is itself important: a suspect DB's row claiming "provider S said X" is not automatically genuine S evidence. If original attribution or immutable identity cannot be supported, retain the recovery observation outside authoritative admission; do not fabricate provenance, mint a replacement observation or label it locally verified to make it fit. Valid actual Git bytes may justify their own checked intrinsic facts without proving an unrelated repository/ref/source assertion.

**Current origin-policy authority:** [ADR 0036 D1/D2/D6](0036-ref-observations-and-shared-notes-mappings.md#d6-exchange-query-coverage-backup-and-failure)
permits supported original external attribution as an **unauthenticated report**,
without mandatory PKI, signatures or an issuer registry. Preserve acquired
signature-bearing Git bytes without claiming authenticity. An unsigned otherwise
valid original report can be re-admitted with its qualification; a suspect row's
altered/unprovable original identity or attribution is not thereby admissible.
Neither parseability nor replay authenticates the issuer, validates all salvage
or permits fabricated provenance. The retired Capture identity and blanket
same-key root-rejection rules of ADRs 0018–0021/0027 are not revived.

Use typed Exchange/domain admission semantics for the merge, including dependency checks and transactional visibility of each coherent unit. Do not create a generic recovery-bundle owner that grants domain validity. One bad candidate need not discard independent admissible units; rollback the affected unit and report partial results. Preserve original source clocks/observations when justified; rescue time, arrival order and the backup's age select no winner. Receiver-local freshness and Provider assessments still require their established authority/fences, not a copied sender flag.

Ordinary file-body exclusion, binary-exact notes, no hidden unproven-body staging and B02-R02–R04 finite actual-work policies apply to typed salvage output/admission. Preserving the pre-existing suspect files for investigation does not create a generic file archive or permission to publish their contents. Resources/restart details are engineering work; a limit cannot truncate a body, invent complete coverage or reset a resumed request's actual cost silently.

### R4. Backup/restore validation without a quarantine lifecycle or count

Normal backup completion and ordinary restore activation require the relevant structural, schema, identity, referential, exact retained-byte/domain and snapshot/pairing checks to pass. They do not promise unknown facts, unacquired bodies or whole-repository file restoration. A backup file hash proves the copied file matches its manifest, not that every contained fact is correct. Revalidate a baseline rather than trusting only its age or a saved success flag.

Do not complete a normal backup from the stopped suspect catalog or accept a backup containing known damaged retained bodies as a normal operational baseline. Preserve such material as clearly identified forensic/salvage input. If a backup candidate fails validation, keep it out of service and try another suitable verified baseline; no source overwrite or disguised partial successful restore. A previously created known-corruption backup is not grandfathered into a healthy baseline by the old implementation's behavior.

**Scoped replacement of CAS-41:** preserve the safety purpose of validating the actual copied/staged database, manifest identity/digest, required pairing and domain integrity before activation. Retire the old active-quarantine predicate/count and its pre-diagnosis count-comparison requirement from the new target format. A new normal manifest does not require `quarantined_payload_count` or an equivalent isolation counter. No zero count, release/retirement record or sibling I2 can establish health or resume a stopped catalog.

Old count fields, ordering checks and their receipts remain historical format/implementation evidence, not a new-format compatibility obligation or current recovery gate. A legacy artifact's claims do not certify it as a healthy baseline; it remains subject to the selected restore validation. Do not reinterpret an unknown legacy field as zero or relabel old failed evidence as success. Historical fault observations may remain qualified evidence about their actual source, without creating a quarantine state in the recovered catalog.

If a staged destination fails validation, immediately keep it in recovery mode and preserve diagnostics outside its unsafe write path. No diagnostic INSERT, count update or per-copy state transition in that failed database is needed.

The former GCTX-M10 A/B/C question about continuing operation while I1 remains in the same active catalog is **superseded by ADR 0026’s already accepted stop/fresh-restore workflow, carried forward here**, not answered by adopting A, B or C. There is no isolation state, release/retirement mechanism or active-count question left to design for ordinary service. ADR 0036 now owns the surviving external-origin and observation policy; older blocker estimates are not approval evidence. Concrete paired-backup/recovery contracts remain engineering work within accepted guarantees; implementation mechanics and tunable defaults are not new owner blockers.

### R5. Append-only Core, independent Context and scoped supersession

The original suspect catalog and its bytes remain preserved read-only; this decision authorizes no deletion or alteration of that source. Within the fresh target, Git Core remains INSERT-only with no UPDATE/DELETE/REPLACE/GC, trigger bypass, mutable verified/active pointer or in-place repair. Recovery does not need to copy damaged/unprovable source units into the new operational Core merely to reproduce the original corruption. Omitted/unrecoverable scope must be reported; do not claim every former fact was recovered.

A full Context-containing recovery restores an appropriately consistent Core+Context backup pair and validates newly merged references before activation.
Context remains independently durable; Core never requires Context for fact validity.

**Paired scope retained:** Search/Operational are rebuilt from the recovered
authorities and valid configuration rather than trusted as salvage authorities
or reused for old leases/freshness. This established paired recovery obligation
is unchanged. This proposal grants no paired optional-installation exemption.

**Git-only change (M-01/M-04):** A Core-only recovery is explicitly Git-only and
cannot claim recovery of missing Context. Its complete lifecycle, including final
validation and safe activation, requires no concrete Context, Access, Operational
or Search implementation. Git-only Recovery implementation is included in the
basic Core installation. Git-only activation neither requires nor initializes or
rebuilds `operational.sqlite3` or `search.sqlite3`. It does not certify uninspected
Context. Preserve coexisting source Context and necessary journals/WAL as evidence;
Git-only scope does not authorize discarding them. Refuse unsupported paired or
Context input instead of silently dropping its scope. Use a fresh Git-only target;
no unvalidated coexisting Context is promoted into the activated catalog.

Optional capabilities are initialized when later explicitly enabled and needed,
under their existing rules. Exchange reception still requires explicit Operational
initialization; old request accounting, package bindings, leases and continuation
state are not restored. Search reads never create/repair a Search DB; explicit
index initialization/rebuild derives from recovered authorities. Package installation
alone mutates no catalog DB. Durable Recovery request/usage/reservation accounting
is independent of reconstructible Operational; reuse its semantics and fail-closed
loss behavior, never volatile counters or a renamed whole Operational product.
Shared locks and persistent stop fences remain available with Core.

This remains a stopped-catalog/fresh-destination workflow, not another authoritative
store. No new recovery format, data migration or Context-only lifecycle is selected.

| Prior rule | Current effect |
| --- | --- |
| ADR 0029 carry-forward of retired 0003, KEY-P01, GCTX-M01–M04 | Preserve append-only domain semantics, genuine identities, typed claims/groups and healthy metadata-only operation. Suspect-source read-only inspection is explicitly salvage, not normal canonical service |
| GCTX-M05/M06 | Preserve Git/Context/Operational ownership and bounded historic admission. Supersede any requirement to write a new fault into the suspect Core before stopping; preserve incident evidence outside that unsafe write path and re-admit only justified facts into the fresh target |
| GCTX-M07 | Actual-output checks still apply. Detected authoritative corruption now stops ordinary catalog operations; historical metadata exemptions do not bypass it |
| GCTX-M08/M09 | Preserve copy/identity distinctions and checked-byte candidate selection in ordinary sound operation. Remove per-copy quarantine flags, active sets/counts and release/retirement. Detection enters catalog recovery mode; no same-suspect-DB I1-to-I2 continuation or requirement to import damaged I1 into the recovered active DB |
| CAS-41 and old backup behavior | Preserve actual copied/staged database, manifest, domain-integrity and pairing validation before activation. Retire active-quarantine count/predicate/pre-diagnosis comparison in the new format; known-corrupt artifacts are forensic/salvage material |
| ADR 0014–0025 | Preserve retained-body scope, notes evidence, actual observation/semantic identity under ADR 0036, atomic groups, exact replay/conflicts, finite cumulative actual-work limits and engineering ownership of details |
| Other fixed rules | Permanent repository UUIDv4, classified Unix epoch microseconds under ADR 0028, known-positive Source, five-column/latest-observation Coverage, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, NO_INDEPENDENT_PUBLICATION and ADR 0001 remain |

This is an explicit owner-directed change of fault/recovery policy, including the clarification that a quarantine state is unnecessary. Earlier ADR examples requiring quarantine states/counters, continued metadata service, same-DB failover or normal known-corruption backup/restore retain historical value only where this scoped supersession applies. Product scope and ordinary fault-free admission/query rules are unchanged.

### R6. Future verification requirements (not executed product tests)

1. Detect a retained-byte mismatch or authoritative DB failure; immediately enter catalog recovery mode and fence ordinary readers/writers/workers without first creating a quarantine state or writing to the damaged store. Restart or Operational deletion cannot resume it silently.
2. Confirm malformed incoming input, genuine metadata conflicts, normal zero-body state, budget stops and reconstructible Search-only damage do not falsely diagnose authoritative corruption.
3. Freeze/preserve required journal/WAL state; salvage reads leave the original unchanged, including when opening/closing SQLite would otherwise cause side effects. Copy-based recovery tools cannot modify original evidence.
4. Encounter unreadable ranges and altered/type-confused/constraint-invalid recovered rows; preserve independent candidates and honest unknown scope, never promote all readable rows or execute recovered schema.
5. Restore and validate a fresh Core-only or paired Core+Context baseline; reject corrupt/mismatched/unsupported backups even when the file hash matches. New manifests require no quarantine count; neither a legacy zero count nor a retirement record can bypass actual validation. Preserve historical receipts as history.
6. Merge candidates with repeat/reverse/onward replay, missing dependencies, genuine conflicts, immutable subject/evidence-coordinate rebinding under ADR 0036, unknown provenance and mid-unit failure. Preserve original identities, idempotency and atomicity without automatic winner selection.
7. Reject corrupt/unproven bodies and excluded ordinary file data; independently verify allowed bytes, notes role and canonical intrinsic structure. Source `verified` flags/revisions/clock do not become local authority.
8. Admit partial valid salvage without inventing completeness or deleting known-positive associations. Core-only use remains possible with zero raw bodies and no Context after recovery validation.
9. Fail final validation/activation or interrupt recovery; keep source stopped and target out of service until valid consistent activation. For paired scope retain Search/Operational reconstruction; for Git-only scope complete activation with their code/DBs absent and initialize only when needed later. Never resume on the suspect source or silently overwrite it.
10. Keep actual recovery limits, gaps and checks distinct from "all data recovered" or eternal future health. Preserve forensic source retention without importing known bad copies into active Core or enabling deletion.


## Clause-level reconciliation of ADR 0026

Read paragraph coordinates within each numbered section of ADR 0026 at the pinned
base above. “Retained” means binding meaning carried here if accepted, not a claim
that implementation passed. R anchors identify the exact successor section.
Every retained row applies to both scopes unless its original rule is scope-specific.
Only rows explicitly marked changed alter Git-only completion; no row removes a
paired requirement.

| Effective predecessor clause | Disposition and exact surviving location | Git-only effect; paired boundary |
| --- | --- | --- |
| Header GCTX-M10 / owner clarification / authority and baseline | Retained meaning: Decision, R1, R5 and Constraints. Historical PR permission, obsolete governance status and old baseline implementation are provenance, not current authorization. | Same stop/fresh restore; normal Schema 21 unchanged. |
| §1 ¶1 ordinary→recovery; no quarantine/count/lifecycle | Retained: R1 ¶1 | No optional-module exemption from stop; paired unchanged. |
| §1 ¶2 suspect whole authority; SQL/structural checks/siblings insufficient | Retained: R1 ¶2 | No certification of uninspected T; paired unchanged. |
| §1 ¶3 stop triggers and all ordinary query/write/worker/Exchange/backup operations | Retained: R1 ¶3 | Global stop covers completion even for explicit single-authority reads. |
| §1 ¶4 malformed input/conflicts/nonacquisition/limits versus reconstructible failure | Retained: R1 ¶4; missing capability distinction in Constraints | Do not call missing T/O/S code authoritative corruption. |
| §1 ¶5 concurrent/in-flight fence; no unsafe diagnostic write; persistent across restart/O loss | Retained: R1 ¶5 | Fences stay with basic C; paired unchanged. |
| §1 ¶6 actual evidence; only fresh validated activation resumes | Retained: R1 ¶6 | Original source remains stopped in both scopes. |
| §2 steps 1–5 | Retained: R2 step table | No skipped preservation, baseline, typed merge or final validation. |
| §2 read-only paragraph: no repair/trigger bypass/diagnostic append/checkpoint/VACUUM; WAL/journal/copies/immutable misuse | Retained: R2 paragraph after table | Preserve original coexisting T evidence without promising interpretation; paired unchanged. |
| §2 best effort/unreadable scope/no working backup | Retained: R2 best-effort paragraph | No normal service from unverified salvage. |
| §2 continuing storage/memory/app faults | Retained: R2 final paragraph | Fresh filename is insufficient for either scope. |
| §3 forensic/salvage/backup distinction and no recovered schema execution | Retained: R3 first two paragraphs | Same receiver trust boundary. |
| §3 candidate OID / metadata | Retained: R3 candidate table row 1 | Typed identity, qualified supported provenance, no parseability trust. |
| §3 retained representation / note body | Retained: R3 candidate table rows 2–3 and ADR 0036 D5 | Recompute exact bytes/intrinsics and relevant role proof; no file archive. |
| §3 Capture/claim/group row | Already superseded identity/conflict wording by ADR 0036 D1/D2/D4; surviving rule: R3 candidate row 4 | Preserve v4-origin/v7-observation and exact semantic coordinates, distinct genuine contradictions; no revived Capture pair/root rejection. |
| §3 Context resources/text/associations | Retained: R3 candidate row 5 | Applies to supported T input, not new Git-only T admission; paired unchanged. |
| §3 old success/local ID/revision/diagnosis/membership / corrupt-incomplete-unproven units | Retained: R3 candidate rows 6–7 | No imported local authority; exclude unsafe units, report omissions. |
| §3 unsupported attribution / intrinsic byte facts versus unrelated source assertions | Retained: R3 paragraph after table, current RefObservation vocabulary | No invented provenance or replacement observation. |
| §3 subsequent 0027 clarification | Already superseded by 0036 D1/D2/D6; R3 current-origin paragraph | Qualified unsigned reports allowed, no PKI/issuer proof or arbitrary salvage trust. |
| §3 typed semantics, coherent units, independent partials, clocks and assessments | Retained: R3 “Use typed Exchange” paragraph | Reusing typed admission does not require high-level optional X; paired unchanged. |
| §3 file-body exclusion, binary-exact notes, finite actual-work and no hidden staging | Retained: R3 final paragraph; R5 durable accounting | No volatile/reset budget, truncation or false completion in either scope. |
| §4 normal structural/schema/identity/referential/bytes/snapshot/pair validation; hash insufficient | Retained: R4 ¶1 | Actual scope validated, no Context promise in Git-only. |
| §4 stopped backup/corrupt baseline refusal; try another verified baseline | Retained: R4 ¶2 | No working baseline → no operational restore. |
| §4 CAS-41 scoped retirement and historical count fields/receipts | Retained: R4 ¶3–4 | No count compatibility/relabeling; both scopes preserve actual checks. |
| §4 failed staged target | Retained: R4 ¶5 | Keep target stopped without unsafe diagnostic writes. |
| §4 former A/B/C and engineering ownership | Retained: R4 final paragraph, current 0036 reference | No reopening same-DB continuation; old blocker estimate not carried as approval. |
| §5 source preservation, Core INSERT-only/no GC/repair/mutable flags, honest omissions | Retained: R5 ¶1 | Same no destructive recovery rule. |
| §5 full paired baseline/references; independently durable Context; no reverse validity dependency | Retained: R5 opening and “Paired scope retained” | Paired still requires both authorities and optional-store reconstruction. |
| §5 unconditional Search/Operational rebuild; §6 case 9 rebuild | **Changed only for Git-only:** R5 “Git-only change”, subsequent optional-capability paragraphs; R6.9 | Git-only activation requires/creates neither O nor S; paired obligation retained verbatim in R5. |
| §5 scoped supersession table rows 1–7 | Retained: R5 table; retired 0003 now 0029, observation identity now 0036 | Preserves metadata-only, ownership, outputs, immutable copies, no I2 continuation, CAS-41 validation, notes and cumulative budgets. |
| §5 table final “Other fixed rules” and closing paragraph | Retained: R5 table final row and closing paragraph, plus ADR 0028 classified times | UUID, Source/Coverage, Q01/Q02/Q03, PF, no Publication and ADR 0001 retained; no global unqualified time rule overriding 0028. |
| §6 cases 1–5 | Retained: R6.1–5 | Stop/restart/classification, WAL/no source mutation, typed bad rows and verified fresh baseline rejection all remain. |
| §6 cases 6–8 | Retained with 0036 identity correction: R6.6–8 | Replay/reverse/onward/atomic failures, byte/role proof, partial scope and zero-body Core-only remain. |
| §6 case 9 | Changed Git-only O/S timing only: R6.9 and R5; retain all failure/no-publication/source safeguards | Paired reconstruction still required. |
| §6 case 10 | Retained: R6.10 | Report limits, gaps and evidence truthfully; no all-recovered/permanent-health claim. |
| §7 constrained engineering details and verification/authorization distinction | Retained: Consequences and References below | No old task's permissions transferred; current authorization is design only. |

## Consequences

Git-only recovery becomes available in a basic Core installation, with optional
capabilities initialized at use. Costs include separating R's authority-specific
validation, shared coordination and durable budgets from optional feature code.
Paired recovery and established optional-feature safety remain unchanged.

R6 cases are future acceptance requirements, not executed tests. Existing Recovery
implementation/tests and minimal future installation verification are mapped in
the operation contract; historical receipts remain evidence only of their original
trees. DDL, tools, serialization, stop fencing, journal capture, validation/activation,
pairing mechanics and defaults remain constrained engineering work. No real data,
source acquisition, implementation, runtime test, migration, merge or release is
authorized by this proposal.

**Pending transition:** independent preservation review must confirm this map and
complete successor; the owner must explicitly accept its full text and retirement
of 0026. Then, in a coherent acceptance/retirement commit under policy §6, set the
actual status/date/approval reference, remove 0026 and update the index, active
root/nested agent guides, applicable skills and effective normative references.
Inspect inbound links and plain-text obligations, including ADR 0029, ADR 0036,
selective Exchange, recovery/transition contracts and implementation navigation.
Use history-pinned links where original receipts refer to the predecessor; do not
rewrite evidence. No retirement or acceptance is performed in this draft PR and
no merge is authorized. The review branch's proposed exception is permitted by
policy §2; both conflicting records must not enter main as accepted.

## References

- [ADR policy](policy.md), [module decisions](0037-operation-scoped-module-independence.md),
  [operation obligations and implementation deltas](../architecture/module-independence-contract.md).
- Predecessor text pinned for reconciliation: [ADR 0026 at investigation base](https://github.com/TakashiSasaki/git-repo-db/blob/c2ae058b6402e0f5055c864fba1ed4ec7992a8aa/docs/adr/0026-stop-salvage-restore-merge-after-corruption.md).
- [Current observation/trust policy](0036-ref-observations-and-shared-notes-mappings.md),
  [five responsibilities](0029-independent-access-store.md),
  [classified times](0028-classified-times-and-sha256-exchange.md).
- Owner selections M-01/M-04 and authorization to submit design PR, 2026-10-31;
  full successor acceptance pending. Allocation checked with 0037 in the same PR.
