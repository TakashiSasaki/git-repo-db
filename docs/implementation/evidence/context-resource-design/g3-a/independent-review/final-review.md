# Independent final review: G3=A decision and native-Issue SQL delta

**READY FOR OWNER DESIGN ACCEPTANCE — no substantive finding remains in this
bounded design/evidence review.** This is readiness for the owner's decision,
not acceptance of ADR 0031, production implementation approval, merge permission
or runtime/distribution acceptance. ADR 0031 remains proposed with date null and
`replaces: []`; PR #114 must remain Draft on #113.

## Independence and frozen subject

The reviewer authored none of the revised design documents, candidate SQL/UDFs,
Admission helper or GA author scenarios. Review and execution used a separate
detached checkout of commit **4c07cb8ecc4d744ddfb8c3908deb91d8ad72f6f9**, tree
**e171de9f2459b0ade409bebb40787b850d88ff5e**. No tracked reviewed file or remote
ref was edited. The independently authored [probe](probe.py) and this review are
later evidence outside that reviewed tree. Initial parallel author investigations
were not substituted for this final review.

Read root AGENTS.md, ADR index/governance, accepted ADRs 0017/0028/0029/0030,
current ADR 0031/schema/handoff/index/eight-obligation map, new SQL/UDF/Admission
sources, F2 executable sources and #115's fixed semantic-gap publication.
Historical F2 is `9eeacb28f7e4a426114a9ce40e2324b4da302817`; its publication is
`8ab57eb74068f5ba303b5985a335f0f76be4fdd2`. Neither that branch nor its old
receipts was changed. The former QualificationRequired result remains historical.

The [checks](checks.json) verify all ten new executable-input hashes, the exact
input manifest SHA-256, 28 pinned blob targets and unchanged product source tree.
They independently verify author raw/compressed receipt hashes and both runtime
identities against the reviewer reruns. Actual stack parent is #113
`24f593861327328fa00dab0b83f956cec330a0ac`; update baseline is #114
`3e6debe41f8e75f0a75be3a71cb1b12a0b70f0f5`. Both diffs pass whitespace checks;
protected product/dependency/test/workflow/accepted-ADR paths are unchanged.

## Independently executed results

Both actual runtimes ran the same final probe bytes, SHA-256
`bd94905307096060cb20bb794e2a4c655e69d3e77e26566a5ac1a301ef0d8a92`:

| Runtime | Actual Python and SQLite source ID | Independent execution |
| --- | --- | --- |
| SQLite 3.51.3 | Python 3.13.5; `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` | 99 own observations, zero failures; separate 11-group/292-step author rerun passes |
| SQLite 3.53.1 | Python 3.12.14; `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` | 99 own observations, zero failures; separate 11-group/292-step author rerun passes |

These counts overlap in behavior and include explicit transaction markers; they
are not added to each other or presented as distinct product test cases. Raw
[minimum](minimum.json.gz) and [newer](newer.json.gz) receipts preserve every own
observation's SQL trace, actual SQLite error name/extended code, pre/post rowsets
and transaction state, plus Python/runtime source IDs, compile options, PRAGMAs,
registered UDF flags, module paths and input binding. [Receipt manifest](manifest.json)
records exact raw and compressed hashes. Author rerun receipts are preserved
separately under `author-rerun/`; rerunning author cases is not probe authorship.

| Independent probe group | Observed result |
| --- | --- |
| IRG01 | Complete native-I7 Event exists before I7 without synthesized Parent. I8 Parent report is saved/reread. Direct SQL I8 report raises **SQLITE_CONSTRAINT_FOREIGNKEY / 787** inside BEGIN, rows unchanged, then explicit ROLLBACK. Admission raises permanent `Qs10Violation`. Eligible I7 report/endpoints COMMIT; I8 report remains. Normal replay revalidates/deduplicates. |
| IRG02 | Missing I7 row and missing complete I7 report are dependency failures. I7/Parent arrival generates no Transfer; only original report re-supply succeeds. Raw missing-report SQL reaches FK787. |
| IRG03 | Explicit alternative complete I7 ParentReport succeeds with independently different Parent/Event provenance, clock and observed time. Mixing real components from different reports, Event or service fails; endpoints retain their own EventReport time. |
| IRG04 | NULL/malformed/missing/noncanonical support or Identity, wrong kind/service/subtype and generated-column writes fail SQL. An ordinary comment cannot claim the Timeline subtype. |
| IRG05 | Direct UPDATE, DELETE, equal-input REPLACE and malicious IGNORE/DO NOTHING/UPSERT paths cannot rebind Resource metadata, Parent reports, Event reports or endpoint support. Actual errors and unchanged rowsets are recorded. |
| IRG06 | Correct I7 alone does not accept actual `closed` event, bool/float/string original timestamps or truncated endpoints. A second endpoint FK787 rolls back the entire Admission savepoint, leaves original E/Parent unchanged and allows outer COMMIT; good original re-supply then succeeds. Stored valid rows do not approve invalid replay. |
| IRG07 | Recursive-array, genuinely empty-array, empty-string and nested-empty native Issue identities work through exact canonical binding. Each still rejects I8 support with FK787. |
| IRG08 | General scoped Document namespace differs from semantic Parent without imposing native equality. Independent Documents, their Document child, unknown kinds and genuine empties survive. G2 decoded alternative and malformed known PR no-fallback inputs fail. |
| IRG09 | **Same normalized fixtures, exact old/new differential:** F2 direct SQL stores and COMMITs the I8-supported Event report and both endpoints with clean FK checks. The new schema rejects the identical Event-report tuple with FK787, unchanged rowsets and explicit ROLLBACK. This demonstrates the new constraint rather than inheriting an old receipt. |

IRG09 verifies old composed SQL SHA-256
`2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f`
and new SQL SHA-256
`ee8618874d061b8fc71bf83be94a10b1d009d7d1859ddd145e560c7755c41cd0`.
It independently imports F2 from exact Git objects using its own module name;
recorded module paths prevent accidentally testing the new candidate twice.

## Contract and enforcement assessment

G3=A is dated 2026-10-21 and confined to Q-S10. Native I7 is E's semantic Issue;
I8 remains a lawful attributed Parent report but permanently ineligible Transfer
support for E. Correct I7 support missing from storage is a re-supplyable
dependency, while eligible I7 still needs every other Q-S10 requirement. No
pending A/B choice, deletion/correction/winner selection or general namespace
Parent-equality rule is introduced.

The generated service/kind/Canonical ID comes from the sole support payload.
Explicit non-NULL and same-service checks close composite-FK NULL exemptions.
The wider Resource UNIQUE has matching BINARY comparison and namespace metadata
is checked against Identity by mandatory SQL `cp_resource`. The new same-Event,
Timeline/Issue/native-I7 FK is additional to the complete ParentReport FK;
endpoints still reference the complete Event report. Generated projections are
not independently writable or a new Parent authority. Child Resource admission
has no Parent-existence FK. Actual table count is 19 as measured, without making
that a new absolute invariant.

Required baseline and candidate UDFs are registered as deterministic; their actual
flags and connection settings were independently queried. FK/recursive triggers
and trusted schema are ON, CHECK ignoring and deferred-FK mode OFF. Python UDFs
require trusted schema because they lack SQLITE_INNOCUOUS. Bounded predicates
perform only row-local parsing/validation, never table lookup or network calls.
Table searches occur openly in FK/trigger enforcement and Admission. SQL-invoked
predicates are not an optional Admission check.

All fixed A3/B3/U1–U5/U2-E2 choices, PK triple, String/recursive-Array identity,
Canonical Parent-ID TEXT encoding, PR identity/no-fallback, sole resource_relations
Parent authority, five stores, permanent Repository identities, six roles,
immutable competing claims/Dispositions, Source positives, five-column Coverage,
classified times/provenance, Access separation and no Witness/Publication/new
Mapping/Link store are preserved. No accepted ADR body is edited or retired.
The ADR index correctly distinguishes main's #112/ADR 0030 integration from
unimplemented ADR 0031.

## Limits and handoff

SQL proves native-I7 binding and complete structural reference identity under the
required connection settings. It does not authenticate Provider information,
prove actual external event type, original pre-affinity timestamp type,
arbitrary-length declared-member existence, the complete supplied endpoint set
or arbitrary direct-SQL whole-unit atomicity. Author GA07/GA10 deliberately
preserve those limitations; independent IRG06 verifies the supported Admission
transaction guarantee separately. No saved row or checked flag replaces current
semantic revalidation.

I1 common Identity → I2 Resources/DDL → I3 Parent reports → I4 native-I7 Transfer
SQL → I5 typed Admission is coherent. I6 generic Relation/Collection/Exchange can
start from I1–I3; Transfer additionally needs I4/I5. I7 stored validation and
Backup/Recovery need I1–I6 persistent formats. I8 basic reads may parallel I1–I3,
while Transfer consumption/final integration must agree with I4–I7. V1 validates
actual supported runtimes stage by stage; V2 follows all engineering work with
outside-checkout isolated wheel/sdist-derived wheel and bundled DDL/UDF/fingerprint
and independent final integrated-tree checks.

Product replay/import/recovery, integrated Exchange/backup/query/Search, packaged
UDF/DDL/fingerprints and distributions remain unimplemented/unexecuted here.
These are explicit future I6/I7/I8/V2 acceptance obligations, not residual G3
owner-choice blockers or failures of this bounded experiment. Hosted CI for the
final publication HEAD is outside this frozen source review and must be bound
separately. No whole-ADR acceptance, merge, runtime activation or P8 is claimed.

## Reproduction

Extract the six exact F2 candidate files named in `manifest.json` from
`git show 9eeacb28f7e4a426114a9ce40e2324b4da302817:docs/implementation/evidence/context-resource-u3-cprime/candidates/FILE`
into a fresh external directory. The probe checks the old composed SQL hash.
Run both interpreters against the same frozen checkout and probe:

```sh
python probe.py --repo /path/to/frozen-checkout --f2-candidates /tmp/exact-f2-candidates --output /tmp/newer.json
LD_LIBRARY_PATH=/tmp/g3-sqlite-runtime/minimum/lib /usr/bin/python3 probe.py --repo /path/to/frozen-checkout --f2-candidates /tmp/exact-f2-candidates --output /tmp/minimum.json
G3_MIN_SQLITE_LIB=/tmp/g3-sqlite-runtime/minimum/lib sh /path/to/frozen-checkout/docs/implementation/evidence/context-resource-design/g3-a/reproduce.sh /tmp/independent-author-rerun
```

The executed review used `/workspace/g3-review-final` and new outputs under
`/tmp/g3-independent-final`. Ruff lint and format checks pass for the final probe;
both authoritative receipts carry the final probe hash above. The existing
lessons-to-skills procedure was assessed: source binding, exact-runtime identity,
conflict-before-ignore guards and current-versus-historical evidence separation
are already covered by existing procedures; no new skill rule is necessary.

Publication losslessly compresses stdout logs as `.log.gz` to preserve raw
whitespace while keeping `git diff --check` clean. Pre-transport summary/manifest
snapshots are retained; raw log hashes/bytes and all execution results are unchanged.
