# P2 production development verification

The exact corrected executable revision is
`cd30f7638a3d7e7b9d5f690a7b7b734693c20044`, tree
`91375d1d1c8d28b9a87589d3f2dc76c604caf162`. It preserves P1 and all four P2
implementation/correction commits, and merges the same separately reviewed common
P1 correction dependency consumed by sibling P3. No PR71 test repair is included.
Evidence-only follow-ups do not claim a new runtime execution.

[Machine-readable evidence](p2-execution-evidence.json) binds exact commands,
selected nodes, JUnit and journal artifact hashes, production inputs and actual
versions. Direct pytest uses the existing journal hook without the broken duplicate
profiling-plugin registration. Selected node IDs, JUnit cases and journal starts
match exactly once. Actual environment: Python 3.12.14, SQLite 3.53.1, Git 2.52.0,
uv 0.12.19, Ruff 0.16.10.

| Local category | Selected/executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Production P2 Core and retained P1 adversaries through `GitCore` | 159 | 159 | 0 | 0 |
| P1 contracts and shared provenance/runtime-isolation corrections | 260 | 260 | 0 | 0 |
| Architecture prototypes/audits | 128 | 128 | 0 | 0 |
| Installed wheel/sdist-wheel P1 schema | 2 | 2 | 0 | 0 |
| Installed wheel/sdist-wheel production P2 native round-trip, both Git formats | 4 | 4 | 0 | 0 |
| **Total** | **553** | **553** | **0** | **0** |

The full focused batch passed in 51.29 seconds. Global Ruff check/format, P1
composed/physical fingerprints, 84-table/625-column disposition, historical
call-site source audit and `git diff --check` passed. The four-store target remains
46 tables (18 Core, 17 Context, 8 Operational, 3 Search); the only DDL correction
comes from the common dependency, which requires genuine receiver qualification
on intrinsic evidence links. P2 added no physical table or identity representation.

An earlier exact `8b73322` batch executed 519 nodes: 518 passed and one failed.
That failure exposed the historical runtime audit's missing explicit exclusions
for opt-in P2/P3 modules. The coordinator corrected the shared audit while
strengthening public-runtime import detection; the final batch executes that guard
successfully. The separate unchanged Schema21 Operational-`jobs` fixture failure
is owned by PR71, which the coordinator revalidates independently. Neither failure
is skipped, xfailed, deleted or described as successful evidence.

## Independent source review and execution

[Independent review](p2-independent-review.md) and its
[receipt](p2-independent-review/receipt.json) preserve the reviewer's own report,
exact source revisions, commands, findings and actual results. The
[31 external adversaries](p2-independent-review/test_adversarial.py) are copied
byte-for-byte from the read-only review workspace for reproducibility; the
implementation author did not write those tests or treat a self-review as
independence. They can be rerun explicitly using:

```sh
uv run --no-sync python -m pytest -c pyproject.toml docs/implementation/p2-independent-review/test_adversarial.py -q
```

Final independent execution at `cd30f76`: **318 selected/executed/passed**, zero
failed/skipped: 159 production P2, 104 P1 Core/notes, 4 common intrinsic-provenance,
16 disposition/schema, 4 installed production variants and 31 external cases.

All material findings are closed:

| Finding | Severity | Demonstrated problem | Correction and independent revalidation |
| --- | --- | --- | --- |
| Original report promotion | High, shared P1 | Supported coordinator SQL linked original `reported` assertion to intrinsic evidence | One common reviewed physical guard correction; SHA1/SHA256 scalar/group refusals preserve original qualification |
| Ordinary-read completion after stop | Medium | A stop published during final scalar SELECT still allowed a successful projection | Final completion fence on all public Core reads and production outer byte/notes methods; original reproduction now raises `RECOVERY_STOP` |
| Folded-header quadratic allocation | Medium | Repeated continuation concatenation made a 480KB valid folded header take about 2.65 seconds, multiplied by SQL rechecks | Linear buffering/join, exact byte equality and large-header correctness regression; independent same input about 0.077 seconds, without brittle timing assertions |

Source-review recommendations also closed generic SQL payload export, full
native parsing for notes proof structures, null-reference and huge-timestamp
refusals, typed process failures and actual parser-work accounting before the
first committed review freeze. Actual retained-copy loss, partial admission
rollback, canonical/report conflict and no-file-archive boundaries have executable
regressions. No unresolved owner-level architectural contradiction was found.

## Scope and handoff

This is local development validation, not a complete release receipt. Hosted
coverage is reported by the coordinator from actual PR checks; this agent did not
execute hosted acceptance. Full live acquisition, public CLI switch, all notes
semantics, power-loss-safe recovery/activation and final four-store release remain
explicit P4/P5/P6/P7/P8 work. No public initializer, accepted ADR, real catalog,
source backup, `main`, Pages deployment or production migration was modified.

The [production implementation brief](p2-production-git-core.md) documents exact
native grammar, typed exception scopes, portable identities, retained byte gates,
notes foundation, field encodings and ownership. P4 may consume the stable notes
foundation; P5/P6 should use the coordinator's combined compatibility evidence and
the same reviewed dependency SHAs. There is no ordinary-file body endpoint.
