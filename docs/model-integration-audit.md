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

## Remaining architectural and validation limits

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

