# ADR 0030 I1 renewed independent review

Target HEAD: 5be4a8fa7e7ac32085e350cc83bf753591912748
Target tree: a842ce26c8b7d4fd0aacd08f9b9f28629678f946
Base: 6780088befd33e711230d570bb291edb2ee40cbf

Verdict: CHANGES REQUIRED for one public keyword contract mismatch. All four initial review findings are resolved on this revision; their original evidence remains in the committed initial-independent-review.md.

## Unresolved finding

**P2: Production facade rejects the protocol/reference adapter's public keyword.** ContextAdmission.admit_repository_relation and ContextStore.admit_repository_relation declare `relation`; production Context declares `claim`. With a valid transaction and valid owning_repository value, `ctx.admit_repository_relation(relation=value)` raises `TypeError: Context.admit_repository_relation() got an unexpected keyword argument 'relation'`. The result wrapper has the same mismatch. Full signature comparison also found two facade mismatches: `relations_for_provider_repository` calls its first argument `service_or_resource`, whereas Protocol/Store call it `service_instance_uuidv4`; `evaluate_provider_repository` calls its first argument `resource`, whereas Protocol/Store call it `provider_repository`. Those ordinary keyword calls likewise fail to bind. All other ContextAdmission keyword names match. These are ordinary protocol-shaped calls, so positional-only local coverage does not establish public substitutability. Rename the facade parameters to match. No semantic/schema/design change is needed.

## Initial findings resolved

1. Shared finite per-(role,target) Transfer mapping supports allow complete A→B reports to retain exact A and B ClaimKeys while preserving the same report provenance/key. Separate endpoint qualifications remain isolated; missing second dependency rolls back the complete unit.
2. selection_truncated preserves partially omitted alternatives across reselection and dedicated admission rejects the incomplete report.
3. Full Provider IDs and Timeline Event filter coordinates are validated before stored-data fault handling. Invalid caller filters do not create P7 stops.
4. Shared canonical stored-scope parser checks explicit event type, exact clock/supplied roles and Provider member declarations; adapter checks reject missing Provider Resources. Malformed retained scope creates a real production P7 stop.

## Independent verification

- Exact clean HEAD/tree verified before and after checks; no checkout/index/branch/PR writes.
- Focused pytest: **918 passed**, comprising all P1, P3 and Access integration tests plus the I1-seeded I3 export refusal control. PYTHONDONTWRITEBYTECODE=1; pytest cache disabled; temporary fixtures outside checkout.
- Twelve independent executable controls in /workspace/i1-review-final-controls.py pass, covering both generic Transfer roles/result APIs on replay, supported complete A→B round trip, absent-dependency atomic rollback, role support isolation, duplicate support, selection truncation/reselection, explicit-null versus unresolved Provider endpoints, malformed scope/clock/type/Provider/members, mapping REPLACE/UPSERT/NULL rebind guards under FK+recursive triggers, nineteen tables and both sides of P7 input/storage error handling.
- All five audits pass: build_p1_schema --check, audit_p1_schema --check, audit_callsite_dependencies --check, audit_implementation_boundary --check and audit_context_registration.
- Independent clean git archive of this exact SHA built direct wheel and sdist-derived wheel outside the checkout; both installed smoke suites passed with isolated import origins, matching Context fingerprint fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434, nineteen Context tables and real SQLite UDF registrations. Log: /workspace/i1-review-final-dist.log; result JSON: /workspace/i1-review-final-dist/artifacts/access-registry/distribution.json.
- Independently recomputed the 414-file runtime input digest: d2fb070b8c5fc37e552d8933774d64e4aee092a1f14b40a81a0a15323415755d, matching committed evidence.
- Local runtime: CPython 3.12.14 / SQLite 3.53.1. This is not a hosted minimum-version 3.51.3 run.

## Scope and limits

This is I1 typed/admission/public contract review, not I2 Provider authenticity, I3 selective Exchange acceptance, I4 query acceptance or release validation. The existing 19 tables, exact composite keys, six roles and no-Witness decision remain unchanged; no ADR change was introduced. SQL structure and bounded mutation checks show real FK targets, nonnull typed Transfer FK coordinates, all-or-none replacement references and immutable mutation guards consistent under foreign_keys=ON/recursive_triggers=ON. These are not exhaustive SQLite engine tests.

The broader 1,883-pass/37-failure registry reproduction is the author's evidence; this reviewer did not rerun the full registry selection. Documentation correctly preserves the ten direct P5 I2 stops (five Exchange fixture failures never reach Exchange) and 27 P6 retired-API setup dependencies, with separate I2/I3/I4 ownership. The standalone passing I3 refusal proves its boundary only. Hosted check status and PR text are the parent agent's independent API responsibility.

Updated skill guidance matches the verified complete-report, mapping-support, selection-scope and false-P7-stop lessons. No further material defect was found in the read-only bounded review beyond the public keyword mismatch above.
