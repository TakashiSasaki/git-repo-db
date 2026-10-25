# Independent I1a implementation review

Reviewer: non-author `codec_review` subagent. Reviewed frozen commit
`ebb48d4c0beeeb6c19d33d672185894886765835`, tree
`318ad07874ab436206e6a61f231b308a421cfc54`, against accepted ADR 0031 and
the identity/finite-bound/canonicalization clauses and complete specification-vector
table in `docs/architecture/context-resource-schema.md`. Review used a separate
detached worktree at the exact commit; uncommitted I1b work was excluded.

**Disposition: approve the bounded I1a scope. No substantive finding or accepted-ADR
conflict identified.** This is a codec implementation review, not generalized
production DDL, integrated product, packaging, release, or activation acceptance.

The public API preserves the native-versus-serialized distinction:
`encode_identity(value: IdentityValue) -> str` and
`parse_identity(text: str) -> IdentityValue`. Exact native str/list types only,
Unicode scalar validation, ASCII-escaped spelling, exact serialized equality, and
inclusive limits agree with the normative contract. Generic `canonical()` and
Exchange envelope serialization are unchanged in this commit. Parser byte/type
checks and iterative grammar/depth/node scan precede `json.loads`; native exact
escape-expansion accounting and iterative O(depth) traversal precede `json.dumps`.
Arrays are never flattened or sorted, and strings are never normalized/coerced.
Rejecting all byte buffers, including invalid UTF-8, is explicit in this TEXT-only
API; transport decoders remain responsible for strict UTF-8 before supplying TEXT.

Independent execution, per genuine runtime:

| Runtime | Source ID | Frozen author tests | Independent observations |
| --- | --- | --- | --- |
| SQLite 3.51.3 / Python 3.13.5 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` | 195 executed, 195 passed, 0 failed/error/skipped | 50 groups, all passed |
| SQLite 3.53.1 / Python 3.12.14 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` | 195 executed, 195 passed, 0 failed/error/skipped | 50 groups, all passed |

The independently authored script is `work/i1a-independent/counterexamples.py`.
Its 50 groups include distinct independently spelled escape expectations;
supplementary-plane endpoints; malformed/lone/reversed/uppercase surrogate
spellings; alternative quote/backslash/solidus/control escapes; DEL; trailing
data and arrays; exact depth 31/32/33; exact node 4,096/4,097 with root included;
exact 262,144/262,145 bytes; supplementary escape expansion; sentinels proving
structural/forbidden/budget refusals occur before decoding/serialization; a native
cycle; and an already-allocated 1,000,001-node sibling array rejected with less
than 65,536 temporary bytes in this measured runtime observation.

Each runtime also independently passed deterministic reference comparisons:
5,000 native identities against the specified stdlib serialization profile;
15,000 serialized mutations (3,753 canonical accepts, 11,247 refusals); and
9,331 exhaustive short strings over `[]",a\\` (110 canonical accepts, 9,221
refusals). These iterations are nested in the 50 groups and are not summed with
pytest counts as distinct tests. No timing or universal memory guarantee is
inferred from the observation.

Commands were run from `work/i1a-review-tree`:

```sh
LD_LIBRARY_PATH=/workspace/git-repo-db/work/i1-sqlite/runtime/minimum/lib \
  /workspace/git-repo-db/work/i1-sqlite/venv/bin/python \
  /workspace/git-repo-db/work/i1a-independent/counterexamples.py
LD_LIBRARY_PATH=/workspace/git-repo-db/work/i1-sqlite/runtime/minimum/lib \
  /workspace/git-repo-db/work/i1-sqlite/venv/bin/python -m pytest \
  tests/unit/test_resource_identity.py -q --junitxml=../i1a-independent/minimum-author-suite.xml
/workspace/git-repo-db/work/i1-sqlite/venv-newer/bin/python \
  /workspace/git-repo-db/work/i1a-independent/counterexamples.py
/workspace/git-repo-db/work/i1-sqlite/venv-newer/bin/python -m pytest \
  tests/unit/test_resource_identity.py -q --junitxml=../i1a-independent/newer-author-suite.xml
```

All four processes exited zero. Full JSON observations/runtime source IDs and
module SHA-256 are retained in `work/i1a-independent/minimum.json` and `newer.json`;
full author-suite output and JUnit are retained alongside them. No SQLite
comparison-schema cases were claimed in this pure codec review. No Provider,
real catalog, merge, release or production activation was performed.

## Published commit binding

The connector-published commit is
`d92377599a50f192f534836fc12402a5fe87ca83`, parent
`1ccb7f1902127cde649edcf605bb6d5935427302`. The reviewer independently fetched
that exact object and verified its tree is
`318ad07874ab436206e6a61f231b308a421cfc54`, identical to the executed local
`ebb48d4c0beeeb6c19d33d672185894886765835` tree. `git diff --quiet` between the
two commits exited zero. This binds the review and executed source to the
published I1a commit despite different commit metadata; no source rerun or
separate product acceptance is claimed for the publication operation.
