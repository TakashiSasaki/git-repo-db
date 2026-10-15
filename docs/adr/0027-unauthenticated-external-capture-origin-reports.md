---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0016-immutable-notes-ref-capture-observations.md
  - 0017-domain-keys-without-storage-surrogates.md
  - 0018-notes-capture-uuidv4-composite-identity.md
  - 0019-monotonic-notes-capture-fact-admission.md
  - 0020-immutable-competing-notes-member-claims.md
  - 0021-direct-semantic-notes-claim-group-keys.md
  - 0022-receiver-verified-notes-role-admission.md
  - 0025-cumulative-request-budgets-and-scoped-blockers.md
  - 0026-stop-salvage-restore-merge-after-corruption.md
---

# ADR 0027: Unauthenticated external Capture-origin reports without PKI or electronic signatures

- **Decision scope:** External Capture-origin admission, the origin-trust policy left open by ADR 0016/0018. This fixes that policy without claiming the entire B07 Exchange wire contract is implemented or finalized.
- **Owner choice:** **Option A**, accepted 2026-10-15, with the explicit instruction that this application does not use PKI or electronic signatures at present.
- **Direct base:** [PR #67 / ADR 0026](https://github.com/TakashiSasaki/git-repo-db/pull/67), live-verified HEAD `1a9fc10894d097d4af68f040155d85f8fe5b684d`, branch `codex/adr-0026-stop-salvage-restore-merge`. Direct documentation-only successor.
- **Inherited authority:** ADR 0014–0026, KEY-P01 and GCTX-M01–M09 remain binding. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1 is unchanged. This decision authorizes no implementation, source acquisition, actual recovery or merge.

## 1. Binding origin-report policy

An external observation may be admitted as an **unauthenticated attributed report** when its typed identity, immutable binding, supported reported provenance and other applicable domain checks pass. Issuer authentication is not an admission prerequisite. Preserve what the report claims about its original issuer and observation, with the qualification that the application has not authenticated that issuer. Do not assert that possession of an origin UUID proves who produced the observation, when it occurred, or that the named provider really supplied it.

For example, a file says that origin P issued Capture `(OP,K1)` and observed `refs/notes/review` at root T. The receiver may retain the qualified assertion as reported by that input. It does not thereby know that P made the observation or that the remote ref pointed to T at the claimed time. A well-formed UUID or many agreeing reports do not resolve this limitation. Spoofed origin claims can be indistinguishable from honest unsigned claims under this policy; the application makes no origin-authenticity guarantee.

The application currently has **no PKI or electronic-signature feature for issuer identity or observation authenticity**. Do not introduce issuer certificates, public-key enrollment, signature creation or signature verification as a requirement or a hidden follow-up blocker. A future authenticity feature requires an explicit new policy decision. Ordinary transport/access configuration is outside this decision; it does not redesign HTTPS or credentials. Preserve exact acquired Git representations, including any existing signature-bearing bytes, without treating their presence as authenticated evidence. Required Git OID, CAS and text-digest checks remain; content digests are not issuer signatures.

**Provenance remains truthful rather than authenticated.** Keep the original reported issuer/source coordinates and their actual qualifications, and distinguish them from what the receiver directly observed or verified. A genuine local capture adapter may still issue its own UUIDv4 pair for its actual observation of Git/API input under ADR 0018; it must retain any underlying remote attribution separately. Merely forwarding or receiving another Capture is not a new observation by that issuer. No mandatory Context Source registration, raw API archive, per-receipt assertion ID or all-attempts ledger is introduced.

## 2. Identity, replay and conflict do not become trust shortcuts

Preserve the original actual `(capture_origin_uuidv4,capture_uuidv4)` pair, with both components version 4. External values are the report's claimed original pair, not proof of the issuer's identity. Forward the same qualified report without minting a receiver-local replacement Capture, changing its attribution, or adding transport/receipt details as semantic-key salt. A genuinely new observation still receives a genuinely new Capture under ADR 0018.

KEY-P01 and ADR 0021 still require direct semantic composite claim/group PK/FKs: Capture pair, actual typed slot, asserted value, original supported provenance and, for groups, full immutable asserted membership/scope. In this policy, supported provenance can be a **preserved unauthenticated reported attribution**; it does not mean certificate-backed issuer proof. Do not invent source coordinates, reinterpret a forwarding route as independent original evidence, or create a surrogate to conceal missing identity. Preserve qualifications without mutating a prior assertion or using a receiver-local `verified` flag as a key component.

Equal Capture UUIDs identify only a replay candidate. Exact full semantic equality deduplicates the same qualified assertion; a changed transfer path alone creates no new fact. An incompatible immutable origin/repository/ref/root/source binding fails closed as identity/provenance misuse, without overwriting accepted facts or silently selecting a sender. Different eligible member reports follow ADR 0020/0021's immutable alternatives and derived conflicts. Inadequate identity remains unadmitted; lack of cryptographic issuer proof alone is not such an identity defect under Option A. Detected misuse can be rejected, but this policy cannot detect every spoof that supplies an otherwise consistent report.

## 3. Receiver-local verification retains its exact scope

| Evidence or operation | What it may establish | What it does not establish |
| --- | --- | --- |
| External report with original Capture pair | An identifiable qualified reported assertion, eligible for metadata admission under existing rules | Authenticated issuer, remote observation time, current ref or canonical Git facts |
| Exact semantic replay comparison | Same full typed assertion and original reported provenance | Truth of the claim or independent corroboration |
| Checked commit/tree/tag bytes | Their checked intrinsic fields and relations for that exact representation | Unchecked provider statements, repository membership or remote ref freshness |
| ADR 0022 notes-role proof plus exact note-body checks | The relevant mapping relative to the supplied captured root and admissible exact note content | Who observed that root, whether a remote ref held it, whole-inventory completeness or unrelated claims |
| Backup manifest/file digests | The checked artifact binding and applicable validation results | Issuer authentication or blanket correctness of every contained statement |

Metadata-only Core, zero retained bodies and Context-independent reads/imports remain valid. PKI absence does not require fetching bodies to accept a report. Conversely, a trusted label, an unauthenticated report, UUID equality or a sender `verified` flag cannot replace receiver-local content checks. Retaining a note body still requires ADR 0022's relevant structural role proof plus exact format/OID/type/size/digest checks. No ordinary file-body archival, durable unproven-body staging, whole-inventory or target-body prerequisite is introduced.

Canonical projections remain field/group-specific and evidence-derived under GCTX-M04. Preserve reports and genuine competing alternatives; do not pick a winner by issuer name, receipt order, claimed timestamp, agreement count or decoder. Complete/partial/known-empty/unknown scope, atomic coherent groups and finite cumulative actual-work policies remain as accepted. Exact grammar, lossless encoding and enforcement are engineering work within those meanings.

## 4. Recovery is not origin authentication

Ordinary external reports and suspect-database salvage candidates share typed receiving-domain checks, but salvage also retains ADR 0026's corruption/uncertainty boundaries. A readable recovered row saying "provider P said X" is not automatically reliable evidence that the original report or its identity survived intact. Preserve omissions and uncertainty. Do not fabricate a Capture, claim provenance, execute recovered schema or import saved success flags to make a candidate pass.

Lack of a signature is not by itself a salvage rejection reason: an otherwise supported original **unauthenticated report** can be re-admitted as that same qualified report. Unsupported or altered original identity/attribution remains outside authoritative admission, with only the honest recovery observation preserved. This distinction requires no PKI proof and grants no license to treat every parseable recovered row as an admissible report. Valid actual bytes may independently support their own checked intrinsic structure, without proving unrelated origin/ref assertions.

Conflicting or invalid incoming reports do not themselves diagnose corruption in an otherwise sound catalog. Actual authoritative-storage corruption still immediately stops ordinary operation under ADR 0026: read-only preservation/salvage, fresh verified-backup restore, validated merge and activation. No quarantine state/count, same-suspect-DB continuation, known-corrupt normal backup, source overwrite or purge is reintroduced.

## 5. Consistency with accepted decisions

| Accepted scope | Preserved result |
| --- | --- |
| ADR 0014–0016 | History/structure/notes scope, namespace discovery and distinct genuine observations; reported origin is not body-retention authority |
| ADR 0017 / KEY-P01, ADR 0018–0021 | Actual two-UUIDv4 Capture and direct semantic claim/group keys; immutable binding, exact replay, attributed alternatives, no surrogate or fabricated provenance |
| GCTX-M01–M03 / ADR 0004–0006 | Metadata-only Core, common nominal full OID, typed scalar claims and observation-scoped atomic groups; no false completeness |
| GCTX-M04–M06 / ADR 0007–0009 | Reports remain distinct from locally checked intrinsic facts; Core owns Git verification, Context owns provider assessment, bounded immutable evidence remains |
| GCTX-M07–M09 / ADR 0010/0012/0013 | Actual selected/emitted-byte checks and physical-copy distinctions in sound operation; semantic or UUID equality does not prove physical health |
| ADR 0022–0025 | Receiver-checked relevant notes role and exact body admission, finite configurable actual-work accounting across request retries; routine mechanics are not owner blockers |
| ADR 0026 | Immediate catalog recovery, untrusted qualified salvage, verified fresh restore/merge and honest gaps; no quarantine lifecycle or damaged normal baseline |
| Other fixed rules | INSERT-only Git Core, independent durable Context with no required Core→Context FK, permanent repository UUIDv4, known-positive Source, five-column/latest-observation Coverage, Unix epoch microseconds, NO_INDEPENDENT_PUBLICATION, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, paired full backup and ADR 0001 remain |

No existing accepted identity or content-verification rule is reversed. Earlier statements leaving origin authentication unselected are refined here: **unauthenticated attributed reports are accepted, with no application PKI/signature feature at present**. Origin-authenticated admission Option B is unselected. Earlier alternatives and exact-revision execution evidence remain historical in their actual scope.

## 6. Remaining owner blockers and work boundary

**Estimated remaining architectural owner blockers: provisionally 0 in the current Git Core/Context migration scope, after this decision.** This is a scope-limited estimate, not a claim that implementation, protocols or validation are complete. No successor question is required merely to continue the design sequence.

- Notes proof/parser grammar, typed group/complete/partial/known-empty encoding, physical DDL, Exchange wire, actual clone/retry issuance mechanics, stop/read fences, paired-backup coordination and recovery serialization remain design/engineering work under accepted semantics. Independently producing origins must remain distinct; replay preserves the original pair. These mechanics do not reopen that policy or require an authentication system.
- Context GC-03/GC-04 and enhanced Exchange authenticity are deferred features, not prerequisites for this current scope. Existing accepted Context retention stays binding.
- If a concrete new conflicting persistent meaning, trust/admission authority or backup guarantee is found, state the affected dependent stage and conflicting outcomes. Ask the genuine blocker with a concrete example, choices, pros/cons and recommendation, and include the estimated remaining blocker count **with every question**, explaining any increase or scope change. Do not count ordinary defaults/algorithms or absence of implementation permission as architectural owner choices.

No implementation begins automatically when the estimate reaches zero. Implementation, runtime verification, actual recovery and merge remain separately unauthorized by this documentation task.

## 7. Future verification cases and actual check boundary

These are future product requirements, **not executed product tests**:

1. Admit a typed unsigned external Capture as an unauthenticated report without certificate/key registration or signature checks; never display its issuer as authenticated.
2. Forward/reverse/repeat the same qualified Capture and semantic claim/group: preserve original pair/provenance and deduplicate exact replay without receipt-based new assertions.
3. Reject inconsistent immutable Capture rebinding and insufficient identity without UPDATE/REPLACE or a surrogate; preserve separately attributable eligible competing member alternatives.
4. Supply valid report UUIDs and `verified=true` without relevant notes-role proof: metadata may remain qualified, but durable note-body admission is refused.
5. Verify exact notes structure/body relative to the reported root: only the checked intrinsic scope becomes canonical; remote issuer/ref/time and whole inventory stay unproven.
6. Preserve exact acquired commit/tag bytes containing signature material without asserting signature authenticity; digest and actual-output integrity checks still apply.
7. Re-admit a supported unsigned salvaged report with its original qualifications; exclude altered/unprovable identity, recovered verification flags and fabricated attribution. Report partial recovery honestly.
8. Distinguish a rejected incoming claim from actual authoritative corruption; the latter immediately enters ADR 0026 recovery without a quarantine state or same-DB failover.

Only this accepted design and its current-status/workflow-skill reconciliation are recorded. Local document/skill checks and selected hosted development/documentation CI are evidence about this PR's actual final tree, not the future behavior above. No application/SQL/schema/workflow/dependency change, real catalog inspection/mutation/recovery, source acquisition, migration, release, deployment, merge or auto-merge is authorized. Author consistency checks are not an independent review.
