# First Query/CLI/paired projection checkpoint

Cloud-only implementation on `codex/adr0036-query-projections`, directly based
on fixed PR 226 HEAD `1e70d1ddfe5c9f4a43f52775bcc39598b8d656cc`, tree
`18e0a00c9eb6445dbca13984931632fcb509bf1a`. Fresh main was
`2ff4aab59dcdbada264d9a6a978c07b6ac4ad0d2`; open-PR lookup found only PR 226.
The parent reported scoped PASS for PR 226 (135 cases/405 phases) and closure
of R226-01/02. This implementation neither edits that fixed branch nor claims
its own independent approval. No old HTTP-403 artifact was fetched.

## Implementation and boundaries

Git-object results automatically expose new `ref_notes_targets` without requiring
Capture rows. The paired resource's Core resolutions carry that same projection
inside the existing paired snapshot. Each entry retains the whole original
observation/Claim candidate set and the exact Claim's checked Mapping projection,
including reported Groups, alternatives and receiver-local evidence. Shared
root content alone confers no association or local proof. The existing checked
Core APIs supply these results; no duplicate ref reader/proof implementation
is introduced. Legacy `notes_targets` remains separately labeled.

The `ref-observations` opt-in CLI command and paged application endpoint expose
rootless, unknown and subject-only observations as well as known results.
They reuse snapshot fencing, endpoint/filter checks and explicit UUIDv4/v7 cursor
validation. Byte-valued refs/symbolic names use `{bytes_hex: ...}` without UTF-8
loss. Scan scope is bounded to 10,000 subjects/association coordinates; excess
raises QUERY_BUDGET rather than truncating into apparent completeness. New checked
projection work is shared across object pages, paired dependencies and paired
resource pages rather than resetting per object.

This first unit is metadata/evidence projection. New note bodies continue to
use the existing explicit `read_ref_note_bytes`; no physical availability or
permission is inferred, and no new generic note-body output interface is added.
`include_bytes` retains its metadata/legacy behavior. The old `notes` CLI remains
the legacy Capture listing. The transition contract documents these exact
boundaries. Search, schema/wire/family removal, normal Schema 21 and unrelated
GitObservation IDs are unchanged. No old assertion was removed or weakened.

## Actual verification

Clean tested HEAD `904eead6b4775171c03719ab39bc7d3afd5a4d65`, tree
`3a3c95fc7e3b871ac0536ee1c888c70494d8ff69`. Python 3.12.15 / Python-loaded
SQLite 3.53.1 / x86_64, using the verified `scripts/local-run.sh` environment.

```sh
scripts/local-run.sh python scripts/ci_profile.py profile \
  --name ref-query-reviewed --output artifacts/ref-query-reviewed --workers 2 -- \
  tests/integration/p6/test_ref_query_transition.py \
  tests/integration/p6/test_queries.py \
  tests/integration/p6/test_pagination_snapshots.py \
  tests/integration/p6/test_cli.py
```

23 passed, zero failed/error/skipped/unexecuted; process exit 0; 9.23 seconds
elapsed with two workers. Collection/start/JUnit sets each contain 23 nodes;
69 successful phases and terminal exit reconcile with `consistent_success=true`.
The profile's raw ALL_PASSED_UNVERIFIED_SELECTION label is retained separately
from the additional node reconciliation and its recorded clean runtime binding.
Ruff and format checks passed. These are focused development results, not full
release or installed-distribution acceptance.

New tests cover both native Git formats, bare modes, Core-only/paired Query,
new data without Capture, competing root/unknown Claims, no Mapping authority
borrowed by the other Claim, binary ref JSON/CLI output, subject-only pagination
and stale-cursor refusal. Existing object, paired, cursor and CLI behavior checks
remain in the selected cohort. This does not claim exhaustive corruption/body,
concurrency, forged-cursor or every paired-resource dependency counterexample;
those remain relevant independent-review scope.

Initial execution: 19 passed/4 failed because the new pagination endpoint had
not yet been registered in cursor-key validation. The original logs are kept.
The correction adds explicit endpoint width and typed UUIDv4/v7 validation.
Later runs followed changed work-budget sharing, competing-root assertions and
clean-source binding; counts are not added together.

Complete logs, JUnit, journals, source receipts and node reconciliation for the
initial and corrected runs are in
[`query-projection-profile.tar.gz`](query-projection-profile.tar.gz).
Uncompressed copies remain under `artifacts/ref-query*` in this environment.
Later evidence/ownership commits leave the tested product inputs unchanged;
final candidate SHA/tree and final hosted CI are reported at handoff.

Parent PR is 226, with the new Draft PR targeting its fixed branch. No merge,
deployment, formal APPROVED review, real-catalog change or access workaround
was performed. Await independent review of this first unit before follow-up.
The requested Sol/high selection is not independently attested by runtime receipts.
