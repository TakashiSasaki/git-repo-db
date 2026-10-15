# Independent P2 Git semantics/integrity review

Reviewer: independent read-only agent `/root/p2_review`. No implementation source or test edits, commits, PR approvals, catalogs or backups touched. External adversaries and oracle scripts live only under `/workspace/evidence/p2-review`.

## Exact reviewed source and execution

P2 implementation SHA `8b73322c10a79929f3023f9947d400aa0f666f6a`, tree `2d5d465296cb856413bb72ec659db7dba0dc90c2`; initial base P1 `67e8be65c3061b494c2c7373e2fd151398435f62`.

Inspected production parser, selective local Git source, production Core subclass, Core-owned P1 validators, DDL intrinsic guards, inherited immutable admissions/read/stop boundaries and actual adversarial tests. Read repository instructions, ADR index/policy, relevant accepted Core/identity/notes/integrity ADR scopes, P1 domain/ports/adapter and P2 handoff; frozen P1 review findings supplied additional regression boundaries.

Executed independently (Python 3.12.14; SQLite 3.53.1; Git 2.52.0):

- `python -m pytest tests/integration/p2 tests/integration/p1/test_core.py tests/integration/p1/test_notes.py -q --junitxml=/workspace/evidence/p2-review/production-p1.xml`: 239 selected/executed/passed; 0 failed/errors/skipped.
- `python -m pytest -c pyproject.toml /workspace/evidence/p2-review/test_adversarial.py -q --junitxml=/workspace/evidence/p2-review/independent-adversaries.xml`: 31 selected/executed/passed; 0 failed/errors/skipped.
- Actual Git differential oracle created disposable SHA-1/SHA-256 repositories: Git rejects null tree-entry OIDs and overflowing native timestamps; final production parser rejects them through `NATIVE_SYNTAX`. Extension before tagger is rejected; supported fourth-header tagger and following extensions remain allowed. Legacy tag objects without tagger are intentionally tested with `hash-object --literally` and should be described as such.

All commands used `/workspace/git-repo-db/.venv/bin/python`, working directory `/workspace/p2`, with direct pytest (no profiling wrapper). Machine-readable exact command/version/result binding and external test digest: `review-receipt.json`.

External tests cover both Git formats, reversible non-UTF8 messages/headers and raw binary tree names, folded signatures/encoding headers, malformed/truncated native grammar with matching exact native OID/digest, null refs, huge timestamps, malformed proof roots, tagger placement, canonical known-empty parents excluding differently labeled reports, original report preservation, exact replay, metadata-only Core without Context, ordinary blob refusal, generic SQL payload/proof-export denial, historical metadata before corruption detection, actual selected corrupted bytes and persistent catalog stop afterward. Repository tests additionally execute real native Git creation, missing children, immutable mutation refusal, semantic tree-name/mode conflicts, rollback, physical copies, notes roles, budgets and derivative loss.

## Findings and resolution

**P2-R1 / High / shared P1 defect:** supported `AdmissionTransaction.execute` could insert an intrinsic evidence link referencing an earlier original reported scalar/group. Matching native values passed the SQL guard, and projection changed the original alternative from `checked=False` to `checked=True`, preserving its original `qualification=reported`. This violates ADR 0005's prohibition on promoting earlier reports merely because matching bytes later arrive.

Independently executed against untouched P1 archive `67e8be65...`, tree `1d9b73e363e5b8a2bfe252fdcb87c7571d012e37`, not an uncommitted local combination. Exact script `promote_report.py`; receipt `promote-report-p1-exact.json` contains before/after provenance and checked state. The same path was independently source-confirmed by the cross-domain reviewer.

Coordinator isolated one shared correction at `2e8618428bea482ececef580045066cd49552455`, tree `9f50e3be6bdf92cfc33ccb490b04a369f74e1609`. Both physical intrinsic guards now refuse provenance lacking `receiver_intrinsic`, in addition to retaining exact local value/body checks. Identity contracts, table/column counts, source reports, receiver evidence and canonical values are preserved. Reviewed the exact correction and regenerated fingerprint scope. Independently ran its SHA1/SHA256 scalar/group supported PairCoordinator regressions: 4 selected/executed/passed, 0 failed/errors/skipped. Original `promote_report.py` now fails at the intended INSERT with `sqlite3.IntegrityError: field outside checked intrinsic scope`; refusal is successful revalidation, not a green exit from the original reproducer. P2 must incorporate this single correction dependency before final review readiness; no independent P2 DDL fix was made.

Draft review recommendations were incorporated before freeze: full production grammar validates notes proof structures, generic SQL cannot bypass checked byte reads, numeric conversion is bounded/typed, null native references are rejected, structural tagger placement is checked, actual parser iterations count toward work and local Git subprocess output is finite/timed. These are source-review recommendations plus final executable controls, not claims that a committed initial P2 failure was independently executed.

No other material P2 defect found in reviewed frozen source. This conclusion is scoped to local development verification and the tested grammar, not a proof of every malformed Git object or full release acceptance.

## Boundaries and limitations

- P2 consumes the exact P1 typed OID/provenance/claim/group/capture and coordination ports. No duplicate semantic identity or P3 ownership edit found. Schema 21 runtime initializer and accepted ADRs are unchanged.
- Notes role grammar remains P1's supported relevant captured root/tree mapping (two-character fanout and exact target leaf). This is a foundation for P4; neither full notes discovery/acquisition nor arbitrary notes grammar completeness was approved by this review.
- Tree count is derivable from the complete checked tree-entry relation; frozen four-argument intrinsic scalar SQL guard has no format argument, so production does not fabricate a checked stored `tree_count` scalar.
- CoreFailure scopes cover native syntax/integrity, retention purpose, notes role, replay, budgets, availability and persistent stop. Inherited physical FK/guard failures may retain SQLite IntegrityError taxonomy; do not claim all storage rejections are CoreFailure.
- No hosted CI, P4/P5 orchestration, P6 public readers/Search, P7 activation/recovery or P8 runtime switch independently executed by this reviewer.

## Verified reusable lessons

For existing `three-store-invariants`/`ci-final-tree-verification` skills:

1. Recompute correct native OID, size and digest for a deliberately malformed native object, so an adversary reaches syntax/role verification rather than failing only a hash precondition.
2. Test the supported raw coordinator callback boundary as well as typed production APIs. A native-value check alone does not preserve original report qualification; assert the original alternative remains `checked=False` after later matching receiver evidence and attempted link insertion.
3. Audit inherited generic SQL byte columns alongside typed readers. A correct checked byte method does not close an alternate unverified SELECT path.
4. Distinguish the original reproducer's expected nonzero refusal after correction from pytest regression success, and bind each to its exact commit/tree.

## Corrected P2 revalidation

**P2-R2 / Medium / ordinary-read completion after stop:** on committed P2 `bd3cb33ccaba14f2bcde28e15ebe039c2cf69dba`, tree `02337b30c5fc2c56b1be44d03189646cff33f784`, an independent detector publishes the persistent stop during the last scalar SELECT; the method nevertheless returned a successful ordinary projection while the stop already existed. Exact trace-controlled script `stop_during_read.py`, independently rerun from a detached archive of that exact revision; durable receipt `stop-before-exact.json`. This is a method-completion race, not an impossible demand to revoke results after return.

Corrected Core-owned source `999f8a55575b8d18018b91c404ed1e53d57e3c00`, tree `25096b68839ed718f00589419dc5cff647640ae3`, decorates all standalone public Core read results and production outer overrides with final availability and short `catalog_completion` fence. No completion fence is held during SQL/parsing, avoiding a detector deadlock; transaction-bound capabilities remain under their coordinator's outer fence. Reviewed exact changes and trace-last-read regressions. Original independent script now reports `CoreFailure(code=RECOVERY_STOP)` with stop present. Finding closed.

Also reviewed correction that distinguishes a genuinely metadata-only OID from dangling surviving intrinsic references after privileged deletion of an admitted physical-copy row. Historical relation remains queryable before detection; byte access detects missing admitted-copy evidence and stops. The native syntax failure scope now identifies the exact requested OID. Additional production replay cases cover actual P1 notes binary/empty/fanout/body/role/replay/rollback/integrity boundaries.

Independent re-execution on exact `999f8a5` through the **local worktree environment**:

`uv run --no-sync python -m pytest tests/integration/p2 tests/integration/p1/test_core.py tests/integration/p1/test_notes.py /workspace/evidence/p2-review/test_adversarial.py -q --junitxml=/workspace/evidence/p2-review/corrected-production-p1-external.xml`

293 selected/executed/passed (158 P2, 104 P1 Core/notes, 31 external); 0 failed/errors/skipped. Actual parser/adapter imports recorded as `/workspace/p2/src/...`; Python 3.12.14, SQLite 3.53.1. Full receipt updated in `review-receipt.json`. No other material P2 finding remains, conditional on integration of the separately reviewed shared provenance correction.

Shared audit follow-up `fe925cc61ad6cf09c826b36dec0854ad44bd8e27`, tree `010e09014f860cf012c13346b9dc19d419affb76`, was independently source-reviewed. Exact optional isolated-module allowlist and absolute/relative import checks preserve historical Schema 21 indexing while detecting accidental public-runtime imports. Local `uv run --no-sync python -m pytest tests/integration/p1/test_disposition.py ...` passed 16/16. Initial runs using the root worktree's interpreter produced 1 failed/15 passed because the test's offline autouse fixture overwrote PYTHONPATH and its subprocess imported the root editable package; this was an environment-binding mistake, corrected by using the current worktree's own editable venv. The failures are preserved in `shared-audit*.xml`, and corrected success in `shared-audit-local-venv.xml`. Do not describe the failed runs as schema success.

Additional reusable lesson: a pytest `pythonpath=src` or manually supplied PYTHONPATH may bind the parent correctly while child Python imports another checkout, especially when fixtures overwrite PYTHONPATH for a network guard. Use per-worktree editable environments and record actual imported `__file__` paths; do not accept parent-path evidence as proof of child-path binding.

## Final reviewed P2 tree with shared correction

**READY FOR P2 OWNER REVIEW** within the declared opt-in production boundaries.

Final independently reviewed and executed source: `cd30f7638a3d7e7b9d5f690a7b7b734693c20044`, tree `91375d1d1c8d28b9a87589d3f2dc76c604caf162`. It incorporates the common correction branch through merge `878f8fd40673bb994e3649ed7c5b5c175d41c1fd`; P2 and P3 remain siblings sharing that dependency, not dependent on one another.

**P2-R3 / Medium / quadratic folded-header parsing:** on the pre-correction parser, every continuation concatenated the whole preceding immutable byte string. Valid large signature headers therefore incurred quadratic work, amplified by each independent intrinsic SQL recheck. Independently timed a 480,117-byte/160,000-continuation commit at about 2.65 seconds for just one parse, far below the 64 MiB local input ceiling. A detached archive of exact merged pre-correction source `878f8fd...`, tree `696a2f7b7b52848c1d7322c0be3c07175e1a1746`, preserves the counterexample (`folded-header-before-exact.json`, parser path/hash recorded). Final `cd30f76` buffers pieces and joins each value once; a correctness regression verifies a large folded header without a brittle time threshold. Independent same-input timing was about 0.077 seconds and exact raw header bytes remained unchanged. Timing is illustrative local experimental evidence, not full performance acceptance. Finding closed.

Final independent command, cwd `/workspace/p2`:

`uv run --no-sync python -m pytest tests/integration/p2 tests/integration/p1/test_core.py tests/integration/p1/test_notes.py tests/integration/p1/test_intrinsic_provenance.py tests/integration/p1/test_disposition.py tests/packaging/test_p2_distribution.py /workspace/evidence/p2-review/test_adversarial.py -q --junitxml=/workspace/evidence/p2-review/final-p2-shared-external.xml`

| Category | Selected/executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| P2 production | 159 | 159 | 0 | 0 |
| P1 Core/notes | 104 | 104 | 0 | 0 |
| Shared provenance correction | 4 | 4 | 0 | 0 |
| P1 disposition/schema | 16 | 16 | 0 | 0 |
| P2 installed packaging variants | 4 | 4 | 0 | 0 |
| Independent external adversaries | 31 | 31 | 0 | 0 |
| Total | 318 | 318 | 0 | 0 |

The final actual adapter/parser imports resolve to `/workspace/p2/src/...` in the local editable worktree environment. Python 3.12.14, SQLite 3.53.1, Git 2.52.0. Commands, exact source identity, XML and machine-readable result categories are bound in `review-receipt.json`. All three material findings are closed on this exact reviewed tree; no remaining material P2 finding or demonstrated owner-level architectural contradiction. Hosted CI and complete release acceptance remain separate evidence.

Additional verified reusable lesson: finite input bytes do not prevent quadratic parser allocation. Folded native headers should buffer original continuation pieces and join once; test exact bytes/work accounting and use direct timing only as supporting evidence, not flaky CI thresholds.
