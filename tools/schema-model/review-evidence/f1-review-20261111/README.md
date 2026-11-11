# ADR 0040 F1 independent review and correction evidence

This directory retains the independent review of PRs #262 and #263, the original
counterexamples, the scoped F1-B correction, and the actual verification records.
It also preserves the three historical Actions artifacts before their finite
retention expires. It does not authorize integration or certify the whole product.

## Exact source identities

| Source | Commit | Tree |
| --- | --- | --- |
| Main checkpoint | `3a5457af1e42c158641a73fe5172cad2dbe0718c` | `dafa230332cad251edc1baab0f0ccc6df03647ab` |
| F1-A, unchanged parent | `f6a6a3ca2dd64e92a6fc4decd460a62e44e01a25` | `007749b955d156ee6a7a24a7798ed6f9dffc4e5f` |
| F1-B, initially independently reviewed | `ac732094676f1c3ebc4330c25c2177538b72585d` | `98a709e165fc732bd8a8b5fb3c86ec3fa324e8e2` |
| Corrected F1-B code | `a710c5880dd6404efc698b5962bad6266eae1a96` | `8b90a043296147353470769ba20b23bdb694e146` |

The correction's sole parent is `ac732094676f1c3ebc4330c25c2177538b72585d`.
The source reviews and fresh author execution bind the corrected code commit,
not the later evidence-only commit that adds this directory. That later commit
must retain an explicit unchanged-input comparison; it is not a fresh execution.
The retained main checkpoint is an observation, not a guarantee about future refs.

## Review findings and disposition

Independent subagents reviewed F1-A and F1-B in separate worktrees. They did not
author their reviewed implementation. These worktrees are an isolation convention,
not enforced filesystem sandboxes. The reports identify inspected files, actual
commands and unverified scope.

| Finding | Correction and remaining boundary |
| --- | --- |
| R263-01: positive hash-profile case identities could be swapped, or a required boundary witness removed, while aggregate coverage still passed | Bind each named qualified case to its required kind/state/size/digest/error tuple; reject missing or mislabeled positive witnesses at input admission. Keep legitimate domain tuples valid in the synthetic `values` profile. |
| R263-02: documentation conflated SQLite digest checks with full-string lexical SHACL validation | Record and test the SQL/API versus SHACL differential for embedded NUL suffixes; retain strict full-string SHACL and the prior newline correction. **The pre-existing product NUL-admission gap remains unresolved outside F1. No product fix is claimed.** |

The correction reviewer found no remaining material F1 finding at `a710c588...`.
F1-A remains unchanged. AGY was not used during maintenance; no independent-review
claim is based on the earlier unavailable AGY/OpenCode attempts or ordinary CI.

## Newly executed verification versus reused evidence

At the exact corrected source, the author's completed run records seven commands
with exit code zero, a fresh hash producer and CLI, **16 unittest methods**, scoped
Ruff checks/formatting, whitespace verification and unchanged-input comparison.
The source was clean at completion. Runtime: Python 3.12.15 / loaded SQLite 3.53.1;
the optional checker uses pySHACL 0.40.2 / RDFLib 7.6.0 from the committed lock.

Fresh hash-profile expected/selected targets:

| Shape | Expected / selected |
| --- | ---: |
| EntryShape | 15 / 15 |
| ScanShape | 9 / 9 |
| OutcomeShape | 7 / 7 |
| ReferenceShape | 1 / 1 |

The producer records **14 SQLite rejection controls** and **two SQL-admitted
differential controls**. These are not additional unittest methods. The independent
post-correction driver executes **five controls with three supported checker
invocations**: the ordinary positive remains a pass, both NUL-digest graph cases
remain failures, and the two missing/mislabeled positive-witness cases now return
`undetermined` at input admission before any checker invocation. The original
incorrect passes and all raw before/after records are preserved.

Only selected `data_conformance` is evaluated. `spec_satisfiability`,
`operation_invariants` and `implementation_conformance` remain `not_run`.
Internal engine evaluation counts remain null. The correction's successful
positive CLI completes one supported checker invocation.

The **25 instance and 12 outcome regression methods are historical reused
evidence**, not fresh runs at the correction. Product pytest was not rerun.
The initial F1-B product execution remains bound to `d18ecbf9...`, run 42937529485.
The following direct comparison was independently executed during bundle assembly
and exited zero with no output:

```sh
git diff --exit-code \
  d18ecbf9705e47bdeda04eec439131bf70b7b7f5 \
  a710c5880dd6404efc698b5962bad6266eae1a96 -- \
  packages src tests scripts pyproject.toml uv.lock \
  tools/schema-model/uv.lock tools/schema-model/worker.py
```

The archived historical and correction commands additionally bind each intervening
unchanged-input comparison. Across the historical F1-A four-node and initial F1-B
two-node product selections, there are five distinct test identities because one
node overlaps. Test methods, product nodes, SQL controls and shape targets are
different measurements.

## Preserved setup refusal

The first external correction driver refused its proposed temporary fixture root
because `/workspace/.git` was an ancestor. It stopped before fixture construction
or tests. The refusal is retained under `author/setup-refusal/` and is classified
as setup failure, not a product/SHACL failure. The completed retry used a fresh
private root under `/tmp/git-repo-db-f1b-correction-a710c588`, verified to have no
ancestor Git metadata. No guard was bypassed and the failed attempt was not erased.

## Archive, manifest and preservation

- Archive: `review-evidence.zip`
- Bytes: **468,472**
- SHA-256: `e59191eda112637c123cfde1ac56d4e0da8248cf8ed51ffd9e691bf558b76dea`
- Members: **99**, including raw records, reports and bundle metadata
- External index: `manifest.json`
- Manifest SHA-256: `1146af46c205896ccb68ef1c66f2c29f8ec9882d2146caee2512ca8a8d71cae2`

The external manifest indexes every ZIP member with its exact bytes, SHA-256,
original source path and archive destination. Keeping that manifest outside the
ZIP avoids a recursive self-hash. Every member was reread and checked after ZIP
creation; every selected original source was checked again to detect changes
during snapshotting. No original raw record was rewritten or sanitized.

| Archive area | Contents |
| --- | --- |
| `reports/` | Complete F1-A, initial F1-B, final F1-B and historical-evidence reviews |
| `historical/` | Original artifacts 13818407030, 13819945183 and 13818878151, plus independent reconciliation |
| `fixtures/` | Exact historical final hash fixture used by the independent reviewer |
| `reviewer/` | Probe scripts, actual product NUL results, original and corrected raw graph receipts/inputs/diagnostics, setup logs |
| `author/` | Exact corrected-source producer/CLI/test records, driver, preserved setup refusal and verified environment receipts |
| `bundle-metadata.json` | Source identities and bounded inclusion inspection |

The three historical ZIPs retain their original bytes and original SHA-256 values.
Their 259 indexed files and ten normalized/raw receipts were independently
reconciled. The broader bundle inclusion scan inspected 369 text records,
including historical ZIP members, totaling 3,349,054 bytes. No high-confidence
credential indicators, unexpected non-UTF-8 members, retained user catalogs or
authenticated traffic were identified in this explicit synthetic evidence
selection. This bounded inspection is not a proof of universal secret absence.
Virtual environments, caches and source workspaces are excluded.

Hashes establish consistency, not source authentication or trusted execution.
Do not execute archived scripts automatically. The archived absolute paths
describe the actual execution environment and are not instructions to reuse a
different checkout's environment.

## Acceptance and integration boundary

PR #262 must be separately accepted and authorized for integration first. PR #263
must retain its parent base until #262 is merged under a later owner instruction;
then recompute the effective child diff, ancestry, tree and relevant evidence
bindings. **Neither merge is authorized by this review.**

The F1 scope does not include a full product audit, Windows/release qualification,
F2/F3/M1/V1/T1, exhaustive race detection, real-file-byte authenticity, retained-data
validation, or a new mandatory semantic CI gate. The product NUL-admission
discrepancy remains explicit outside the optional model correction. No merge,
release, tag, deployment, force-push, security-setting change or retained-data
mutation was performed by the reviewers or authorized by these records.


## Publication transport and preserved original commits

The ordinary Git push failed with exit code 128:
`could not read Username for 'https://github.com'`.
The original feature ref remained at
`ac732094676f1c3ebc4330c25c2177538b72585d` at that observation. This was a transport
authentication failure, not a source-test failure or permission to force-push.

The authenticated GitHub connector created correction commit
`ad4774b43a0caad7526828341e69ef554cf16e6d`, with sole parent
`ac732094676f1c3ebc4330c25c2177538b72585d`. Its code tree is exactly
`8b90a043296147353470769ba20b23bdb694e146`, equal to the independently reviewed and
executed local correction `a710c5880dd6404efc698b5962bad6266eae1a96`.
The commit identities differ; the code trees do not. No execution is relabeled as
a fresh run of `ad4774b4...`, and no new implementation is implied.

The original local ancestry is preserved in `local-source-history.bundle`:

- Prerequisite: `ac732094676f1c3ebc4330c25c2177538b72585d`.
- Original correction: `a710c5880dd6404efc698b5962bad6266eae1a96`, tree
  `8b90a043296147353470769ba20b23bdb694e146`.
- Original evidence-only tip: `d0fa2c843922f528d184730972c1a0272b5632f7`, tree
  `1c9d0be4076189039d59c494cc3f2181beec55d7`, parent `a710c588...`.
- Bundled ref: `refs/heads/fix/adr0040-f1b-review-20261111`.
- Bundle bytes: **364,591**.
- Bundle SHA-256:
  `b28c905bb65c2bb75430875a6b25919960e8579c73fd31e8d23bd76693cc448f`.

The coordinator verified this Git bundle; its listed tip and copied byte hash
were independently checked during publication preparation. The earlier review
ZIP, its manifest, all raw records and the reports remain byte-for-byte unchanged.
This section supplements the original README without changing the historical
execution identities.

`publication-binding.json` records the failed transport, original local ancestry,
remote correction/tree mapping and planned evidence-only additions. The final
remote evidence commit/tree is not yet known in this preparation record. The
coordinator must create it with parent `ad4774b4...`, verify that changes are
limited to this evidence directory, then update
`refs/heads/feat/adr0040-f1-hash-states-20261111` with expected old SHA
`ac732094...` and `force=false`. That ref update is a normal descendant update,
not a PR merge. Source evidence is reused by exact tree identity and unchanged
input comparison; no additional product or SHACL execution is claimed.
