# Current-state conflict boundary corrections

This follow-up starts at PR #14, `fix/current-state-schema-closure`, exact HEAD
`3f76d4873d14604b918198ac06c1660d0fa9e1b9`, schema 15. Its separate branch is
`fix/current-state-conflict-boundaries`. Fresh schema 16 removes two duplicate
native FK declarations. Earlier development catalogs are rejected; no migration,
merge or release is included. Historical schema 14/15 receipts remain unchanged.

## Reproductions and resulting behavior

The two new test modules contain 57 cases using the complete packaged DDL,
production `CurrentResources`, trusted fixture profiles and actual `Graph` intake
and export. Running those exact modules against the unchanged PR #14 checkout
produced **38 failures and 19 passes**. R1/R2 were therefore executable failures,
not prevented counterexamples. Reversed receipt order and omitted-body controls
also ran. The baseline report is
`artifacts/current-state-boundaries/boundaries-final-before.xml`.

**R1:** A@10, B@unknown, repeated A@20, then B@15 used to expose B as the winner.
The conflicted early return discarded A's new proof. Admission now retains
stronger evidence for explicitly supplied paths whose values equal the incumbent,
including when another field or candidate remains unordered. It never adopts a
different value, clears a remaining conflict or advances a successful local check
in that path. With B dated at 15, A's retained proof at 20 disproves that fork.
With an additional unordered C, the resource stays hidden until C is dated too.
An A@20 partial response without a body leaves the old body proof at 10, allowing
a proven B@15 body to replace it.

JSON values use type-aware canonical comparison: `true` and `1`, `[true]` and
`[1]`, and an object marker and an empty array are distinct. Equal-clock
contradictions remain unresolved. The typed deletion flag accepts bool/int and
normalizes to its physical integer representation separately from provider
metadata. These controls prevent attribution from certifying an unobserved value.

Actual Exchange tests retain A@20 and the unordered B at the receiver. A resolved
sender's A-only snapshot cannot date a previously received B@unknown; that receiver
conservatively keeps its conflict. Receiving an independently exported B@15
observation provides the missing proof and permits resolution. Current-only
exchange does not fabricate proof that a sender's discarded fork was old.

**R2:** A comment fork staged in repository A survives a parent-only transfer to
B, while the capture/intake registration remains A. Export now finds alternatives
through each incumbent's typed natural key instead of relying on the stale intake
repository column. For an accepted child with the same stable parent identity,
the portable candidate derives repository/binding/number from that parent;
captured endpoint, Source, original repository, times and field proofs remain
unchanged. Original A and Source A are absent from the B-only unit. The receiver
keeps the comment disputed through reverse record order, repeats and onward export.
Later dating of a transferred alternative also uses the projected semantic key.

An intake child with no accepted incumbent cannot gain valid membership merely
because an unrelated parent first arrives in B. A different parent ID remains an
independent relation claim. An unresolved Issue ownership claim, or a distinct
parent claim whose ownership spans repositories, cannot be represented by this
one-repository format. Export explicitly fails with
`CURRENT_STATE_CROSS_REPOSITORY_CONFLICT`, including the natural key and both
owners. It refuses both the old and current repository export rather than erasing
the claim or exporting a detached undisputed alternative. A richer portable
ownership-conflict representation remains a possible future format decision.

## Dependencies, columns and removed work

The [complete schema 15/16 inventory](current-state-boundaries-inventory.json)
lists every named object, physical/generated column and native FK. The previous
[column-use matrix](current-state-schema-liveness.md) still covers every current
column: no physical column was added or removed in this follow-up, and no unused
current column was found. Its writer, ordinary-reader, ownership, profile,
integrity, exchange and backup dependencies continue to apply.

| Audited dependency | Result and reason |
|---|---|
| Stable natural identity, current owner and parent/number copies | Retained. Typed readers, indexes, eligible views, direct owner validation and exchange consume them; Issue transfer does not change identity. |
| Body/status, title/state/author/URL/deletion, code/review/reply/thread references and provider metadata | Retained. Provider projection and ordinary query/search/target consumers use each group. Shared current tables remain independent from immutable PR/Git/thread histories. |
| Aggregate clock/capture/profile and per-field evidence | Retained. Structural ownership ordering, exposed provenance and sparse field ordering have distinct jobs. One proof per retained current path contains no previous value. Identical complete proofs are repeated storage within a bounded current map; normalizing that representation would require a different schema/validator design. |
| `last_checked_at_us` | Retained locally for a successful fenced live check. Removed from current Exchange records, expected portable columns and staged alternatives. Imports/replays cannot advance a receiver's check. A supplied wire column is rejected as an invalid envelope. |
| Two standalone binding-ID FKs | Removed. Both columns are NOT NULL; retained `(binding ID, repository UUID)` FKs already prove existence and ownership. Graph derives the same binding dependency from the composite FK, and the direct repository FK still supplies the repository dependency. No other Graph FK dependency changes. |
| Direct service/repository/profile FKs and generated discriminators | Retained. They supply typed wire references and capability/parent discrimination, even where existence also follows transitively from another relation. |
| SQL identity, clock, JSON, owner, selection, reply-cycle, transfer and retain guards | Retained. Direct SQL is an independent mutation boundary, not an unused duplicate of Python admission. The packaged JSON guards are unchanged and match regeneration exactly. |
| Repeated `_observation_evidence` assignments and discarded fingerprint validation | Removed. The first assignment already supplies missing/profile-pending intake, canonical validation covers serializability and admission computes the actual fingerprint. No alternate behavior was reachable through the repeated assignments. |
| Duplicate UUID/capture/proof validation within one call | Removed. Every path and distinct proof/capture remains checked; there is no cache between rows or transactions. |

The inventory confirms **103 tables, 48 views, 500 triggers and 108 named indexes**,
with no new history store. Only `database_identity`, `issue_resources` and
`review_resources` named table SQL changed. Six generated discriminators and all
physical columns are unchanged. Graph FK groups change from 6 to 5 for Issues and
9 to 8 for reviews, precisely the two removed singleton binding references.
DDL SHA-256 is
`d29295ce86ee60c67d0abb1b88bf5e8d94d9da5bb0b60b5d1e2e56fc02640aed`.

Other receiver-only state remains excluded through the existing Exchange table
allowlist: local trust, payload quarantine, validators, active cache/lease state
and local Source handles. Preferred repository endpoint selection is a real
operational pointer and remains cleared on the wire. Portable observation/parse
times, profile identity and captured acquisition context remain required evidence.
Coverage v2, epoch microseconds, CAS-41 and immutable history guarantees are
unchanged.

Reproduce the structural comparison without reading any retained database:

```sh
uv run --no-sync python scripts/audit_current_state.py \
  --output artifacts/current-state-boundaries/inventory.json
```

## Pagination and physical retention

The unchanged large test still collects 101 threads and 10,201 comments, using
the existing 60-second CLI deadline. Local Python 3.12.14 / SQLite 3.53.1 baseline
was **27.08 seconds**; the development follow-up was **21.90 seconds**. The former
PR #14 hosted run was 57.44 seconds on SQLite 3.45.1. These different environments
are not interchangeable; submitted-HEAD hosted timing belongs in the PR receipt.

A smaller instrumented fixture (101 threads, 10 replies, 1,015 review rows and
33 requests) measured 5.121 to 4.164 seconds. Under cProfile, field-evidence
validation fell from 1.357 to 0.489 seconds, acquisition shape calls from 13,219 to
3,054, and UUID construction from 158,901 to 15,475 calls. Each distinct proof is
checked once per synchronous invocation while every path's presence/ancestor
checks still execute. SQLite guards, collection completeness, profile/trust and
page revision fences stay active. No timeout or member-count assertion changed.
These profiling runs explicitly used the test-only synthetic parser bootstrap;
they are diagnostic measurements, not final acceptance certificates.

The [new disposable retention measurement](validation/synthetic/2026-10-09-current-state-boundaries-retention.json)
made twenty distinct 1,020-byte Issue edits. It retained one current Issue, seven
current evidence paths (3,009 bytes), zero immutable document observations and
20 interned bodies (20,400 exact bytes). Nineteen old bodies (19,380 bytes) had no
native text-body FK reference. Twenty identical imports and twenty genuine
fenced live checks added no body rows. Text-body table/index allocation was
36,864 bytes; whole-catalog pages also include schema and operational state.

The complete native text-body reference owners are `issue_resources`,
`review_resources` and `document_observations`. Staged alternatives embed exact
body text rather than a native body FK. Export interning that alternative added
one body row: 21 total bodies, 20 without a native FK, but **one of those twenty
was still needed by unresolved intake**. Current collection receipts keep
immutable semantic digests rather than native body references; retained immutable
document interpretations also require their own body/lifecycle analysis. A native
FK orphan count therefore does not establish permission to delete those bytes.
No physical deletion, GC, transport-archive policy or retention duration was
implemented. The receipt embeds its exact synthetic reproduction script.

## Acceptance evidence

Final local commands, counts, genuine parser certificate, independent review and
schema/JSON checks are recorded in
[the boundary receipt](validation/synthetic/2026-10-09-current-state-boundaries.md).
The stacked PR body records exact submitted HEAD, Git tree and hosted CI URL.
The baseline failures and provisional bootstrap runs are disclosed separately
from final no-bootstrap acceptance.
