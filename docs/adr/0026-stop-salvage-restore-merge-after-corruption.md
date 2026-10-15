---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0003-append-only-git-core-and-context-store.md
  - 0007-verification-aware-git-metadata-reads.md
  - 0008-domain-split-git-verification-ownership.md
  - 0009-bounded-byte-admission-and-physical-health.md
  - 0010-operation-scoped-cas-physical-integrity.md
  - 0012-append-only-multiple-cas-physical-instances.md
  - 0013-deterministic-cas-instance-eligibility.md
  - 0025-cumulative-request-budgets-and-scoped-blockers.md
---

# ADR 0026: Stop, salvage read-only, restore a verified backup, then merge validated recovery data

- **Decision ID:** GCTX-M10, resolved by immediate catalog recovery mode, with no separate quarantine state or lifecycle.
- **Owner instruction and clarification:** Detection of authoritative corruption immediately stops ordinary operation and enters recovery mode: preserve the source read-only, serialize/export what can be rescued, restore from backup and merge validated rescued data. A separate "quarantined" operating state is unnecessary. Accepted and clarified 2026-10-15. This changes the earlier fault-state/recovery policy; it does not authorize implementation or an actual recovery.
- **Direct base:** [PR #66 / ADR 0025](https://github.com/TakashiSasaki/git-repo-db/pull/66), verified HEAD `8cb70cd2c9a4ef2abbf6052ad9e5541a6c20c4ce`, branch `codex/adr-0025-budget-scope-blocker-triage`. Direct documentation-only successor.
- **Authority:** Preserve ADR 0014–0025, KEY-P01 and GCTX-M01–M09 except the explicitly superseded post-corruption behavior below. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1 is unchanged. Its digest-keyed quarantine, same-database repair, and known-corruption backup/restore behavior are historical implementation, not the accepted recovery target.

## 1. Failure scope and the operation that stops

The operating distinction is **ordinary operation → recovery mode** when authoritative corruption is detected. Do not first persist or manage an object/payload quarantine state, keep ordinary service running beside it, or require a quarantine INSERT to enter recovery. Recovery progress may have engineering substeps; there is no product/domain quarantine flag, active set/count, release or retirement lifecycle.

Detected corruption of retained authoritative data makes the **affected catalog suspect**. A mismatching stored body does not prove its stored digest, OID association, metadata, diagnosis rows, sibling copies or the rest of that database are intact. Successful SQL queries or a SQLite structural check do not establish all application content as trustworthy. Multiple BLOB rows in one database do not establish independent fault isolation.

Trigger the recovery workflow on a confirmed integrity failure of persisted Git Core or Context data, a database structural failure, or an authoritative-storage fault that prevents establishing the required integrity. Stop routine use of that catalog, including normal query/export success, writes, acquisition, Exchange admission/output, background workers and normal backup completion. A metadata-only query exemption is valid for a catalog in ordinary operation, not a way to continue serving a catalog after this stop condition.

Rejected malformed incoming data, attributed conflicting reports, intentional nonacquisition and resource-limit stops do not themselves diagnose damage in the authoritative database. Search/Operational failures retain their reconstructible-store treatment when the authoritative stores remain sound. Other independent catalogs are outside the affected catalog's stop scope.

The implementation must fence concurrent/in-flight users before claiming the catalog is frozen; do not publish unchecked results or keep committing after detecting the fault. Do not require a successful diagnostic INSERT into the suspect Core/Context to stop it. Preserve the observed failure and stop condition outside the suspect write path, with honest limits on the observation. Restarting the app, deleting Operational state or finding a usable sibling must not silently clear the stop. Precise coordination/restart mechanics are constrained engineering work, not another owner-option chain or a generic Publication authority.

Keep the actual detection/diagnostic evidence for investigation and truthful salvage reporting. Evidence that a fault was observed is not a mutable isolation status or permission to use the rest of the database. Recovery resumes service only by validating and activating the fresh restored/merged catalog; the old source remains preserved in recovery, without an "unquarantine" action.

## 2. Recovery sequence and admission boundaries

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

## 3. A salvage export is untrusted input

Keep a forensic preservation copy, a typed salvage serialization, and a normal verified backup distinguishable. A forensic image may contain damaged bytes and prior incident state; it is not a healthy restore baseline. A salvage serialization is a carrier of candidate domain data and recovery observations, not an authoritative success seal. Do not execute recovered SQL/schema/triggers as the destination's production definition or restore suspect internal tables wholesale.

SQLite recovery may lose, alter, resurrect or misplace records and violate constraints; a readable exported row is not sufficient admission evidence. [SQLite's recovery limitations](https://www.sqlite.org/recovery.html#limitations) support treating extracted data as candidates. The serializer/format must preserve its actual scope, typed values, provenance qualifications, dependencies and errors; exact wire spelling/tool selection remains engineering work.

| Candidate | Required receiving treatment |
| --- | --- |
| Nominal Git OID or metadata-only report | Validate typed identity and the claim's actual supported provenance; maintain reported/unknown/conflict qualifications. Parseability cannot authenticate its source or make it canonical |
| Retained commit/tree/tag representation | Recompute actual CAS and Git format/OID/type/size, parse intrinsic structure and install the justified facts atomically; do not import stored `verified` flags |
| Note body | Also re-establish ADR 0022's relevant structural notes-role proof; neither rescue origin nor a standalone matching body digest authorizes arbitrary file retention |
| Capture, claim or relation group | Preserve evidenced original UUIDv4 pair, immutable binding, direct semantic composites and full group scope/membership. Exact replay deduplicates; genuine conflicts follow ADR 0020/0021; incompatible Capture rebinding fails closed |
| Context resources/text/associations | Apply existing identity, text digest, provenance, latest-state/conflict, known-positive Source and five-column Coverage rules. Missing rescue data is not a deletion or an empty complete inventory |
| Old success checks, local IDs/revisions, diagnoses or source-membership assertions | Do not promote them to receiver-local authority solely because they were recovered. Use only the independently supported domain meaning; uncertain evidence remains outside authoritative admission |
| Corrupt, incomplete or unproven body/unit | Exclude it from active-domain admission; preserve the source/forensic evidence and report the omission or rejection honestly |

The source of an uncertainty is itself important: a suspect DB's row claiming "provider S said X" is not automatically genuine S evidence. If original attribution or immutable identity cannot be supported, retain the recovery observation outside authoritative admission; do not fabricate provenance, mint a replacement Capture or label it locally verified to make it fit. Valid actual Git bytes may justify their own checked intrinsic facts without proving an unrelated repository/ref/source assertion.

Use typed Exchange/domain admission semantics for the merge, including dependency checks and transactional visibility of each coherent unit. Do not create a generic recovery-bundle owner that grants domain validity. One bad candidate need not discard independent admissible units; rollback the affected unit and report partial results. Preserve original source clocks/captures when justified; rescue time, arrival order and the backup's age select no winner. Receiver-local freshness and Provider assessments still require their established authority/fences, not a copied sender flag.

Ordinary file-body exclusion, binary-exact notes, no hidden unproven-body staging and B02-R02–R04 finite actual-work policies apply to typed salvage output/admission. Preserving the pre-existing suspect files for investigation does not create a generic file archive or permission to publish their contents. Resources/restart details are engineering work; a limit cannot truncate a body, invent complete coverage or reset a resumed request's actual cost silently.

## 4. Backup/restore validation without a quarantine lifecycle or count

Normal backup completion and ordinary restore activation require the relevant structural, schema, identity, referential, exact retained-byte/domain and snapshot/pairing checks to pass. They do not promise unknown facts, unacquired bodies or whole-repository file restoration. A backup file hash proves the copied file matches its manifest, not that every contained fact is correct. Revalidate a baseline rather than trusting only its age or a saved success flag.

Do not complete a normal backup from the stopped suspect catalog or accept a backup containing known damaged retained bodies as a normal operational baseline. Preserve such material as clearly identified forensic/salvage input. If a backup candidate fails validation, keep it out of service and try another suitable verified baseline; no source overwrite or disguised partial successful restore. A previously created known-corruption backup is not grandfathered into a healthy baseline by the old implementation's behavior.

**Scoped replacement of CAS-41:** preserve the safety purpose of validating the actual copied/staged database, manifest identity/digest, required pairing and domain integrity before activation. Retire the old active-quarantine predicate/count and its pre-diagnosis count-comparison requirement from the new target format. A new normal manifest does not require `quarantined_payload_count` or an equivalent isolation counter. No zero count, release/retirement record or sibling I2 can establish health or resume a stopped catalog.

Old count fields, ordering checks and their receipts remain historical format/implementation evidence, not a new-format compatibility obligation or current recovery gate. A legacy artifact's claims do not certify it as a healthy baseline; it remains subject to the selected restore validation. Do not reinterpret an unknown legacy field as zero or relabel old failed evidence as success. Historical fault observations may remain qualified evidence about their actual source, without creating a quarantine state in the recovered catalog.

If a staged destination fails validation, immediately keep it in recovery mode and preserve diagnostics outside its unsafe write path. No diagnostic INSERT, count update or per-copy state transition in that failed database is needed.

The former GCTX-M10 A/B/C question about continuing operation while I1 remains in the same active catalog is **superseded by this accepted recovery workflow**, not answered by adopting A, B or C. There is no isolation state, release/retirement mechanism or active-count question left to design for ordinary service. Other genuine unresolved domain/trust/paired-backup contracts remain separately scoped; implementation mechanics and tunable defaults are not new owner blockers.

## 5. Append-only Core, independent Context and scoped supersession

The original suspect catalog and its bytes remain preserved read-only; this decision authorizes no deletion or alteration of that source. Within the fresh target, Git Core remains INSERT-only with no UPDATE/DELETE/REPLACE/GC, trigger bypass, mutable verified/active pointer or in-place repair. Recovery does not need to copy damaged/unprovable source units into the new operational Core merely to reproduce the original corruption. Omitted/unrecoverable scope must be reported; do not claim every former fact was recovered.

A full Context-containing recovery restores an appropriately consistent Core+Context backup pair and validates newly merged references before activation. A Core-only recovery is explicitly Git-only and cannot claim recovery of missing Context. Context remains independently durable; Core never requires Context for fact validity. Search/Operational are rebuilt from the recovered authorities and valid configuration rather than trusted as salvage authorities or reused for old leases/freshness. This is a stopped-catalog/fresh-destination workflow, not a fifth authoritative store.

| Prior rule | Current effect |
| --- | --- |
| ADR 0003, KEY-P01, GCTX-M01–M04 | Preserve append-only domain semantics, genuine identities, typed claims/groups and healthy metadata-only operation. Suspect-source read-only inspection is explicitly salvage, not normal canonical service |
| GCTX-M05/M06 | Preserve Git/Context/Operational ownership and bounded historic admission. Supersede any requirement to write a new fault into the suspect Core before stopping; preserve incident evidence outside that unsafe write path and re-admit only justified facts into the fresh target |
| GCTX-M07 | Actual-output checks still apply. Detected authoritative corruption now stops ordinary catalog operations; historical metadata exemptions do not bypass it |
| GCTX-M08/M09 | Preserve copy/identity distinctions and checked-byte candidate selection in ordinary sound operation. Remove per-copy quarantine flags, active sets/counts and release/retirement. Detection enters catalog recovery mode; no same-suspect-DB I1-to-I2 continuation or requirement to import damaged I1 into the recovered active DB |
| CAS-41 and old backup behavior | Preserve actual copied/staged database, manifest, domain-integrity and pairing validation before activation. Retire active-quarantine count/predicate/pre-diagnosis comparison in the new format; known-corrupt artifacts are forensic/salvage material |
| ADR 0014–0025 | Preserve retained-body scope, notes evidence, actual Capture/semantic identity, atomic groups, exact replay/conflicts, finite cumulative actual-work limits and engineering ownership of details |
| Other fixed rules | Permanent repository UUIDv4, Unix epoch microseconds, known-positive Source, five-column/latest-observation Coverage, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, NO_INDEPENDENT_PUBLICATION and ADR 0001 remain |

This is an explicit owner-directed change of fault/recovery policy, including the clarification that a quarantine state is unnecessary. Earlier ADR examples requiring quarantine states/counters, continued metadata service, same-DB failover or normal known-corruption backup/restore retain historical value only where this scoped supersession applies. Product scope and ordinary fault-free admission/query rules are unchanged.

## 6. Future verification requirements (not executed product tests)

1. Detect a retained-byte mismatch or authoritative DB failure; immediately enter catalog recovery mode and fence ordinary readers/writers/workers without first creating a quarantine state or writing to the damaged store. Restart or Operational deletion cannot resume it silently.
2. Confirm malformed incoming input, genuine metadata conflicts, normal zero-body state, budget stops and reconstructible Search-only damage do not falsely diagnose authoritative corruption.
3. Freeze/preserve required journal/WAL state; salvage reads leave the original unchanged, including when opening/closing SQLite would otherwise cause side effects. Copy-based recovery tools cannot modify original evidence.
4. Encounter unreadable ranges and altered/type-confused/constraint-invalid recovered rows; preserve independent candidates and honest unknown scope, never promote all readable rows or execute recovered schema.
5. Restore and validate a fresh Core-only or paired Core+Context baseline; reject corrupt/mismatched/unsupported backups even when the file hash matches. New manifests require no quarantine count; neither a legacy zero count nor a retirement record can bypass actual validation. Preserve historical receipts as history.
6. Merge candidates with repeat/reverse/onward replay, missing dependencies, genuine conflicts, invalid Capture rebinding, unknown provenance and mid-unit failure. Preserve original identities, idempotency and atomicity without automatic winner selection.
7. Reject corrupt/unproven bodies and excluded ordinary file data; independently verify allowed bytes, notes role and canonical intrinsic structure. Source `verified` flags/revisions/clock do not become local authority.
8. Admit partial valid salvage without inventing completeness or deleting known-positive associations. Core-only use remains possible with zero raw bodies and no Context after recovery validation.
9. Fail final validation/activation or interrupt recovery; keep source stopped and target out of service until valid consistent activation. Rebuild Search/Operational; never resume on the suspect source or silently overwrite it.
10. Keep actual recovery limits, gaps and checks distinct from "all data recovered" or eternal future health. Preserve forensic source retention without importing known bad copies into active Core or enabling deletion.

## 7. Authorization and actual verification boundary

Only this documentation decision, its current-status reconciliation and a focused existing workflow-skill lesson are authorized here. Exact DDL, tools, serialization, stop fencing, journal capture, validation/activation and paired-snapshot mechanics remain constrained implementation/design work. They do not call for repeated owner approval unless a concrete new policy conflict appears.

Static document/skill checks and selected hosted development/documentation CI on this PR are separate from the future recovery tests above. No recovery program, real catalog, database permissions, source acquisition, SQL/schema/application/workflow/dependency change, runtime recovery test, migration, release, deployment, implementation, merge or auto-merge is authorized. No live/source catalog data is inspected or changed by this design PR; author consistency checks are not an independent review.
