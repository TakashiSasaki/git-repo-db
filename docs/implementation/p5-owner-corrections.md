# P5 owner-decision correction

This change implements ADR 0028 on the shared opt-in schema contracts. It does
not activate Schema 21 replacements, perform migrations, merge to main, or
implement P7 recovery. Decision acceptance, implementation, local verification,
independent review and GitHub approval are separate states.

## Corrections and reproducible boundaries

| Owner item | Reproduced defect / disposition | Implementation and regression |
| --- | --- | --- |
| A | Repository metadata's missing observation became 0; missing provenance/Provider identity was invented | Nullable observation preserved through normalization; explicit Provider registration, actual repository Provider ID and provenance required. `test_repository_unknown_observation_retained_without_fabricated_coordinates`, `test_provider_registration_is_explicit`, timestamp boundary parametrizations |
| B | Native refs used unbounded capture_output; metadata parsed/hashed before charging; fallback recreated ephemeral progress; lost old request could be recreated | Bounded Notes input primitive reused for native metadata and refs, permits before reads/validation; no implicit fallback; explicit new/continuation and loss witness. `test_git_input_read_is_prepaid`, `test_operational_loss_never_reissues_same_request_even_new_flag`, `test_exchange_wire_budget_and_repeat_are_cumulative` |
| C | Replayed native copy and Notes discovery generated new UUIDs | Request-scoped allocations saved before native processing, fixed discovery observation and existing P4 copy progress. `test_retry_preserves_notes_capture_and_all_copy_ids` (both Git formats) |
| D | Selected-OID success certified repository-wide git_metadata complete | Request report may describe selected work success; repository claim stays partial/unknown without repository closure proof. Notes partial/unknown propagates to report. Retry regression explicitly checks partial repository Coverage |
| E | Git source I/O occurred during paired Core callback; Exchange discarded AdmissionFailure outcome | Finite in-memory typed plan prepared before callback, keeping live Operational permits through admission; Core/Context independent commit outcome preserved. `test_paired_git_processes_run_before_core_transaction`, `test_exchange_partial_commit_outcome_survives` |
| F | No declared sender digest was compared; onward metadata-only provenance renamed at each relay; paired export's initial snapshot did not cover extraction | Versioned declared SHA-256 envelope, bounded prevalidated input; preserve original attribution with qualification downgrade; writer fence spans extraction and completion fence spans return. Baseline repeat/reverse/onward tests retained. Sender flags still confer no receiver authority |

The independent review report records additional adversarial executions against
its corrected commit. Tests above are author regressions, not independent review.

## Exchange v2

`ExchangePackage` serializes exact top-level keys: `format`, `digest_sha256`,
`package_id`, `exported_at_us`, `sender_catalog_instance_uuidv4`,
`repository_uuidv4`, `selection_scope`, `core`, `context`.
`format` is `git-repo-db/p5-exchange-v2`. `digest_sha256` is the sender-declared
lowercase SHA-256 of all the other keys. Receiver recomputes and compares it
before domain admission. JSON uses sorted string keys, separators `,` and `:`,
UTF-8 with literal Unicode, finite JSON numbers, no Unicode normalization, and
ordered arrays. Bytes use lowercase contiguous even-length hexadecimal.
Duplicate keys and unsupported top-level/selection/section keys are rejected.
There is no v1 compatibility layer, HMAC, signature, PKI or key management.
Rewriting both content and checksum defeats transport integrity: origin is
unauthenticated under ADR 0027. Receiver Git native SHA-1/SHA-256, grammar,
Notes-role and body checks remain mandatory.

The finite limits are 32 MiB wire/canonical UTF-8, depth 32 and 200,000 traversed
JSON values including embedded `*_json` documents; bytes expansion is bounded
by that hex-bearing envelope. Native/Notes body and structural proof limits
also apply through the cumulative WorkBudget. Permit upper bounds precede
parsing/canonicalization/checksum processing and settle measured successful
input, hash and value traversal; failure uncertainty retains upper reservations.
Native/proof revalidation is charged separately. Default Exchange metadata
budget is 10,000,000 units; other finite defaults come from NotesLimits. These
are engineering defaults, not new owner policy.

`import_package(raw, *, request=None, new_request=False, work=None)` requires an
explicit request identity for wire strings/bytes, permitting accounting before
parsing. Typed packages/dicts derive the transport work occurrence from sender
catalog UUID plus package UUID when no explicit request is supplied. First
intentional admission uses `new_request=True`; normal retry uses the existing
request. Absent Operational accounting fails closed unless the caller supplies
an explicit cumulative WorkBudget. Export's unknown timestamp is None; newly
measured local receipt scheduling time is separate from the original envelope.

## Request issuance and Operational loss

`GitAcquisition.acquire_from_native`, `acquire_metadata_only`, and
`PairedAcquisitionCoordinator.admit_paired` accept `new_request=False` and
`request_identity=None`. Default request coordinates are the Capture UUID pair;
a separate genuine explicit request can preserve Capture by supplying a fresh
RequestIdentity. Existing requests always verify their checkpoint and accumulate
actual work across attempts. Initial deliberate work requires the new flag.

Before creating a request, `OperationalAcquisitionLedger` atomically creates and
fsyncs `p5-request-witnesses/<request-origin>/<request>` containing only those
request UUIDs. Missing old SQLite state cannot become unspent work, even if a
caller repeats `new_request=True`. An incomplete witness also fails closed.
These local scheduling safeguards are not Core facts, sender authentication,
source payload staging, or authority for completeness. Losing both accounting
and its external witness is outside continuation support; callers must not
remove witnesses to restart an issued request. Accepted Core/Context reads do
not depend on Operational or these witnesses. Process/SQLite behavior is tested;
host power-loss recovery/activation remains P7.

## Historical evidence and replacement nodes

The old P5 prose's 790 total was an arithmetic/documentation error: its stated
20+4+762 equals 786, matching the historical JSON receipt. That receipt is kept
unchanged and is not a new run. The old independent review's HMAC claims were
incorrect; no such implementation existed and none is added.

Existing nodes keep their original intent. Initial acquisition/import calls now
explicitly start requests. `test_exchange_refuses_intrinsic_spoofing_without_validated_bytes`
recomputes the checksum after changing sender flags, so it still reaches the
independent domain check. `test_operational_retry_ledger_and_recreation_resilience`
now rejects reusing the lost request and creates a genuinely fresh RequestIdentity;
additional total/partial loss nodes cover the corrected distinction. No nodes
were removed, skipped or xfailed. New execution receipts bind the corrected
feature/tree separately from the preserved historical receipt.

## Executed correction evidence

See [the exact-node correction receipt](evidence/p5-correction/README.md): author160 focused nodes, independent64 (47 overlapping P5 +17 external), and4 clean-archive installed distribution nodes. Counts are separate and not summed across overlapping selections. Four required audits, Ruff and formatting passed. Final combined acceptance belongs to the integration receipt.
