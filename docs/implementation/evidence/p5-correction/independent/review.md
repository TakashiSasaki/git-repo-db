# Independent P5 corrected-source review

Reviewed executable commit `c90e9b12f7b240efdeb5dcffc12098680b04317f`, tree `4266da7f4b0f169260112cfe8075a9f1691b6ce5`, exported to an independent archive and installed into its own locked editable virtualenv. The reviewer authored no reviewed production changes. Original `4394667` and `5a5e07a` runs and artifacts are preserved separately; this review reran all selected inputs on the follow-up executable.

**64 selected, 64 unique executed, 64 passed, zero failed/errors/skips.** Exactly one passed setup/call/teardown is recorded for every selected node. This includes 47 repository P5 nodes and 17 independent external nodes. Collection, journal starts, phases and JUnit identities reconcile; the receipt enumerates all exact node IDs, commands, versions and input/artifact SHA-256 values. Schema build, schema reconciliation, implementation boundary and callsite dependency audits also passed on this exact source.

The original eight independent desired-behavior assertions failed against archived baseline `55f8f592fedcb2cd165284c4e8a5e0c6ca68a2e7`, tree `5dd689b80105217ea1cfc8955b98576aa36c10af`. A separate ninth completion-stop counterexample also failed. Their artifacts remain separate failed reproduction evidence.

| Reproduced defect | Root cause | Independent corrected regression |
| --- | --- | --- |
| No declared package digest | Digest only calculated from received content | `test_declared_digest_required` |
| Missing Provider repo identity invented | Local repository UUID substituted for Provider resource ID | `test_missing_repository_provider_id_rejected` |
| Native Git process executed under Core writer transaction | Acquisition called directly inside coordinator callback | `test_native_external_io_outside_write_transaction` uses an actual SQLite writer contender during source metadata I/O |
| One selected commit gave whole-repo complete | Selection success promoted to repository git_metadata coverage | `test_selected_object_never_repository_complete` constrains only that broad scope; narrow scope complete remains allowed |
| Exact retained retry made second physical copy | UUID minted on each delivery | `test_retry_preserves_physical_copy`; authored both-format Notes capture/copy retry controls also execute |
| Same request after Operational loss restarted at zero | Missing row treated as initial creation | `test_missing_request_after_operational_loss_refuses_resume[False/True]`; both re-declaration flags are refused after SQLite loss; authored partial-budget loss and finite cumulative tests execute |
| Exchange lost committed-Core outcome | AdmissionFailure unwrapped to original cause | `test_exchange_retains_partial_admission_outcome` checks exact PairAdmission(True,False) |
| Paired export mixed stores from different states | Snapshot was opened/closed before actual extraction | `test_exchange_export_uses_one_paired_snapshot` uses a separate writer thread; verifies writer waits during export and completes afterward |
| Export returned after persistent stop | Missing final completion fence | `test_exchange_export_refuses_stop_before_return` injects stop after final Context extraction |

Six independent Provider observation-order permutations preserve latest comparable title, stale-field inheritance and incomparable explicit-null body, then compare exact candidate/resource/clock/provenance/time rows across repeat, reverse and onward Exchange. Those semantics already passed the original baseline in the checked cases; they are refutations of a blanket arrival-order defect, not additional bug claims. A valid non-time JSON real roundtrip independently prevents applying timestamp type restrictions to unrelated scalar values.

Authored corrected-source tests additionally execute SHA-256 data+digest rewrite controls without authentication claims, both native Git object formats, receiver validation, strict timestamps, missing-vs-null, byte limits, declared/native hashes, finite prepayment and cumulative budget behavior. These do not establish sender authentication.

No open material executable finding remains in this reviewed scope. Historical review prose had nonexistent test-name citations and falsely claimed HMAC; these were separately flagged for documentary correction. An evidence/docs-only successor must prove unchanged executable input hashes rather than claim another execution. Issuance witnesses establish conservative refusal after SQLite accounting loss; this review does not claim durability against adversarial removal of all matching evidence or host-power-loss behavior.

This is independent focused local development verification, not GitHub approval, hosted Development CI, full Release Acceptance, final combined P5/P6 verification, installed wheel/sdist verification, P7 restore/activation or P8 public initializer acceptance. No reviewed-tree mutation, real data operation, main update, merge, publication or release was performed.
