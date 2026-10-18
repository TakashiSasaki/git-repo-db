# R3 independent re-review, second candidate 8dcb515

Start: 2026-10-18 12:57:39 JST. Fixed commit
`8dcb5150ac6c987a93b96e56a9f935184affab94`, tree
`9e4886fcecab35e30ac92125d75d552c869d0004`, read-only worktree
`/workspace/access-review-post-final`, clean before and after the scripts.
Actual module import came from that worktree. Runtime was Python 3.13.5,
SQLite 3.51.3, source ID
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.

R3 is independent of the root implementation author. No source/test edits were
made. Independent scripts ran sequentially alongside root's separate controlled
workflow; R3 ran no heavy pytest cohort.

## Verified corrections

The same independent `probe_metadata_post.py` passed all 58 check groups at
12:57:58 JST; results are `metadata/results.json`. The independent
`probe_notes_post.py --expect-fixed` passed its 12 groups at 12:58:11 JST; results
are `notes/results.json`. Both record exact commit/tree/runtime/module binding.

The new diff correctly adds the real Notes request scope in standalone and paired
preparation, saves source scope/format for explicit caller progress, and checks
every incoming Capture against its existing entire original key, including paths
without Coverage. The new 17 regression cases exercise eight live-Notes seed/
nonseed/format/API controls, one explicit source-switch refusal, and eight existing
Capture owner/source/ref/root conflicts. This brings the source file to 63
parametrized cases; R3 read assertions but did not claim to execute root's pytest.

Independent real direct-tree Notes cases passed in SHA-1/SHA-256 and both APIs:
exact note body, Capture pair and full authoritative rows survive replay. Actual
source A-to-B switch now refuses `INCOMPATIBLE_REPLAY` without admission. All six
incoming Notes paths hiding a foreign existing owner now fail `REPOSITORY_SCOPE`
before any write, and external attributed Capture sources different from outer
intake remain exact. First-round direct R3-01/R3-02 and first post-fix P01/P02/P03
counterexamples are therefore corrected at this second candidate.

The report/skill text combines the first-pass scope/source findings as R3-P01 and
the incoming stored-Capture finding as R3-P02. The independent earlier
`post/f81a-review.md` used three more granular labels; those are the same cases,
not additional unrelated findings.

## New material finding: touched authoritative Capture bypasses stop semantics

Severity: **High**, authoritative corruption may be silently repaired by normal
acquisition. Source:
`src/repo_catalog/application/acquisition.py:156`, `_capture_binding`, and its
preflight callers. The application reads a full stored Capture through generic
`core.sql`, outside a checked typed adapter reader.

Independent `probe_stored_capture.py` constructs disposable catalogs, changes only
synthetic stored evidence under explicitly disabled fixture guards, then restores
the exact schema/immutable trigger text before invoking unmodified production
APIs. `8dcb-stored-capture/results.json` records 14 groups in both APIs:

| Touched stored value | Observed result at 8dcb515 |
| --- | --- |
| Empty source | `INCOMPATIBLE_REPLAY`, no persistent stop |
| Invalid UTF-8 source | Raw `OperationalError`, no persistent stop |
| Invalid canonical ref tag | `INCOMPATIBLE_REPLAY`, no persistent stop |
| Invalid root OID | `INCOMPATIBLE_REPLAY`, no persistent stop |
| Missing referenced Repository parent | **Acquisition succeeds, Core changes, no stop** |
| Missing referenced nominal root object | **Acquisition succeeds, Core changes, no stop** |
| Sound stored Capture with valid but conflicting incoming source | Correctly refuses `INCOMPATIBLE_REPLAY`, leaves source unchanged, no stop |

The last row is the negative control: invalid incoming input is not corruption.
The missing-parent cases demonstrate automatic repair of previously authoritative
evidence under normal use, violating the accepted persistent-stop/fresh-restore
boundary. File hashes show the suspect Core was changed. The first four cases
show misclassification and failure to persist the stop when reading damaged rows.

Required correction: put selected Capture lookup in a typed SQLite adapter reader
with snapshot, `_decoded_read`, `_stored` canonical Capture/ref/UUID/OID
reconstruction, selected FK-presence checks and completion fencing. Let prepared
metadata delegate to that reader. Publish the catalog stop before returning the
failure or admitting anything; leave the suspect Core unchanged. A matching hash
or supplied valid Capture must not repair a missing repository/root row. Keep the
sound incoming-conflict control non-corrupt.

The executable script supports `--expect-fixed` for the next exact-tree re-review.
The earlier four-case observation is also preserved as
`stored-capture-corruption.json`. Root was notified at 12:59:05 and 13:00:13 JST.

## Scope and gate outcome

Exchange source remains byte-unchanged from the fixed baseline; its mismatch and
physical pairing guards remain intact. Same-seed onward evidence passes and
cross-seed admission remains an explicit contract gap with no mutation. Access
backup implementation is also unchanged; baseline backup results keep their own
tree binding and are not a claim that they were rerun on this candidate.

The new corruption finding leaves this candidate's R3 gate **not complete**.
The 58+12 successes are exact-tree scoped and may not certify a later executable
tree. No whole-ADR approval, merge/release eligibility or real-data permission is
implied. No real catalog/backup/credential or deployment was operated on.

Reusable lesson: new application preflight SQL becomes a typed authoritative read
when its result controls admission. Generic SQL's metadata-inspection contract
does not validate stored domain rows or classify UTF-8 failures. Validate actual
parents before a normal writer can recreate them; test the suspect file remains
byte-identical and the persistent stop exists. Preserve a valid incoming-conflict
control so malformed input cannot falsely stop a sound catalog.
