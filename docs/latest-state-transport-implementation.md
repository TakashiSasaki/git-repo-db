# Latest resource state and optional transport archive

Current schema 15 corrections and acceptance are described in
[current-state-schema-closure.md](current-state-schema-closure.md). The schema 14
implementation and successful checkpoint below remain historical evidence for
PR #13, not acceptance of the follow-up.

## PR #13 schema 14 checkpoint

This change starts from PR #12, `feat/complete-model-contracts`, commit
`a3a4cb7482d42709f79d137b802f1789e3aa45cb`. The implementation branch is
`refactor/latest-state-transport`. Schema 14 is a fresh incompatible development
format; there is no migration or legacy intake. The schema 12/13 validation
receipts are historical evidence and do not establish acceptance of this change.

## Production contracts

`issue_resources` holds each ordinary Issue and each of its comments in one
physical table. Its natural key is service-instance UUID, kind and canonical
provider resource ID. Repository membership is mutable and is separate from
identity. `review_resources` holds each review and each review comment in one
physical table, keyed by change request, kind and canonical provider document ID.
Both stores retain the latest accepted state of every resource, including exact
nullable UTF-8 bodies, provider identity, ownership, title/state/author/URL where
applicable, deletion state, provider update clock, observation, last check and
parse times. Review comments retain typed review/reply/thread relationships and
frozen code OIDs, paths, positions and diff context.

Missing, provider-null, inaccessible and present body states are distinct; the
present empty string is exact text. Partial observations preserve unknown
fields. Comparable provider clocks reject delayed edits. A serialized live
refresh may use the captured catalog revision and typed acquisition scope;
import and replay cannot claim that authority. Unordered changed candidates
remain bounded variants in existing exchange staging. Ordinary readers expose
the unresolved conflict and do not advertise a receipt-order winner. Current
rows require an eligible explicitly selected, verified and locally trusted parser
profile, without becoming immutable result publication members.

Reviews no longer use marker tables or immutable document observation history.
PR title/body, PR conversation comments, Git/code acquisition and interpretation
history, and review thread identity/state history retain their existing immutable
contracts and required original inputs. The refactor does not make those inputs
optional.

The transport recorder defaults to disabled. Optional private local files retain
the exact representation supplied to parsers after HTTP content decoding, named
`http-content-decoded-v1`; this is not a claim of raw wire-byte fidelity. Metadata
uses a bounded whitelist of non-secret context. Recorder failures produce bounded,
sanitized diagnostics while valid collection and current admission continue.
Archive inspection and reparse use a separate reader and produce inspection
output without changing current selection. Ordinary queries, search, collection
proof, exchange and restore of current resources need no archive files.

`current_collection_pages` retains the minimum immutable page boundary, member
identity/digest, exact parser profile, observation and terminal proof. It contains no body transcript
and does not FK/seal mutable resource rows. Completion markers bind exact page
sets, including nested thread comment collections. Incomplete, malformed or
unresolved collections cannot advertise completeness. Coverage v2 retains
exactly five claim columns and derives the maximum observation-time candidate
set, including unknown and conflict, without falling back to an older complete
claim. Full and selective exchange close required profile/owner/parent/proof
dependencies, while independently handling mutable admission and immutable UUID
collisions.

CAS-41 adds required `quarantined_payload_count` to backup manifests. It is a
strict JSON integer in `0..2^63-1`, excluding booleans, counting active physical
quarantine rows in the verified copied catalog. Restore checks checksum and
catalog identity, then compares that count before diagnosis. Matching positive
counts preserve documented known corruption; unexplained corruption, missing or
malformed counts and mismatches reject admission while preserving failure stages.
Full-byte verification, no-overwrite and atomic publication contracts remain.

## Existing decision reconciliation

| Decisions | Schema 14 scope |
|---|---|
| D24, D27, D30, D32–D35 | Exact definition, full capability evidence, explicit selection, trust and inheritance barriers apply to current resources as well as retained history. |
| D25, D28–D29, D31, D36 | Immutable results retain exact input/output publications and composite ownership. Scoped mutable Issue/review rows instead carry parser/profile attribution, typed owners and minimum acquisition proof; refreshes do not generate hidden per-resource history. |
| D26 | Current rows and necessary portable dependencies exchange without optional archives; retained historical interpretations and inputs retain their existing exchange boundary. |
| CAS-3, CAS-9 | Exhaustive JSON classification, canonical typed references, real owner validation and missing-dependency staging include current collection membership and proof. |
| CAS-46, CAS-49 | Selective exchange and exact completeness proof include current pages without claiming unrelated or missing member completeness. |
| CAS-41 | Implemented as the required verified-copy physical quarantine count described above. |
| D2 | `not_applicable / retired`; no fabricated identity or observation time. |

The complete table/key/owner/lifecycle inventory and actual view, trigger and
index changes are in [latest-state-table-inventory.md](latest-state-table-inventory.md)
and its machine-readable JSON. Transport details are in
[latest-state-transport.md](latest-state-transport.md). Independent counterexample
review is recorded in
[the current-state review receipt](validation/synthetic/2026-10-09-current-state-independent-review.md).

## Verification and limits

Final local schema 14 acceptance passed with bootstrap absent: **1,311 ordinary tests** in 197.66s and **2 isolated wheel/sdist tests** in 61.76s, with zero failures, errors or skips. The exact certificate was generated from a successful 1,311-case bootstrap report (175.66s) and binds 35 implementation files/resources, complete composed DDL and all 13 capabilities.

| Gate | Executed receipt |
|---|---|
| Ordinary JUnit | SHA-256 `a146c980506e9437d60f9607e3af79723a3e5b2b7528a3f837953e91341cbcbf`; no bootstrap. |
| Installed wheel/sdist JUnit | SHA-256 `7791f90e66786aabcfc2e6282f2f4099f53cfccabe0e647b5ed458e15c91c5ad`; no bootstrap; current Issue/review queries/search, selective/full exchange, explicit receiver trust and backup/restore run outside the source checkout without an archive directory. |
| Fresh production DDL | Schema 14; 103 tables, 48 views, 496 triggers, 108 named indexes. Every view queried, every named index accessed and trigger-target INSERT/UPDATE/DELETE compiled. FK check empty; integrity `ok`. DDL SHA-256 `13d835b5b141c9d8647f0318c8b2bd1d1590df341baa28f98f755f274753a531`. This is not a claim that every trigger branch was exercised. |
| Existing identity/text/time/coverage | Canonical UUID/NUL guards, exact UTF-8 digests, natural current/historical keys, signed int64/unknown times and exactly five coverage columns with latest unknown/conflict probes passed. |
| JSON and static checks | All 55 JSON fields classified; generated guards equal registry; authored audit passed. Ruff lint/format (203 Python files), whitespace and report validation passed. |
| Parser certificate | SHA-256 `83cea60778fe7b63b1a180ee820376730add0fe5903916fedfbeb41ad7506979`; pre-run snapshot equals final definition and certificate report hash equals the successful JUnit. |
| Independent review | 43 focused cases passed without bootstrap; final ordinary suite includes the same 43 cases and the mandatory exact page-profile boundary. No reproduced defect remains unresolved. |

Exact commands, environment, successful and failed development receipts, full DDL object names, certificate definition and unexecuted scopes are in the [final local receipt](validation/synthetic/2026-10-09-latest-state-transport.json). The installed selective test independently computes transitive sealed-result input closure: 12 required fetches retained, 24 unrelated PR fetches excluded. The earlier Issue coverage spelling defect and test-only closure/scope corrections are disclosed separately from final acceptance.

Submitted HEAD, stacked PR #12 base, effective hosted commit/tree and downloaded CI receipt are recorded in the PR body after publication. The accepted commit is not amended to contain a self-referential CI receipt.

LFS remains pointer-only. Attachments retain text/link metadata only. Archive
deletion, incidental GC changes, comprehensive deletion propagation, removal of
PR/Git history, CAS-76/CAS-77 and broader provider collection are deferred. No live
authenticated acquisition, private data, physical power-loss test or non-Linux
atomic restore is exercised by this synthetic validation.
