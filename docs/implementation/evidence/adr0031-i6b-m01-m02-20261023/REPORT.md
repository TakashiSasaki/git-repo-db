# Author correction of I6B-IR-M01 / I6B-IR-M02

This is the Author's correction and verification, **not independent re-review or
Release acceptance**. Only the two Medium findings from #152 are addressed.
The parent arranges a separate non-Author review after this Draft PR is submitted.
I6-C/I7/I8, normal Transfer activation, both-fence retirement and PR integration
remain outside this change.

## Frozen target and implementation

The actual #152 branch is `review/adr0031-i6b-independent-20261023`, HEAD
`8521158f2996f125d2fcaac36ea79ac1296a7cf7`, tree
`455ef25606ee555e4154dd2d14929b41aa4ef50f`. This is the direct base of the new
correction branch. Its actual parent #151 is
`impl/adr0031-i6b-generalized-wire` at
`ef787a5ff8b13f118d6bf5107c7338f43fde56dc`, tree
`a3ed2628a98db134bdc65d13da905f5ddf25e972`. Start metadata matches the assignment;
no moved target or competing open correction PR was substituted. See `TARGET.json`
and `initial/` for the actual GitHub reads.

Final executable source: **`fe9e48bfac750a276b2622da2c50d3d4559de338`**, tree
**`8ef254ff060f44f02370a695743c7a581e7b9b5c`**. Evidence publication commits follow
without changing those executable inputs; the final publication HEAD/tree is
bound externally in the PR body and final handoff. `INPUTS.json` hashes all 487
runtime/test/script/workflow/configuration inputs. `protected-inputs.json.gz`
checks equality of all 6,311 protected, unchanged paths against #152. Existing
product tests/assertions, Accepted ADRs, old evidence, DDL/fingerprints, authority
and fence modules are unchanged. Only two product files and two new test files
change. The existing three-store-invariants and efficient-repository-investigation skills
add verified work/checksum and traceback-comparison lessons.
No #144/#147/#150 sibling change is incorporated.

| Finding | Reviewed failure / contract | Author correction | Acceptance evidence |
| --- | --- | --- | --- |
| I6B-IR-M01, R04/R13, T11 | `context_dependencies.py` completed the shared scanner before inspecting remaining work; a zero budget still caused 1,501 embedded parses over 314,392 characters for the saved 1,001-row fixture. | The planner supplies cumulative `spend` to the same shared scanner. Reservations precede traversal, queue growth, escaping and embedded JSON/identity parses. A fixed-envelope length lower bound preserves necessarily oversized row-array `INPUT_LIMIT` even at zero work, without touching rows. Completed whole units remain publishable after a later stop. | Unchanged three required-bound probes, independent planner28, new scanner16, exact scan/full-work/depth/byte/cycle controls, source and both installed forms. |
| I6B-IR-M02, R03, T10/T24/T27 | Selection construction sorted/deduplicated received arrays before checksum verification, accepting a stale digest for a changed received dictionary. | A shared canonical dictionary encoder verifies the bounded received dictionary excluding only `digest_sha256` before selection conversion. Then selection `to_dict()` remains the sole canonical representation authority; rehashed duplicate/permuted arrays refuse `INVALID_SELECTION` rather than silently repair. | Unchanged saved30 require and observe `DIGEST_MISMATCH`; new40 cover correctly rehashed noncanonical arrays, all three carriers, canonical Unicode positives and conversion ordering. |

The checksum remains unauthenticated SHA-256 integrity. It supplies no Provider
origin, identity legitimacy, authorization, freshness or replay authority.
Canonical normal input retains the existing outer `ensure_ascii=False`, sorted,
compact UTF-8 encoding; Resource identity/report encodings retain their existing
separate authorities.

## Work counting and refusal order

The scanner's returned element count remains the existing wire hard-cap counter.
It is deliberately distinct from planner request work. Request work reserves
visited values/container exits, member/queued-reference checks and Unicode
codepoints before the corresponding escaping, lexical/JSON or identity pass.
Repeated passes cost again. Embedded JSON reserves both its escaping pass and
parser input before entering either operation; parsing cannot run first and be
refused only afterward. Existing row, dependency, copy and output work also stays
charged. Reservations for an entered bounded operation remain spent on rejection;
a reservation which cannot fit performs no refused operation and charges exactly
one fixed refusal unit. Thus a work stop adds at most one unit beyond the
available ceiling (or one beyond supplied already-excessive prior work), never a
full rejected parse. No work is refunded by omission, rollback or retry.

Fixed envelope checks inspect only the known section names, list types and
`len(list)`: their cost is independent of row count/body length. They reject a
necessarily over-hard-cap list before work scanning. Unknown deeper malformed
input can instead stop at `work_limit` before its unvisited suffix is inspected.
With sufficient work, shared hard depth/byte/element/cycle and strict identity
checks still refuse. `include_context=False` returns `section_not_selected`
after fixed envelope inspection without scanning unselected bodies.

The original scaling script is re-executed against frozen baseline and corrected
source with parser instrumentation. At 500 Resources plus 500 reports, budgets
0/1/17 and exhausted prior17 change from 1,501 parses / 314,392 characters each
to **zero embedded parses / zero characters**, with charged total **1/2/18/18**.
The old totals were 26,041/26,041/26,041/26,058. These are measured logical work
and parser counts, not sequential performance benchmarks. The 24-record sets
retain small and larger irrelevant inputs, commands, exits and actual imports.

## Execution receipts and remaining failures

Every invocation has its own command, actual interpreter/import binding, input
hashes, exit, collection, JUnit, journal and phase reconciliation. Overlapping
lanes are never added into a full-run total. Python 3.12.14 actually loads SQLite
3.53.1; the complete source ID and options are in each runtime receipt. No SQLite
library was downloaded, built, replaced or selected by version, and no floor or
network guard was weakened.

- `source-baseline/`: unchanged saved33 on #152, **33 FAIL / exit1**.
- `source-contracts-root-guard/`: unchanged saved33 on corrected source, **33 PASS / exit0**.
- `source-independent-root-guard/`: unchanged independent normal208, **208 PASS / exit0**.
- `source-author-extra-root-guard/`: attributed unchanged Author34, **34 PASS / exit0**.
- `source-diagnostic-root-guard/`: separate matched745, **446 PASS / 279 FAIL /
  20 ERROR / exit1**, exact collection/JUnit/journal/normal phases. In
  `diagnostic-root-guard-comparison/summary.json`, every old node/outcome/phase and all299
  unsuccessful primary exception/refusal/frame-function signatures match the
  #152 retained diagnostic. All call-phase assertion entries match, as do every
  unsuccessful node's assertion entries. Actual worker traceback comparison in
  `diagnostic-root-guard-actual-frame-comparison/summary.json` confirms zero
  exception/refusal/project-function changes; one legacy three-column node has
  shifted source line coordinates, with the same MALFORMED_ROW refusal. Two
  passing P6 nodes differ only in
  setup fixture association under worker scheduling; the actual shared setup
  assertion remains reached elsewhere. Statement entry is not subexpression,
  other-thread or child-process coverage. The observer-binding sidecar records
  the unchanged actually used runner/plugins; an unused standalone measurement
  helper added to the broad external-tool inventory during execution is explicit
  and is not treated as a loaded test input.
- Both final installed forms separately pass safety626 (I4217/I529 included),
  wire212, independent normal204 + V07 alternatives4, Author34, saved33 and new56;
  every lane exits0 with exact node/phase reconciliation, zero skip/xfail. These
  overlapping invocations are not a unique total. The original smoke remains a
  separate FAIL1 in each form; see `distribution/REPORT.md` and its all-member,
  metadata, RECORD, import-origin, source-retention and lossless raw receipts.
- `source-full-root-guard/`: **one complete final-product-source invocation,
  6,344 unique: 6,045 PASS / 279 FAIL / 20 ERROR, exit1**, zero skip/xfail/xpass.
  All/ordinary collection retains two unexecuted live/benchmark opt-ins. This is
  neither an aggregate of focused runs nor complete Release acceptance. The raw
  generic reconciliation booleans for duplicate calls remain false because they
  also count real SubTestReports; the typed controller reconciliation separately
  checks all19,012 ordinary phases and the actual57 passing subtests, preserving
  those raw booleans rather than overwriting them. `full-signature-reconciliation.json`
  and `full-root-guard-actual-frame-comparison/summary.json` prove that all6,288
  prior nodes retain outcome/phase, all56 additions pass, and the same299
  unsuccessful nodes retain actual exception/refusal/frame-function signatures.
  Only one physical source-line coordinate shifts. The initial JUnit text
  comparison retains164 display-label differences caused by tb=auto versus
  tb=long; actual worker frames resolve that presentation difference without
  rewriting the raw comparison. `source-full-root-guard/subsets.json` verifies
  safety626, wire212, I4SQL217, I5Admission29 and new56 as passing subsets of this
  single invocation, never additions to its total.
- `static-root-guard/`: policy, callsite, schema, boundary, Ruff lint, Ruff format
  and prose validation checks all exit0. These are static/development checks, not full runtime acceptance.

The known #152 full baseline is 5,989 PASS / 279 FAIL / 20 ERROR, exit1. This
correction must not relabel its 299 unsuccessful nodes as solved or accepted.
Their node/phase/refusal/trace and assertion-reach comparisons are retained by the
final source full/diagnostic receipts. The historical #149 comparison still has
298 unchanged primary signatures plus the one old three-column fixture refusing
earlier as `MALFORMED_ROW`; its downstream assertions remain unexecuted. Both
original migrated fixture parameters and all their original assertions are
unchanged by this correction.

An early nonfinal source freeze `a3185cd` exposed one unchanged independent
hard-element probe failure (207 PASS / 1 FAIL). The constant-size envelope lower
bound fixes that failure without changing the probe. Its partial full run and
partial installed safety run were interrupted and remain explicitly nonfinal;
none is combined with a later complete invocation. Initial new-test fixture/
expectation mistakes and a duplicate-conftest bootstrap attempt also remain in
raw attempt records, not hidden as passing tests.

A subsequent final read also found that root `set(data)` allocation preceded its
shape check for invalid caller-owned dictionaries. The final fe9e48b guard first
checks `len(data)` against the fixed section count, then compares only a bounded
key set. The new root-allocation probe observes the actual `set` boundary at a
20,000-key malformed root with max_work0. The actual baseline and d68 calls build
sets with argument lengths [20,000,16], while fe9 makes zero such calls and keeps
`MALFORMED_SECTION`. Supplementary tracemalloc peaks are 1,051,944 versus 2,026
bytes, excluding input and patch construction; these are individual observations,
not a statistical benchmark. Prior d68dc43 completed/partial receipts
remain separately labeled superseded; current complete-source and distribution
verification are re-executed from fe9e48b, not inherited from that prior source.

## Distribution and CI boundaries

Direct and sdist-derived wheels are independently built from the exact same
frozen source, installed into separate environments outside checkout, and checked
against all archive members, metadata, archive/installed RECORD entries and
actual product files/import origins. The actual product set is measured rather
than fixed to a historical count: 160 files / 6,025,551 bytes and all164 wheel
members match. Direct and derived wheel SHA256 is
`2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`;
tested sdist SHA256 is
`96134d412faf97119c50e98845c494f6a4554ea67d22d328da0a314049f8fbd7`.
These artifacts are built from fe9e48b's complete frozen source. The later full
publication sdist containing this new evidence is not built/tested or inferred
tested from matching product inputs; build/publication inventories remain distinct. `distribution/final-root-guard/` raw evidence records build inputs,
all sdist members, product hashes and before/after installed equality.

The existing sdist ignores 120 historical CI files beneath `artifacts/` via its
existing exclusion policy. The first exhaustive source-retention check therefore
fails; that exact failure and omitted paths remain recorded. All product inputs
are retained. This correction changes no packaging rule or sibling sdist work.
The original minimal Access smoke still stops at unwired export with
`PERMISSION_DENIED`, pytest/child exit1; all later original assertions remain
unexecuted. A successful separate installed safety lane does not repair that smoke.

Historical #151 Development39955068751 is SUCCESS, Access39955068823 is FAILURE;
#152 Development39963122681 is SUCCESS. Current statuses are re-read into
`initial/`. The known large Access artifact download denial is historical; this
correction does not retry or bypass it. Final new-PR HEAD Development status,
actual test-merge parents/tree and compact receipt are checked after publication.
Development success never means Release acceptance; Access/Release not triggered
for the new HEAD must be called never-run, not pending or passed.

## Independent re-review handoff

Re-run the unchanged saved33 and normal208, both new regression files and the
retained safety/wire/Author lanes using the exact publication HEAD's verified
unchanged executable inputs. Inspect reservations before real high-cost work,
raw-dictionary checksum ordering and rejection of correctly rehashed noncanonical
selections. Preserve all 299 old unsuccessful results and the original failed
Access smoke. Review full node/phase/refusal/trace/assertion differences, whole
terminal/Transfer/Source/Coverage units and current admission/fence checks.

No independent PASS is claimed. Normal Provider/selective Exchange composition,
late/reverse/onward delivery, I7 recovery/pairing, I8 query/Search, opt-in live/
benchmark runs, assembled PR integration and complete hosted Release acceptance
remain unexecuted/out of scope. Both Transfer fences remain active.
