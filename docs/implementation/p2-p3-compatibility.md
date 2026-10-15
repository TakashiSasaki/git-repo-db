# Production P2/P3 compatibility and integration handoff

**READY FOR P2/P3 OWNER REVIEW.** Both substantial implementations and their
independent reviews are complete. Zero open material findings or demonstrated
owner-level architectural contradictions remain. The common corrective dependency
[PR #73](https://github.com/TakashiSasaki/git-repo-db/pull/73) is required; original
#72 alone is **CHANGES REQUIRED**. The separately reviewed corrected integration
sequence #71 → #70 → #72 → #73 is **READY FOR OWNER MERGE APPROVAL** with current
checks and exact-tree revalidation. No authorization to execute it is implied.

No PR was merged, auto-merge enabled, main updated, Pages deployed, release made,
real catalog/backup changed, migration run or public initializer switched.
Schema 21 remains the active application until P8.

## Exact source and production boundaries

| Input | Executed/reviewed commit | Git tree |
| --- | --- | --- |
| Common P1 correction | `06a4ccd432476af15ee942e8cfcd9fbdf42357c7` | `58f627ff6acc5171d8620f606e366543eb3c7d02` |
| P2 production source | `8ce2fc4b41f2f7f5a1da9f2fcfbddb4c5cbabc8b` | `f61a7d9053e73d2fdf4761577012c9f989b2ca92` |
| P3 production source | `5e3b373bfc16ff1cad8d8f093af42a7f00d3d320` | `5776bb9b0aa81c9d4a841e446cfea5f3744f4726` |
| Committed combined validation | `b1b5f9cf11d9c0dd21302c5e22b881e1fcc39137` | `50f53c648425fa19515f63f514991f9d76c21656` |

Both production branches started from verified P1 `67e8be65` and incorporate the
**same** separately reviewed #73 history by merge commit. They target
`fix/p1-intrinsic-provenance`, with merge-base `06a4ccd...`; neither contains the
other implementation or independent #71 repair. This necessary adjustment from
the initial P1-only stack follows the owner's explicit shared-correction provision.
Feature heads may add documentation-only evidence; final PR metadata supplies
their exact identities. Executed source identities above are not relabeled.

The combined branch is published solely for reproducible validation:
[exact source and 20 compatibility tests](https://github.com/TakashiSasaki/git-repo-db/tree/b1b5f9cf11d9c0dd21302c5e22b881e1fcc39137/tests/integration/p2_p3_compatibility).
It is a real clean committed Git tree, not an uncommitted local union. It has no
PR or deployment. Reproduce with its own `uv sync --locked --group dev` environment,
then the exact collection/execution commands in [the receipt](p2-p3-execution-evidence.json).

P2 implements `GitCore`, selective `GitNativeSource` and a lossless native metadata
parser for SHA-1/SHA-256, preserving exact header/message bytes, binary tree names,
modes/order and tag structure. It uses original P1 nominal OIDs, attributed scalar
claims, immutable whole groups, Capture/ref/root observations and notes-role proofs.
Canonical facts have receiver-checked relevant scope; conflicts and negative
knowledge remain visible. Exact replay, metadata-only/Core-only operation, physical
copies, selected-byte checks and persistent corruption stops are exercised.
Ordinary blob retention and generic unchecked payload SQL are refused.
See [P2 implementation](p2-production-git-core.md), [execution](p2-execution-report.md)
and [independent review](p2-independent-review.md) for declared grammar and limits.

P3 implements `ContextPersistence` extending the exact P1 port, production
`Context` capabilities and modeled observation values. Durable Provider/Source/
repository/resources, PR/Issue/review/comment/thread/document relationships, exact
text, original clocks/provenance, field inheritance, alternatives, detach/transfer,
Source positives and typed Coverage are implemented. Unavailable attributed Git
references retain original field evidence separately from validated required links.
Standalone Context needs no Core; paired admission/reads use the common coordinator.
See the sibling's `p3-production-context.md`, `p3-independent-review.md` and
`p3-execution-evidence.json` for its exact-source evidence. Those files belong to
P3; the validation branch deliberately does not invent a serial PR dependency.

Neither production sibling changes DDL. The single common correction changes only
Core intrinsic guards/fingerprints and shared validation enforcement/audit isolation,
not identity meaning, table ownership or the 46-table/five-column Coverage contracts.
No accepted ADR was changed.

## Executed tests and independent corrections

Environment: Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19,
pytest 9.1.1, Ruff 0.16.10. Synthetic disposable Git repositories and SQLite stores
only. Direct pytest uses conftest's journal registration once; the known duplicate
`--journal` profiling wrapper was not represented as successful profiling.

| Category on exact combined source | Selected/executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| P2 Git Core | 194 | 194 | 0 | 0 |
| P3 Context | 75 | 75 | 0 | 0 |
| P1 regressions (excluding schema/disposition below) | 234 | 234 | 0 | 0 |
| Cross-store compatibility | 20 | 20 | 0 | 0 |
| Packaging/schema/disposition | 40 | 40 | 0 | 0 |
| Architecture prototypes/audits | 128 | 128 | 0 | 0 |
| **Total** | **691** | **691** | **0** | **0** |

All 691 selected IDs reconcile exactly once with journal starts, passing setup/
call/teardown phases and JUnit classname/name identities. Imported P1 functions
collected in P2 execute against `GitCore`; their JUnit source-file attribute alone
must not be used to misclassify them. Ruff check/format and all four schema/audit
commands passed (263 Python files formatted). Eight installed distribution variants
exercise P1 DDL plus P2 SHA-1/SHA-256 and P3 production outside the checkout.

P2's independent standalone branch run passed **594** tests; P3's passed **473**.
The independent combined reviewer passed **107** tests on the exact combined
commit, including all 20 compatibility adversaries, and verified identical shared
Git blobs, unchanged P1 portable dataclasses, 46 tables and complete 84-table/
625-column reconciliation. These overlapping invocations are not summed as unique
coverage. [Independent review](p2-p3-independent-review.md),
[receipt](p2-p3-independent-evidence.json) and
[identity/ownership proof](p2-p3-contract-identity.json) retain exact bindings.

Material counterexamples were corrected and revalidated rather than waived:
original reports gaining intrinsic verification; malformed native callback bodies;
metadata JSON/UTF-8/type damage; missing retained-copy/text evidence; forged head/
base proof scope; foreign-parent child collections; unavailable references causing
false corruption; wrong-store capabilities; stop timing through final reads,
rollback, deferred fetch and engine BEGIN/body/COMMIT faults; shared semantic-UDF
validation failures; and quadratic folded headers. The independent domain reports
preserve initial failing cases, correction commits and scoped rechecks. No reviewer
edited or approved its own production changes. These are task-specific independent
reviews, not invented formal GitHub approvals.

Development CI is lightweight; no complete hosted runtime or release acceptance is
claimed. Full application/live Provider/P4 acquisition/P5 Exchange/P6 public readers/
P7 power-loss recovery and activation/P8 runtime switch acceptance remains unexecuted.
The focused installed checks are not the complete released CLI distribution suite.

## Contract compatibility and collision result

All twelve requested cross-domain boundaries are checked by the actual production
adapters plus the common P1 adversaries: identical portable types/schema; independent
physical ownership and durability; Core-only operation; genuine-identity retry after
Core-first partial success; explicit missing-dependency qualification; pinned paired
reads rejecting false coherence; respective Coverage ownership; derivative-loss
independence; persistent stop despite unrelated Context/derivative success; and no
ordinary-file body endpoint. The six malformed-native callback cases first failed
on an earlier committed combination and all pass on the final one.

Sibling source/test changed-file intersection relative to common #73 is **empty**.
P2 owns native/Core files and Core regressions; P3 owns Context files and regressions.
Shared schema, ports, Coverage, DDL/fingerprints and coordination are byte-identical
between both siblings and the common corrected authority. Core-owned parser/UDF/read
extensions and Context-owned projection extraction do not change the original value
classes or signatures. The [pre-edit ledger and final collision record](p2-p3-ownership.md)
and independent static proof provide the exact paths and Git blob comparisons.

## Integration and next stage

The [read-only integration report](integration-preflight/README.md) records current
main `57de60b65c2ef29420a885b0c2102dc90e11fa75` and unchanged open heads #71/#70/#72,
plus corrective #73. Ordered effective trees are:

| Authorized future step | Expected head | Effective tree |
| --- | --- | --- |
| #71 | `155645c03417905fcb1a6485e916c10aef371318` | `e0ff950e755bc5b9fed18cecc83f26625434ffcc` |
| then #70 | `eb84be9b2061b026ad82b780cc95e062928f838a` | `e3bf1f0aeb3e0f0f16c445ced9f2ef7c6896f5c9` |
| then #72 | `67e8be65c3061b494c2c7373e2fd151398435f62` | `aea20a9aa4ff178b54119936a121fde761bcd001` |
| then #73 | `06a4ccd432476af15ee942e8cfcd9fbdf42357c7` | `819178212290bc8473bbc31e4a78e95bf125ebc0` |

All original commits survive merge commits. The [executable gated plan](integration-preflight/integration-owner-authorized.sh)
was syntax-checked only, never executed. It requires separate explicit owner
approval for all four PR merges and resulting Pages publications, then re-fetches
heads/settings/checks and verifies parent/effective trees. It plans related child
retargeting only after its dependency lands, using REST because this environment's
older `gh pr edit` hits retired Projects Classic fields. No unrelated PR is retargeted.

#71 does not match Pages paths. #70/#72/#73 do and their eventual main merges run
the unchanged build/deploy workflow; their PR builds skip deployment. The current
publication allowlist does not automatically expose implementation reports or new
DDL. No Pages workflow was dispatched by this task.

Baseline differences remain explicit: unchanged main fails the advertised Core-only
`jobs` fixture case; #71 passes its entire 16-test schema file. Two more sampled
Core-only `cache_leases`/`jobs` fixture failures and the managed-browser docs staging
failure were also reproduced unchanged on main. They remain failed baseline/
environment checks, not skipped tests or new implementation regressions. The
integration report contains their exact commands/nodes/versions and corrections
are outside these production branches.

The [next-stage DAG](p2-p3-next-stage.md) permits P4 on P2 and P5/P6 development
against both stable sibling interfaces with their remaining P4 dependencies.
P7/P8 and the public initializer remain separate. Owner architectural blockers: **0**.
Existing `three-store-invariants`, `ci-final-tree-verification` and `lessons-to-skills`
were applied; the first two capture verified boundary/source-binding lessons.
No duplicate skill was created.
