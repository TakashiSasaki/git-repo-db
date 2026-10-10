# Phase 1 decision: retire API-original capabilities

Status: accepted owner instruction, implementation pending in a stacked PR.
Decision date: 2026-10-10. This record authorizes implementation, commits and new
task-branch PRs, but not merge, main changes, deployment, release, or mutation of
retained user catalogs. Work and verification use fresh disposable catalogs.

## Actual baseline

Fetched `origin/main`: `47fd5b88355b98019c0c04408449081e16ab4505`, tree
`e7a41038e26eb93c89b921a9a9d0bf1d2c54a310`, Catalog3 schema 17. The starting
checkout was clean but stale (`7a35962`); implementation starts from fetched main,
which includes merged PRs #14–#18 and their independent corrections. There were
no open PRs at investigation start. The earlier `c8684c2` implementation head is
not the baseline.

This is the next bounded step toward the
[transport-independent core target](transport-independent-core-adr.md). It does
not assert that the entire target is implemented. The previous
[implementation boundary](transport-independent-core-implementation.md) documents
surviving historical publication, completeness, restart and exchange mechanisms.

## Settled retirement scope

| ID | API-original capability | Required outcome |
| --- | --- | --- |
| R1 | Parse a saved API response again after parser changes | Delete every retrospective API-to-domain parsing entry point and its exclusive dependency closure. |
| R2 | Recover previously unmodeled fields from saved responses | Delete speculative extraction surfaces; do not keep originals for future fields. |
| R3 | Replay saved API responses to rerun ingestion | Delete standalone/offline replay and its observation publication routes. |
| R4 | Manage original bytes as an archive/CAS | Delete exclusive archive registration/comparison/bookkeeping; narrow genuinely shared components. |
| R5 | Verify, quarantine or repair originals for later reuse | Delete API-only maintenance/recovery; preserve integrity of required domain content. |
| R6 | Save failed/rejected originals for delayed processing | Delete raw-response retry staging and exceptional-path retention. |
| R7 | Distribute originals for replay/reinterpretation | Delete standalone original distribution; explicitly identify retained domain-exchange proof dependencies. |

Optional transport recording and bounded display of captured diagnostic data may
remain outside the core. Calling a domain parser over an archived API message is
R1/R2 even if it does not publish. In particular, the current `reparse-message`
projection is within this retirement scope; `inspect-message` display is a
different function. No replacement archive, reader pipeline, flag, retry service,
surrogate JSON store, or compatibility shell may recreate a retired capability.

Live API parsing and genuine new remote acquisition remain supported. So do
search rebuilding from domain text, synthetic parser fixtures, and existing Git
domain processing and Git-only reanalysis. Retiring transport originals does not
delete required text or raw Git objects.

## Deletion boundary

Classify every affected dependency by real reachable consumers:

| Class | Action |
| --- | --- |
| A: retired-feature-only | Delete the code, schema and public/test/document contract together. |
| B: shared with a retained domain responsibility | Delete retired callers/branches and retain only the demonstrated responsibility. Semantic-preserving helper extraction/narrowing is allowed. |
| C: another supported capability needs an undecided replacement | Retain its narrow reachable boundary and document the exact caller, reads/writes, purpose, deletion consequence and next design decision. |

Historical PR-list proof construction, live collection restart and conditional
HTTP reuse are investigation seeds, not automatic exemptions. Their existence
does not excuse retaining offline replay, failed-original staging or standalone
original distribution. If part of R1–R7 cannot be separated without choosing a
new contract, report that part as remaining-shared/Phase-2; complete independent
removals. No dummy acquisitions, empty input manifests, fabricated observations
or weakened completeness guards are permitted.

## Preserved and deferred contracts

Preserve exact UTF-8/domain-text identity, SHA-1/SHA-256 Git object-format/OID
identity and required raw Git bytes. Preserve their hash checks, quarantine,
explicit atomic repair, backup/restore and CAS-41 guarantees. A physical digest
can be shared by API and Git references: a representation label alone never
authorizes deleting or refusing protection of its domain bytes. No retained-data
cleanup or GC is part of this task.

Preserve permanent repository/service/Source identities, typed ownership and
parents, signed int64 epoch microseconds, actual parser module/version and
per-field provenance, missing/null/empty distinctions, comparable-clock ordering,
unordered conflicts, Issue transfer capture and receiver-local checks. Keep all
merged independent-review corrections. Coverage retains exactly five claim
columns and the latest-observation-time candidate set, including unknown and
conflict; incomplete collections cannot claim completeness.

Do not choose resource lifecycles or retention durations, historical PR/Git
current selection, replacement domain batch/publication identity, normalized
collection completeness, provider-field inventories, HTTP cache/restart policy,
archive retention, content GC or exchange trust/ownership. The 18 historical
profile/publication/selection tables are not an unconditional DROP list: remove
only dependencies whose consumers are demonstrably gone. The application is
unreleased, so no old schema/CLI/API/wire compatibility is required.

## Scoped supersession of older contracts

Definitions below are checked against the current
[decision status](model-integration-status.md), not inferred from identifier names.
Historical reports remain immutable evidence. This record takes precedence over
older current-feature preservation language only within R1–R7.

| Previous rule | Retired mechanism | Preserved invariant / named later boundary |
| --- | --- | --- |
| D3: reparse identity separate from acquisition | API offline reparse and supplementary parser projection | Git acquisition/result identities remain separate. Live acquisitions keep truthful observation times. |
| D23: payload byte sharing is not observation identity | Archive-only byte registration/comparison | Shared domain bytes do not merge independent observations; legacy live publication inputs remain C where required. |
| D25: permanent independent parsed-result UUID | Retrospective API execution/publication | Existing historical/Git immutable result identities remain until domain publication/lifecycle replacement is decided. |
| D28: multiple owner-checked input references | Inputs used exclusively by API replay | Retained historical/Git result input ownership and sealed membership remain; normalized publication identity is deferred. |
| D29: direct parsed-result FK on generated facts | Replay-generated API facts | Preserve historical domain facts and existing atomic publication until replacement design. Current Issue/review attribution remains gate-free. |
| D31: exclusive repository/source result ownership | Replay-only ownership machinery | Preserve typed domain owners, Source inventory and XOR historical ownership where reachable. |
| D36: composite ownership constraints | Retired-original-only FKs/guards | Preserve Git, historical domain and current typed parent/owner integrity. |
| D37: separate source-owned acquisition evidence | Failed-original retention and saved-original retry | Successful live inventory publication remains C pending normalized inventory/field design. |
| CAS-3: portable self-authored JSON payload references | Reference vocabulary exclusive to retired originals | Retained typed Git/domain and legacy proof references remain validated; no dangling guards. |
| CAS-4: complete bytes in each exchange unit | Standalone original-byte distribution | Required domain bytes and currently inseparable historical proof closure remain, pending normalized exchange proof. |
| CAS-9: schema-aware evidence validation | Validators exclusive to retired scopes | Ownership/missing-dependency/conflict validation of retained records is preserved. |
| CAS-16: stage acquisitions blocked by corrupt bytes | Failed/rejected API original staging | Git/domain staging and existing corrupt content protection remain; no saved-original retry substitute. |
| CAS-42: 304 exchange includes original body evidence | Distribution for reinterpretation/replay | Exact live 304/domain-exchange proof boundary remains C until cache/reuse and normalized proof are decided. |
| CAS-44: include original acquisition owner context | Standalone original distribution context | Required retained historical capture/owner checks remain; do not weaken them. |
| CAS-46: partial collection dependency closure | Original-only exchange branches | Valid domain selection and exact completeness proof remain; replacement historical proof is deferred. |
| CAS-49: no unsupported completeness in partial exchange | Original replay as an independent feature | Preserve honest partial/unknown/conflict and sealed-member checks; normalized proof design remains open. |

The older claim that nonpublishing external `reparse-message` is outside API
retirement is superseded. The claim that failed API raw bytes must be retained is
also superseded. Shared physical integrity and genuine live/domain proof uses are
not superseded merely because they use the same tables.

## Implementation and acceptance handoff

The implementation PR must carry a reproducible before/after inventory of the
executed composed DDL and JSON/wire/runtime dependencies, classify every touched
object, and map every known residual original producer/store/consumer. Count
product objects separately from FTS/SQLite internals and implicit indexes.

Test public absence and no side effects, indirect parser reachability, malformed
responses, parser/CAS rejection, raw/Base64/hex/JSON marker retention, exchange
promotion, generated guard equality and direct-SQL absence. Scope no-original
claims precisely; disclose markers retained by C boundaries. Preserve current
resource/provenance/conflict/transfer, Git/domain integrity, live partial
collections, exchange, search and backup/restore regressions.

Run independent review against the actual integrated diff, focused development
checks, then complete ordinary acceptance and isolated installed wheel/sdist
checks. Bind remaining historical parser certificates to successful executed
tests and a pre-run exact-definition snapshot; final acceptance has no bootstrap
override. Record failures/incomplete runs separately, reconcile selected/executed
CI IDs, and bind hosted evidence to submitted feature HEAD/tree. Neither this
decision PR nor old passing receipts certify the later implementation.

Stack order: this focused decision PR based on main, then one coherent integrated
implementation PR based on its head. Continue without waiting for merge. No PR
merge or release is authorized. The implementation handoff must distinguish
verified removals, already absent paths and shared Phase-2 portions for every
R1–R7 target, and name remaining design questions without selecting their answers.
