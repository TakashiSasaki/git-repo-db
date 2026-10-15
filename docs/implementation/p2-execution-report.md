# P2 production development verification

The final executable revision is
`8ce2fc4b41f2f7f5a1da9f2fcfbddb4c5cbabc8b`, tree
`f61a7d9053e73d2fdf4761577012c9f989b2ca92`. It preserves the reviewed P2 commits
and merges the same final common P1 correction dependency consumed by sibling P3:
`06a4ccd432476af15ee942e8cfcd9fbdf42357c7`. PR71 is deliberately not included.
Subsequent evidence-only commits do not claim another runtime execution.

[Machine-readable evidence](p2-execution-evidence.json) binds actual commands,
selected nodes, JUnit/journal hashes, production input hashes and versions. Direct
pytest uses the existing journal hook without duplicate profiling registration.
Selected IDs, JUnit cases and journal starts match **exactly once**. Actual
environment: Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19, Ruff 0.16.10.

| Final local category | Selected/executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Production P2 Core and retained P1 adversaries through `GitCore` | 194 | 194 | 0 | 0 |
| P1 contracts and common corrections | 266 | 266 | 0 | 0 |
| Architecture prototypes/audits | 128 | 128 | 0 | 0 |
| Installed wheel/sdist-wheel P1 schema | 2 | 2 | 0 | 0 |
| Installed wheel/sdist-wheel P2 native round-trip, both Git formats | 4 | 4 | 0 | 0 |
| **Total** | **594** | **594** | **0** | **0** |

The final batch passed in 41.57 seconds. All implementation/test inputs were
committed; only evidence prose and coordinator skill/ownership documentation were
uncommitted. This is a committed executable tree, not an uncommitted implementation
combination or a clean-tree release receipt. Global Ruff check/format (256 files),
P1 composed/physical fingerprints, 84-table/625-column disposition, historical
call-site audit and whitespace checks passed. The target remains 46 tables
(18 Core, 17 Context, 8 Operational, 3 Search); P2 adds no DDL or semantic key.

## Independent source review and execution

[Independent review](p2-independent-review.md) and its
[receipt](p2-independent-review/receipt.json) preserve the reviewer's own source
bindings, commands, counterexamples and results. The
[31 external adversaries](p2-independent-review/test_adversarial.py) are archived
byte-for-byte from the read-only review workspace. The author did not write those
tests or call a self-review independent. They can be rerun explicitly:

```sh
uv run --no-sync python -m pytest -c pyproject.toml docs/implementation/p2-independent-review/test_adversarial.py -q
```

Independent executions remain bound separately:

- `4e2f613`: **339/339 passed**, zero failed/skipped: 179 production P2, 104 P1
  Core/notes, 4 shared provenance, 17 disposition/schema, 4 installed production
  variants and 31 external adversaries.
- `b878b4e`: **34/34 passed**, zero failed/skipped: three immediate-stop/caller/
  generic-negative controls plus 31 external adversaries. Own trace confirms the
  stop exists before snapshot rollback.
- Final owned `fb0f87c`: **48/48 passed**, zero failed/skipped: 13 engine-boundary
  injections, a generic SQL negative, three meaningful atomicity controls and 31
  external adversaries. Own additional IOERR_FSYNC and CONSTRAINT_UNIQUE controls
  confirm stop-before-rollback versus ordinary rejection.

The later targeted review does not claim that the earlier 339-node selection was
rerun. The final common dependency and final P2/P3 combination have separate
coordinator-owned independent evidence. All owned material findings are closed.

| Finding | Severity/scope | Executed correction boundary |
| --- | --- | --- |
| Original reported evidence promoted by matching intrinsic link | High, shared P1 | One common physical guard correction; both formats and scalar/group callback refusals |
| Ordinary result completed after a published stop | Medium, P2 | All public Core reads have final completion fencing; original reproduction now raises `RECOVERY_STOP` |
| Quadratic folded-header allocation | Medium, P2 | Linear buffering, exact output equality and large-header regression; independent 480KB case about 2.65s to 0.077s, no brittle timing assertion |
| Wrong physical store accepted by transaction capability | High, P2 | Context shared-Coverage bypass refused with `STORE_ROLE`; correct transaction and capability expiry retained |
| Invalid stored UTF8/JSON/semantic metadata escaped stop | High, P2 | Fixed typed row decoders validate claim/group/provenance; generic SQL and caller errors remain noncorruption |
| Hash-correct malformed native representation admitted via callback/output | High, P2 | Native SQL grammar guard, atomic callback refusal and actual selected metadata syntax revalidation |
| Typed decode stop delayed until snapshot cleanup | Medium, P2 | Trace observes persistent stop before `ROLLBACK`, with cleanup allowed |
| Extended engine failures/standalone write failures escaped stop | High, P2 | Low-byte CORRUPT/NOTADB/IOERR handling at open/read/BEGIN/body/COMMIT before rollback/gate unwind |

Engine-boundary tests inject trusted SQLite failures around real disposable
connections and verify actual rollback/committed state. They do not claim physical
media faults or power-loss recovery were induced. Incoming malformed data,
constraints, budget refusal and caller encoding errors do not falsely stop service.

## Previous failures and limits

An earlier exact `8b73322` batch ran 519 nodes: 518 passed and one failed because
the historical runtime audit treated new opt-in P2/P3 modules as Schema21 runtime
imports. The coordinator corrected the common explicit exclusions while
strengthening actual public-runtime import detection. That guard passes in the
final batch. The earlier successful 553-node batch remains bound to `cd30f76`; it
is historical evidence, superseded by the final 594-node batch for current P2.

The unchanged Schema21 Operational-`jobs` Core-only fixture failure is owned by
independent PR71 and revalidated by the coordinator. No test is skipped, xfailed,
deleted or silently repaired by cherry-picking PR71 into P2.

This is local development verification. This agent did not execute hosted release
acceptance. Full live intake, complete notes acquisition, public CLI/Search,
power-loss-safe recovery/activation and the final initializer/runtime switch remain
P4/P5/P6/P7/P8 work. No public initializer, accepted ADR, real catalog, backup,
`main`, Pages deployment or production migration was modified. No owner-level
architectural contradiction was found.

The [production brief](p2-production-git-core.md) documents supported native grammar,
identity/replay/negative-knowledge semantics, integrity/exception scopes, retained
byte gates, notes foundation and ownership. P4 may consume the stable notes
foundation; P5/P6 should use the coordinator's combined compatibility evidence and
the same common dependency. There is no ordinary-file body endpoint.


The coordinator additionally reports the committed final combination `b1b5f9c`
(P2 code `8ce2fc4b`, P3 `5e3b373`) passed **691/691**, with independent final
cross-domain review **107/107**, zero failed/skipped and no findings. The common
compatibility report supplies its full SHAs, tree and command/artifact binding;
this is separate coordinator execution, not an additional P2-author test run.
