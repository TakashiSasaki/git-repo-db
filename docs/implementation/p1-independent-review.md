# P1 independent source and execution review

Three reviewers independent of the implementation authors inspected source,
executed evidence and disposable counterexamples. They did not edit the branch.
Initial reviewed source: `8b6db0c3d4f2e301fe03a32eaba820606116c221`, tree
`6af8a4acf7f4de8e346bb81902b6f595f5da23c4`. Its exact local receipt had **310
passing nodes**, including 180 P1 nodes; passing tests did not cover the findings
below. Earlier `714a6e8` had 306 passing nodes before four open-corruption cases.

Final corrected source binding and independent rechecks are recorded in the
execution receipt and the final revalidation section below. Review is for P1's
isolated executable foundation, not P7 recovery activation or P8 runtime acceptance.

## Findings, counterexamples and corrections

| ID / severity | Reviewer and initial location | Executed counterexample | Correction and regression boundary |
| --- | --- | --- | --- |
| R1 / Medium | A, `p1_core.py:555–574`, `Core.coverage` | Inject supported writer between claims/proof SELECTs: returned complete@10/known-empty although no committed snapshot contained both; newer unknown@11 existed | Pin one local Core snapshot through projection, matching Context; concurrent WAL trace-controlled regression |
| R2 / Medium | A and C, `domain/p1_core.py:463–465`, parent member validation | Partial parent with known OID and genuinely unknown position rejected; caller had to discard it or invent ordinal 0 | Explicit unpositioned member; canonical semantic encoding preserves actual known ordinals and unknown-position membership; out-of-order same-evidence replay |
| R3 / High | C, `p1_core.py:463`, relation conflict slots | Same tree/name `61`, mode 100644/OID B versus mode 100755/OID C, both partial: no conflict | Raw name is logical tree slot; mode/target remain competing asserted values; reversed orders and closed-list controls |
| R4 / High | C, `domain/ports/p1_core.py:70`, Core read port | Contradictory notes reports existed only through raw SQL; typed reads required retained bytes and exposed no metadata conflict | Capture/target-scoped `notes_projection` with claims/groups, conflicts and bounded relevant receiver-checked mapping; zero-note-body reads |
| R5 / Medium | A, `core.sql`, `core_coverage_proofs.members_json` | Supported coordinator callback inserted `[["sha1","not-an-oid"]]`; backup candidate emitted certificate. Missing valid-looking members and storage-row objects also accepted | Physical typed-membership CHECK plus nominal-reference trigger; candidate revalidation of embedded semantic references; intended-boundary malformed/orphan cases |
| R6 / High | B, `p1_coordination.py:314–325`, corruption wrappers | Handler released writer gate before stop; another supported writer committed first. Process death could lose stop | Immediate persistent stop plus short completion fence for COMMIT/certification; actual contender/process-death and paused-completion tests |
| R7 / High | A and B, `context.sql:173–176`, Coverage proof ownership | An issues terminal proved Source `all-notes` known-empty; field/collection kind branches similarly incomplete | Exact owner/category/field/original-collection matching in physical guards; every owner branch cross-scope negatives |
| R8 / Medium | A and B, Context proof/current-terminal reads | Older complete-empty terminal still proved empty after newer same-collection partial observation | Latest applicable terminal candidate set checked on admission and within pinned reads; equal-time incompatible/superseded/missing terminal cases preserve original claims with honest qualification |
| R9 / Medium | B and author/root scope check, Context repository field | Attach then observe explicit null detach: CHECK rejected null, leaving old current repository | Explicit null field/typed membership supported; real FK skips null; Source known-positive pairs remain durable; rollback/source-evidence regression |
| R10 / High | A and C, correction `18bb00e`, `Core.relations` positive slot map | Different observation labels hid contradictory parent[0] or raw tree-name assertions | `924fb20`: compare explicit known positive slots across observation scopes; ten reverse-order/conflict/compatible controls |
| R11 / Medium | A, `924fb20`, checked native negative closure | Actual verified root commit with empty parents plus a differently scoped parent[0] report incorrectly had no conflict | `f56cf3f`: checked full intrinsic closure excludes contradictory slots across scopes; ten known-empty/extra/unknown-position controls; ordinary bounded report absence remains scoped |
| R12 / Medium | B, `18bb00e`, `SearchProjection.context_documents` | A body held through actual text FK projected only its hash; direct fallback also missed the body | `924fb20`: resolve retained text FK; explicit null and supplied digest reports remain distinct; pinned/stale/rebuild/fallback regression |

Additional demonstrated boundary corrections include actual SQLite JSON integer
overflow in generated source clocks, exact retained-text-reference FKs distinct
from supplied digest reports, stop on corruption during connection opening,
retained-byte corruption restart fencing, and work accounting through actual Python
and SQL native/proof checks. These do not reopen accepted decisions.

## Initial independent execution

- **A — physical model:** schema/Core/Coverage/disposition 84 passed; notes and
  coordination 65 passed; build fingerprints and reconciliation passed. Separately
  introspected SQLite 3.53.1: 46 STRICT/WITHOUT ROWID tables (18/17/8/3), five actual
  Coverage columns in each authority, all 84 tables/625 baseline columns routed,
  no added storage surrogate or omitted route found. The malformed-proof backup
  reproduction used a disposable archive of the exact reviewed commit.
- **B — cross-store:** Context/Coverage/coordination/derivatives 90 passed.
  Independently executed stop scheduling, cross-kind proof, older terminal and
  null-detachment adversaries; reconciled the actual 306- and 310-node receipts.
- **C — domain/API:** Core/notes 65 passed. Independently executed tree-mode
  conflict and unknown-parent-coordinate adversaries; inspected typed notes port
  and actual report-only tests. All three requested corrections before approval.

Commands used the relevant files under `tests/integration/p1`, direct pytest
without duplicate journal-plugin registration, and synthetic tempfile catalogs.
No reviewer touched source catalogs or rewrote the reviewed branch.

## Final independent revalidation

**All listed material findings are closed.** Final independently reviewed source:
`f56cf3f2adddaf18e3d5cc5052ad92440a8abc33`, tree
`fd61dca21c8e34c4729e3cf9b43d226a83b95a94`. Later evidence-only commits preserve
all executable input hashes; final feature identity and CI are bound in the PR.

| Reviewer | Exact final source revalidation | Result |
| --- | --- | --- |
| A — physical model | Inspected final two-file correction, reran actual checked-native empty/extra-parent counterexamples in both admission orders (4 cases), executed Core/notes 104 tests, build fingerprints and disposition check | Passed; open material findings 0 |
| B — cross-store | Final f56 source rebind verified all 17 relevant Context/coordination/Search/schema/test/skill input SHA-256 values unchanged from independently reviewed 924 source. Own 120 tests at 18bb and 12 derivative tests at 924, plus original stop/Coverage/detach/actual-text adversaries | Passed; open material findings 0; no redundant execution claimed on identity-only rebind |
| C — domain/API | Inspected final correction, independently reproduced full checked-empty versus differently scoped parent report, executed Core/notes 104 tests at f56. Earlier P2 handoff schema/Core/notes command passed 109 tests at 924 | Passed; open material findings 0 |

The initial findings were corrected in `18bb00e`; subsequent independently
identified conflict/Search regressions were corrected in `924fb20` and
`f56cf3f`. No design/prototype parent commit was rewritten. Reviewers inspected
actual executed evidence rather than treating a passing suite as proof that its
missing cases worked. No accepted architectural owner decision was reopened.

Root's clean f56 integrated run independently selected/reconciled **380 unique
nodes**, all passed: 250 new P1 contracts, 128 retained architecture-spike/audit
regressions and 2 installed distribution variants. The separate unchanged
Schema 21 check remains one known baseline failure, documented and isolated in
PR #71. See [execution evidence](p1-execution-evidence.json) and
[report](p1-execution-report.md). This is development verification, not release
qualification, P7 activation or P8 runtime integration.
