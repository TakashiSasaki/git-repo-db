# I5 Access acceptance requirements 11 and 15: new independent evidence

Implementation under review: `a54cb218226e3c91c44e979ee0df0543ea459502`,
tree `cc2eafaaeb8e3305270c17e74ae69edc42c0a50b`.
Historical `docs/implementation/access-a6-acceptance.json` remains unchanged:
requirement **11 is partial**, requirement **15 is deferred**. Its independent
review/ADR/merge/P8 gate fields have not been repurposed by this I5 report.

## Requirement 11

> Additional repositories beyond the Core seed can acquire independently without
> weakening catalog pairing, UUID selection or cross-repository Exchange fences.

The historical gap was specific: seed-only Exchange with neither a Repository-set
selector nor an explicit receiver-target contract. The current I3 implementation
provides independent R/O/C selectors and explicit
`permitted_repository_uuidv4s`; I2 and I4 preserve typed Repository qualifications
through intake/query/search/backup. This is an accepted ADR 0030 scope, not an
extension of Access authority.

Independent execution on Python 3.13.5 and actual SQLite 3.51.3 selected all 12
historically referenced #11 test functions plus 14 current boundary functions.
Parameter expansion collected/executed **82 nodes, all 82 passed, 0 failed,
0 errors, 0 skipped, 0 xfail**. Collection/execution logs, JUnit and exact command
arguments are retained as `access11-{collection,execution}.log`,
`access11-existing.xml`, `access11-commands.json` and
`access11-existing-execution.json`. These 82 existing nodes overlap the complete
cohort, so must not be added to its unique-node count.

Evidence mapping:

| Required meaning | Concrete executable evidence |
| --- | --- |
| Non-seed native and Notes intake preserves physical pairing | Access `test_nonseed_repository_acquires_actual_metadata`, `test_nonseed_notes_reuse_original_capture_and_budget`, `test_nonseed_paired_native_notes_preserves_catalog_pairing` (SHA1/SHA256); stored seed/instance unchanged |
| Non-seed external metadata preserves actual identity/provenance | All 12 original ledger references, including `test_nonseed_external_metadata_preserves_pairing_and_replay` and capture-owner/physical-pairing tests |
| Original request cannot switch repositories/intent/source or reset progress | Original replay/foreign-metadata/intent/notes-source tests; `test_plain_p5_native_scope_cannot_replay_under_another_repository`; `test_wrong_operational_pair_is_not_reinterpreted_as_repository_target` |
| Different-seed target registration requires explicit R permission | I3 `test_cross_seed_permission_identity_replay`; I23 source Coverage permission-cut and existing-receiver-source support tests |
| R/O/C scope stays independent and shared OIDs do not create membership | I3 empty/omitted sets, empty O/C injection, bounded typed Core graph and shared-OID membership-report tests |
| Capture/Notes/Coverage and complete keys survive interchange | I3 native/capture test and I23 `test_i2_source_coverage_and_native_capture_notes_survive_i3` |
| Domain Exchange does not import or revive execution consent | I23 `test_domain_exchange_neither_transports_nor_changes_real_access_grants` |

A newly authored I5 E2E probe additionally connects the previously separate
acquisition and Exchange paths in one execution. In each of SHA1 and SHA256 it
performs genuinely approved synthetic local Git+Notes acquisition into R distinct
from the sender seed, selectively exports R and O with empty C, and imports into
two fresh independent-seed receivers. Explicit permission admits only R and its
original captures; empty permission never registers R/captures. Neither recipient
registers the sender's unrelated seed. Each receiver's own immutable physical
seed/instance stays unchanged; no Access/Context is created; the original Access
file remains byte-identical; no Access Scope UUID, grants or connection tables
occur on the wire. Final result: **2 collected/executed, 2 passed, 0 failed/error/
skip/xfail**. See `test_access11_cross_seed.py`, `access11-new.xml` and
`access11-new-execution.json`. This probe reuses only existing synthetic fixture
construction/approval from the historical Access tests; its path and assertions
are new. It never acquires real repositories or uses real credentials.

Probe development had two failed two-node attempts, both incorrect SQL column
names in the new probe (`algorithm`/`oid` versus the existing
`object_format`/`full_oid`). Those failed receipts are retained as
`access11-fixture-attempt{1,2}.{log,xml}`. They are test-authoring errors, not
implementation counterexamples. Corrected execution is reported separately;
failed attempts are not erased or counted as passing.

**Recommendation:** the original #11 implementation gap is resolved within the
accepted ADR 0030 synthetic/offline scope. A separately reviewed ledger amendment
may change #11 to `covered`, append the current I3/I23 references and I5 E2E
receipt, set `gaps: []`, and update `verified_scope` to state explicit independent
R/O/C selection, different-seed receiver permissions and retained physical pairing.
Do not rewrite this historical ledger's old execution claims or gate statuses.
New I1–I5 acceptance evidence can record the same closure independently, as this
report does. This finding does not grant owner merge approval, P8 activation,
network-transport acceptance, extraction permission or release qualification.

## Requirement 15

> Real-data extraction is opt-in, leaves sources unchanged and reports excluded
> or unclassified legacy settings instead of guessing or executing them.

**Remain deferred.** The reviewed tree has key classification but no legacy
extractor, and the task explicitly prohibits real Catalog/credential operations.
I2/I3/I4 synthetic domain paths neither implement that tool nor supply real-data
source-preservation/exclusion receipts. No #15 extraction tests were run and no
full requirement fulfillment is claimed. No automatic ledger promotion is
justified. The unfinished optional extractor remains a disclosed separate scope,
not a blocker retroactively added to ADR 0030's synthetic implementation stage.
