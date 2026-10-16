# Independent Reviewer B — final source/tree binding supplement

Reviewer `/root/readiness`, 2026-10-16 UTC. This supplements unchanged `REVIEW-B.md` (SHA-256 `412c6ab72903f2c8853b95305ce2c478c58c508d79bf4d3fbcd6e577f0397934`). It performs Git-object/input comparison, not a new runtime test run. No production or test correction is authored by this supplement.

**APPROVE unchanged B runtime scope at final public candidate `74f90adae40ae60076dca33629fa2edbf5763474`, tree `b11075b53eb0bda4febc710c46c059dc6edf4054`, after combining the reviewed P7 and independent Pages inputs as specified below.** Existing actual execution remains 304 passing nodes / 912 passed phases on `98c818a1cd292bcaf10e0aad851545787d3816b0`, tree `3659919159bae1aee4530c3380493c62eefed425`: 255 P7, 20 P2/P3 compatibility, 29 P5/P6 compatibility. Every collection/JUnit/journal node matched, and the actual 255 P7 nodes matched PR 88's frozen installed-wheel node set. This supplement does not relabel those executions as a fresh run at a different SHA.

Refreshed remote heads are PR 93 `7dc31256907aff4412170bc3f3ce3069b2ad89f2`, PR 91 `1700ed37e82a6028cfa40c86b35db7621dd50404`, PR 92 `74f90adae40ae60076dca33629fa2edbf5763474`; main remains `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`; PR 88/89 remain their original final heads. Actual public production files are byte-identical between prior candidate 83d3c140 and final74. The changed public decoder test moves two real Search assertions to `open_search(readonly=True)`; it is outside the 304-node execution. Other intervening changes are skill/evidence/ancestry follow-ups.

Independent `git merge-tree --write-tree` plus local unreferenced two-parent `commit-tree` objects produce:

| Combination | Conflict-free effective tree |
| --- | --- |
| final74 + PR 88 | `8dcc1f022c50977ad10530b6e2baa24941b15e2f` |
| previous + PR 89 | `5795e1ed9d0224d74600c7e9988229ebb39a20ba` |
| main + #89 | `ed80623514a5e574d1e24e908b95504f60b815db` |
| previous + #87 | `6ebd07cf4d6846e7d964c1be571c8507c037b9be` |
| previous + #88 | `e250fe0ad801013fb9c59e929cfc7f875fabb5b8` |
| previous + #93 | `d4bf2253eed2ea7df26336c681c5a5241dd36bf6` |
| previous + #91 | `f749d63fb1162520b21512a0690bf2015441ba91` |
| previous + #92 | `5795e1ed9d0224d74600c7e9988229ebb39a20ba` |

The direct combined tree equals the owner sequence's final tree. All six steps are conflict-free with true original PR heads preserved as ancestors; synthetic merge SHA values are not predicted GitHub IDs. No remote merges or refs are changed.

`FINAL-BINDING.json` and `final-bound-inputs.json` contain exact scope and hashes for **424 unchanged declared inputs**, including **all 124 production/package/resource files**, 215 test/helper files, 23 scripts, 59 immediate implementation/audit/design files, the test workflow, project configuration and lock file. The canonical manifest SHA-256 is `1720da1515fd51afca022bb42ccfe63e5d2480f98976d23d5d52916745a29b17`. Every byte was compared between actually tested combined98 and final74+P7+Pages. All 25 selected P7/compatibility test/conftest files and their conservative test/helper pool are included. Explicit test imports were inspected; the excluded tests/builder are not imported or invoked by the selected tests/fixtures.

This is **not** a blanket claim that all executable inputs remain unchanged. Exactly four changed executable paths are outside this B runtime binding: `tests/integration/test_git_decoder_byte_validation.py`, `tests/unit/test_build_docs_site.py`, `scripts/build_docs_site.py`, `.github/workflows/pages.yml`. Root's final74 full run and PR 89's exact-source publication evidence own those scopes respectively. No live/stress, installed-distribution rerun, full hosted release acceptance or production activation is inferred.

The four modern audit scripts, all production/schema resources and their immediate generated/authored implementation inputs also match the actual B-tested audit tree. Thus the recorded implementation-boundary, call-site, P1-schema and publication-free exits remain bound to unchanged inputs; no new audit execution is claimed. The historical Phase 2 `exchange.EXCLUDED` helper failure remains separately preserved and is not called PASS.

The optional final merge of old PR 90 head `9f5634536c54cc372b320ef1485d3a83fc90ba91` exposed a concrete documentation-only conflict in `.agents/skills/ci-final-tree-verification/SKILL.md`; this does not affect the six runtime PRs or their tree above. Raw conflict output is preserved in `FINAL-BINDING.json`; its conflict-marker tree is not an accepted merged tree. Root separately authorized an ordinary PR 88→PR 90 reconciliation retaining both verified skill clauses and independent review, with PR 90 retargeted to depend on PR 88. That follow-up's exact source/CI review is separate from this immutable runtime supplement. Owner merge order remains #89 → #87 → #88 → #93 → #91 → #92, with reconciled #90 as a final independent evidence PR. Explicit owner merge authorization and fresh remote-head/parent/tree/base/status preflight remain required.
