# C-F1 author verification

**Disposition: correction authored and verified; independent re-review pending.**
This is the correction author's evidence, not independent approval or a change
to Task D's NOT READY finding on the old inputs. The same conversational agent
previously performed Task D and is now acting as the correction author; no
independence is claimed for this work or its routing-model tests.

The full [Task D report](../adr0031-i2-independent-review/REPORT.txt), literal
[minimal SQL](../adr0031-i2-independent-review/F1-reproduction.sql), and archived
receipts were inspected first. All 60 indexed members of Task D's ZIP were
verified. Its six original failure manifestations and 133-case success reports
were retained as historical observations, not copied into new successful counts.

## Input and implementation scope

Base #121 HEAD: `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6`.
Base tree: `927288ecc20082144887fd668636b35171b647dd`.
All 3,745 predecessor tracked files are hash-bound in
[base-input-manifest.json](base-input-manifest.json) and remain unchanged.
The old Resources fragment, UDFs, codec, typed index/FK rewrite and endpoint
fence are reused without modification. The new composer appends only the
[report fence](fence.sql); the full before/after SQL is inside the new archive.

Before composed SQL SHA-256:
`c8fd84cf5e535d5f4c585d31a2e0ad0e4c791bb9cd7649f243e0bc1c6bfd223e`.
After composed SQL SHA-256:
`0d7cb70c6f8acc46df8944120ef70902b9eef80a02d5f7597eafb926bb399669`.

The actual physical-schema comparison has exactly one delta:
`i2_transfer_report_stage_fence` on `resource_relations`. Resources and the old
endpoint trigger are equal SQL objects before/after. No table, column, key,
index, FK, UDF, role, fingerprint or existing immutable guard changes.

## Actual runtime construction and execution

Both amalgamations were downloaded afresh from sqlite.org and independently
built for this author task, using `cc -O2 -fPIC -shared`, THREADSAFE=1, FTS5,
COLUMN_METADATA and RTREE. Both compiler processes exited 0. They are new builds,
not a reuse of Task D's executable environment or results. Python is the dynamic
`/usr/bin/python3.13` (3.13.5). No SQLite version constant was overridden.

| Actual SQLite | Actual `sqlite_source_id()` |
| --- | --- |
| 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Normal profile in both lanes: foreign_keys=1, recursive_triggers=1,
ignore_check_constraints=0, defer_foreign_keys=0, trusted_schema=1,
synchronous=3/EXTRA, UTF-8, journal_mode=memory for isolated cases. The fresh
file/reopen control uses SQLite's default DELETE journal with both fences.
The deliberately deferred-COMMIT case is marked as an unsupported-profile
control. No WAL durability, performance, concurrency or authentication claim.

| Final case family, per runtime | Executed | Passed |
| --- | --- | --- |
| Exact Task D minimal SQL before and after | 2 | 2 |
| SQL cases on the normal corrected candidate | 61 | 61 |
| SQL conflicts against diagnostically injected reserved rows | 14 | 14 |
| Normalized routing-model cases | 32 | 32 |
| Routing-model handling of injected unsupported storage | 8 | 8 |
| Caller savepoint rollback | 1 | 1 |
| Explicit deferred-COMMIT rollback control | 1 | 1 |
| **Total per runtime** | **119** | **119** |

Both lane processes exit **0**. A separate launcher measured the actual overall
runner OS exit **0**. Case names are duplicate-free. Counts are case groups;
their constituent SQL, setup traces and complete rowsets are preserved, not
misrepresented as 119 single SQL statements. In the 61 ordinary SQL cases,
41 refusals are expected successes. Python StageUnsupported/StageStoredViolation
checks are a different family and are not counted as SQL constraint guarantees.
The two runtimes have the same result; their overlapping cases are not called
238 distinct requirements. Intermediate execution is not added to final totals.

## Observed before/after contract

- The exact old minimal SQL admits one reserved report; the existing reference
  reader returns one Provider-only report. I7 Resource and endpoint counts are
  zero, and FK/integrity checks are clean. This reproduces F1 on the old input.
- The same literal SQL on the corrected composition refuses the reserved
  INSERT with `SQLITE_CONSTRAINT_TRIGGER` / code **1811**, message
  `Transfer reports require I3-I5 implementation`. Its complete pre/post
  statement rowsets are equal. I7, Parent, report and endpoint rows are absent.
  Complete child and Provider identities registered earlier remain admissible.
- Both endpoint roles still refuse under INSERT, OR IGNORE, DO NOTHING,
  REPLACE, OR REPLACE, UPSERT-update and UPSERT-WHERE-0. The report path refuses
  under all those verbs with dependencies missing or present. Forced-PK conflict
  tests use explicit unsupported injected fixtures and restore the guards before
  the statement under test; they do not grandfather stored Transfer rows.
- NULL or malformed reserved payloads cannot escape the unconditional trigger.
  Generic-to-reserved UPDATE and UPSERT-update hit the retained immutable guards.
  Multirow INSERT and OR IGNORE statements containing a later reserved report
  roll back their earlier generic row. Statement ABORT leaves earlier transaction
  prefixes pending until the caller's explicit unit rollback.
- General I7/I8 Parent reports, ordered multi-member reports, opaque relations,
  distinct BINARY names and identical ordinary replay remain admissible under
  the common row contract. An I8 Parent report is retained even when the Event's
  native I7 Resource is absent. This does not prove completed I3 typed reports
  or make I8 eligible Transfer support. Global/scoped Document identities and
  child-first admission remain usable; later I7 arrival creates no report.
- The normalized routing model refuses typed Transfer admission, both endpoint
  representations, report-only import, explicit Transfer query/export, and
  malicious replay shortcuts before effects. Mixed selected transactions are
  preflighted in either order; ordinary generic import/export works. A normal
  later FK failure rolls back the model's earlier import prefix.
- Unexpected reserved storage is refused by the model's ordinary read/export
  and staged-storage check. The existing unadapted reference reader is used only
  as the before/after SQL diagnostic. The prototype guards are not installed in
  the product, and no real production query/import/Search path was tested.

## Evidence and limits

[minimum-summary.json](minimum-summary.json) and [newer-summary.json](newer-summary.json)
retain actual source IDs/options/pragmas and input/schema hashes. The new
evidence ZIP contains full before/after rowsets, SQL parameters and traces,
error codes, build provenance, launcher and lane receipts, and pre/post input
bindings. These original runs used fresh synthetic DBs; no real data was used.

An initial tool call reported an exec transport disconnection after the first
run had actually completed 116 cases per runtime; complete child
receipts were present. That run is preserved as initial evidence, not used to
infer the missing transport result. A separate launcher measured the final
119-case runner's exit. Additional positive controls and unique case names were
added before the final freeze; no product or predecessor input was changed.
The initial probe source was reconstructed from the recorded edit and matched
exactly against that run's pre/post input hash; it is retained with the initial
receipts, without relabeling them as final 119-case execution.

No new Task C 133-case rerun, Task B cohort, installed-distribution test, product
pytest suite or release qualification is claimed. The one-object schema delta,
unchanged-input hashes and focused positive cases bound this correction's scope.
I3 Parent reports, I4 native-I7/full-report FKs, I5 actual Event completeness and
whole-unit Admission, and I6–I8 product integration remain separate work.

The [addendum](I2-F1-ADDENDUM.md) updates Task C's implementation plan and test
matrix additively. Product acceptance must implement the stated API/import/read
constraints and pass a new independent review. No self-issued READY verdict,
Accepted ADR change, branch rewrite, merge, release or deployment is supplied.

Publication follows the repository's exact-tree CI procedure and
lessons-to-skills assessment. No skill file is changed in this scoped correction.
The verified reusable lesson for a future Context-guidance update is to enumerate
and fence every stored representation of an unsupported operation, including
report-only/Provider-only forms; retain the positive general-report controls.
