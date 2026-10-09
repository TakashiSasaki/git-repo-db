# Independent model integration audit

Baseline: PR #10, commit `1c69a868f65b9637a7b8cf00d2c68a4ba05b2faa`.
Review scope: packaged production DDL, acquisition writers, ordinary readers,
profile/current selection, exchange admission and CAS recovery. This is a critical
review independent of the implementation owners. Synthetic data only.

## Reproduced baseline defects

### A1 — A published decision could acquire new predecessors

The supplied focused reference model prohibited updates/deletes of predecessor
rows but allowed additional inserts after the decision had already affected
ordinary selection. Create decision E2 in E1's scope with no predecessor and
commit: two heads, no active selection. Insert edge E2 -> E1 and commit: one head,
E2 active. E2's UUID and decision fields did not change, and foreign-key checking
remained clean. The same immutable decision acquired a different meaning.

Reproduction used the reference test fixture's existing E1 and passed profile,
called `add_decision(E2, RS, 'repository', 'body', P1, V1)`, committed, then inserted
`(E2, E1, RS)` into `parser_profile_selection_predecessors`. Active counts were
**0 before, 1 after**. The baseline reference's 31 tests do not exercise this.

Required resolution: an immutable predecessor manifest, exact membership check
at publication, no later edge insert/update/delete/replace, and no provisional
activation while dependencies remain unsealed or staged. This is an enforcement
defect in the reference, not a change to D6–D9.

### A2 — Shared document/review values were mutable parser projections

In the production baseline, insert a document with author `first`, then update
its author to `second` and metadata to `{"parser":"second"}`. Both changes
succeed with all foreign keys enabled and `foreign_key_check` empty.
`ApiFacts.document` performs exactly this shared-row update, and also overwrites
`reviews.payload` and `review_comments.payload` for subsequent inputs.

Required resolution: immutable result-owned facts store parser-dependent author,
URL, metadata and review/thread values; shared identity rows are not selected
parser projections. Ordinary queries must use an explicitly selected verified
profile and the selected eligible fact, preserving other interpretations.

### A3 — SQLite structural integrity did not detect physical CAS corruption

Insert `stored_bytes` using SHA-256(`good`) but body `bad!` and length 4. Admission
of `good` correctly raises `PAYLOAD_CORRUPTION`, yet the baseline leaves
`unresolved_payloads` empty. `PRAGMA integrity_check` returns `ok`.

Required resolution: full byte hash verification, durable physical diagnostics
plus local quarantine, explicit atomic repair, and source/copy verification for
backup/restore. Merely running SQLite's integrity check does not meet CAS-7 or
CAS-24/CAS-39/CAS-40.

## Integration review status

The baseline counterexamples A1–A3 are addressed by sealed selection DAGs,
result-owned immutable facts and explicit physical CAS integrity management.
The additional independently reproduced defects below have corresponding fixes
and regression tests. The review does not claim complete design compliance:
`model-integration-status.md` maps every D1–D38/CAS-1–CAS-75 decision and records
remaining work. Whole-application/package/CI acceptance belongs to the final
validation record, with its tested HEAD; focused tests below are separate evidence.

## Defects found during integration and regression coverage

### A4 — SQLite NUL termination bypassed borrowed UUID guards

A valid UUID followed by `\x00hidden` was accepted into `parser_profiles`:
SQLite text `length`, `replace` and `GLOB` considered only the prefix, so the
borrowed trigger accepted the noncanonical identifier. A direct insertion with
foreign keys enabled reproduced this, with no FK violations. Every portable
UUID guard now checks the encoded byte length as well.

Regression: `test_sqlite_nul_termination_cannot_hide_noncanonical_profile_uuid`.

### A5 — Sealing inputs alone could lose later-arriving output facts

A parsed result can have complete input references but an incomplete received
set of generated facts. A receiver must not publish it merely because the
currently known input set is complete: sealing would permanently reject the
omitted fact when it arrives. An immutable publication output manifest now
identifies the exact portable fact set. SQL publication checks exact membership;
late facts keep the publication staged until that membership is satisfied.

Regressions: `test_publication_seals_fact_membership_not_only_input_membership`
and `test_late_generated_fact_keeps_result_unpublished_until_manifest_complete`,
including reversed record order, repeated import and unchanged result/fact IDs.

### A6 — Mutable Source provenance was misclassified as identity collision

After a successful import, changing only the sender's Source name/settings and
exporting again originally staged that Source as `conflict:immutable_content`.
The immutable identity subset (registration UUID, service membership, discovery
kind) was unchanged. The generic content-digest comparison bypassed the special
Source handling. Variant definitions now remain historical provenance without
changing the receiver's local operational settings/name or poisoning dependent
records.

Regression: `test_received_source_configuration_variants_are_provenance_not_identity_conflicts`.

### A7 — Source capability declarations were mistaken for Source-owned facts

The repository exchange initially excluded every row with `owner_kind='source'`,
including declarations in `parser_profile_capabilities`. A profile supporting
both repository documents and source inventory therefore arrived with a missing
capability, and its full-profile verification could never be admitted. Capability
declarations describe the whole immutable profile and are now exchanged; actual
Source-owned evidence/results remain excluded from a single-repository unit.

Regression: the delayed-output-fact exchange test uses a mixed-owner profile and
requires all records, including its verification, to leave staging.

### A8 — Late dependency promotion changed Source provenance's sender

Staging initially retained the record but not its original catalog identity.
When a different sender supplied the missing dependency, the pending Source
provenance was attributed to the latter sender. Durable staged records now retain
the original intake catalog and use it during promotion.

Regression: `test_late_source_dependency_does_not_relabel_the_original_sender`.

### A9 — Parser-dependent repository names needed explicit generator ownership

A name observation for repository R2 with a parsed result owned by R1 was
accepted by a plain result FK, with an empty `foreign_key_check`. Inventory-derived
names can legitimately be emitted by a Source-owned result, so merely imposing
repository ownership would be incorrect. The fix must represent repository or
Source generator ownership explicitly, check the relevant composite FK and
Source membership, and include generated names in output sealing. Manual naming
evidence remains separate from generated parser facts.

Resolution: generated names now have explicit repository/Source generator
ownership, owner-keyed FKs and a Source-membership guard. Manual evidence is
represented separately. Generated names participate in the immutable output
manifest and cannot be appended after result publication. A follow-up review
also found unfinished/unselected generated names leaking through the historical
name view; that view now requires a published usable result from the explicitly
selected profile. Quarantine removes affected derived names while preserving
manual name evidence.

Regressions: `test_generated_repository_names_enforce_generator_ownership`
(four wrong-owner/NULL/membership attacks) and
`test_generated_name_is_in_output_manifest_and_cannot_arrive_after_sealing`.
The separately owned parser-model regression
`test_repository_names_require_published_selected_usable_parser_result` was
confirmed to fail before the eligibility fix and pass after it.

### A10 — An immutable collision must also invalidate the first arrival's current

Retaining the first fact while staging a conflicting same-UUID variant is not
sufficient: if the first variant stays eligible for current, A-then-B and
B-then-A expose different winners. Exchange now derives durable dependency
blocks for the associated parsed result and selection scope, including facts
originally created locally. Both arrival orders preserve existing bytes/history,
retain the conflict and expose no current fact.

Regression:
`test_same_fact_uuid_conflict_blocks_current_independently_of_arrival_order`
(two arrival orders).

### A11 — Repository ETags needed immutable historical evidence

Repository ETags originally survived only in the operational validator cache,
which is deliberately excluded from exchange. Fetch context now retains response
status and exact ETag; 304 completion evidence records the same response metadata.
Valid acquisitions blocked by corrupt CAS also retain this context in staging.
The response-header whitelist excludes `Set-Cookie` and other unrelated headers.
Receiver validator cache remains independent.

Writer regressions:
`test_repository_response_etag_survives_as_immutable_history_including_304`
and the staged-corrupt-payload context test. The writer's focused run passed
12 tests in 5.20 seconds; these results are separate from the independent suite
below.

## Independent test scope

`tests/integration/test_catalog3_adversarial_model.py` bypasses application
admission for SQL attacks and also exercises real exchange/CAS admission. Its
33 tests passed after A4–A10 fixes. Each fixture executes the production packaged
DDL and checks both `PRAGMA foreign_key_check` and `PRAGMA integrity_check`.
Coverage includes NULL owner bypass, cross-owner input references, whole-profile
verification failures, exact verification invalidation, CR inheritance blocking,
predecessor sealing/cycles, immutable replacement, interrupted repair rollback,
invalid bytes rejection, delayed exchange dependencies, Source provenance,
result-owned repository names and both immutable-conflict arrival orders.

Reproduction command at this checkpoint:

```sh
uv run --no-sync pytest tests/integration/test_catalog3_adversarial_model.py \
  tests/integration/test_catalog3_parser_model.py::test_repository_names_require_published_selected_usable_parser_result -q
```

Result: **34 passed in 1.45 seconds** (33 independent attacks plus the generated-name eligibility regression), with no skips or expected failures. This
command uses direct production DDL and explicit synthetic profile fixtures;
it does not enable the runtime parser bootstrap.

This focused result is not whole-application acceptance. Development runtime
checks may use the explicitly synthetic parser bootstrap; final installed
acceptance must run without that bootstrap, using genuine packaged verification
evidence bound to the implementation. Final totals/commands belong in the
integration validation report.

## Retired compatibility-only tests

The GitHub runtime test file removes the obsolete v2 fixture builder and exactly
two importer-only tests: initial imported conditional/listing reuse (one case),
and imported-listing resume across two boolean options (four cases). The legacy
importer is retired for the new incompatible format. Fresh acquisition,
conditional responses, preserved page resume, interrupted Git, coverage and
independent reparse scenarios remain. The old 'reparse is a no-op' assertion is
replaced with the required separate parsed result and unchanged remote fetch
identity/time/current selection.

## Remaining architectural and validation limits (historical PR #11 checkpoint)

- Low-level Git structural/text projections (`commits.metadata`, tree rows and
  `contents`) remain shared object data. Snapshot/ref/code observations are
  result-owned, but arbitrary alternative interpretations of every low-level Git
  field are not yet separately modeled. D29/D36 are therefore partial.
- General self-authored JSON provenance needs more schema-aware reference and
  ownership validation. The current concrete checks cover portable payload
  references, FK exchange envelopes and 304 original observation/result/fetch
  evidence; they do not establish CAS-3/CAS-9 for every JSON document.
- Full-repository exchange is implemented, including raw byte closure and delayed
  receipt. A selected-fetch/partial-collection exporter is still absent.
  Complete-claim dependency manifests are conservative and should be narrowed
  only after scope-specific proof tests; no unsupported completeness may be added.
- Restore's atomic no-replace primitive currently targets Linux. Fault injection
  and process-kill tests do not prove behavior under hardware power loss or every
  filesystem failure. Retained rejected acquisitions need explicit replay after
  repair; repair itself deliberately does not fetch or rewrite acquisition history.
- Legacy identity reconciliation is absent after deliberate v2/migration removal.
  This is permitted for the pre-release format; any future legacy intake still
  requires D2's original-record proof.

These limits are implementation work, not requests to reopen established design
choices. CAS-41 remains unselected, CAS-76/77 remain outside this change, and
Source-wide inventory exclusion follows the single-repository exchange contract.

## A12 — Repository inventory projections need Source ownership

The final integration run exposed a stale `repositories.metadata.private` dependency after removing parser output from shared registration rows. Restoring that shared projection would let unrelated interpretations compete for one value. `repository_inventory_observations` now stores one immutable member interpretation per Source-owned parsed result, with owner/membership checks, portable observation UUID and sealed output-manifest membership. `current_repository_inventory_observations` derives eligibility from the Source inventory selection. Ordinary repository output returns a provenance-bearing list instead of merging different Sources. Source-wide exchange exclusion continues to apply.

Reproduction and regression: `tests/e2e/test_github_sync.py::test_private_inventory`, `tests/integration/test_catalog3_job_plans.py`, and reader/profile/CLI suites. The focused private-inventory/profile/CLI run passed 19 cases. Final complete acceptance is recorded in the validation evidence.

## Independent remaining-contract review — 2026-10-09

This new review starts from PR #11, commit
`d76ebc776c9e72f565dc3007c878e2002c5f4e8e`, on
`feat/complete-model-contracts`. A1–A12 and the remaining-limit section above are
historical checkpoint evidence; their original findings and test receipts are
preserved. The current implementation is reviewed independently of its authors
against D29/D36, CAS-3/CAS-9 and CAS-46/CAS-49. Decision classification remains in
the separately maintained status matrix.

The reviewer executed the complete production DDL with foreign keys and
recursive triggers enabled, attacked SQL and actual exchange admission, and
exercised ordinary readers over disposable Git repositories. The review also
read the implementation of parser execution/selection, the JSON registry and
generated guards, selective closure, completeness proofs, quarantine,
maintenance and indexes. Implementation summaries were not used as acceptance
evidence.

### Reproduced defects and current fixes

The regressions in this table are in
`tests/integration/test_catalog3_remaining_adversarial.py`. R1–R13 were observed
by this reviewer against the working implementation before their corresponding
fixes. R14 was independently reproduced by the integration coordinator and then
covered by this reviewer's executable SQL/registry regressions.

| Finding | Observed failure | Current fix and executable regression |
|---|---|---|
| R1 — Arbitrary completeness envelope | A complete claim with only an unrelated repository record in `requires` could be admitted without acquisition proof. | Proof is derived from exact owned evidence, and envelope equality is checked on receipt. `test_unrelated_present_record_cannot_prove_complete_coverage`. |
| R2 — Git format guard lost during fact split | A result-owned SHA-1 commit could point to a SHA-256 tree while all ownership FKs passed. | Commit/parent/tag/tree/manifest format guards were restored. `test_git_commit_cannot_bind_tree_from_another_object_format`. |
| R3 — Source ownership differed between scalar and array references | A nested repository-reference array in Source-owned evidence accepted a repository outside the Source membership; the equivalent scalar reference was rejected. | Scalar and list references use the same SQL ownership predicate. `test_source_owned_nested_json_rejects_outside_repository_membership` covers both encodings. |
| R4 — A subset marker proved a larger collection | A collection containing F0 and F1 accepted a completion marker naming only F0, which exported as complete proof. | Markers seal the exact actual root/child collection fetch set and terminal boundary. `test_collection_subset_manifest_does_not_prove_complete_collection`. |
| R5 — Published Git input could gain objects | A new `repository_object_sources` member could be appended after publication, changing the acquired input represented by an immutable result. | Exact `git_acquisition_publications` object/root manifests seal input membership before result publication. `test_published_git_input_cannot_acquire_late_object`. |
| R6 — Delayed raw Git reception became permanently invalid | When globally shared bytes existed before the owner-specific raw mapping/membership arrived, JSON payload ownership was treated as impossible rather than missing. The publication could not promote after the remaining unit arrived. | Typed natural Git dependencies and owner-specific mapping/membership dependencies stage until complete; publication requires the acquisition seal and raw inputs. `test_missing_raw_git_bytes_keeps_result_unpublished_until_arrival` includes a database close/reopen before promotion. |
| R7 — Structured payload representation crashed admission | A payload reference with `representation=[]` or `{}` raised an uncaught `TypeError` during set membership. | Representation type is checked before membership lookup; malformed values produce `INVALID_JSON_REFERENCE`. `test_nested_payload_wrong_representation_type_is_a_contract_error`. |
| R8 — HTTP detail completion claimed code/broader completion | An exact terminal `pr-detail` marker alone transported complete `pr-code` with zero code observations or Git inputs. The same proof did not establish repository PR/document coverage breadth. | `code_proof` requires a published complete code result, exact listing inputs and acquired Git roles; aggregate proof requires a complete PR listing and scope-specific per-request evidence. `test_terminal_pr_detail_cannot_prove_broader_coverage_without_scope_evidence` checks code, repository PR and document scopes, including a forged HTTP-only receipt envelope. |
| R9 — Captured Git root members had no concrete schema | `git_acquisitions.roots_manifest='[null]'` passed ordinary production SQL and JSON-registry admission, although offline parsing expects structured ref declarations. Primitive strings and an object with only an invalid OID also passed. | Captured roots require typed ref fields, canonical raw/display names, format-specific OIDs and consistent optional PR fields. Captured declarations do not require raw objects to exist before acquisition completes. `test_git_root_declarations_require_structured_reference_members` covers three malformed member forms through registry and SQL gates. |
| R10 — Duplicate marker membership bypassed the new complete-code SQL gate | A commits listing containing F0 and F1, a terminal marker naming `[F0,F0]`, an exact files marker and no local listing progress admitted a complete code observation. Array length matched actual count, but F1 was omitted. | The canonical complete-code triggers require distinct manifest members, exact owned collection membership, a nonempty terminal set and the exact known collection observation boundary. `test_complete_code_requires_exact_terminal_listing_sql_evidence` covers the exact positive and subset, empty, unrelated, duplicate, nonterminal, stale-time and unknown-time attacks. |
| R11 — Consumed code-detail types were not enforced | Registry admission accepted `expected_roles=[]`, a role mapped to `not-a-git-oid`, and a string in `api_head_base_stable`, although code readers/proof evaluation interpret these fields as structured declarations and flags. | Optional consumed fields now have a concrete SQL/Python schema: supported canonical role/OID maps, role-name arrays, booleans and typed limits/merge declarations. `test_code_detail_consumers_reject_malformed_authored_types` tests five malformed forms through both admission gates. |
| R12 — Saved GraphQL variables crashed offline replay | Ordinary SQL admitted a saved thread-comment request with `variables=[]`; actual `ParsingService.reparse` raised `AttributeError: 'list' object has no attribute 'get'`. A string `operational_only='false'` also had the wrong truth-value semantics. | Acquisition context requires object variables, typed consumed variable fields and boolean operational flags. `test_fetch_request_consumers_reject_malformed_authored_types` tests malformed containers and the nonboolean flag through registry and SQL. The original actual replay reproduction used a disposable production Store with a synthetic development profile to bypass only the stale-certificate gate, and performed no network request. |
| R13 — Reader marker fallback selected older completion | The initial portable `_collection_state` fallback returned complete for an authentic terminal marker at -1 followed by a partial marker at 0; it also returned complete with an explicit local partial state. Filtering only complete markers hid newer contradictory evidence. | Reader qualification evaluates the latest immutable marker candidate set across all states, checks exact acquisition proof/conflict/quarantine barriers, and preserves incomplete or conflicting latest evidence. `test_immutable_collection_state_never_falls_back_from_newer_or_tied_incomplete` covers later partial, later unknown and tied complete/partial markers without sender-local progress. |
| R14 — Canonical hex guards accepted a hidden NUL suffix | Direct production SQL admitted `expected_roles.head='a'*38 + NUL + 'a'` and a parser implementation digest with 62 hex characters, NUL and one hidden hex character. Their encoded byte widths were correct, but SQLite text length/GLOB stopped at NUL. | Every generated canonical hex predicate requires both exact text and encoded byte width plus lowercase hex syntax. `test_code_git_oid_cannot_hide_nonhex_suffix_after_nul` covers expected roles, merge and review-target role declarations at SHA-1/SHA-256 widths; `test_parser_definition_digest_cannot_hide_nonhex_suffix_after_nul` covers both byte-width-preserving and full-prefix hidden suffix forms. The component suite separately covers captured ref OIDs/peeled/expected and payload digests. |

The final reader/CLI inspection also identified two application integration gaps.
The CLI could not pass an alternate profile UUID to Git reparse, despite the
application service supporting it. Explicit Git object reads and target search
also consulted only the current repository snapshot, hiding PR-only acquired
facts. The CLI now exposes the explicit profile option. Readers resolve a unique
eligible acquisition-selected interpretation when the explicit object is absent
from current snapshot facts; multiple candidates remain unresolved and an
unselected reparse never substitutes for a selection. Component regressions
include `test_pr_only_acquisition_has_explicit_selected_git_reads` and the
alternate-profile CLI checks. These findings are distinguished from the executed
SQL/exchange/reader counterexamples R1–R13.

The component author's real collector-to-empty-receiver positive test also
exposed an operational-state dependency: incoming listing facts required an
initialized local listing-progress row, and incoming complete code observations
required that excluded local progress to be complete. Receipt now creates only a
receiver-local partial listing boundary; it does not install sender progress or
invent local completion. Complete code qualifies through immutable exact
terminal collection evidence, while published result output membership seals
the received facts. The direct independent SQL test above proves the exact
marker path succeeds without any `code_listing_progress` rows and that truncated
or unrelated proof cannot substitute. The real acquisition/304 round-trip is
checked by `test_production_github_complete_proofs_cover_the_asserted_scope`.

That production positive also compares ordinary source/receiver PR output after
explicit receiver-local verification trust. The component author extended it to
a paginated **101-reply review thread** and compared both status and portable
thread items after full exchange. This exposed a second operational-state
dependency in ordinary PR coverage: collection completeness and a paginated
thread child still required excluded `collection_progress`. Readers now qualify
immutable exact markers independently of local progress, retain all equal-time
candidates, reject disputed/quarantined proof, and never fall back from a newer
incomplete marker. Portable output ordering uses observation time and permanent
identities or page ordinal/position rather than receiver-local surrogate IDs.
The positive thread/PR comparison is component evidence; the reviewer separately
executed the marker-state counterexamples in R13. Complete ordinary and
installed acceptance is recorded separately by the integration coordinator.

The final marker-UUID guard also applies A4's established encoded-byte-length
rule to the newly introduced portable marker identity. A UUID prefix followed by
`NUL` and hidden suffix must be rejected. The new independent
`test_completion_marker_uuid_cannot_hide_noncanonical_suffix_after_nul` checks
that ordinary SQL gate; this is the established canonical-identity contract,
not a newly selected design decision.

### Additional independent counterexamples and evidence

The same reviewer module checks NULL/cross-owner Git fact admission, malformed
nested verification references, disputed acquisition manifests, corruption
quarantine in ordinary file/search readers, invalidation of the specifically
selected verification, and immutable Git fact UUID collisions in both receipt
orders. The collision tests preserve immutable history while suppressing
dependent selected results. The raw-arrival tests preserve original result
identity and verify FK/integrity after reopened staged promotion. These checks
do not infer completeness or current selection from timestamps, UUID ordering or
the presence of unrelated records.

The reviewer module now contains **53 cases**. Before certificate regeneration,
the then-23-case no-bootstrap run produced **21 passed and 2 fixture errors in
9.44 seconds**. Both errors were `BUILTIN_VERIFICATION_STALE` during ordinary
discovery, correctly enforcing the stale packaged parser certificate. The
subsequently expanded three-scope HTTP-proof regression passed all three cases.
The nine new complete-code/marker-UUID SQL cases passed in **3.41 seconds**,
including the exact positive without local listing progress. The eight concrete
code-detail/request-schema cases passed in **3.27 seconds**; the three immutable
reader-state cases passed in **1.20 seconds**. The eight canonical hex/NUL cases
passed without bootstrap in **3.37 seconds**, with JUnit evidence in
`artifacts/independent-hex-development.xml`. Ruff check and formatting passed for
the reviewer module. These receipts are focused development evidence, not final
runtime acceptance.

After genuine certificate regeneration from passing capability evidence for the
exact implementation/DDL, the reviewer independently executed the following
command without a bootstrap override:

```sh
uv run --no-sync pytest tests/integration/test_catalog3_remaining_adversarial.py -q --tb=short --junitxml=artifacts/independent-final.xml > artifacts/independent-final.log 2>&1
```

The final independent receipt is **53 passed in 31.90 seconds**, exit status 0,
with no failures, fixture errors or skips. The exact result is preserved in
`artifacts/independent-final.xml` and `artifacts/independent-final.log`.

The final source review and executable counterexamples identify no further
substantive gap in the six targeted contracts. This conclusion applies to the
reviewed fresh Catalog3 implementation and the independent cases above; complete
ordinary/installed acceptance, submitted HEAD and hosted CI are separately
recorded by the integration coordinator. No hosted-CI conclusion is inferred
from an earlier checkpoint receipt or development bootstrap run.

