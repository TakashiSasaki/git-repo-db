# C′ evidence integrated into proposed ADR 0031

**Recommendation: NOT YET READY for owner design acceptance.** G1 and G2 are
closed by independently reviewed corrections. G3 requires one owner decision.
The bounded physical candidate is demonstrated; the whole ADR acceptance
contract and future product implementation are not. This document maps existing
execution evidence, not a new SQLite run or owner approval.

## Provenance and dependency ledger

| Coordinate | Exact identity / role |
| --- | --- |
| Main at fresh inspection | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree `117d580b31098ecb8287281bd843894fdfad71fc` |
| #113 unchanged parent of #114 | `24f593861327328fa00dab0b83f956cec330a0ac`, tree `7318fdb1cb5ef4959d685bf2a3a1d9d91385c89e`; branch `audit/context-provider-agnostic-20261020` |
| #114 before this revision | `5244b98a9a302f082a07a526480faf438fc91838`, tree `4e44d04c9425942cdd1392a2a748f80f2ad485ed`; branch `docs/generalized-context-resources-20261020` |
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
#113 and #115 remain unchanged by this documentation task.

## Executed scope and limits

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
Every row below is bound to **F2**, the input hashes above and the linked receipts.
F1 supplies retained earlier evidence, not an alternate encoding accepted by F2.
Layer numbers: **1 FK; 2 CHECK/generated projection; 3 trigger; 4 typed admission
and transaction; 5 selection/Exchange dependency/semantic qualification**.

| Obligation / required invariant | Exact experimental mechanism and layer | Executed evidence | Remaining product boundary |
| --- | --- | --- | --- |
| 1. One Parent report authority; no new domain table, surrogate or duplicate writable truth | [resources.sql][resources] removes semantic Parent FK; identification metadata stays row-local. [relations.sql][relations] stores whole `members_json`, scope and provenance; generated `parent_service/kind/id` and `source_document_kind`, `parent_report_typed_fk` index. Layers 1–2; schema inventory shows the same 19 tables and five Coverage columns. | T02–T03, T07, T10; independent IR01–05 and G1 source/target controls; [inventory][inventory]. | Implement exact packaged schema/composer/fingerprint and all consumers; no experiment-only UDF is already a packaged product contract. |
| 2. Complete child before Parent; missing report/Transfer withheld, genuine re-supply required | `resources.identifier_namespace_*` has consistency CHECK without Parent existence FK. `resource_relations` target/source FKs and exact dependent references reject missing support. No pending payload table. Layers 1–2, 4–5. | T02–T03, T11; IR01–05; G1 missing Parent reaches FK, later re-supply and stable Document identity. | All acquisition/Exchange writers must preserve original payload/time/provenance, report missing dependencies, avoid synthesis and durably staged unadmitted bodies. |
| 3. Typed Issue-parented Timeline Event plus actual-event admission | `resources_typed_event_fk` over `reference_document_kind`; [Transfer constraints][transfer-fks] reference typed source and full Parent key with `timeline_event`/`issue`; `cp.event` checks structure; `structural_admit` checks normalized event type and supported `admit` adds temporary G3 withholding. Layers 1–2, 4–5. | T04, T12; IR11/12; G3 direct SQL versus supported admission; [review assessment][gap-review]. | Preserve real typed FKs in production; event type checks do not authenticate Provider truth. Q-S10 semantic Issue remains blocked by G3. |
| 4. Exact Event/Issue/support, no borrowed or missing support | Whole seven-column Parent key plus source subtype/target kind in composite FKs; generated support fields from report scope; complete event-report FK; mandatory non-NULL CHECKs. Layers 1–2. | T04, T05, T07; IR04/09–13; G3 SQL I8 counterexample and withholding. | Exact supplied report linkage is demonstrated. Rejection of a different Issue relative to native I7 is **not** a demonstrated SQL guarantee; owner must resolve G3 before broad acceptance. Python withholding is not an FK substitute. |
| 5. Same EventReportKey endpoint pairing, coherent whole report, original times and alternatives | Existing `transfer_event_report` group in `resource_relations`; `report_clock_json`, full report reference; [guards][guards] `cp_event_report_no_rebind`, `cp_endpoint_report_time`, `cp_relation_no_rebind`; no broad UNIQUE(Event) winner. Layers 1–4, 5 for qualification. | T05/T05-independent, T06, T08; IR06–08/13–20; exact replays and independent Parent/Transfer clocks. | Whole endpoint set must be admitted atomically; separate reports cannot be fused. I8 alternatives retained in T06 are explicitly structural diagnostics, not qualified Transfer success. |
| 6. Members/projections agree; NULL cannot bypass typed references | `cp_resource`, `cp_relation`, `cp_endpoint` deterministic predicates; generated `support_*` and typed properties; complete non-NULL checks. Global Document `reference_document_kind=''` is a non-key absence projection, with explicit null subtype scope. Layer 2 plus layer 1 typed FK. | T01, T07; IR09–10/21–22; G1 omitted subtype CHECK and global/scoped mismatch FKs; G2 vectors/alternate-profile refusal. | Keep deterministic functions registered on every supported connection and strict validation before SQLite affinity. No individual FK exists for arbitrary members of a general JSON array. |
| 7. Mutation, conflict-ignore and replay cannot bypass immutable payload/reference rules | Existing update/delete guards plus `cp_resource_no_rebind`, `cp_endpoint_no_rebind`, `cp_relation_no_rebind`, `cp_event_report_no_rebind`; recursive-trigger REPLACE protection. Exact payload comparison in replay helpers. Layers 2–4. | T08, T09; IR17–20 and later replay probes; G1 INSERT/IGNORE/REPLACE rebinding, G2 mixed-profile IGNORE rejection; G3 replay cannot qualify a raw-SQL mismatch. | Supported writer APIs, configured connections, reopens and stored validators must all carry the constraints. Disabling enforcement or replacing schema is outside the supported boundary. |
| 8. Rollback preserves complete units and original identity/time/provenance | `SAVEPOINT transfer_unit`; strict `validate_observation_us` on original report/endpoints; whole supplied endpoint-set comparison; actual declared Provider member existence loop; rollback on failure. Layers 4–5; referent failures originate in layer 1. | T05, T09, T11 missing member, T12 strict original types; independent prior-probe mid-unit second-endpoint FK failure; G3 rolled-back diagnostic and no-write withholding. | SQL alone can store a report before all endpoints exist. Every product intake/Exchange/recovery admission path must use whole-unit validation; experimental snapshot/reconstruction is not Product Exchange or paired-backup acceptance. |

## G1–G3 and compatibility disposition

G1 and G2 are **CLOSED — corrected and independently verified**. The schema now
specifies the tested independent/scoped forms and one Parent-TEXT encoding.
G3 is **OWNER DECISION REQUIRED**: retained attributed Parent report, structurally
valid exact support and semantically qualified Transfer are separate outcomes.
The [owner question](../../../architecture/context-resource-schema.md#g3-owner-review-required-before-complete-acceptance)
states the competing Q-S10 interpretations without choosing one.

The [updated ADR compatibility matrix](../../../architecture/context-resource-schema.md#adr-compatibility-and-lifecycle-plan)
preserves ADR 0017 semantic keys, 0028 times/digests, 0029 five-store and Context
carry-forward, and 0030 roles/report pairing/typed-reference obligations. G3 is
marked unresolved rather than silently weakening 0030. No accepted ADR is edited
or retired; a substantive answer requires explicit governance/carry-forward.
One blocker concerns this newly examined semantic scope, not a reopening of the
earlier migration scope or the fixed owner ledger.

## Documentation-only verification

The integration author inspected F2 input hashes and composed SQL receipts, R2
review/author receipts and the original F1 report. This task does not rerun SQL,
product tests, packaging or release validation. Local documentation/link/scope
checks and a separate frozen-document review are recorded in the [design review
record](README.md#evidence-integration-revision). Future product work and review
gates are in the [implementation handoff](../../context-resource-design-handoff.md#proposed-later-implementation-and-validation-sequence).

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
