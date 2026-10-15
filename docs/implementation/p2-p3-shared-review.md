# Independent cross-domain review: shared intrinsic-provenance correction

Reviewed commit: `2e8618428bea482ececef580045066cd49552455`
Reviewed tree: `9f50e3be6bdf92cfc33ccb490b04a369f74e1609`
Parent: `67e8be65c3061b494c2c7373e2fd151398435f62`
Reviewer did not edit production source or the reviewed commit.

Finding: supported coordinated callback SQL could attach a physical-copy intrinsic marker to an original reported scalar or whole relation group. A later matching representation then made the original report's projection appear checked, contrary to the immutable original-attribution boundary. This is an implementation enforcement defect, not an owner architecture contradiction.

Correction inspection: both marker INSERT guards require the frozen six-part provenance qualification to equal `receiver_intrinsic`, in addition to the existing checked-native field/group guard. Reported provenance is not rewritten; receiver checks remain separate evidence. Core DDL/fingerprint and generated disposition SQL bindings change together. No Context DDL, shared Coverage columns/keys, portable types, coordination interfaces, table count, initializer, accepted ADR, or history change appears in this four-file correction. SQL `IS NOT` also rejects absent/null qualification rather than allowing a NULL condition to pass.

Independent executed command from the exact committed correction checkout:

```sh
uv run --no-sync pytest tests/integration/p1/test_intrinsic_provenance.py tests/integration/p1/test_context.py tests/integration/p1/test_coverage.py tests/integration/p1/test_coordination.py tests/integration/p1/test_derivatives.py -q -o junit_family=xunit1 --junitxml /workspace/evidence/cross-review/shared-correction-junit.xml --journal /workspace/evidence/cross-review/shared-correction-journal.jsonl
```

Result: **125 selected/executed/passed, 0 failed, 0 skipped**, 20.10 seconds. The four actual SHA-1/SHA-256 scalar/group negative cases reject original-report promotion, leave projections unchanged, preserve separate canonical receiver evidence and do not falsely enter corruption stop. Context/current-state/Coverage/coordinated rollback/snapshots/derivative-loss tests also pass. Root separately executes broader Core/notes/schema/distribution checks; those are not claimed as this reviewer's execution.

Runtime: Python 3.12.14, SQLite 3.53.1, Git 2.52.0. JUnit and journal sit alongside this report. No duplicate-journal wrapper was invoked. This is focused local development verification, not hosted or release acceptance. Open material findings in this correction: **0**. Production P2/P3 combined source and their P3 unavailable-reference correction remain pending exact-head review.

## Audit-only follow-up revalidation

Final shared executable dependency: `fe925cc61ad6cf09c826b36dec0854ad44bd8e27`, tree `010e09014f860cf012c13346b9dc19d419affb76`. The entire difference from reviewed `2e8618428bea482ececef580045066cd49552455` is `scripts/audit_callsite_dependencies.py` and `tests/integration/p1/test_disposition.py`; all previously reviewed provenance guard, DDL, fingerprint, Core/Context/coordination and 125-test execution input files are unchanged. The preceding execution is identity-rebound, not rerun.

Inspected the explicit five optional production-module exclusions. A sibling may omit the other sibling's files; public Schema 21 inputs remain included. The stronger AST import guard resolves absolute, `from package import module`, and relative imports to the same explicit isolated target set, including the P2/P3 modules. It does not claim to detect arbitrary dynamic Python imports; this remains the historical lexical audit boundary. Six new parameter cases exercise the relevant absolute/relative forms.

Additional independent execution from exact `fe925cc`:

```sh
uv run --no-sync pytest tests/integration/p1/test_disposition.py -q -o junit_family=xunit1 --junitxml /workspace/evidence/cross-review/shared-audit-junit.xml --journal /workspace/evidence/cross-review/shared-audit-journal.jsonl
```

**16 selected/executed/passed, 0 failed, 0 skipped**, 0.69 seconds. No public initializer activation or accepted ADR change is introduced. Material findings in final shared dependency: **0**. Both siblings must inherit this same exact dependency, not independent variants.

Final optional-port audit follow-up: `bc6c2c18e05b0c77c0d928626f28518727318a52`, tree `180f34e68df72d19a443982ad8dca03eece175dd`. Compared with `fe925cc`, executable changes are one explicit optional `domain/ports/production_context.py` path and one matching import-guard test case; intervening documents preserve their originally executed source receipts. No reviewed authority behavior, DDL, portable identity or coordination input changes. Independently ran the same focused disposition command with artifacts named `shared-final-audit-*`: **17 passed, 0 failed/skipped**, 0.61 seconds. Guard and 125-test review remain bound by unchanged executable inputs. Common dependency has zero open material findings. The historical 390-node receipt remains at `fe925cc`; it must not be presented as rerun at `bc6c2c1`.

## Persisted-authority validation correction and final common approval

Independent reviewer and P3 reviewer separately reproduced valid-incoming/invalid-stored classification failure: corrupting an already persisted Context Provider configuration or field JSON into invalid UTF-8 caused SQLite's semantic CHECK UDF to raise `SQLITE_ERROR` during `PRAGMA integrity_check`, rather than returning a corruption row. On committed combination `a83a233f2e84053795c98a5c01f7c4b2e8be9d64` (tree `5e5c12b97a45ac84ad21b6dfcd89d6d8376c9c3e`), the independent Provider reproduction returned `OperationalError: user-defined function raised exception`, code 1, with no persistent stop. This was a material enforcement defect; it was not a conflict between accepted architectural requirements.

Final reviewed common source: `7ac94a9183eb18f54273fcaeb0a561b01d25048c`, tree `6905cd58843759333577adb6fe30dce4d2f9d25b`.

Source inspection confirms translation is confined to validation of existing authority, not incoming admission. It translates actual corrupt/not-a-database/I/O storage faults and the observed semantic-UDF/UTF-8 failures. Other database errors, including resource exhaustion, interruption, locking and permission failure, propagate without manufacturing corruption. Including I/O storage faults follows ADR 0026 section 1: "an authoritative-storage fault that prevents establishing the required integrity." Both initially validated raw connections and revalidated `ReadSnapshot` capabilities notify their owner before a caller could swallow the translated failure. Existing domain corruption errors likewise notify the owner immediately. No portable identity, schema fingerprint, Coverage, ordering, snapshot token, admission port or initializer change accompanies this correction.

Independent final execution:

```sh
uv run --no-sync python /workspace/evidence/cross-review/probe_invalid_utf8_pair.py
uv run --no-sync pytest tests/integration/p1/test_validation_stop.py tests/integration/p1/test_coordination.py -q -o junit_family=xunit1 --junitxml /workspace/evidence/cross-review/shared-approved-validation-stop-junit.xml --journal /workspace/evidence/cross-review/shared-approved-validation-stop-journal.jsonl
```

Own actual Provider corruption probe now returns `CoordinationError CORRUPTION` and `STOP_EXISTS True`. **51 selected/executed/passed, zero failures/skips**, 13.27 seconds. This includes actual invalid UTF-8 Provider/field cases through initial certification and direct read-capability validation, stop persistence after derivative loss, and actual progress-handler interruption of a healthy catalog followed by successful uncancelled validation without a recovery marker. Intermediate reviews executed 48 nodes at `9e4bb773` and 50 at `03836901`; these are separate correction iterations and are not additive test coverage.

Final common dependency verdict: **approved for both P2/P3 sibling consumers; zero open material findings**. Its broader historical guard/Context and audit reviews above remain bound through unchanged relevant inputs; only the exact final 51-node command was rerun here. All execution was local and disposable. This is not merge authorization, hosted release acceptance, recovery activation or final production-sibling approval.
