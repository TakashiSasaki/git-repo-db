# ADR 0031 I6-C main integration

The owner explicitly requested completing and merging the remaining work on
2026-10-25. This integration carries the reviewed source from PR #172 and the
supplementary review evidence from PR #174 into main as one merge, preserving
the complete stack ancestry and original branches.

## Corrected identities

`identities.json` records values obtained from actual Git objects. The correct
submission tree for `a700676b317e60566f2925222b6cbc5582a525ef` is
`85246784625024ecbed114c36c75aac88d8504f8`; PR #174 had recorded
`3f191b7d3f82cb34220b330ec02882a88dc18042`. Its active report and summary are
corrected here, with their provenance digests regenerated. Earlier versions
remain in Git history. The review HEAD is
`3a52cd8dee8f0ac5ac4e8f319e3b54f27a3c55ad`; a different SHA copied into the
PR #172 description was a transcription error.

## Integration and validation scope

The main-only merge commit since the common ancestor has no effective file
changes relative to that ancestor. `git merge-tree --write-tree` combines main
and the reviewed stack without conflict and reproduces the review tree.
The integration commit has main and the review HEAD as parents. Additional
changes are limited to documentation and identity/provenance corrections.

The source Access CI is successful, with 947 scoped passes. Its broad suite
reports 1,646 passes, 181 failures and 20 errors, reconciled to 201 inherited
non-successes, 73 resolved nodes and zero changed/new failures. This is scoped
acceptance, not an all-tests-pass or release claim. The formerly blocked wire
identification test now executes and passes; the comparator exception is unused
in the current result (zero progressed barriers).

Final candidate identity, independent ancestry/tree review and CI results are
recorded in the main integration PR, avoiding a self-referential commit SHA in
its own tracked manifest. Executable input equality is checked over src, tests,
scripts, pyproject.toml, uv.lock and .github. Package README inputs are unchanged.

I7/I8 activation, ordinary Transfer, deployment, Release dispatch and real
catalog operations are outside this merge. Both Transfer SQL fences remain.
Existing final-tree verification procedures already cover this correction;
no additional Agent Skill is needed.
