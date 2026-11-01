# Coding agent guide

This guide applies repository-wide. Task specifications and agent handoffs are written in English; user-facing explanations may be Japanese. Read the [ADR index](docs/adr/README.md), then the relevant accepted decisions and their scoped supersessions. For ADR lifecycle/triage/numbering/retirement, follow the owner-accepted [ADR 0011](docs/adr/0011-adr-governance.md) and single [ADR operating policy](docs/adr/policy.md); the optional [adr-workflow skill](.agents/skills/adr-workflow/SKILL.md) contains procedures, not additional authority. The policy's bounded pre-adoption migration exception preserves still-binding ADR 0001–0027 clauses; no automatic bulk retirement or re-opening of accepted design decisions.

## Current development phase

This is currently a single-user project in active prototyping. **No formal release
is planned for the foreseeable development period; release preparation is outside
the current development scope.** Do not impose release-only qualification, tests
or CI as development completion or merge gates, or run them unless the owner later
explicitly requests release preparation. Existing release procedures remain dormant
reference material. Preserve functional, consistency and safety tests/CI, focused regressions,
artifact isolation and relevant packaging checks required by the particular change;
these correctness checks are not release-only merely because releases also use them.
This applies the development/release distinction in ADR 0001 and the owner's
2026-11-01 project-stage instruction; it does not disable existing development CI.

Prefer simple solutions over
backward compatibility: old helper interfaces and workflows may change incompatibly
when useful; document the changes. Zero-downtime documentation publication and
simultaneous availability of every generated icon are not requirements. Revisit
these preferences if the project's users or deployment needs change.

Preserve source and user-data integrity, unrelated work, historical evidence and
meaningful verification. ADR 0035's product/documentation separation and accepted
architecture and retirement decisions remain binding. These preferences do not
authorize destructive operations, security-setting changes, merges or deployments.

For documentation content refresh, see [documentation/AGENTS.md](documentation/AGENTS.md#content-structure-and-refresh).

**Owner priority:** minimize avoidable token consumption and duplicate local or
offline CI work. Apply the [efficient agent execution policy](#efficient-agent-execution).

## Architecture orientation

- [ADR 0037](docs/adr/0037-operation-scoped-module-independence.md) and its
  [operation contract](docs/architecture/module-independence-contract.md) are the
  accepted module/install target. [ADR 0038](docs/adr/0038-scoped-recovery-and-optional-initialization.md)
  replaces retired 0026: Git-only activation requires no Operational/Search
  initialization; paired recovery is unchanged. These are targets, not implemented
  distribution guarantees.

- [Accepted design](docs/adr/0029-independent-access-store.md) defines five responsibility stores: Core, Context, Access, Operational and Search. This is a target boundary, not a count of databases opened by every startup.
- The normal catalog path uses the implemented Core Schema 21, Operational 1 and Search 1; see [schema factories](src/repo_catalog/adapters/sqlite/schema.py) and [catalog initialization](src/repo_catalog/adapters/sqlite/store.py). P1 is opt-in: its [four-store factory subset](packages/core/src/repo_catalog/adapters/sqlite/p1_schema.py) and separate [Access factory](src/repo_catalog/adapters/sqlite/access_schema.py) do not by themselves describe normal startup.
- Reports must state what is counted (responsibility stores, factory entries, schemas, files or open connections), the source SHA, startup path and unverified scope. Do not equate these units.
- Use the [task-oriented ADR index](docs/adr/README.md) and [documentation workspace](documentation/README.md). Authoritative contracts and machine inputs must track product changes; derived human documentation follows product work and does not block routine product checks ([ADR 0035](docs/adr/0035-independent-documentation-workspace.md)).

## SQLite validation

Follow [ADR 0032](docs/adr/0032-environment-sqlite-validation.md): use the SQLite
actually loaded by the execution environment's Python, one version per environment
for both development and release; local and hosted versions may differ. Never
download/build/install/swap SQLite just for tests, require a SQLite version matrix,
or gate startup on an exact version/source ID. Record actual runtime identities.
Preserve product capability/WAL safety floors, integrity/schema/transaction checks,
independent review, wheel/sdist checks and failure reconciliation. If the runtime
is insufficient, report failure and unexecuted work without bypassing guards.
Report reason/scope and obtain explicit owner approval before any exception.

**Local environment:** use the verified project environment from
[docs/local-python.md](docs/local-python.md) for every product validation. Establish it with
`./scripts/setup-local-python.sh`, run commands through `scripts/local-run.sh <command>` (or
`.venv/bin/python`), and never use the system Python/SQLite, an unverified `.venv`, or a
bare `uv run` without that environment. If setup, `local_env.py verify` or preflight fails,
report the failure; do not bypass it, delete an incompatible `.venv` silently or substitute another runtime.

## CPU architecture validation scope

During ordinary development (including feature PRs, local tests, development CI,
and independent development reviews), verification on **one available CPU
architecture** is sufficient. Do not require x86_64/aarch64 parity, a
cross-architecture test matrix, or an x86_64 local-bootstrap end-to-end run as a
development acceptance gate when another available architecture has passed.
Existing hosted CI runners may use x86_64; that fact does not designate x86_64
as a supported release target.

**Release targets are undecided.** At explicit release planning, the owner selects
the CPU architectures to support. Require architecture-specific release
validation only for those selected targets and report any unverified target as
an outstanding release gap; do not silently imply support. Preserve ADR 0001's
independent local **and** hosted release-acceptance requirements and exact-tree
evidence, without imposing identical CPU architectures across environments.
This policy changes hardware-platform validation scope only: accepted software
architecture decisions, SQLite/WAL safety floors, authorization, data integrity,
and other product safeguards remain binding.

## Product and authorization

**Shared time and Exchange integrity contract: [ADR 0028](docs/adr/0028-classified-times-and-sha256-exchange.md).** SHA-256-only Exchange compares a declared canonical-data digest with receiver recomputation; no HMAC/signature/PKI or sender-authentication claim. Cursor SHA-256 is a checksum with independent content validation. The original task authorized shared opt-in time/DDL/fingerprint corrections to P1–P4; that historical authorization does not grant permission for later tasks. Public Schema 21 stays default. Preserve historical evidence and independent P5/P6 sibling implementation dependencies.

**Accepted ref-observation origin policy: [ADR 0036](docs/adr/0036-ref-observations-and-shared-notes-mappings.md).** Preserve unauthenticated attributed reports without PKI; issuer identity does not prove authenticity or local verification.

**Latest accepted corruption recovery: [ADR 0038 / GCTX-M10](docs/adr/0038-scoped-recovery-and-optional-initialization.md).** Detected corruption of retained authoritative data immediately enters catalog recovery mode and stops ordinary service, writes, workers, Exchange and normal backups. No per-object quarantine flag, active set/count, release or retirement lifecycle belongs to the new target. Preserve the suspect source read-only; explicit diagnostic/salvage reads serialize untrusted candidates. Restore a revalidated backup into a fresh destination (paired Core+Context for full scope), revalidate/merge only admissible typed units, validate and activate the result. Do not require a write into the damaged Core to stop, continue via I2, trust recovered flags/rows, resume after Operational loss or complete a normal known-corrupt backup. Preserve source evidence without importing damaged copies into active Core or altering/deleting the source. Core remains INSERT-only; genuine replay/conflict, metadata-only, identity, notes-role, Source/Coverage and actual-work rules remain. Former M10 A/B/C disposition options are superseded; detailed mechanisms are engineering work. No implementation, real recovery or merge.

**Latest accepted request scope and owner correction: [ADR 0025 / B02-R04 A](docs/adr/0025-cumulative-request-budgets-and-scoped-blockers.md).** One explicit acquisition request accumulates actual work across continuations/resumes/retries; automatic retry does not reset it. Deliberate finite increases and genuinely separate explicit requests remain possible. Resource defaults, units, settings, counters and progress/resume mechanics are agent-owned engineering choices under accepted policy, not an endless series of owner blockers. No new numeric defaults are selected. Identify a concrete unresolved persistent meaning/trust/backup outcome and the affected dependent stage before calling work an architectural owner blocker. GCTX-M10 is now fixed by ADR 0038's stop/salvage/fresh-restore/validated-merge workflow; its details are engineering work, with other independent design work unaffected. No implementation or merge.

**Latest accepted notes resource accounting: [ADR 0024 / B02-R03 A](docs/adr/0024-actual-notes-resource-work-accounting.md).** Charge actual input/verification, metadata/relation and proof work. Reprocessed deliveries cost work again despite idempotent Core insertion; safe reuse does not invent another full-body charge, while real lookup/relation/proof work still counts. Failed/rolled-back processing does not erase work already performed. Preserve finite configurable raw-note/aggregate/proof limits, local structural/body checks, actual-output integrity and immutable Capture/semantic keys. Operational owns scoped progress; no Core counter/success ledger, new capture for retry, free sender-verified reuse or physical-health inference. B02-R04 A / ADR 0025 fixes cumulative request scope; counter units/defaults and resume mechanics are engineering work, not owner blockers. Other proof/completeness work remains scoped separately; GCTX-M10 recovery follows ADR 0038. No implementation or merge.

**Latest accepted notes resource policy: [ADR 0023 / B02-R02 A](docs/adr/0023-configurable-finite-notes-resource-budgets.md).** Use explicit finite configurable defaults/limits for individual raw-note size, aggregate operation bytes/work and structural-proof traversal. At a limit, preserve independently admissible metadata/complete atomic units, withhold oversize/unproven bodies and unfinished units, and report the actual stop without truncation, false completeness, hidden durable staging or a false corruption/recovery trigger. Deliberately higher finite settings permit retry with actual original Capture/provenance and semantic keys; never rewrite facts/groups, weaken B02-R01 checks or delete already admitted bytes after a lower setting. B02-R03 / ADR 0024 fixes actual-work accounting. B02-R04 A / ADR 0025 fixes cumulative request scope; numeric defaults, counters and resume mechanics are engineering work without further owner gating. Exact notes grammar/completeness remain separately scoped work; GCTX-M10 recovery follows ADR 0038. No implementation or merge.

**Latest accepted note-body role evidence: [ADR 0022 / B02-R01 A](docs/adr/0022-receiver-verified-notes-role-admission.md).** Before retaining a note blob, require the receiver's checked captured-root/tree-to-target-to-note structure under supported notes semantics plus exact body format/OID/type/size/digest checks. A source report, trusted source, ref prefix, decoder or sender verified flag is insufficient. Preserve admissible metadata without durable unproven-body staging. Check only the needed mapping scope; no full enumeration, target-body acquisition, invented commit for a direct-tree root or mandatory live fetch. Structural proof does not authenticate ref freshness/origin or prove physical health now. Preserve immutable scoped evidence, semantic composite references, alternatives and existing admitted bytes. B02-R02 configurable finite budget policy is fixed by ADR 0023; B02-R03 actual-work accounting is fixed by ADR 0024; B02-R04 cumulative request scope is fixed by ADR 0025; remaining budget details are engineering work; exact proof grammar and B03 remain unfinished; GCTX-M10 recovery follows ADR 0038. No implementation or merge.





**Latest accepted repository-wide key policy: [ADR 0017](docs/adr/0017-domain-keys-without-storage-surrogates.md).** Use real domain keys and full composite FKs; prohibit storage-only surrogates. RefObservation uses the ADR 0036 direct UUIDv4 origin and UUIDv7 observation pair.

**Accepted ref observation identity: [ADR 0036](docs/adr/0036-ref-observations-and-shared-notes-mappings.md).** Distinct genuine reads have distinct keys; replay preserves the original. Immutable subject and result claims are separate. Retain independently attributed conflicting known targets or comparable present/confirmed-absent results with explicit conflict, never rebind evidence. Share mapping content without merging original claims or receiver verification.

**Latest accepted notes-ref discovery: [ADR 0015](docs/adr/0015-automatic-git-notes-ref-discovery.md).** Enumerate observable notes namespaces and explicitly nominated refs. A listing alone proves neither body eligibility nor remote completeness; source and scope evidence follow ADR 0036.

**Latest accepted product scope: [ADR 0014 / GCTX-S01](docs/adr/0014-history-and-notes-catalog-without-file-archive.md).** `git-repo-db` is a Git history/structure/notes catalog, not a repository-file-content archive. Do not offer ordinary blob-body storage as a default, option, generic CAS endpoint or hidden staging/search/cache feature. Retain commit/tree/tag metadata and their actually acquired exact representations, and retain evidenced Git notes content. Notes are native Git blobs; retention is purpose-bound, not `type != blob`. Annotating or tagging an ordinary blob never authorizes storing its target body. Metadata-only operation remains valid with zero raw bodies and no Context. Do not infer a digest, object size, raw serialization, current availability or verification from an OID or relation alone.

Retained metadata/notes still require strict verification and physical integrity. GCTX-M01–M09 and retained-byte/backup integrity remain binding in that domain, scoped by ADR 0014 and ADR 0038. ADR 0038 retires CAS-41's quarantine state/count/pre-diagnosis comparison from the new target format while preserving actual database, manifest, domain and pairing validation. A scope-excluded file body is neither corruption nor a preservation job. Known loss of previously admitted bytes is not normal omission. No existing catalog data is deleted by this redesign; any fresh-format extraction/migration and treatment of legacy retained data require explicit authorization. The [transition plan](docs/architecture/git-core-context-transition-plan.md) is the current implementation planning entry point.

The **implemented** normal format remains Catalog3 Core Schema 21, Operational Schema 1 and Search Schema 1; accepted targets include the five-store boundary in ADR 0029 and ref-observation design in ADR 0036. Adoption does not activate or prove implementation. Preserve historical evidence and the Publication-independent reconstruction in its unsuperseded scope.

The developer documentation site is https://git-repo-db.moukaeritai.work/ and publishes from `main` under the existing explicit allowlist.

The project is unreleased and has one developer. No old database, internal API, CLI or migration compatibility is required. Preserve Git history and other agents' uncommitted work. **Permissions come from the explicit current owner task**, not this file or an older prompt. Create commits/branches/PRs only within that scope. Merge only specifically authorized PRs after required validation; otherwise do not merge `main`. An authorized merge does not authorize release, deployment, tagging, force pushes, bypassing branch protection, retained-catalog mutation or authenticated live collection. Use disposable synthetic state; stateful CLI commands require an explicit disposable `--state-dir`. Never commit real catalogs, credentials, private content, caches or raw authenticated traffic.

## Decision authority

Apply explicit owner decisions first, accepted ADRs and scoped replacements next, then unsuperseded production contracts and historical evidence. Preserve Q01-B/Q02-B/Q03-B, NO_INDEPENDENT_PUBLICATION, unaffected PF-P01–PF-P17, ADR 0001, ADR 0029, ADRs 0004–0010 and 0012–0017, accepted ref-observation ADR 0036, receiver body proof ADR 0022, finite budgets ADRs 0023–0025 and corruption recovery ADR 0038. No ordinary file-body archive or silent integrity repeal. ADR 0011 governance remains binding. ADR 0030 adds typed Context Repository relations and bounded selective Exchange without mapping Witness storage; its Context decisions are distinct from Access Scope decisions.

The source `schema_sql()`, `operational_schema_sql()` and `search_schema_sql()` plus generated DDL fingerprints identify the implemented formats. Hardcoded labels, old prompts and focused green checks do not prove current runtime acceptance. Three-store separation was integrated through PR #39; five-store/metadata-only and this product scope remain target decisions; ADR 0029 acceptance does not activate the Access runtime. No generic result/batch/bundle/member-seal owner or eligibility layer may recreate Publication. Local revision, per-object atomicity, domain scope completeness and installation readiness have independent responsibilities.

For documentary status, read the [Phase 2 decision register](docs/phase2/decision-register.md) and [status audit](docs/phase2/documentation-status-audit.md) subject to the ADR 0014 override. Historical "Selection paused" or blanket "Q05–Q12 resolved" cannot override scoped explicit decisions. Separate accepted target, implemented behavior, verified behavior and unresolved design. Dated plans are not orders to repeat completed work. CAS-76/CAS-77 remain deferred identifiers needing original-source clarification, not guessed requirements.

## Architecture and domain invariants

- **Five stores:** Git Core is authoritative for permanent repository identity, attributed Git metadata, history/structure/notes, actual observations and allowed retained metadata bytes. It is application-level INSERT-only: no UPDATE, DELETE, REPLACE, mutable progress/revision or in-place repair loopholes. Context independently owns durable PR/Issue/comment/review/Source/Provider state, its text/evidence/conflicts; it is not disposable. Context may reference Core, never the reverse for Core validity. Access separately owns durable Scope identities, locator registrations, connection settings and local approvals under ADR 0029; losing Access does not erase Core/Context history. Operational and Search remain reconstructible. Full Context-containing domain backup includes Core and Context with their consistency evidence; Git-only backup is labeled as such, and Access backup scope is explicit and separate. Neither domain backup is a full file-content repository backup under ADR 0014.
- **Layering:** dependencies remain `cli -> application -> domain/ports`; adapters own SQLite, Git/HTTP and filesystem operations.
- **Schema:** `adapters/sqlite/schema.py` composes packaged production DDL, including generated JSON guards. Initializer, writers, readers, Exchange, maintenance and installed distributions use exact fingerprints. Fresh format only; no compatibility shim.
- **Connections:** enable foreign keys and recursive triggers. Use SQLite snapshots/savepoints and OS `locks/writer.lock`. Do not use immutable connections against mutable catalogs or hold a write transaction over network work. Roll back intended units on body/constraint/COMMIT failure.
- **Identity:** service, repository and Source-registration UUIDv4 are portable; local Source IDs differ. Names/URLs do not merge identities. Explicit equivalence/cancellation assertions do not rewrite facts or coverage. `repository_uuidv4` is permanent.
- **Time:** follow [ADR 0028](docs/adr/0028-classified-times-and-sha256-exchange.md): Unix epoch microseconds with `_us`; observation/acquisition/Provider times are NULL or strict integers 1..int64-max, required Coverage/terminal coordinates are positive nonnull, native Git author/committer/tagger times remain signed int64 (including zero/negative). Classify by meaning, not store or caller flag. Keep generic signed conversion separate. Never coerce bool/float/numeric strings, fabricate unknown time, or order NULL/incomparable candidates by arrival; preserve missing versus explicit null and original retry/Exchange times. Durations/offsets/counts are separate. SQL storage checks do not prove pre-affinity input types.
- **Provider state:** PR attributes, natural-key title/body/conversation documents, independent threads and known Source roster retain latest accepted state with necessary current-field provenance. No normalized full API edit history. Missing differs from explicit null; inherited fields keep original clock/capture/module/version. Genuine equal/incomparable-clock alternatives stay unresolved.
- **Issue/review identity:** ordinary Issue identity is service/provider ID, independent of repository membership/number. Review identity is PR/kind/provider document ID. Transfers preserve capture. Detached captured IDs may survive Exchange without invented registrations; verify relationships when present. Receiver-local checks advance only on accepted authoritative live acquisition with pre-request revision/scope fences, never sender checks.
- **Documents:** use `(change_request_id, kind, provider_change_request_document_id)`. Exact UTF-8 SHA-256 identifies domain text. No document surrogate/version table or duplicate PR title/body authority.
- **Coverage:** exactly five claim columns and explicit typed ownership. Latest observation's candidate set determines complete/partial/unknown/conflict; no fallback to older complete. Details are advisory. Individual resources remain usable when a larger list fails. Empty terminal differs from no terminal; nested required-child and exact head/base evidence must be truthful. Metadata/notes inventory, allowed-body presence and file-content restorability are different scopes; no relabeling a stronger old completeness claim.
- **Source associations:** known positive pairs only. Partial inventory R1 cannot delete known R2. No new negative membership or deletion policy.
- **Context anchors:** retain actual provider events and minimal head/base/role anchors. Current head B cannot borrow A's assessment or require the whole old PR as provenance.
- **GCTX-M01–M03:** metadata-only Core needs no bytes/rehash/Context. Use one nominal full `(object_format, oid)` identity; neither identity nor shared references imply membership, actual bytes or canonical facts. Preserve potentially conflicting field-level claims and coherent observation-scoped ordered relation groups. Keep unknown/partial/known-empty distinct; do not union parent/tree groups, invent raw offsets/ordinals or update prior reports on later arrival.
- **Notes:** Preserve actual ref, typed root, annotated target, note OID, path, original claims and receiver evidence under ADR 0036. Direct-tree roots, binary/empty notes, unknown targets, independent namespaces and shared nominal OIDs remain supported. Never propagate note-body permission to the target file, collapse namespaces onto target alone, truncate content, infer canonical mapping from a flag or erase earlier ref history. Notes are a Git blob role, not a native type. Discovery follows ADR 0015, verified role and exact-body admission ADR 0022, finite work ADRs 0023–0025, and corruption recovery ADR 0038. B03 completeness and exact proof grammar remain open.
- **GCTX-M04–M06:** retain explicit decoder provenance, canonical verified values only for actually checked fields, conflicting reports and historical admission evidence. For allowed exact metadata/notes representations, check Git format/OID/type/size and physical digest, install intrinsic structure atomically and retain bounded immutable proof. An earlier unverified type/size/parent claim cannot poison later valid bytes. No preferred decoder, generic success ledger or sender-verification laundering. Core owns Git checks/evidence; Context owns Provider assessment; Operational owns Jobs.
- **GCTX-M07–M10:** in ordinary sound-catalog operation, preserve metadata-only/historical read tiers, evidence-derived candidate selection and actual selected/emitted-byte checks. Detecting corruption stops ordinary use of the affected catalog under ADR 0038. No quarantine state/count/release lifecycle, same-suspect-DB failover, required diagnosis INSERT before entering recovery, automatic restart after lost progress, byte overwrite or trigger bypass. Preserve source/incident evidence read-only; fresh verified restore plus validated salvage merge supplies a new operational catalog. Finding I2 or retiring I1 never clears the source stop. Copy identity/evidence distinctions remain, without requiring damaged I1 in the new active Core.
- **Transport:** no required API originals/replay. Normalize accepted partial GraphQL requirements/continuations/targets in memory. Reject opaque Provider replicas and hidden original-bearing pending/job JSON. Optional external recording/warning failures are nonfatal with bounded allowlisted diagnostics.
- **Body retention/CAS:** ordinary file-body archival is excluded by ADR 0014; allowed commit/tree/tag/notes bodies and Context text keep their domain boundaries. Preserve actual-byte/domain checks and database/manifest/identity/pairing validation before activation under ADR 0038; do not complete normal backup/restore with known damaged retained bodies. Quarantine counters and their comparison/order are historical format evidence only, with no new-format counter or legacy-compatibility obligation. Forensic preservation and untrusted typed salvage are separately labeled. Validate fresh Core-only or paired Core+Context destinations before consistent activation; never overwrite or purge the suspect source. No physical source cleanup, new Core GC or reinterpretation of intentional nonacquisition as corruption.
- **Exchange:** resolve typed resources/dependencies from a consistent snapshot. Envelopes/idempotency records do not own domain validity. Preserve genuine missing/conflicting candidates, reverse/repeat/late promotion/onward export without invented closure or provider authenticity. Validate retention purpose before accepting body-bearing entries; don't reintroduce ordinary file contents through staging or decoded text. Metadata-only exchange never needs fake payloads; sender checks are not local authority.
- **Revision:** implemented `local_revision` is the receiver-local counter and `advance_local_revision` replaced mechanical publication. The target must replace this mutable Core counter with an append-only-safe/fenced design. No counter-history table or sender-revision freshness import.
- **Jobs/caches:** freeze Source registrations and nonsecret settings. Resolve credential references at resume. Operational/cache loss cannot invalidate admitted facts. For allowed body-dependent work, require genuine safe fetch or reuse-unavailable, not a fabricated observation; ordinary metadata queries never hydrate content. No long-lived hidden file archive.

LFS objects and ordinary LFS pointer file bodies are outside new file archival; genuine supplied LFS/attachment metadata and existing Context evidence keep their meaning. Automatic external body fetching, broader deletion propagation, transport archive retention and CAS-76/CAS-77 remain deferred. Context-only GC-01/GC-02 remain; GC-03/GC-04 are not decided and never apply to accepted Git Core facts.

## Implementation, review and acceptance

For substantial architectural changes, fix owner decisions in a focused ADR/design PR, then implement coherent stacked PRs only when authorized. Independent subagents and executable counterexamples are permitted. The four-scope review requirement applies to the large Schema 20 redesign and tasks explicitly requiring it, not automatically to a prose fix. Reviewers must not approve their own production changes. Fix root causes, add regressions and re-review material findings.

### Efficient agent execution

**Development versus release:** run risk-relevant focused local tests, expanding by dependency and correctness risk rather than demanding full suites after every edit/PR. Ordinary development CI uses inexpensive static/lint/format/configuration checks and smoke tests, inspecting local evidence and reporting gaps without automatically duplicating a full locally verified suite. A green development run means selected checks passed, not full runtime acceptance. Only explicit user-invoked release validation requires full independent pytest locally AND hosted CI, isolated wheel/sdist packaging, schema/integrity checks and exact test-node reconciliation. Release validation itself authorizes no release, deployment, tag or merge. Preserve meaningful behavior tests; retire obsolete mechanism assertions only with explicit replacement-node mapping. Report versions, failures, skips, exclusions and unexecuted tests.

- Choose each run to answer a concrete unresolved question. Use the existing CI
  planner, input bindings and execution records across **all triggered workflows**;
  do not create a second selection policy or duplicate evidence ledger.
- Repeat a completed cohort only for changed relevant inputs, unresolved risk,
  incomplete evidence, or required independent/release verification. For prose or
  evidence-only followups, verify unchanged relevant inputs instead of rerunning
  tests; identify the original execution SHA and do not claim fresh execution.
  After a setup failure, rerun affected failed/unexecuted scopes, preserving
  successful unrelated evidence and the original failure record.
- Prepare the verified environment and actual offline dependency/build inputs
  before a long run. Keep cache settings consistent with setup and reuse only
  complete, hash-validated immutable artifacts. Never gain speed by hiding
  failures, weakening checks or skipping required independent verification.

**Token-efficient investigation:** Coding agents MUST minimize text consumed by model context while preserving complete evidence on disk. This applies to tests, CI, source reads, tool discovery and status checks:
Read only decision-relevant fields or excerpts. Success normally needs status,
counts, reconciliation, source binding and evidence paths; do not repeatedly dump
full profiles, journals, PR bodies, tool catalogs or unchanged documents.
Expand diagnostics only for a concrete unresolved question. Redirect raw JSON,
full logs and receipt/Base64 payloads to files, then select needed fields/ranges.
If output is truncated, narrow the query rather than merely raising its budget.

1. **Mandatory 5-step investigation sequence:**
   Escalate only as needed: a completed successful summary with known scope and
   source binding ends the investigation; later steps apply to failures or
   unresolved results, not every successful run.
   - *Step 1 (Summary):* Run `scripts/ci_query.py summary <evidence_dir>` or inspect the 1–2 line machine-readable terminal summary. Never ingest multi-megabyte raw logs into context.
   - *Step 2 (Failure counts):* Inspect failure counts and categories with `scripts/ci_query.py status <evidence_dir>`. Check total, passed, failed, and inherited vs unclassified counts.
   - *Step 3 (Bounded failure list):* Query only new or changed failures with a strict limit: `scripts/ci_query.py failures <evidence_dir> --new-only --limit 10`. Never query unbounded failure lists.
   - *Step 4 (Targeted traceback):* Fetch the exact traceback for an individual failing node: `scripts/ci_query.py failure <evidence_dir> --node <nodeid>`.
   - *Step 5 (Fallback raw log inspection):* Open raw logs (`invocations/*.log`) only when structured summaries and failure indices lack sufficient diagnostic detail. Use `scripts/ci_query.py filter-log <raw.log> -o <clean.log>` to strip large Base64 receipts before viewing. Use `scripts/ci_query.py extract-receipt <raw.log> -o <out_dir>` to unpack Base64 receipts directly on disk without expanding them into terminal text.
2. **Execution defaults:** Never run bare, unbudgeted pytest in agent sessions. Always use `scripts/ci_profile.py` or pass `--quiet` (`-q`) and worker budgeting (`-n auto` or `--max-workers`) through verified `./scripts/local-run.sh`. Non-test commands must not print "0 passed" test statistics.

Use one controlled workload at a time for comparable timing; concurrent timings are not sequential benchmark evidence. Keep historical reports and submit real dependencies/findings. Synchronize authoritative contracts and machine inputs with product changes; derived documentation follows independently under ADR 0035 and does not block routine product checks. Complete release acceptance still requires independent local and hosted product and documentation evidence. Named merges require authorization and independent integration-ancestry/effective-tree verification. ADR 0014 does not authorize any implementation, real-catalog extraction or data deletion.

At stable checkpoints, use existing timing/size summaries to identify the slowest
steps, repeated work and excessive output. Improve recurring causes within the
authorized scope and capture verified reusable lessons in existing helpers or
skills. Distinguish elapsed time from summed worker time, and output bytes from
measured tokens/billing; do not add heavyweight measurements or process gates
when existing evidence answers the question. Use
[efficient repository investigation](.agents/skills/efficient-repository-investigation/SKILL.md)
and [CI verification](.agents/skills/ci-final-tree-verification/SKILL.md) for procedures.
For explicit work start/pause/resume/end and external preparation, use the
stdlib-only `scripts/ci_timing.py` helper described in that verification skill.
Keep raw session timing local; declared active elapsed does not measure effort.

## Reuse lessons as repository Agent Skills

Repository-local skills live in `.agents/skills/<skill-name>/SKILL.md`, with YAML name/description and optional neighboring references/scripts. Discover/read only relevant skills at task start. Agents without discovery should inspect that directory. Skills are reusable procedures, not policy changes or execution permissions. When a skill conflicts with the latest owner-accepted design, proactively correct its current instructions within the authorized task branch; do not knowingly pass stale procedures to the next agent. Check scoped ADR supersessions, distinguish implemented-baseline diagnosis from target implementation, and preserve clearly labeled historical execution evidence. Include skill corrections in independent review and report them at handoff.

Actively capture a verified generalizable lesson from repeated root-cause failures, non-obvious independent-review findings or hard-won reliable procedures. Prefer improving an existing skill rather than overlapping skills. At stable checkpoints and handoff, use `$lessons-to-skills` to assess symptoms, root cause, verified fix, reproduction/check commands, applicability, counterexamples and source links. Favor deterministic helpers. If trial and error yields a verified procedure likely to recur, record it as an Agent Skill now, preferably by updating the matching existing skill. Document the failed symptom and cause, working procedure, reproducible verification, applicability and limits; do not leave reusable knowledge only in a conversation or task log. Avoid speculative recipes, one-off logs, unverified PASS claims, private data/credentials and converting open architecture choices into skill rules.

When authorized to edit the task branch, commit applicable skill updates with their correction or a dependent documentation PR. A read-only reviewer may recommend but not mutate the reviewed tree. Validate frontmatter, links and helpers; include skills in review/handoff. Do not create placeholders if no reusable verified lesson exists. See `docs/change-aware-ci.md` and the existing repo-local skills practice for CI selection. Accepted governance PR #52 does not authorize wholesale ADR retirement.
