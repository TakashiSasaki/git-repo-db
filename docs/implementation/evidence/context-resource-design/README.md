# Generalized Context Resource design review and verification

This record concerns documentation for proposed ADR 0031. The original review
below remains historical. The [evidence integration](#evidence-integration-revision)
now cites independently executed C′ results; this design revision runs no schema
experiment. See the [handoff](../../context-resource-design-handoff.md).

## Original preparation at 5244b98

Frozen PR #113 branch parent: `24f593861327328fa00dab0b83f956cec330a0ac`, tree
`7318fdb1cb5ef4959d685bf2a3a1d9d91385c89e`. Product main:
`efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree
`117d580b31098ecb8287281bd843894fdfad71fc`. Full remote-head fetch, open PR
listing, non-shallow reachable ADR history including deletions and index found no
allocation above 0030; the author allocated 0031. A second fetch/open-PR check
before submission still found only #113 and no separate public experiment PR.

Read-only code-contract and ADR-compatibility research by two agents identified
separate Context/Exchange canonical profiles, weaker SQL JSON validation, encoded
parent-ID string in document coordinates and the scoped six-role meaning of
Q-S6. These informed author edits, not independent package approval or executed
canonicalization/schema evidence.

## Original frozen independent review

The separate `independent_review` agent, which authored none of these documents,
reviewed six changed Markdown files against the actual frozen audit parent:

| Review stage | Commit | Tree |
| --- | --- | --- |
| Original authored package | `c5f840365cadf0603fab56b09e2ccf1862d2c60e` | `5bce0c78452bb523f4d08d569a7fdd860a91a749` |
| Independently rechecked corrections | `2770f0133e4c52975d82b5ab90c8356b44377446` | `1f4ac3d74db5979c2805ba796e4d9d14368ab5d2` |

**Outcome: approved for documentation-only Draft submission. No Blocking or Major
findings; two Minor findings corrected and independently rechecked:**

1. The added skill reference named Exchange's helper `_canonical_bytes()`.
   Fixed actual source names are `_canonical_content()` in prose and its search
   command. The author reran the exact source searches.
2. The ADR 0029 matrix's DS-R01–DS-R05 wording overbroadly grouped deferred work.
   Corrected it to five-store/ACC/carry-forward scope and expressly retained
   GC-03/04, DS-R01/03/04/06/07/08 and broader unselected DS-R05 deferred scopes.

The reviewer verified selected versus proposed status, both canonical profiles,
meaningful empty coordinates, genuine PR-document keys, the six Repository roles,
typed Q-S10 obligations, original report/clock and PackageKey/digest boundaries,
selection/dependencies, open U3 gate and documentation-only scope. Independent
checks covered 92 local links/anchors, strict UTF-8/nonempty files, fences,
metadata/index, exact-parent scope, unchanged accepted ADR/product/test/dependency/
workflow paths, whitespace, and `python scripts/ci_execute.py reports`.

The reviewer made no file changes and ran no product suite, canonicalization
vectors, U3 experiment, catalog operation or external write. Review approval is
not acceptance of the complete design package or proof of physical feasibility.

**After the reviewed correction commit:** the author replaced only this file's
pending review/check sections with the actual receipt. No design/ADR/index/skill
content changed afterward. That receipt edit is outside the independently
reviewed commits; it is identified here rather than called independently reviewed.
The author reran documentation and scope checks on the resulting committed tree.

## Original author checks

All checks below passed using Python 3.12.14; no dependency install or product
runtime execution was required:

- `python scripts/ci_execute.py reports`: repository prose/report validation;
  **402 readable nonempty files**, with report JSON syntax checks where applicable.
- A temporary stdlib checker read every changed Markdown file (including new
  files), checked strict UTF-8/no BOM/nonempty text, paired code fences,
  frontmatter/refinement targets, unique Proposed ADR index entry/watermark and
  **92 local links/anchors**. It also asserted unchanged production/test/workflow/
  dependency/root-guide paths and all pre-existing accepted ADR bodies against
  the fixed parent. This helper is a local check, not a newly installed CI linter.
- `git diff --cached --check` before authored commits and
  `git diff --check 24f593861327328fa00dab0b83f956cec330a0ac HEAD` after freeze.
- `git diff --name-status 24f593861327328fa00dab0b83f956cec330a0ac HEAD`:
  only six Markdown files, including one existing skill reference. Production
  Python, packaged DDL/fingerprints, dependencies, existing tests, workflows,
  accepted ADR bodies, root guide and default runtime are unchanged.
- Live main and parent-branch refs were reread; they still match the fixed SHAs
  above. Branch history descends directly from frozen #113, without modifying it.

The reusable verified lesson was added to the existing three-store-invariants
Context registration/Exchange reference: trace inner canonical values separately
from outer digest construction and compare parser/UDF boundaries. It records
source-inspection evidence and reproducible searches, not unresolved FK policy.
The reference and links were included in independent review. No new overlapping
skill or executable helper was added.

Canonical vectors remain specifications. The 163-case audit was not rerun or
relabelled. No runtime suite, minimum-SQLite check, package build, U3 experiment,
real-catalog/backup operation, credential inspection or live Provider operation
was performed. Hosted checks for the published head are reported separately in
the PR with exact commit/tree binding; no predecessor CI result is reused.

## Evidence integration revision

The current owner task authorizes updating #114 with #115's completed original
and semantic-gap experiments. Fresh inspection found unchanged main/#113/#114
baselines and #115 at `8ab57eb74068f5ba303b5985a335f0f76be4fdd2`.
The [integration map](cprime-integration.md) pins the executed/reviewed freezes,
report commits, mechanisms, enforcement layers, actual receipts and product gaps.
G1/G2 are closed; G3 remains an owner decision. Recommendation: **NOT YET READY**
for complete owner design acceptance. ADR 0031 stays proposed with date null.

This revision preserves #113 → #114 and treats #115 as external evidence. It
does not import that branch, change either sibling, or execute product/schema/
release tests. The eight fixed owner decisions and accepted ADR bodies remain
intact. A separate reviewer will inspect the frozen revised documents and the
original evidence; actual review/check results are recorded after that review.
