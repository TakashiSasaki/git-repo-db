# R3 final independent verification of the typed-reader candidate

Reviewer: R3, independent of root's implementation and regression authorship.
Final review started 2026-10-18 **13:03:58 JST**. The fixed source was commit
`536ad33941283a439825ad606b8718c88c967ffa`, tree
`169b5d7ad5dea4fa271f71bea96863bc318fb332`, in clean read-only worktree
`/workspace/access-review-typed`. R3 changed no source/test files and ran no heavy
pytest process. Evidence and synthetic data were written only outside checkout.

**Disposition: all reproduced R3 implementation findings are corrected and
independently rechecked at this exact executable tree.** Cross-seed Exchange
remains the explicitly documented R3-03 contract gap, with its guards preserved.
This bounded review does not accept the whole ADR replacement, authorize merge,
or certify a release. Final broad CI/distribution results belong to root's
separately bound evidence, not to the executions below.

## Actual runtime and executed evidence

Python 3.13.5 loaded
`/workspace/access-review-typed/src/repo_catalog/__init__.py`. Actual SQLite was
3.51.3; `SELECT sqlite_source_id()` returned
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
No runtime version substitution or disabled network guard was used.

All four scripts ran sequentially with
`LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1` and
this worktree's own locked `.venv/bin/python`. Each exited 0 and wrote its exact
commit/tree/runtime/module binding. These are **91 independent check groups**,
not 91 pytest nodes or a replacement for root's full workflow cohort.

| Script / result directory | Actual JST interval | Groups | Verified meaning |
| --- | --- | --- | --- |
| `probe_stored_capture.py stored --expect-fixed` | 13:04:07–13:04:09 | 14 | Twelve touched stored-corruption cases stop persistently and preserve suspect Core bytes; two valid incoming conflicts reject without a false stop. |
| `probe_metadata_post.py metadata` | 13:04:14–13:04:23 | 58 | Standalone/paired nonseed SHA-1/SHA-256, nested ownership, all Capture Coverage containers/owners, global OID/field meaning, physical pairing, fixed intent, actual budgets, no raw staging, explicit new request and preserved Exchange fences. |
| `probe_notes_post.py notes --expect-fixed` | 13:04:28–13:04:31 | 12 | Real direct-tree Notes, exact body/Capture replay in both APIs and object formats; explicit-progress A-to-B source refusal; all incoming foreign-existing-Capture paths; distinct external source preserved. |
| `probe_capture_controls.py controls` | 13:05:06 | 7 | Exact Unicode/surrogateescape ref/key round trips, absent pair=None, invalid caller tuple/list/UUID inputs refused without corruption stop. |

Every directory above contains `results.json`; adjacent `.stdout` and `.stderr`
files preserve command output. Script copies in this directory are byte-identical
to the scripts actually invoked from the earlier `post`/`final` evidence paths.
No fixture error occurred in these final four runs. Earlier fixture mistakes and
superseded candidate failures remain in their original evidence/reports.

## Finding closure and exact corrected source

| Finding | Final disposition | Checked corrected source and independent evidence |
| --- | --- | --- |
| R3-01: external nonseed target refused as catalog-seed mismatch | Closed | `application/acquisition.py:902` passes selected Repository into request scope, while actual Core/Operational pairing stays seed+instance based. Four metadata positive groups retain original observations, physical R0 identity and exact replay rows with increasing work. |
| R3-02: seed-shaped outer request accepts registered foreign nested claim | Closed | `domain/native_acquisition.py:220` and `application/acquisition.py:164` preflight nested repository/capture owners. Sixteen negative groups include the original registered-R1 counterexample shape and assert all authoritative rows unchanged in both APIs. |
| First post-fix Notes scope/source findings (root report R3-P01; independent first report P01/P02) | Closed | `application/acquisition.py:885`, `:895`, `:1808` preserve supplied source scope/format and the exact Notes request scope in both preparation paths. Four real live-Notes groups pass; shared explicit work/progress A-to-B retarget fails before admission. |
| First post-fix existing Capture path (root report R3-P02; independent first report P03) | Closed | `application/acquisition.py:194` compares every supplied Capture's stored original binding before admission, including no-Coverage cases. Six explicit/claim/group controls reject foreign actual ownership with no changed rows and unchanged original Capture. |
| R3-C01: touched corrupted Capture mislabeled or missing parents repaired | Closed | `adapters/sqlite/git_core.py:114` is now a typed snapshot reader with `_decoded_read`, `_stored`, canonical full-key reconstruction, both FK-parent existence checks and successful-completion fencing. `application/acquisition.py:156` delegates to it; prepared Core delegates to the same reader. Twelve corrupted-value/parent controls now raise `AUTHORITATIVE_CORRUPTION`, persist stop and leave exact suspect Core bytes unchanged. Sound incoming mismatch remains non-corrupt. |
| R3-03: cross-seed Exchange | Remains partial contract, intentionally unexpanded | Exchange production files are byte-unchanged from the reviewed baseline. Same-seed onward RepositoryClaim/observation preservation passes; cross-seed import still refuses `REPOSITORY_MISMATCH` without mutation. No singular-header relabeling, pairing removal or invented Repository membership is used. |

Core's immutable Capture identity and original source/ref/root are preserved.
Externally attributed Capture.source may differ from outer intake attribution;
the explicit positive control retains its entire original key. Unicode and
surrogateescape references are reconstructed byte-exactly, not normalized or
replaced. Global OID/field facts remain independent of Repository membership.

The work budget remains cumulative: in the independent native-body replay case,
input work grows from 152 to 304 bytes and verification work from 608 to 1,216
bytes. Operational continuation JSON contains neither raw text nor hex nor the
unique body canary. Explicit new requests can append compatible facts under the
same genuine Capture pair; changed old request attribution/time/selection fails.

## Diff, tests, skills and limits

R3 read the full production/test delta from the second candidate and the associated
report, acceptance-ledger and skill changes. The new 12 regression cases assert
six exact-schema corruption types in standalone/paired paths, persistent stop and
unchanged suspect file hashes. The source file now contains 75 parametrized cases;
R3 reviewed their assertion meanings but **did not execute that pytest file** in
this pass. Root's reported 75-case checkpoint is separately authored/executed.

The workflow change adds `git_core.py` to path triggers and lint/format scope; it
does not remove runtime targets or lower the SQLite requirement. The linked
acceptance entry adds the actual corruption regression rather than marking item
11 complete. Root must still reconcile its exact final collected/executed node
sets and interrupted-node rerun, audits, distribution and hosted checks.

The existing `three-store-invariants/references/access-native-acquisition.md`
skill now records the independently demonstrated live-Notes scope/explicit-progress
source distinction, all incoming Capture paths, and typed touched-authority
validation with parent checks. The skill correctly preserves invalid-input versus
stored-corruption classification and grants no new authority.

Access backup source is unchanged from the baseline. Its original independent
WAL, history, grant stripping, input immutability, strict member/hash/CHECK/FK,
no-replace and uncertain-publication results keep their baseline tree binding;
R3 does not claim those scripts were rerun on this final candidate. R3 did not run
installed wheels, hosted CI, MkDocs, full ordinary/release pytest, process-kill or
hardware power-loss qualification. The 91 groups above are finite independent
rechecks, not an exhaustive attack/performance claim.

R3 performed no GitHub write, push, main/parent update, merge, release, tag,
deployment, real-catalog/backup access, credential lookup or activation. All data
was synthetic. Whole-ADR replacement approval/date, merge and release remain
distinct human gates. No outstanding reproduced material R3 defect remains in
the authorized correction scope at the stated tree.
