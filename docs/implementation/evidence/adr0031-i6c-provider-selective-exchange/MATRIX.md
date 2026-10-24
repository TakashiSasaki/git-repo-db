# ADR 0031 I6-C Provider / Selective Exchange Verification Matrix

Target branch: `impl/adr0031-i6c-provider-selective-exchange`
Base: `review/adr0031-i6b-rereview-20261023` (commit `91827360c185cbf813277bf32a6627d894b1b20a`)
Tree: `4db21ecf4267f1f31023fd63ac6de7ebd8d93d3c`

## Requirements Mapping (R02–R16)

| Requirement | Description | Implementation / Authority | Verification Evidence |
| --- | --- | --- | --- |
| **R02** | Exact v5 wire format envelope | `exchange.FORMAT = "git-repo-db/adr0031-exchange-v5"`, exact envelope sections and row schemas. | `test_context_boundary.py`, `test_context_wire_v5.py`, export/import round-trips. |
| **R03** | Canonical UTF-8/JSON and digest validation | `_canonical_dictionary`, `_bounded_json`, raw-dictionary digest validation on envelope ingest. | `test_bounded_json_adversarial.py`, `test_digest_tampering.py`. |
| **R04** | Finite cumulative work and request budgets | `_ReceiveWork`, `spend()`, `AdmissionBudget`, non-refundable rollback accounting. | `test_planner_adversarial.py`, `test_context_admission.py`. |
| **R05** | Seven Resource Identification columns | `ResourceIdentification` preserves 7 columns; distinct from 3-coordinate `ResourceKey`. | `test_generalized_resources.py`, `test_resource_identification.py`. |
| **R06** | Generic relations, ordered collections & real terminals | `ResourceRelation` preserves member order, time, and alternatives; no synthesized terminals. | `test_context_relations.py`, `test_selective_exchange.py`. |
| **R07** | Source inventory, CoverageScope & proofs | Positive (source, repo) pairs, complete coverage scope FKs, terminal state binding. | `test_coverage_exchange.py`, `test_coverage_admission.py`. |
| **R08** | Full ParentReportKey & immutable Parent observation | Parent observation independent of Event clock, provenance, or arrival sequence. | `test_parent_reports.py`, `test_selective_exchange.py`. |
| **R09** | ProviderEndpointDeclaration & complete endpoint columns | `event_report_members_json` and `event_report_scope_json` preserved on transfer relations. | `test_generalized_resources.py`, `test_provider_exchange.py`. |
| **R10** | Service-issued local Context admission authority | `LocalAuthorizationPolicy`, `ContextAdmissionService` created locally; no duck typing. | `test_context_boundary.py`, `test_paired_admission.py`. |
| **R11** | Policy leases held through outer COMMIT | `LocalAuthorizationPolicy.lease()`, `check_current()` checked before and during commit. | `test_context_coordinator_admission.py`, `test_context_boundary.py`. |
| **R12** | Native semantics before missing-dependency diagnostics | Native identity, parent eligibility, and schema validation precede existence lookups. | `test_context_refusal_order_i6a.py`, `test_context_admission.py`. |
| **R13** | Selective exchange unit withholding | Atomic semantic units withheld rather than admitting partial claims; complete units admitted. | `test_selective_exchange.py`. |
| **R14** | Replay protection, out-of-order & duplicate delivery | PackageKey content binding, immutable progress check, idempotent exact replays. | `test_selective_exchange.py`, `test_provider_exchange.py`. |
| **R15** | Transaction atomicity & rollback integrity | Outer commit failure rolls back core + context; failed work remains charged. | `test_context_boundary.py`, `test_paired_admission.py`. |
| **R16** | Mandatory Transfer staging fences | `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence` fail closed. | `test_transfer_sql.py`, `test_resource_stage.py`. |

## Vectors Mapping (V01–V09)

| Vector | Description | Implementation & Evidence |
| --- | --- | --- |
| **V01** | Global Document full 7-column identity | Preserved without synthetic parent or namespace scoping; verified in `test_generalized_resources.py`. |
| **V02** | Scoped Event child-first, exact canonical namespace | Resolved native identity without inferring parent existence; verified in `test_generalized_resources.py`. |
| **V03** | Independent original Parent full-key & observation time | Independent Parent and Event clocks verified across intake and selective export/import. |
| **V04** | Genuinely one-sided explicit NULL endpoint | `ProviderEndpointDeclaration("explicit_null", "not_reported")` preserved without fake targets. |
| **V05** | Two-sided complete & truncated declarations | Complete two-sided declarations transported; truncated reports withheld atomically. |
| **V06** | Unresolved Provider-only repository target | Provider-only native keys retained without manufacturing fake core repository UUIDs. |
| **V07** | Mapping support qualification and denial | Verified in `test_selective_exchange.py`; claims must have valid mapping support. |
| **V08** | Rechecksummed malformed schema, ID, or time | Digest validation catches modifications before selection or database mutation. |
| **V09** | Ordered generic members, terminal alternatives & coverage | Full preservation through v5 export and selective import. |

## Test Scenarios (T01–T27)

| Test ID | Scenario | Verified Outcome |
| --- | --- | --- |
| **T01** | Bounded identity and wire parsing | PASS (`test_context_wire_v5.py`, `test_bounded_json_adversarial.py`) |
| **T02** | Seven Resource columns & child-first intake | PASS (`test_generalized_resources.py`) |
| **T03** | Independent Parent / Event clock and provenance | PASS (`test_parent_reports.py`) |
| **T04** | Original evidence preservation | PASS (`test_originals_revalidation.py`) |
| **T05** | One-sided vs two-sided endpoint declarations | PASS (`test_generalized_resources.py`) |
| **T06** | Explicit NULL vs Provider-only vs resolved endpoint | PASS (`test_provider_exchange.py`) |
| **T07** | Per-dependency authorization policy denial | PASS (`test_context_boundary.py`) |
| **T08** | Service-bound handle & replay authorization | PASS (`test_context_coordinator_admission.py`) |
| **T09** | Empty selection and selection boundary | PASS (`test_selective_exchange.py`) |
| **T10** | Rehashed invalid version / digest tampering | PASS (`test_digest_tampering.py`) |
| **T11** | Cumulative work and byte budget limits | PASS (`test_planner_adversarial.py`) |
| **T12** | Atomic semantic unit omission | PASS (`test_selective_exchange.py`) |
| **T13** | Source inventory and positive pair admission | PASS (`test_coverage_exchange.py`) |
| **T14** | Disjoint selection / authorized dependency orchestration | PASS (`test_selective_exchange.py`) |
| **T15** | Repeated / out-of-order provider delivery | PASS (`test_provider_exchange.py`) |
| **T16** | Reverse and onward exchange paths | PASS (`test_selective_exchange.py`) |
| **T17** | Second endpoint failure & rollback | PASS (`test_paired_admission.py`) |
| **T18** | Existing I4/I5 regression suite preservation | PASS (all regression test suites retained) |
| **T19** | Packaged SQL transfer staging fences | PASS (`test_transfer_sql.py`) |
| **T20** | Fail-closed behavior on altered/missing fences | PASS (`test_resource_stage.py`) |
| **T21** | Stored corruption fail-closed verification | PASS (`test_context_boundary.py`) |
| **T22** | Paired admission coordinator local service binding | PASS (`test_paired_admission.py`) |
| **T23** | Provider intake without manufactured evidence | PASS (`test_context_boundary.py`) |
| **T24** | Empty OID & context payload selection override rejection | PASS (`test_selective_exchange.py`) |
| **T25** | Missing core OID retains original report clock | PASS (`test_selective_exchange.py`) |
| **T26** | Wheel and sdist installation in clean venvs | PASS (`test_p5_distribution.py`) |
| **T27** | Unwired ordinary transfer refusal | PASS (`test_provider_exchange.py`, `test_resource_stage.py`) |
