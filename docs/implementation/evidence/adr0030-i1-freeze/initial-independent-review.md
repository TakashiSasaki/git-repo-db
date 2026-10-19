# ADR 0030 I1 independent read-only review

Target HEAD: caf525b77207f4c99f1b407b22e8ee9735cde1b1
Target tree: 200da4721607e87c900663d18abc0d4e11be65a5
Base: 6780088befd33e711230d570bb291edb2ee40cbf

Verdict: CHANGES REQUIRED. Four actionable I1 contract findings remain on this exact target. This review does not approve a later revision.

## Findings

1. **P1: A complete two-sided Transfer cannot retain exact MappingClaimKey support for both distinct targets.** In domain/p1_context.py, RelationClaimKey.__post_init__ validates the single embedded MappingSupport against its own target, while TransferEventReport._validate_endpoint_relation requires every endpoint to carry exactly the report provenance JSON. Construct from=A with provenance containing support(A), to=B with support(B): report construction fails with `Endpoint relation.provenance_json must match report_key.provenance_json`. Reuse provenance containing support(A) for to=B: endpoint construction fails with `mapping_support target_repository_uuidv4 must match relation target_json`. Bare reports work but resolve to missing_supporting_binding. This defeats the architecture's implementation proof obligation to retain actual mapping ClaimKey support in resolved Core-target reports. Recommended correction: retain shared original report provenance and encode finite per-role/per-target support within it; select the exact support appropriate to each endpoint, including alternatives. No schema/key/role/table change is required.

2. **P1: Selection can truncate alternatives while retaining complete-report meaning.** domain/p1_context.py TransferEventReport.select_for_repositories only adds an omitted role when no relation in that role remains. Construct one report with from alternatives A and B and select {A}: B disappears, omitted_roles remains empty and has_selection_omission is false. Such a result can be admitted as a complete report. Architecture section 5 explicitly forbids supplied endpoints being silently dropped while preserving completeness. Add a typed qualifier for partially omitted alternatives or refuse the operation; do not expand permission to B.

3. **P1: Invalid caller filters stop an otherwise sound catalog.** production_context.py relations_for_provider_repository validates only the provider ID's Python string type before entering _stored; the base method then constructs ResourceKey and rejects an empty ID inside _stored. A valid fresh Context snapshot queried with `(service, '')` raises AUTHORITATIVE_CORRUPTION and creates p1-recovery-stop.json. Similarly, transfer_event_reports accepts any comment ResourceKey before _stored; a non-Timeline comment ID is rejected inside _stored and creates a corruption stop. Both were reproduced on independent disposable catalogs. Validate the full provider key and Timeline Event coordinates before _stored. Preserve stored-data corruption handling separately.

4. **P2: Stored Transfer scope and members are silently ignored by read/recovery validation.** p1_context.py transfer_event_reports and recovery_validation.py validate_stored_context_relations reconstruct reports without checking scope provided_roles or resource_relations.members_json. With FK and recursive triggers ON, directly insert a valid endpoint plus a transferred scope declaring provided_roles=[]; both validators accept, reconstructing a different actual provided-role set. A scope whose members_json references an unrelated nonexistent Provider Repository also passes. A recovered authoritative report must preserve and check the declared scope, rather than silently repairing it. Validate exact finite scope fields/types, provided roles against actual endpoints/provider IDs, members against the unique explicit Provider Repository coordinates, and their existence. Share the parser between read and recovery paths.

## Independently executed checks

- Verified clean worktree and exact HEAD/tree before/after initial review.
- Executed all tests in tests/integration/p1/test_context_relations.py and tests/integration/p3/test_production_context.py: **109 passed**, using the existing .venv, PYTHONDONTWRITEBYTECODE=1, pytest cache disabled and basetemp outside the checkout.
- build_p1_schema.py --check: pass; all four packaged schema/fingerprints match.
- audit_p1_schema.py --check: pass; 84 baseline tables / 625 columns, 48 target tables, zero unclassified.
- audit_context_registration.py: pass; 25 routes / 33 typed fields, no omitted route.
- Executed the four counterexamples above in independent disposable in-memory or temporary catalogs without disabling SQL guards.

## Other reviewed scope and limits

Read root AGENTS.md, ADR index, accepted ADR 0030, architecture contracts, the entire main-to-target implementation diff, public facade, admission/reference adapter, domain types, SQL constraints/triggers, recovery validation, packaging verifier, CI selection and modified skills/docs. The generic endpoint/result admission and generic transfer_event_report scope bypasses described by the author are correctly closed on this target. I1 typed admission does not establish Provider authenticity; no I2 GraphQL work is required to correct these findings.

The 19-table structure, existing semantic composite keys, six-role closed vocabulary and no-Witness decision are preserved. SQL inspection found the generated nonnull Transfer type/parent coordinates, real Repository FK, all-or-none replacement references and immutable REPLACE/UPSERT guards consistent with the required foreign_keys=ON and recursive_triggers=ON assumptions. No additional SQL mutation defect was found in that bounded review. This is not exhaustive SQLite engine testing.

The downstream failure documentation correctly distinguishes ten P5 I2 stops (including five Exchange fixtures that never reach Exchange) from later I3 ownership, and 27 P6 retired-API setup dependencies. A passing standalone UNSUPPORTED_UNTIL_I3 refusal is not selective Exchange acceptance. Original 37 failures must remain visible.

Distribution verifier now checks both built distributions' Context fingerprints and table count, real UDF registration and isolated origins. I inspected this code and the author's evidence, but did not independently rerun packaging because its script writes checkout artifacts. Hosted SQLite 3.51.3 evidence remains separately necessary; this review's local Python uses the existing supported environment. Skill additions about complete report admission and first-reached failure classification match the authorized boundaries, but should gain regression guidance for findings above after correction.
