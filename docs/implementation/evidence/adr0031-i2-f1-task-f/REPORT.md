# Task F — independent ADR 0031 I2 C-F1 architecture re-review

Date: 2026-10-21 UTC. Repository: <https://github.com/TakashiSasaki/git-repo-db>.

**Verdict: READY WITH CONDITIONS. No unresolved design blocker to starting the
I2 product implementation was found at the exact reviewed inputs.** F1 is closed
for the proposed staged SQL contract. The conditions below are mandatory product
implementation and acceptance gates; they are not claims that those features
already exist. This verdict approves neither product acceptance, PR merge,
release nor deployment. It does not change Task D's NOT READY verdict on #120.

## Frozen scope and independence

| Input | Exact commit | Tree |
| --- | --- | --- |
| #120 basic I2 proposal | `9eaa5111c94204c4adf791cd1565b704728493f1` | `d91c73b5caed2601a6b097c69017e0e49e96bc53` |
| #121 Task D | `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6` | `927288ecc20082144887fd668636b35171b647dd` |
| #122 C-F1, reviewed source and publication parent | `2199a882d79c9c707fffcba3a8327ef96a3fc384` | `b1595725bce322d04baf0f3b9b340cfdc71552a0` |

Initial live API inspection found #117–#122 Draft/Open, #122 at the requested
HEAD, and no equivalent later Task F PR, review submission or #122 discussion
comment. All remote heads were also enumerated. Immediately before publication,
#122 still had the same HEAD, no comments/reviews, and the newest PR remained
#122. `initial-github-observations.json`, `remote-heads.txt` and
`prepublication-github.json` preserve the observations. Search covers the visible
repository PR/ref/review records, not unpublished private conversations.

The reviewer in this Task F conversation did not author C-F1 or Task D. The
author's own `AUTHOR-VERIFICATION.md` identifies the Task D/C-F1 author as one
earlier conversational agent. This is a separate review conversation with no
authored correction in its history. Publication uses the owner's connected
GitHub account; that account is not an independent human-reviewer credential.
Agent independence is based on this session's provenance, not inferred from a
different GitHub login or a fabricated external reviewer identity.

A fresh network clone at `/workspace/task-f-review` was detached at the exact
#122 commit. New SQLite source downloads, separate locally compiled libraries,
independently written harness and synthetic data under `/workspace/task-f-evidence`
were used. No author DB, binary, venv or probe was reused as independent execution.
The target composer, SQL, UDF and codec are necessarily the reviewed inputs.
No other agent was commissioned. All 3,762 tracked reviewed files were bound
before execution and unchanged afterward. The author's 3,745 predecessor-file
manifest also verifies unchanged, and #122 adds only its 17 documented files.

Read: root AGENTS, ADR index and accepted 0031, the full Resource schema contract
and design handoff, #120 I2 implementation plan and proposal SQL/UDF/composer,
#121 REPORT and unchanged F1 SQL, #122 addendum, fence/composer, stage model,
author verification, probe/runner, summaries, publication bindings and archived
execution receipts. Relevant existing product admission/read/import paths were
inspected to distinguish their present behavior from proposed guards.

## Independent execution and evidence

Official sources were downloaded anew from sqlite.org:

| Runtime | Download SHA-256 | Measured sqlite_source_id() |
| --- | --- | --- |
| 3.51.3 | `acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4` | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| 3.53.1 | `36ad6e7f38540a3b21a2ac36340833f0a9e426bc1c752751c3ba669466827eae` | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Both compiler processes exited 0. Independent builds use `cc -O1 -g0 -fPIC
-shared`, THREADSAFE, FTS5, COLUMN_METADATA and RTREE. `/usr/bin/python3.13`
dynamically loaded each library in a separate process. Each lane asserts the
actual SQL version and records source ID, full compile options and PRAGMAs.
No version constant was overridden. Source/header/library hashes and exact build
argv are in `runtime/provenance.json` inside the evidence ZIP.

Normal profile: `foreign_keys=1`, `recursive_triggers=1`,
`ignore_check_constraints=0`, `defer_foreign_keys=0`, `trusted_schema=1`,
`synchronous=3` (EXTRA), UTF-8. Isolated cases use memory journaling; the fresh
file/reopen control uses DELETE journaling. These are constraint/design checks,
not WAL crash, concurrency, performance or power-loss qualification.

| Final independent case family, per runtime | Executed | Passed |
| --- | ---: | ---: |
| Direct SQL, including positive identity/name controls | 226 | 226 |
| Malformed/NULL/wrong payload SQL | 48 | 48 |
| Same-key SQL collisions using explicitly poisoned fixtures | 21 | 21 |
| Unchanged Task D before/after script | 2 | 2 |
| Combined positive child/Parent/ordered/opaque scenario | 1 | 1 |
| Caller transaction/savepoint scenario | 1 | 1 |
| File reopen/metadata scenario | 1 | 1 |
| Physical schema/index/FK/UDF inventory | 1 | 1 |
| Normalized routing model (Python and SQL rollback) | 42 | 42 |
| **Total case groups** | **343** | **343** |

Both lane OS exits and the separately measured overall runner OS exit are 0.
Names are unique. Groups may execute multiple statements; counts are not single
SQL statements or pytest/product tests. The same requirements overlap across
runtimes. The initial successful 322-case run is preserved separately, including
its original harness hash; 21 correct-I7 Parent controls were then added. Initial
and final totals are not added together. There were no failed SQL-review attempts.

Each final lane has 327 refusal groups with directly equal complete pre/post
rowsets (this includes Python model refusals), plus separately recorded literal
and transaction comparisons. These comparisons cover all 19 Context tables and
every selected column, including generated projections. Hashes accompany many
snapshots but do not replace byte/value equality. Real exceptions and driver
extended codes are retained. Observed codes include TRIGGER 1811, datatype 3091,
SQLITE_ERROR 1 and FK 787. The driver reports 3091 as `unknown`; the evidence
does not manufacture a driver name. Some invalid endpoint generated JSON and
STRICT input types fail before the fence can raise 1811. They still refuse
atomically; the review does not claim every malformed input reaches the trigger.

The author's ZIP independently verifies all 46 indexed entries. Its 119-case
receipts, bound source hashes, complete refusal rowsets and actual child/runner
exit records are internally consistent. That is an evidence audit, not a rerun
or 119 additional independent successes. Neither the author 119 nor Task C 133
was rerun here. See `evidence-audit.json`.

## A — SQL fence and rollback

The unchanged Task D SQL is executed verbatim, statement by statement, on both
compositions. On the old composition its Provider-only report is stored and the
existing reference reader returns one report, with no native I7 or endpoint.
On the corrected composition the report INSERT raises 1811, no report is stored
or returned, and all pre/post statement rowsets are exactly equal. Earlier lawful
Provider and complete child registrations remain. Later SELECT/PRAGMA results
are preserved in the literal receipt. This reproduces the original defect and
confirms the correction without rewriting the reproducer.

All three reserved representations are refused: `transfer_event_report`,
`transfer_from_repository`, `transfer_to_repository`. For each, seven verbs cover
INSERT, OR IGNORE, DO NOTHING, REPLACE, OR REPLACE, UPSERT-update and UPSERT with
WHERE 0. Eight independent combinations of native-I7, lawful I8 Parent report
and endpoint existence are tested. The impossible existing endpoint is an
explicit diagnostic fixture restored to the exact guarded schema before the
action; it is never presented as supported storage. Extra controls provide a
correct native-I7 Parent report. No dependency combination enables Transfer.

Separate poisoned fixtures force genuine same-PK collisions for each of the
three representations and all verbs. Exact replay still fails before a conflict
shortcut. Ordinary generic relation UPDATE and UPSERT-update cannot change into
the reserved report; ordinary owning-repository rows cannot change into either
Transfer endpoint role. Retained immutable guards supply those update refusals.

Independently varied members/target, scope/clock, provenance and time inputs
include SQL NULL, malformed JSON, structurally wrong metadata and wrong types.
Additional counterexamples include INSERT SELECT, NOCASE source expressions,
RETURNING, multirow OR FAIL and OR ROLLBACK. Multirow statements with a legal
generic prefix and reserved later row leave no statement prefix. RAISE(ABORT)
keeps earlier caller statements pending; an explicit whole-unit savepoint
rollback removes that unit. The receipts preserve all three snapshots and the
real error. SQL statement atomicity is not claimed to be whole-API atomicity.

## B — lawful common storage and identity preservation

The combined positive scenario admits a complete comment/Timeline Event identity
before any Issue Resource or Parent report. A lawful attributed I8 Parent report
then persists while native I7 is still absent. Arrival of I7 does not fabricate a
report. Multiple genuine Parent reports, separate evidence alternatives and both
member orders are retained; no child-wide winner/unique rule is added. A new
opaque Resource kind and its ordered general relation persist under the common
contract. This is common staged storage, not completed I3 typed Parent validation.

I8 report storage and I8 Transfer support remain distinct. This I2 design refuses
all Transfer. It does not itself implement the future G3=A native-I7 support FK.
I4 must permanently refuse I8 support for an I7-native Event while preserving the
general I8 report, and I5 must distinguish that from missing correct-I7 support
requiring original-report re-supply. No accepted choice is reopened.

Case, whitespace and NUL-suffixed report-name variants are distinct opaque BINARY
names and remain stored; they confer no Transfer semantics. Product consumers
must not trim/casefold them into aliases. Independent global scalar/array/empty
Document declarations succeed, and the same key shaped like a scoped Document
can be initially declared by either genuine contract in separate fixtures.
All opposite-declaration replay verbs refuse, while identical DO NOTHING replay
and file reopen preserve full metadata. Omitted global identification refuses.
No global/scoped shape guess or extra PK discriminator is introduced.

Physical comparison of both executed schemas has exactly one difference:
`i2_transfer_report_stage_fence`. The old composed SQL is an exact prefix of the
new SQL. Resources, all old triggers, FK/index definitions and generated fields
are identical; the 3/4/5/6-column reference targets stay intact. All indexed key
slots observed by `index_xinfo` use BINARY. The two new Resource functions retain
deterministic flag 2048 and are the unchanged row-local I1-codec predicates,
without DB lookups/external I/O. Resource PK remains the direct triple. Provider
FK, open kinds, canonical grammar, four non-key identification columns and typed
absence projection are unchanged. No Parent-existence FK is restored.

Before SQL SHA-256: `c8fd84cf5e535d5f4c585d31a2e0ad0e4c791bb9cd7649f243e0bc1c6bfd223e`.
After SQL SHA-256: `0d7cb70c6f8acc46df8944120ef70902b9eef80a02d5f7597eafb926bb399669`.
Accepted ADR 0031 A3/B3/U1/U2/U3/U4/U5/G3=A, product source/DDL/fingerprints,
existing tests and all frozen predecessor evidence remain unchanged.

## C — API, Import and Reader design sufficiency

The addendum is sufficiently concrete to start implementation. It specifies
error category, operation families, placement relative to side effects/replay,
selected atomic transaction scope, poisoned-store handling, unaffected common
operations, file impact map and fence removal gate. It does not substitute a
model for the still-unimplemented real parser, facade, query or Search route.

| Requirement | Design source and independent evidence | Product status |
| --- | --- | --- |
| Typed Transfer refused before Resource/evidence/clock/ledger effects | Addendum item 1; model admit refusals with unchanged full rowsets | Future I2 guard; current `p1_context.py:279` still has the old Transfer admission path |
| Generic report and both endpoint bypasses refused | Addendum 1; independent direct SQL plus normalized preflight | SQL proposal verified; actual facades still require coordinated stage guards |
| Selected atomic import unit scanned before any effects | Addendum 2/5; model mixed ordinary/reserved input in either order, both duplicate modes | Nested real typed units, decoder, selection and transaction mapping unimplemented |
| Unsupported input rejected before duplicate/replay | Addendum 1/2/5; poisoned same-PK SQL controls and model duplicate=True | Must precede real Operational package/unit shortcuts and domain registration |
| Explicit Transfer query/export unsupported on empty DB | Addendum 3; both model query routes and export preflight | No installed consumer support supplied by stage_contract.py |
| Impossible stored rows cause Stored Invariant handling | Addendum 3; poisoned report/from/to fixtures, generic read/export/open/duplicate checks | Existing schema/config checks must run first; real ADR 0026 stop behavior unimplemented here |
| Preserve generic relations and independent Core-only Exchange | Addendum 2/4; model ordinary roundtrip and SQL common positives | Core-only route is document/architecture review only; not exercised by this Context model |

The unmodified product `production_context.py:536` already prevents a generic
Transfer report at that one facade, but this alone cannot protect direct SQL,
all typed paths or reader exposure. Its old `relations` reader still reconstructs
stored rows. `application/exchange.py:1615` currently prevalidates both received
sections before filtering, and later routes selected Core/Context effects.
Therefore the new I2 stage restriction must be placed at the selected typed-unit
boundary; a blanket "package contains any Transfer" check before selection could
unnecessarily disable an independent Core-only selection. Ordinary malformed
wire/version/digest checks remain binding on their existing scope. The addendum
explicitly requires selected-unit fencing and preserves Core-only operation;
this placement is a product regression requirement, not an observed defect in
the design or a model test of the real importer.

No ordinary reader may silently return an empty list by filtering poisoned rows,
delete them, downgrade them or repair storage. A matching-schema impossible row
must reach stored-invariant/recovery handling before domain exposure. A schema
mismatch is instead format refusal. Untrusted diagnostic/salvage reads retain
their separate explicit scope. The model throws StageStoredViolation and changes
no rows; it neither implements persistent catalog stop nor proves it.

## Mandatory conditions and remaining work

1. Implement both fences and retained immutable guards in the same packaged I2
   DDL/composer/UDF/index/fingerprint/connection unit. Register and verify the
   exact trusted schema and required PRAGMAs on every initializer/writer/reader,
   expected-schema and stored-validation connection. Fail closed on mismatch.
2. Guard every typed Transfer facade and intake before any Resource/evidence,
   time, ledger or replay effect; generic admission must not become an opaque
   fallback. Reject unsupported replay too. Carry complete identification
   metadata through actual local admission/read/reopen paths.
3. Preflight the real selected atomic import transaction, recursively including
   typed units, report-only Provider forms and endpoints, before effects or
   duplicate return. Retain supported version/digest/permission/dependency and
   outer rollback rules. Add real mixed-order, malicious replay, nested-unit,
   late SQL/COMMIT failure and independent Core-only selection regressions.
4. Implement explicit unsupported query/export even on empty stores and minimal
   staged stored-invariant checks before normal domain/read/export/Search
   exposure. Exercise real poisoned-storage stop handling without hide/delete/
   repair, and ordinary general relations/unknown kinds without blanket refusal.
5. Keep both fences until one independently reviewed effective tree contains
   I3–I5 and matching routing support. I4 must retain full Parent/Event report
   keys plus SQL native-I7 binding; I5 must add semantics, original type/time,
   declared members/endpoints and whole-unit Admission. General I8 storage stays
   lawful. Re-execute actual packaged/installed implementation on both runtimes,
   including the retained Task B Event nodes and scoped/global metadata checks.

These are concrete implementation gates already required by Task C/C-F1, not new
owner policy questions. I3 full Parent typing, I4 support FKs, I5 event admission,
I6 wire/selection, I7 complete recovery/paired backup, I8 Search and isolated
wheel/sdist verification remain unimplemented/unaccepted by this review. No full
product pytest, Access cohort, live Provider, real catalog or release suite ran.

## Reproduction, preservation and lessons

`README.md` describes fresh-runtime reproduction. `review_sql.py` is independently
authored; `counterexamples.sql` extracts independent concrete SQL traces for
inspection; `F1-reproduction.sql` is byte-identical to Task D. Complete case
rowsets, SQL/parameters, input manifests, build records, attempts, actual exits,
schema inventories and public GitHub observations are inside `task-f-evidence.zip`.
No runtime binary or database is published. `artifact-index.json` binds the
published files. The review parent and final publication commit/tree are distinct;
the latter are reported in the Draft PR description and final user receipt.

Procedures used: cloud-environment-runtime, repository efficient investigation,
lessons-to-skills assessment and exact-tree CI verification. The frozen reviewed
tree and existing skills were not edited. Reusable lesson recommendation:
enumerate every durable representation of a staged unsupported operation, test
fresh and true-collision/no-op paths independently, and keep lawful opaque and
Parent controls. Malformed generated expressions/STRICT types can fail before a
BEFORE trigger; record the real code and full rowset instead of requiring one
trigger message for all errors. This recommendation is evidence-backed here;
it is not a new product policy or an instruction to repeat the author's cohort.
