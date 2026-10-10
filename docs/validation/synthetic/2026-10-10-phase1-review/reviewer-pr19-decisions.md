# Independent review: PR #19 decision scope

## Reviewed revision and integration

- Decision commit: `1cd407b41cb0ee6ede2b0f6ec025d8c5f528b017`
- Decision tree: `ecb272517551d00009787f84f268f7ef01e34fa0`
- Parent: `65e80cf5eac5bc7aa99415c9a09517fdc6017d92`
- SHA-256 of `docs/phase1-api-original-retirement.md`: `1d47814b00dd9d4eecfc1be25b5b50bb12f10c27dd3ac3a8b05187297c14daf7`
- Base: `47fd5b88355b98019c0c04408449081e16ab4505`, schema 17.
- The decision checkout was clean and read-only. The document diff passed `git diff --check`.
- Normal merge into the PR #20 integration checkout is present as `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9` (tree `bf6f5e1b037cf18b798086b9ef56abd68e211380`), with parents `7beab8bae32b1adfad077393975245f3975fc641` and the decision commit above. The decision commit is an ancestor of the integration HEAD. The integration checkout has other uncommitted work; this review made no changes there.

## Decision review

The R1–R7 scope at decision lines 27–47 clearly retires independent saved-response reparsing/extraction, offline replay, standalone archive/CAS management, API-only repair for reuse, rejected-response retry retention, and standalone original distribution. Lines 51–65 classify retired-only, shared, and deferred dependencies and require separable removals without fabricated observations or weakened completeness. Lines 69–82 preserve exact domain text, raw Git identity/content, shared byte integrity, ownership, provenance, conflicts, transfer evidence, and Coverage v2. Lines 84–90 defer lifecycle, historical selection, publication identity, normalized completeness, provider fields, cache/restart, retention/GC, and exchange trust/ownership.

The document explicitly preserves retained dependencies at lines 59–65 and 101–121: successful historical PR/Git publication inputs and Source inventory, accepted live restart/304 evidence, historical exchange proof, and shared physical integrity are not treated as deleted. Rejected API bytes are retired without deleting required domain content. No replacement lifecycle, publication, collection-proof, cache, retention, or exchange architecture is selected.

## Historical rule mapping

The mapping below is in `docs/phase1-api-original-retirement.md` lines 99–116, checked against `docs/model-integration-status.md` entries D3/D23/D25/D28/D29/D31/D36/D37 and CAS-3/4/9/16/42/44/46/49:

| Rule | Retired mechanism | Preserved contract / boundary |
| --- | --- | --- |
| D3 | API offline reparse and supplementary parser projection | Git acquisition/result identity and truthful live observation times. |
| D23 | Archive-only byte registration/comparison | Byte sharing does not merge observations; retained publication inputs remain where required. |
| D25 | Retrospective API execution/publication | Historical/Git immutable result identities remain pending replacement publication/lifecycle decisions. |
| D28 | Inputs used exclusively by API replay | Typed, owner-checked historical/Git inputs and sealed membership remain. |
| D29 | Replay-generated API facts | Historical facts and existing atomic publication remain; current Issue/review attribution stays gate-free. |
| D31 | Replay-only ownership machinery | Typed domain owners, Source inventory and historical owner XOR remain. |
| D36 | Retired-original-only FKs/guards | Git, historical-domain and current typed owner/parent integrity remain. |
| D37 | Failed-original retention/retry | Successful live inventory publication remains pending normalized inventory decisions. |
| CAS-3 | Original-exclusive JSON references | Typed Git/domain/proof references and validation remain. |
| CAS-4 | Standalone original distribution | Required domain bytes and inseparable historical proof closure remain pending normalized proof. |
| CAS-9 | Validators exclusive to retired scopes | Ownership, missing-dependency and conflict validation remains. |
| CAS-16 | Rejected API original staging | Git/domain staging and shared corruption protection remain; no API retry archive substitute. |
| CAS-42 | Distribution for reinterpretation/replay | Exact live 304/domain-exchange proof remains pending cache and normalized-proof decisions. |
| CAS-44 | Standalone original distribution context | Required historical capture/owner checks remain. |
| CAS-46 | Original-only exchange branches | Valid domain selection and exact completeness proof remain; historical normalized proof is deferred. |
| CAS-49 | Original replay as an independent feature | Partial/unknown/conflict and sealed-member checks remain; normalized proof is deferred. |

## Authorization clarification and conclusion

The original version's no-merge wording was corrected in this final decision commit. Lines 4–8 and 145–149 now distinguish what this decision record itself authorized from the later owner instruction, which explicitly authorizes PR #19 and #20 merges after review and acceptance gates pass. This resolves the only documentation finding from the earlier independent review.

Conclusion: PR #19's decision scope is accurate and safe to merge. No critical architectural scope defect was found. This is a documentation/design review; it is not an implementation acceptance or runtime test receipt for PR #20.
