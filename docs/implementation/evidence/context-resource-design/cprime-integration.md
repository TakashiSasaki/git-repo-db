# C′ evidence integrated into proposed ADR 0031

**G3=A selected on 2026-10-21; whole-package owner acceptance is separate.**
G1/G2 retain their independently reviewed corrected scope. Historical F2 permits
structural I8 support and temporarily withholds it in Admission; that is not the
current contract or a native-I7 SQL proof. The new [G3=A delta](g3-a/README.md)
contains separate executable inputs, runtime receipts and non-author review.
This map distinguishes those generations from unimplemented product integration.

## Provenance and dependency ledger

| Coordinate | Exact identity / role |
| --- | --- |
| Main at fresh inspection | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree `117d580b31098ecb8287281bd843894fdfad71fc` |
| #113 unchanged parent of #114 | `24f593861327328fa00dab0b83f956cec330a0ac`, tree `7318fdb1cb5ef4959d685bf2a3a1d9d91385c89e`; branch `audit/context-provider-agnostic-20261020` |
| #114 before G3=A revision | `3e6debe41f8e75f0a75be3a71cb1b12a0b70f0f5`, tree `87c4a5963e6fc15e43d919b884907251f038178d`; branch `docs/generalized-context-resources-20261020` |
| F1: original independently reviewed executable | `e9aba86f4530b2e683c77e23a4fe58bdf02192c5`, tree `7db7773f4cc2860b3818856b048a5832cdb00d6b` |
| Original report/PR publication | `22b58ce7ff59478f1a4c8c8ef89b17d2f0068590`, tree `fcc55256de88c711379d27e38b7eed0c63db6c4a`; contains [original report][original-report] and [original final review][original-review] |
| F2: corrected independently reviewed executable | `9eeacb28f7e4a426114a9ce40e2324b4da302817`, tree `8f78de68058582327beddbb656207659507d43c6` |
| R2: follow-up report and inspected #115 HEAD | `8ab57eb74068f5ba303b5985a335f0f76be4fdd2`, tree `10f5e85bf2c3a189bad0b7b3e9c58ad7929f35da`; contains [G1–G3 report][gap-report] and [independent review][gap-review] |

F1 composed SQL SHA-256:
`c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee`.
F2 composed SQL SHA-256:
`2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f`.
The exact [F2 input manifest][manifest] has file SHA-256
`30e0e1b75f476f0813bd410b5726fe952511125adbd2e1f0bc2fbf980d3605a3`;
it binds 18 executable/imported inputs, including predicates, SQL fragments,
author harness, focused probe, reproduction scripts and product sources.
The candidate predicate hash is
`ae495167209711d39776af42719fccd79b2c33aa2167a2dfaa454b9c4b1ba755`;
the author admission/harness hash is
`88dc60201b1aae7279ba57c76a6f4d10841514a24893405b56fa1ad64a8c0fc6`.
Read the frozen [predicates/constructor][predicates], [admission/author harness][harness]
and [focused probe][probe] alongside the SQL fragments. The design author's
[source verification receipt](cprime-source-verification.json) recomputes the
18 input hashes and both SQL hashes from Git objects and inspects runtime receipts;
it is not a fresh execution claim.

The follow-up reviewer executed F2 in a detached checkout and inspected its
manifest; R2 is the later report/evidence publication, not an executed candidate
revision. Author receipts record their pre-commit HEAD plus the actual input
hashes. The historical F1 result remains valid within its original obligations;
G1 extends missing coverage, G2 changes representation explicitly, and old T06
establishes structural acceptance only. No failed/successful receipt is rewritten.

The #113 → #114 stack is preserved. F1/F2/R2 are **external evidence dependencies**,
not ancestors of this design branch. Every experiment link here is commit-pinned;
no experiment branch was cherry-picked or merged to make relative links work.
Future integration must deliberately bring in the appropriate authorized code
and reconcile its effective tree; a citation does not implement that dependency.
#113 and #115 remain unchanged. The new local candidate copies explicitly attributed F2 inputs and applies a bounded delta; it does not merge or cherry-pick #115.

## Historical F2 executed scope and limits

Both genuine SQLite runtimes passed the bounded author and independent checks:

| Runtime | Actual source ID |
| --- | --- |
| SQLite 3.51.3 / Python 3.13.5 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| SQLite 3.53.1 / Python 3.12.14 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

For each runtime: nine packaged-baseline controls; 15 prior author groups with
163 steps; three focused groups with 46 steps; 75 adapted prior reviewer
observations; 39 independently authored focused observations. Counts overlap
and are not added. [Independent rerun summary][rerun] identifies the exact freeze.
[Author current][author-current] / [minimum][author-minimum], [focused current][focused-current]
/ [minimum][focused-minimum], [reviewer prior current][prior-current] / [minimum][prior-minimum]
and [reviewer focused current][review-current] / [minimum][review-minimum] retain
actual errors, SQL traces, transactions, rowsets, runtime options/pragmas and
FK/integrity checkpoints. Deliberately disabled enforcement is recorded as
unsupported configuration, not a clean supported-state result.

The candidate uses immediate FKs. T09 observes immediate statement failure,
rollback/reopen behavior and explicit misconfiguration controls; no deferred
FK mechanism or reverse endpoint-set COMMIT hook is claimed. The exact supported
connection enables foreign keys and recursive triggers. No SQL function performs
a database lookup for member existence or external authentication.

## Acceptance obligation map

Obligation numbers refer to the [schema acceptance contract](../../../architecture/context-resource-schema.md#u3c-experimental-acceptance-contract).
The F2 mechanisms/cases below are historical and bound to the hashes above.
The separate G3=A column identifies the added current obligation and evidence;
its exact cases/hashes/results are indexed in [the delta receipt](g3-a/README.md).
F1 remains earlier evidence, not an alternate encoding accepted by F2.
Layer numbers: **1 FK; 2 CHECK/generated projection; 3 trigger; 4 typed admission
and transaction; 5 selection/Exchange dependency/semantic qualification**.

| Obligation / required invariant | Historical F2 mechanism / evidence | G3=A addition and current evidence | Remaining product boundary |
| --- | --- | --- | --- |
| 1. One Parent authority; no new domain table or surrogate | Existing `resource_relations`, whole members/scope/provenance, generated Parent projections and `parent_report_typed_fk`. T02–03/T07/T10, IR01–05 and G1; [inventory][inventory] measures 19 tables/five Coverage columns. Layers 1–2. | Same authority; namespace metadata remains identity metadata. New typed Resource UNIQUE adds no Parent table or independently writable truth. See delta inputs/inventory. | Packaged composer/DDL/UDF/fingerprint and all consumers need implementation. 19 is a measured count, not a new immutable total. |
| 2. Complete child before Parent; original re-supply | Row-local namespace consistency without Parent existence FK; report referent FKs. T02–03/T11, IR01–05/G1. Layers 1–2,4–5. | Complete E survives missing I7. I7 arrival creates no report or Transfer; original unit must be re-supplied. I8 report can be saved/reread. | Every intake/Exchange writer must preserve actual keys/times/provenance and report missing dependencies without hidden payload staging. |
| 3. Typed Q-S10 Event and actual-event Admission | `resources_typed_event_fk`, typed `timeline_event`/`issue` references, `cp.event`; T04/T12/IR11–12. Historical Admission used temporary `QualificationRequired`. Layers 1–2,4–5. | Additional composite FK binds this Event's quoted support to its native Issue I7. Direct SQL I8 support must fail without Admission; Admission reports permanent Q-S10 violation. See delta direct-SQL errors and typed refusal. | Preserve the new SQL guarantee in I4; actual event eligibility remains I5. Neither authenticates Provider truth. |
| 4. Exact Event/Issue/support, no borrowing | Full seven-column ParentReport FK with source subtype/target kind; generated support; complete EventReport FK and non-NULL checks. T04–05/T07/IR04/09–13. F2's I8 SQL success is a historical counterexample. Layers 1–2. | Keep full ParentReport FK **and** native-I7 binding, same service and required non-NULL canonical projections. Reject another Event/service, mismatched real ReportKey components and wrong kind/subtype. Preserve explicitly quoted complete alternative report as a positive. | I4 cannot substitute Python withholding or `foreign_key_check` for actual SQL rejection; I6/I7 must revalidate full keys. |
| 5. Coherent EventReportKey endpoints and original alternatives | `cp_event_report_no_rebind`, `cp_endpoint_report_time`, `cp_relation_no_rebind`; full report reference, no Event-only winner. T05/T05-independent/T06/T08; IR06–08/13–20. Layers 1–4. | Parent and Event reports can have independent provenance/clock/observed time; endpoints within the same EventReportKey retain their coherent original values. Eligible I7 Transfer keeps I8 report. | Complete endpoint-set and atomic admission remain I5/I6; arbitrary direct SQL is not whole-unit atomic. |
| 6. Members/projections agree; no NULL bypass | `cp_resource`, `cp_relation`, `cp_endpoint` deterministic predicates; generated typed projections; explicit non-NULL checks. T01/T07/IR09–10/21–22/G1/G2. Layers 1–2. | Mandatory row-local SQL UDFs and canonical metadata consistency; same-service support CHECK; complete native-binding FK. New NULL/missing/malformed values and generated-column writes are probed. | Register every UDF and enforce FK/CHECK/recursive-trigger settings on every normal connection; no UDF table/network lookups. Arbitrary generic JSON members have no individual FK. |
| 7. No mutation/conflict-path rebinding; replay idempotent | Immutable/rebind guards on Resource/relation/Event report/endpoint; recursive REPLACE protection, exact-payload replay. T08–09/IR17–20/G1/G2. Layers 2–4. | Exercise UPDATE/DELETE/IGNORE/DO NOTHING/REPLACE/UPSERT and valid replay; I8 cannot become approved via replay or saved flags. Equal direct-SQL REPLACE may be refused. | Product connections/reopens/stored validators and I6/I7 intake must carry the same contract. Disabled enforcement/schema replacement is unsupported. |
| 8. Admission rollback preserves whole unit | `SAVEPOINT transfer_unit`, strict original timestamp validation, exact supplied endpoint set and declared Provider member existence. T05/T09/T11–12 plus independent second-endpoint failure. Layers 1,4–5. | Matching I7 cannot bypass ineligible actual event, missing member, original timestamp type or truncated endpoints. Mid-unit failure rolls back new unit and preserves E/Parent reports. | Product Exchange/import/recovery atomicity is unexecuted. SQL can store a report before all declared endpoints exist; no reverse-set FK/COMMIT hook or arbitrary-SQL transaction guarantee is claimed. |

## G1–G3 and compatibility disposition

G1 and G2 are **CLOSED — corrected and independently verified** in their frozen
experimental scope. G3 is **A SELECTED — 2026-10-21**: native I7 is E's semantic
Issue under Q-S10; attributed I8 reports survive, but cannot support its Transfer.
Missing correct I7 support is a dependency failure requiring original re-supply;
eligible I7 support requires every other Q-S10 condition. The
[scoped contract](../../../architecture/context-resource-schema.md#g3a-native-issue-binding-and-admission-boundary)
introduces no general namespace/Parent equality.

The [ADR compatibility matrix](../../../architecture/context-resource-schema.md#adr-compatibility-and-lifecycle-plan)
preserves ADR 0017 semantic keys, 0028 times/digests, 0029 five-store and Context
carry-forward, and 0030 roles/report pairing/typed-reference obligations. G3=A
preserves Q-S10's semantic Issue; no accepted ADR is changed or retired. There
is no remaining G3 option question or inferred whole-package acceptance.

## Verification generations

The previous integration task inspected F1/F2 hashes/receipts without rerunning
SQLite. Its [independent review](cprime-independent-review.md) remains unchanged
and historical at design freeze `060da07e0412e2d93dd4132332ab3bf908e3d8db`.
Its then-pending G3 disposition is not the current recommendation.

This revision adds a separately frozen [G3=A bounded experiment and review](g3-a/README.md).
Only its new receipts support the new SQL-delta claims; no old green receipt is
promoted to this HEAD. Current checks and final review are appended to the
[design review record](README.md#g3a-decision-integration-and-sql-delta).
Product gates remain in the [implementation handoff](../../context-resource-design-handoff.md#proposed-later-implementation-and-validation-sequence).

[original-report]: https://github.com/TakashiSasaki/git-repo-db/blob/22b58ce7ff59478f1a4c8c8ef89b17d2f0068590/docs/implementation/context-resource-u3-cprime-experiment.md
[original-review]: https://github.com/TakashiSasaki/git-repo-db/blob/22b58ce7ff59478f1a4c8c8ef89b17d2f0068590/docs/implementation/evidence/context-resource-u3-cprime/independent-review/final-review.md
[gap-report]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/context-resource-u3-cprime-semantic-gaps.md
[gap-review]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/independent-review/final-review.md
[manifest]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/input-freeze.json
[predicates]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/candidates/cprime.py
[harness]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/reproduction/run.py
[probe]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/probe.py
[resources]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/candidates/resources.sql
[relations]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/candidates/relations.sql
[transfer-fks]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/candidates/transfer-constraints.sql
[guards]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/candidates/guards.sql
[inventory]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/results/corrected-author/current/inventory.json
[author-current]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/results/corrected-author/current/results.json
[author-minimum]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/results/corrected-author/minimum/results.json
[focused-current]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/results/corrected-author/focused-current/results.json
[focused-minimum]: https://github.com/TakashiSasaki/git-repo-db/blob/9eeacb28f7e4a426114a9ce40e2324b4da302817/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/results/corrected-author/focused-minimum/results.json
[prior-current]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/independent-review/previous-75-current.json
[prior-minimum]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/independent-review/previous-75-minimum.json
[review-current]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/independent-review/corrected-current.json
[review-minimum]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/independent-review/corrected-minimum.json
[rerun]: https://github.com/TakashiSasaki/git-repo-db/blob/8ab57eb74068f5ba303b5985a335f0f76be4fdd2/docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/independent-review/author-rerun/summary.json
