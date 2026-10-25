# I6-B generalized wire v5 — Author validation

I6-B implements the accepted R02–R09 contract and its pure finite dependency
planner. This is Author-team evidence. Independent non-Author I6-B review is
unexecuted and belongs to the parent's next task. Ordinary Transfer remains
staged, I6-C/I7/I8 are unimplemented here, and no Release acceptance is claimed.

## Source and authority

- Actual sole base: #149, `review/adr0031-i6a-task-c-20261023`, HEAD
  `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`, tree
  `e7ca7e361b8b766f1976a12fc84d5cc50ac32232`. Initial live metadata matched
  the assignment. The base's independent scoped PASS and closed findings retain
  their historical meaning.
- Complete ordinary source before fixture migration:
  `2f874ce5c31efc1a266bc40e0472e64f82c82860`, tree
  `e0b50e80bae5aec92c1d9cf68ba8afc17ad6810d`.
- Final focused/diagnostic/build source:
  `a354348b800177608f6a83e2484cb6a784b7190a`, tree
  `169f0f95449c7bd728261b3d7799f795162c03fd`.
- New branch: `impl/adr0031-i6b-generalized-wire`. Publication HEAD/tree and final
  selected CI are externally bound in the PR body and publication receipt.
- AGENTS.md, the applicable repository skills, Accepted ADR0001/0031/0032 and
  related identity, provenance, time, store and selective-Exchange decisions,
  the three I6 contracts, original implementation handoff, #141 design review,
  #149 independent evidence and the actual codec/identity/Context sources were read.
- #139/#142/#144/#147 heads are absent from this ancestry. No sibling import,
  pre-existing PR mutation, rebase, force-push, merge, release, deployment or GitHub
  setting change is performed.

The [fresh submission checks](submission/CHECKS.json) reread live #149, its actual
commit tree, main, remote branch roster and all 150 PRs across all states. The
base HEAD/tree and main remain unchanged; no competing I6-B implementation exists.
The parallel fixed-stack audit is [Task B #150](https://github.com/TakashiSasaki/git-repo-db/pull/150),
not an implementation dependency and not imported here. A local old-gh
`--slurp` compatibility failure and downstream empty-output parse are preserved;
the supported paginated JSON stream is then decoded without changing results.

## Resulting behavior

The envelope is v5-only, with exact fields and strict JSON/UTF-8, duplicate-key,
nonfinite-value and primitive checks. Existing ResourceKey/ResourceIdentification
remain the sole canonical ID authority; all seven Resource columns and complete
Event references survive. Outer SHA-256 is recomputed using its distinct UTF-8
canonical profile. A digest is content consistency, not Provider authentication.
`decode_package` returns untrusted parsed envelopes/keys; the explicit pure
`decode_context_v5` additionally runs the existing typed semantic validators.
Neither supplies admission authority or substitutes for current receiver checks.

Complete original Parent keys and their actual observation payloads are
reconstructed only from their exact original rows. Event coordinates, surviving
endpoints and transport order cannot synthesize them. Generic member order,
empty/partial/complete/unknown/no terminal, Source positive pairs, set inventory
and original Coverage alternatives/proofs are preserved. The planner uses only
actual declared dependencies and whole units; namespace coordinates add no Parent
registration or traversal edge. Its node/edge/depth/unit/byte/work bounds are
finite, cumulative actual work is retained, and a stop preserves only completed
whole units. Diagnostics carry input-row offsets rather than withheld originals.

The planner now follows the complete Coverage FKs: claims/proofs require their
actual Scope row, and Collection-owned Coverage requires its exact Collection
header. Field and Source-inventory scopes retain their existing weaker ownership
requirements. Generic Collection scope values remain valid without proofs;
proofs needing named attributes reject non-object scopes with a typed outcome.

## Measured executions

| Invocation | Source | Actual result | Test/check exit |
| --- | --- | --- | --- |
| Complete ordinary, once | `2f874ce` / `e0b50e8` | 6,288 unique: 5,987 PASS / 281 FAIL / 20 ERROR; 57 passing subtests, zero skip | 1 |
| Pre-migration matched diagnostic | `2f874ce` / `e0b50e8` | 745: 444 PASS / 281 FAIL / 20 ERROR | 1 |
| Final collection only | `a354348` / `169f0f9` | 6,290 all / 6,288 ordinary IDs, Counter-exact; zero executed cases | 0 |
| Final source safety | `a354348` / `169f0f9` | 626 PASS, including original I4 217 / I5 29 and both migrated guard cases | 0 |
| Final source wire/planner | `a354348` / `169f0f9` | 212 PASS | 0 |
| Final source external probes | `a354348` / `169f0f9` | 34 PASS | 0 |
| Final matched diagnostic | `a354348` / `169f0f9` | 745: 446 PASS / 279 FAIL / 20 ERROR | 1 |
| Direct installed wheel, separate lanes | `a354348` / `169f0f9` | Safety 626, wire 212, external 34, reused authorization 27, reused Task C 132: all PASS; retained 19 originals / 4 invalid / 2 normal-fence controls PASS | 0 per lane/control |
| Sdist-derived installed wheel, separate lanes | `a354348` / `169f0f9` | Same measured lane rosters and outcomes, independent venv | 0 per lane/control |
| Original Access minimal harness v1 | `a354348` / `169f0f9` | Collection failure; smoke child UNEXECUTED | 4 |
| Original Access minimal v2, direct wheel | `a354348` / `169f0f9` | 1 FAIL at unconnected export; later smoke steps UNEXECUTED | 1 |
| Original Access minimal v2, derived wheel | `a354348` / `169f0f9` | 1 FAIL at unconnected export; later smoke steps UNEXECUTED | 1 |
| Final-source static checks | `a354348` / `169f0f9` | Ruff lint/format, SQLite policy, exact callsite audit, report checks, whitespace: six successful commands | 0 each |

Every completed lane preserves commands, process exits, source HEAD/tree,
actual input hashes, collection, JUnit, journal, typed main/subtest phases and
actual imports. Timing values describe those invocations only. Source, direct
installed, derived installed, extra probes and repeated diagnostics overlap and
are never added into a unique full-suite total. The initial 480 historical
runtime/test/script/workflow inputs were independently bound to the actual #149
Git blobs before using its 6,076-node baseline. New measured input inventories
include every new wire/planner module and test; no historical file count is a gate.

The complete ordinary source has 6,288 unique selected/executed nodes, zero
removed/duplicated nodes and 212 additions to the 6,076-node #149 reference.
Its 5,987 PASS / 281 FAIL / 20 ERROR, exit 1 and 57 passing subtest reports are
retained exactly. All 212 additions pass. The pre-migration diagnostic repeats
745 selected nodes (444 PASS / 281 FAIL / 20 ERROR, exit 1). The final diagnostic
repeats the same 745 nodes (446 PASS / 279 FAIL / 20 ERROR, exit 1); only the two
migrated guard nodes change FAIL to PASS. The final 299 unsuccessful nodes retain
the historical owners: I6-C 242, I7 composition 14, Transfer stage 43. No fixed
count is used as an acceptance gate; exact node/phase/trace comparisons establish
these observations. Final source safety 626, new wire/planner 212 and external
34 are separate successful invocations, not additions to the full aggregate.

The completed ordinary run belongs to the pre-migration snapshot `2f874ce` and
retains its actual 301 unsuccessful cases. Its only two newly unsuccessful nodes
are `test_unconnected_exchange_import_refuses_before_progress_and_cached_success`
(`[initial]` and `[cached-receipt]`): both stop at `ExchangePackage` construction
with `ExchangeError/MALFORMED_ROW` because their old Resource fixture has only
three columns. The one fixture assignment is migrated to
`ResourceIdentification.unscoped(KEY_ISSUE_7).to_wire()`. Whole-file AST equality
outside that assignment and equality of every assertion AST are mechanically
checked; the original test IDs, guards, cached-receipt/privacy checks and failure
propagation are retained. Final source/installed executions are separate receipts.

One already-unsuccessful I6-C node,
`tests/integration/i3/test_selective_exchange.py::test_empty_oid_and_context_payload_cannot_override_selection`,
also has an old three-column Resource fixture: the failure stays `failed/call`,
but changes from `AdmissionRefused/PERMISSION_DENIED` at receive to
`ExchangeError/MALFORMED_ROW` at package construction. Its downstream selection
assertions were unentered in the baseline and remain unentered. It is retained,
explained and not implemented ahead as I6-C. The other 298 inherited failure
signatures retain their exception types/codes/frame functions. Per-node traces,
assertion-line observations and the MALFORMED_ROW-aware parser controls are saved.

Matched 745-to-745 diagnostics retain the exact restoration mapping: the
`[initial]` guard reaches three original assertions and `[cached-receipt]` reaches
four. These two nodes are outside the old 743-node diagnostic, so its absent
observations are never treated as old assertion coverage. In the historical
299-node unsuccessful set, both raw and canonical assertion-entry sets remain
unchanged. In passing P6 packaging cases, module-scoped `p1_distributions` setup
runs on whichever xdist worker first needs it: compared with `2f874ce`,
`[sha1-sdist-wheel]` gains and `[sha256-wheel]` loses only the unchanged setup
helper return-code assertion at `tests/packaging/test_p1_distribution.py:26`.
Call-phase entries are identical. Relative to the old 743-node diagnostic, the
final setup-only additions are `[sha1-sdist-wheel]` and `[sha256-sdist-wheel]`.
Every node/phase/canonical statement mapping is retained; statement entry does
not claim subexpression or spawned-thread/process coverage.

The final source `a354348` and completed ordinary source `2f874ce` have the
same complete `src/repo_catalog` Git tree
`b0f47d5f139a70267c1cf168aa7943f0ce99729c`. Their 484 measured runtime/test/script/
workflow inputs differ in exactly the one migrated test file; all other inputs
and every product byte match. The entire ordinary suite on `a354348` is
**UNEXECUTED**. Final collection, safety, focused, diagnostic and installed
observations remain separate; the two restored guard cases are not subtracted
from the earlier 301 failures to invent a new complete-suite aggregate.

## Runtime and distributions

Selected local Python is 3.12.14 using its own SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Interpreter/base executable, SQLite module origin/options and product schema,
PRAGMA, UDF, both exact fences, FK and integrity checks are retained. No SQLite
was obtained, built, installed, substituted or matrix-tested. Dependency setup
uses the existing lock and a hash-verified external wheelhouse.

The direct wheel and sdist-derived wheel are each 790,488 bytes and
byte-identical, SHA-256 `6b3a865b90673b9626ad120ecf106064d2211657d2d78a68fb6568a52a8aba71`. The sdist is 128,336,141 bytes,
SHA-256 `28376ce29ae8023cca1701dc78e10c727e01b27e678527ddf6365222328190cd`. The measured product has 160 files / 6,022,477 bytes;
the frozen complete build source has 5,273 files and the actual sdist has 5,274
members. Full manifests bind every member and all new wire inputs.

The complete artifact audit passes: all 5,273 frozen Git source entries are
retained byte-for-byte in the 5,274 sdist entries; `PKG-INFO` is the only extra.
All direct/derived wheel members and archive RECORD entries match. Each actual
installed RECORD has 169 rows / 168 declared hashes, all hashes/sizes verified;
only RECORD itself is unhashed. Five installer-added entries and the rewritten
RECORD are explicitly distinguished from the immutable archive; generated product
bytecode is separately inventoried. All 160 actual product entries/bytes match
the frozen source/wheel. Installed paths are constrained to their actual venvs.

In each separate installed environment, safety 626, wire/planner 212, external
34, reused authorization 27 and reused Task C 132 all pass, as do the retained
19-original, four-invalid-carrier and two-normal-fence controls, CLI doctor and
isolated module help. Actual in-pytest site-packages imports, full schema/UDF and
both exact SQL fences, PRAGMAs, FK/integrity and before/after runtime/byte bindings
are checked. Staged original test/support bytes are separately remeasured after
execution rather than represented by copied earlier receipts.

The unchanged original Access SMOKE is executed separately in two minimal
wheel-only/test-helper environments. Both actual runs **FAIL**, one node each,
exit 1, exact JUnit/journal/typed reconciliation. The original child reaches
SMOKE line 187 `export_package` and raises
`AdmissionRefused/PERMISSION_DENIED` at `application/exchange.py:397` because
`ExchangeService` is unconnected; later smoke steps are unexecuted. These are
real retained staged-route failures, not xfail or passing receipts. The original
`httpx`-absent assertion passes unchanged. Actual site-packages/product/runtime
before-and-after checks and installed RECORD 169 rows / 168 hashes also pass in
both minimal environments; 166 measured inputs remain unchanged per invocation.

The preceding minimal harness v1 exits 4 during collection because copied
`tests/support/cli.py` requires `jsonschema`; the original child is **UNEXECUTED**
in that attempt. Its driver/command/logs and missing-dependency state remain.
A separately named v2/env adds only the locked jsonschema dependency closure,
retains HTTPX absence and all original smoke checks, and produces the two actual
failures above. Neither dependency preparation nor a collection error is counted
as product-test execution. These overlapping legacy-smoke failures are not added
to the earlier complete ordinary aggregate.

Both installed forms use separate external venvs and actual site-packages imports.
The complete source/sdist member sets, all product bytes, wheel members and RECORD
are checked dynamically. All new product inputs are verified rather than assuming
155 files/678 KB. The large sdist does not justify importing the unintegrated
#142/#144 packaging changes or #139/#147 C0 changes. Later evidence publication
changes the complete sdist input set; unchanged product/runtime input hashes do
not claim those later full archive bytes were built or tested.

## Preserved nonfinal attempts and corrections

- The first environment sync used a read-only default cache and failed before
  testing; an explicitly writable cache succeeded. The installed gh lacked a
  requested read-only JSON field; the supported REST/field read then succeeded.
- Early dirty-tree exploratory logs remain diagnostic. Some lack complete
  source/command bindings and are not frozen-source acceptance. A test-file
  bootstrap attempt exited4 before execution; its raw receipts remain.
- Actual aggregate-ID counterexamples exposed independently valid IDs bypassing
  enclosing node/depth accounting. Positional scanning then also preserves
  attributed dictionaries that merely resemble Resource coordinates. No opaque
  evidence is reinterpreted as typed identity by shape.
- Pinned `14571e2` cap controls reproduce four failures; the corrected controls
  pass. Object keys, final digest overhead and the final string work chunks are
  all included. An initial archive-control bootstrap omitted a nonexistent
  `.python-version` file and failed; its correction did not change product code.
- Two pre-fix full attempts were deliberately interrupted after further own-scope
  defects were identified: `14571e2` has 777 PASS/1 FAIL/778 JUnit cases, exit2;
  `6c12c05` has 856 PASS/1 FAIL/857 JUnit cases, exit2. Starts/phases differ from
  JUnit because work was interrupted. Their exact mismatch predicates remain
  false. They are not complete ordinary invocations or passing receipts; their
  single observed failure is inherited Transfer-stage refusal. No outcomes from
  these runs are combined with the final full invocation.
- On unchanged `6c12c05`, the external extra cohort gives 26 PASS/8 FAIL. It exposes
  absent full Coverage dependencies; two NULL-time expectations also originally
  required a later code despite the correct earlier strict-row refusal. Exact
  code assertions and contract-level unit-limit invariants were corrected with
  old/new helper hashes and reasons retained; product refusal was not weakened.
- A bound proof-scope control gives five AttributeError failures and five valid
  generic-scope passes. The explicit typed proof-scope guard corrects the five
  failures while retaining the five preservation cases.
- Two directories initially named for intended pre-fix checks actually used
  already-corrected inputs because edits crossed the intended observation window.
  Their recorded input hashes and actual passes are preserved and accurately
  relabeled; actual pre-fix results come from separately pinned snapshots.
- Postprocessing controls preserve an initially incomplete refusal-code regex
  and its MALFORMED_ROW-aware correction. A separate later frame comparison mixed
  ordinary/diagnostic traceback verbosity and produced 164 apparent frame-list
  differences. That parser observation is preserved as an invalid comparison,
  then replaced by matched diagnostic-to-diagnostic analysis; it is not evidence
  of 164 product changes or a product-test rerun.
- Final staged whitespace checking first detects literal context-line spaces
  inside the recorded `aggregate-before/working.diff` (exit 2). Its original
  bytes are retained using gzip transport, not stripped or rewritten. The old
  raw index and successful earlier verification remain under transport controls;
  the updated 1,057-entry index passes full length/hash/gzip verification and
  staged whitespace checking. This changes transport only, not test evidence or
  product/test inputs.
- A focused post-cap Ruff import-order failure was corrected before the final
  frozen inputs. No assertion, skip/xfail, permission grant or SQL safety fence
  was weakened to make a run green.

## Limits and handoff

The final-commit entire ordinary runtime suite is unexecuted after the one test
fixture migration; the completed ordinary snapshot and final narrower lanes
remain separately attributed above. The opt-in benchmark
`tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload` and live
`tests/live/test_smoke.py::test_selected_repository` are unexecuted, matching the
collected inventory. No live Provider traffic, general Transfer activation,
I6-C/I7/I8 integration, benchmark/timing comparison, independent non-Author
I6-B review or complete local+hosted Release acceptance is claimed.

Development CI Success means its selected static/configuration/smoke checks
passed; complete hosted pytest and Release acceptance remain unexecuted. The
pure Context planner does not establish Core object availability or receiver
permission, and ordinary unwired Provider/Exchange routes remain fail closed.
Both SQL Transfer fences, native-I7/full-report references, original I4 217 and
I5 29 case sets, service-bound current authority, replay revalidation, leases and
failure propagation remain mandatory. Protected source/schema/ADR/history and
prior-evidence byte comparisons are recorded separately from runtime assertions.

The repository skills [efficient-repository-investigation](../../../../.agents/skills/efficient-repository-investigation/SKILL.md),
[ci-final-tree-verification](../../../../.agents/skills/ci-final-tree-verification/SKILL.md) and
[lessons-to-skills](../../../../.agents/skills/lessons-to-skills/SKILL.md) were used.
The updated [Context registration/Exchange reference](../../../../.agents/skills/three-store-invariants/references/context-registration-exchange.md)
records verified aggregate/canonical-limit and full-Coverage-dependency lessons;
no new overlapping skill was created. No action is pending approval,
denied or of uncertain outcome at local Author completion. Publication and final
GitHub/CI state are verified separately. The parent requests the non-Author review
next; this Author task does not start it.
