# I6-A contract and execution ownership

This is Author mapping. Exact executed-node lists/JUnit/journals and distribution
origins are the evidence; a named test below is not a substitute for its receipt.
No historical report or Accepted ADR is edited.

| Requirement / finding | Implemented I6-A boundary | Test anchors | Remaining owner |
| --- | --- | --- | --- |
| R01 | Direct Resource and Parent keys; child registration independent | `i6a::test_complete_child_registration_requires_no_namespace_resource_or_parent`, Parent reports cohort | No new Parent/Witness/storage-surrogate table |
| R02–R07 | Preserve inherited wire/Source/terminal semantics, pure dependency enumeration only | Domain Source/Collection dependencies and existing SQL cohort | Exact v5 codec, generic closure/proofs and active routes: I6-B/C |
| R08 / I5-B1 | Mandatory original Parent key+explicit time; exact row/time check | `test_transfer_originals` V03/V04; `i6a::test_independent_parent_originals_are_preserved_and_rechecked`; missing dependency resupply | I7 durable reconstruction/recovery |
| R09 / I5-C1 | Total Provider declaration and explicit original endpoint set; whole withholding | Originals V04/V05/V06/V07; `i6a::test_missing_declared_endpoint_cannot_be_rescued_from_local_rows`; inherited I5 genuine/null cases | Provider normalization/wire forwarding: I6-B/C |
| R10–R12 / I5-A1 | Service-bound authenticated exact contexts; dependency permission then selection before lookup/replay | `i6a::test_deny_each_dependency_before_initial_or_replay_lookup`, `test_context_admission`, OID carrier tests | Local application composition and routes: I6-C; no temporary grant |
| I6-L1 | Foreign service handle and forged principal refused before policy/lookup, initial+replay | `i6a::test_service_handle_and_principal_substitution_never_authorize`; exact identity/session mutation unit tests | Independent re-execution required |
| R12 refusal precedence | Current permission, then selection, then pure permanent eligibility before missing-Source diagnostics | `test_context_refusal_order_i6a`: six initial/replay deny/omit/native-ineligibility cases | No downstream query acceptance implied |
| R11 | Current mapping/Disposition authorization+qualification; Source positive-pair checks | Dependency-denial integration parametrizations; bounded claim scan; current mapping evaluator | Operation-specific Disposition evidence routes remain unconnected/fail closed |
| R13 | Finite pure input/dependency scan; cumulative byte/work budgets; bounded SQL current-candidate scan | Budget/zero-work unit+integration cases; `test_context_admission_bounds_i6a` | Whole wire closure planner I6-B/C |
| R14 | Current authority before Event duplicate and unconnected Exchange cached receipt | I5 replay/time/key conflict; actual cached public import refusal | Active package resupply/reverse/onward routing I6-C |
| R15 / I5-D1 | Original pre-affinity types; SAVEPOINT unit; commit-held leases; outer rollback | Actual trigger second-INSERT, deferred FK COMMIT and revision-trigger integration probes; inherited I4 SQL 217 | No normal Transfer activation |
| R10/R15 coordinator lifetime | Constructor-bound trusted service; exact issued invocation and expiring transaction capability; shared lease stack through actual outer commit | `test_context_coordinator_admission`, original 46 coordination nodes with unchanged assertion ASTs | Remaining callers need explicit finite authority; public Provider/Exchange composition remains I6-C |
| R16 / I5-F1 | Both exact definitions; unsupported state refusal; explicit ephemeral fixture only | `test_context_fences_i6a`; product SQL stage node retains authorized-stage assertion | Later separately authorized integrated retirement |
| R17 / T20 | Reuse pure validator interface and keep safety profile/fence floor | Restricted coordinator, FK/recursive/UDF profile and corruption-stop negative controls | Full recovery G-R1/source Stop/pairing acceptance: I7 |
| R18 | No query/Search implementation or acceptance | Existing broad failures remain visible | I8 |
| R19 / T24/T27 | Both fences retained, source and distribution verification, honest broad delta | Exact-node comparison, artifact origins/hashes | Full integrated I6-B/C/I7/I8 + non-Author final gate |

Required I6-A design test mapping: T02–T06 (mandatory identification/originals,
independent Parent/Event, complete endpoint states and whole units); T07–T09
(permission, initial/replay forgery and revocation); T13 (explicit current
selected dependency and native-I7); T17/T18 (real SQL and outer COMMIT rollback);
T19/T20 (both-fence state and safety floors); T26 (unconnected public routes and
current caller context); T27 (source/distribution/regression inventory). T20's
full enduring recovery and T27's active wire forwarding remain assigned to later
stages. No partial I6-A coverage is relabeled as their full acceptance.

## Intentional inherited-node changes

All 29 I5 node IDs and 217 I4 SQL node IDs are retained. See
[raw/i5-node-mapping.json](raw/i5-node-mapping.json). Their positive synthetic
Transfer fixtures are now explicitly fresh-memory capabilities; normal
product-factory refusal still uses real product files. Old selection-fragment
assertions are replaced by whole-report withholding plus explicit truncated
constructor refusal, keeping the original no-partial-admission purpose.

I4 `test_product_admission_is_still_fenced` now first asserts unconnected caller
denial, then passes an explicit locally issued context to reach its original
stage refusal. Parent API tests use finite explicit Resource/service grants and
issued selections rather than removed caller callbacks. The swallowed-corruption
test uses an ordinary read to prove the persistent recovery stop; an unbound
mutation separately proves denial precedence. Neither correction weakens the
SQL/fence/recovery assertions or hides failures with skip/xfail.

Other unauthenticated legacy fixtures and unconnected Provider/Exchange routes
are deliberately left visible in final full-suite node/phase results. A new
permission failure at fixture setup does not prove the previously named Query,
Recovery or Exchange assertion ran. Actual new/resolved/changed failures and
unreached stages are reported separately; counts alone are insufficient.
