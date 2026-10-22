# Minimal product sdist: design and implementation validation plan

This is the implementation-facing companion to accepted
[ADR 0033](../adr/0033-minimal-product-sdist.md). Requirements below describe
future work, not implemented checks or newly executed distribution acceptance.
Only this document, the Mini-ADR and the ADR index change in this design PR.

## Inspected baseline and scope

Inspection on 2026-10-22 UTC confirmed:

| Reference | Commit | Tree |
| --- | --- | --- |
| `main` | `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` | `318ad07874ab436206e6a61f231b308a421cfc54` |
| PR #133, actual parent | `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `6bfa580baafa9f6a117b7a0b610c4e65cd031b86` |

Main and #133 match the supplied starting SHAs. #133 remains a Draft PR on #132
(`a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37`), itself on #131
(`01b427e392243e06eb9be0e3a50bb09ecacd0d5f`). Open Draft #134 is a sibling I6
boundary-design PR on #133, not a dependency of this proposal. The initial local
branch was clean `work` at main; the new design branch starts at #133. Recheck
remote heads and allocations before implementation; never rebase or force-push
these existing branches as part of this work.

The non-shallow repository's reachable filename history includes allocated IDs
0001–0032, including retired 0003; 43 historical index blobs and current remote
index watermarks contain no higher allocation. All 19 open PR heads matched the
69 fetched remote branches. The parent index already lists accepted ADR 0032 and
a final watermark of 0032, but its opening watermark says 0031. The index change
reconciles both to 0033 and lists 0033 separately as proposed. Accepted record
bodies and their approval states stay unchanged.

No baseline sdist was built or measured in this design task. The risk follows
from the broad default selection and growing tracked inputs; this document makes
no numerical artifact-size or savings claim.

## Existing paths and planned implementation

All links in this table refer to inspected baseline files. Changes are for a
separately authorized implementation PR after the design decision is accepted.

| Path | Observed behavior and planned work |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | Hatchling `>=1.27,<2`; wheel packages select `src/repo_catalog`; no sdist target selection. Add target-specific `only-include` without changing wheel mapping or product dependencies. Locked Hatchling is 1.32.4; verify actual selection/automatic metadata with the prepared locked backend. |
| [tests/packaging](../../tests/packaging/) | Generic distribution fixture builds both artifacts offline and rebuilds the extracted sdist. P1 fixture also builds both; P2–P7 reuse it. Tests/drivers come from the checkout. Both fixtures must check sdist membership/size before extraction. Verify that the first wheel really comes directly from source: a frontend's default combined build can itself build its wheel via sdist; use explicit separate source-wheel and sdist builds where needed. Preserve existing CLI, schema, resource and installed-behavior checks. |
| [tests/support/distributions.py](../../tests/support/distributions.py) | `build_once` locks cross-worker builds and atomically publishes hashes for wheel, sdist-wheel and requirements; rejects changed/partial products. Preserve that contract; decide how to bind the sdist inventory/measurement receipt before publishing success, without trusting a stale cached artifact. |
| [verify_access_distribution.py](../../scripts/verify_access_distribution.py) | Builds direct wheel + sdist with Hatchling, rebuilds wheel from extraction, installs each in a separate venv outside checkout and preserves runtime/failure receipts. Validate sdist before extraction and compare complete wheel contents in addition to existing Access DDL/smoke checks. |
| [verify_i4_distribution.py](../../scripts/verify_i4_distribution.py), [verify_i5_distribution.py](../../scripts/verify_i5_distribution.py) | Freeze HEAD via `git archive`, build both artifacts, record bytes/hashes, and copy tests/network guard/probes from that separate Git source snapshot. Preserve this separation: drivers must not be read from the reduced sdist. Existing installed `.py`/`.sql`/`.json` hash checks do not cover all data; add complete wheel equivalence, including `.graphql`. |
| [scripts/ci_plan.py](../../scripts/ci_plan.py), [scripts/ci_dependencies.json](../../scripts/ci_dependencies.json) | `pyproject.toml`, `src/**`, `scripts/**`, common test support and workflows are shared inputs. Development selects static/smoke and reports local test obligations; explicit release selects all acceptance files, including packaging. Verify new checker/budget inputs cannot evade input hashing/classification; update rules only if their placement requires it. |
| [tests.yml](../../.github/workflows/tests.yml) | Existing conditional packaging lane prepares locked wheels, collects tests, executes isolated offline packaging and reconciles results. Integrate membership/size/equivalence into that lane; keep ordinary prose development checks lightweight and preserve the independent SQLite-policy job. |
| [access-registry.yml](../../.github/workflows/access-registry.yml) | `pyproject.toml` already triggers this separate focused workflow, which invokes I5 and Access distribution tools, retains failures/evidence and also builds docs from checkout. Its path list does not cover every packaging test or I4/I5 verifier; audit changed validator/helper triggers and add narrowly needed coverage in implementation. Do not broaden every PR to full release validation. |
| [pages.yml](../../.github/workflows/pages.yml) | Checks out Git, prepares dev/docs dependencies and runs the allowlisted docs builder. Keep that source path, publication scope and deployment conditions; no new sdist-based site route. A future pyproject change already matches its existing trigger. |
| [docs/testing.md](../testing.md), [docs/change-aware-ci.md](../change-aware-ci.md) | Already require both installed distributions, outside-checkout execution, offline preparation, actual SQLite and truthful development/release outcomes. After implementation, document the concrete membership/size receipt and execution commands without claiming this proposal is implemented. |

## Distribution boundary

Prefer this sdist-specific source inclusion contract; the implementation PR must
test actual Hatchling behavior rather than assume configuration alone guarantees
the final archive:

| Input | Proposed treatment |
| --- | --- |
| `src/repo_catalog/` | Entire product package, keeping source layout for rebuilding. At the inspected parent this includes 132 Python, 19 SQL, 2 JSON and 2 GraphQL files. Preserve resources under all subdirectories, not just `resources/`. Detect missing data against the frozen source inventory. |
| `pyproject.toml`, `README.md` | Explicitly include these root files. Current project metadata does not declare `readme`; including README does not authorize unrelated project-metadata changes. |
| Required license/notice metadata | Include actual required files and metadata if present. No tracked LICENSE/LICENCE/COPYING/NOTICE file was found at the parent. This task makes no new licensing choice or synthetic license file. Review any later addition and wheel license metadata. |
| Backend-generated metadata | Enumerate exact allowed names and provenance, initially expecting `PKG-INFO`; confirm against the locked backend. No general exemption for arbitrary generated files, build hooks, `artifacts` or `force-include` entries. |
| `docs/`, `tests/`, `scripts/`, `.github/`, `.agents/`, ZIPs/logs/receipts, caches and build outputs | Exclude from the product sdist while preserving tracked files in Git. No requirement to ship a standalone test, evidence or docs checkout. Reject unexpected non-product content even if it is accidentally placed under an allowed package directory. |
| `uv.lock`, wheelhouse, validation requirements | Keep as separate checkout/validation inputs. Sdist wheel rebuild uses its declared PEP 517 build requirements and explicitly prepared backend dependencies; it must not require the project's Git lock or any hidden checkout file. |

The exact source-file set is derived from the pinned product inputs and compared
with the archive; a broad directory prefix check alone is insufficient. Review
changes to that source set, so adding a ZIP under `src/repo_catalog` cannot silently
make it a product resource. Explicit backend metadata is an addition to that set,
not permission to omit required source files.

## Required implementation acceptance

1. **Membership and archive safety:** Strip exactly one validated distribution
   root, require the expected paths, and compare the complete duplicate-free
   member inventory with allowed source files plus exact generated metadata.
   Reject unexpected or missing members, absolute/traversal paths, multiple roots,
   escaping links and special files before extraction. Directory entries must be
   structurally valid. Specify any legitimate link handling explicitly; do not
   let a tar extraction filter substitute for the membership check.
2. **Size and recurrence:** Record sdist SHA-256, compressed byte length, summed
   regular-file logical sizes, member/file counts and largest contributors.
   Compare before/after builds from the same pinned source with the same backend
   and environment. Select and commit finite absolute compressed and unpacked
   limits plus an explicit growth-review rule, with measured headroom for normal
   product growth. Fail on an exceeded budget; do not auto-increase it or use
   only a percentage comparison to a moving baseline. Prove an added docs/evidence
   ZIP/log cannot change product members or inflate product bytes under controlled
   build metadata/timestamps, and that an
   accidental product-path payload is rejected or exceeds the checked budget.
3. **Independent rebuild:** Create the direct wheel from a frozen Git source
   snapshot and build a second wheel from the validated extracted sdist in a
   directory without `.git` and without access to original checkout inputs.
   Use prepared dependencies offline, preserving existing locked-wheel hashes
   and network guards. Hash the source snapshot, sdist, both wheels and receipts;
   record commit/tree, backend/frontend and actual runtime identities. A hidden
   fallback to source tests, docs, scripts, lockfiles or package data must fail.
4. **Wheel and installed equivalence:** Compare duplicate-free wheel member
   paths and uncompressed bytes for the entire product and `.dist-info`, including
   SQL/JSON/GraphQL, metadata, dependencies and entry points. ZIP timestamp/order/
   compression differences alone are not content differences; do not blanket-ignore
   `.dist-info` or `RECORD`. Validate each RECORD against actual members; any
   proposed normalization must be narrow, explained and independently checked.
   Install both wheels into fresh separate venvs, verify actual site-packages
   origins and installed product hashes, and run from outside both source trees.
   Compare installed product files separately from installer-created `.pyc`,
   scripts and installation bookkeeping.
5. **Real behavior and negative controls:** Preserve the existing packaging
   suite's console script / `python -m`, resources, schema initialization,
   fingerprints, generated JSON guards, DDL integrity, acquisition/query/Search,
   Exchange and backup/restore checks on both artifacts. Preserve installed
   Access/I2/I3/I4/I5 probes where applicable. Add meaningful negative cases for
   an unexpected member, missing SQL/JSON/GraphQL, divergent wheel content and
   exceeded size limits. Tests/drivers may be copied from the pinned Git snapshot
   into an isolated harness but may not import product code from that snapshot.
6. **CI and outcome integrity:** Locally run focused packaging and validator/CI
   selection checks for the implementation. Verify affected hosted development
   routes and report their actual scope. Preserve failure exits, exact collected/
   JUnit/journal node reconciliation, invocation identities and historical
   evidence. #133's inherited 79 non-successes and failing original Access smoke
   are not resolved by packaging; equal failing results do not pass acceptance.
   Complete release acceptance still requires explicit full independent local
   and hosted validation under ADR 0001. No release-validation dispatch is part
   of this design task.
7. **Documentation path:** Check the existing allowlisted checkout-based site
   build where affected, without expanding the publication allowlist or deploying.
   Verify Git documents/evidence are unchanged even when absent from the sdist.

## Preserved authority and remaining details

[ADR 0001](../adr/0001-validation-lifecycle-architecture.md) keeps its validation
lifecycle, complete independent release execution, hashes, reconciliation and
evidence retention. [ADR 0032](../adr/0032-environment-sqlite-validation.md) keeps
actual environment SQLite, one library per environment, explicit interpreter
binding and all WAL/STRICT/JSON/FTS/product safety guards; no setup exception is
requested. [ADR 0011](../adr/0011-adr-governance.md) keeps allocation and explicit
acceptance; 0033 is accepted and retires no record. ADR 0031 domain contracts and
stage/independent-review obligations also remain unchanged.

The owner accepted the convention on 2026-10-22 UTC (2026-10-23 JST) and
authorized dependent implementation PR B. Engineering details
for the implementation PR are the actual generated-member list, complete source
inventory policy, finite byte limits/headroom, shared-validator placement and
receipt/cache integration, and any narrowly required workflow path triggers.
These details must be measured and reviewed; they are not additional product
architecture blockers. No artifact size result, runtime acceptance, implementation,
merge, release or deployment is claimed by this documentation.
