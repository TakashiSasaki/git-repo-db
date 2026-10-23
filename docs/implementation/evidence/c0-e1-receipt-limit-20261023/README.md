# C0-E1 compressed receipt limit correction

This is a focused development correction for the Low finding in [PR #136](https://github.com/TakashiSasaki/git-repo-db/pull/136). The parent audit and its historical evidence are unchanged.

## Source and scope

- Base branch: `review/c0-hosted-runtime-audit-20261022`.
- Frozen base HEAD: `8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82`.
- Frozen base tree: `65e9311819ec354cbc3d6ede1cbc10ebd5c2ced9`.
- Audit implementation parent (#133): `f16e5b1713bde9a2f18263a25397c4b450fd5773`.
- [Accepted ADR 0001 VAL-07](../../../adr/0001-validation-lifecycle-architecture.md) requires at most 2 MiB (2,097,152 bytes) for the compressed in-log bundle.
- The old emitter compared the complete ZIP against 4 MiB. The correction names the 2 MiB constant, applies it to the finalized ZIP bytes before hashing/base64/printing, and exits nonzero with GitHub Actions artifact retrieval guidance when oversized. No truncation, member omission, partial receipt, or success marker is used to accommodate an oversized archive.
- No product code, product safety assertion, DDL, UDF, accepted ADR, existing workflow, old evidence, or parent branch changes. No merge, release or deployment.

## Reproduction and observed results

The new regression tests run against both the historical emitter loaded from the frozen base and the corrected emitter. The size fixture executes the actual `main()` collection, index, ZIP construction and limit predicate. It writes seeded incompressible bytes, closes a real DEFLATED ZIP, and adjusts its legal ZIP comment (at most 65,535 bytes) to reach the requested exact total byte size. It checks the actual final length, ZIP CRC validity and compression method. No fake `len`, input-size proxy or production-limit override is used. ZIP metadata timestamps and digests may differ on replay; the tested total sizes are deterministic.

| Actual complete ZIP bytes | Before | After |
| --- | --- | --- |
| 2,097,151 | success | success |
| 2,097,152 | success | success |
| 2,097,153 | incorrectly succeeds | refused, exit 1, zero stdout |
| 2,323,560 (audit counterexample size) | incorrectly succeeds | refused, exit 1, zero stdout |
| 53,803 (expanded members exceed 2 MiB) | success | success |

`baseline.json` records 7 tests, 3 expected failures, exit 1. `fixed.json` records the same test/verifier hashes, 7 passes, exit 0. Both record actual bundle size/digest, stdout byte count/digest, markers, interpreter and measured SQLite identity. The counterexample's old stdout was 3,640,436 bytes; the corrected stdout is 0 bytes. Large DATA output is measured in memory and is not saved in these evidence logs.

Successful receipts are independently decoded with strict base64 and checked against BEGIN length, SHA-256, matching END, the exact archive-member/index roster and every member byte count/hash. Binding fields and the 120-character DATA chunk contract are checked. The fixture verifies artifact source files stay byte-identical on success and rejection. An additional unmocked CLI subprocess with an oversized synthetic input exits 1, emits only the artifact diagnostic to stderr and preserves its files.

The unchanged Access workflow emits receipts before `actions/upload-artifact`; both steps use `if: always()`. The upload retains `access-registry-verification` and both `artifacts/access-registry/` and `artifacts/runtime/`. The regression checks that ordering, condition, action, name and paths. This establishes preservation of the existing artifact fallback configuration and upload inputs after local overflow; it does not claim a newly executed hosted overflow/upload/download experiment. No CI workflow change was needed.

## Commands and evidence

Run from the repository root, choosing new output prefixes to preserve these records:

```sh
python docs/implementation/evidence/c0-e1-receipt-limit-20261023/verify.py --baseline-ref 8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82 --output-prefix /tmp/c0-e1-baseline
python docs/implementation/evidence/c0-e1-receipt-limit-20261023/verify.py --output-prefix /tmp/c0-e1-fixed
```

The historical replay intentionally exits 1; current replay exits 0. Exact commands, exits and durations for the broader checks are in `checks.json`, with raw `check-*.log` files:

- Focused pytest: emitter, CI plan/profile/journal/Python runtime/SQLite policy units and CI execution integration tests: **280 passed, 57 subtests passed, zero failures/errors/skips, exit 0**.
- `ruff check src tests scripts`: pass, exit 0.
- `ruff format --check src tests scripts`: 421 files formatted, exit 0.
- Verifier lint and format: pass, exit 0.
- SQLite validation policy detector: zero violations, exit 0.

`collection.log`, `regression.xml.gz`, `regression-journal.jsonl.gz` and `reconciliation.json` preserve the exact 280 selected/started/JUnit node identity multiset, successful session exit and passed phases, including the 57 extra subtest calls. The JUnit suite counter includes subtests (337); there are 280 testcase elements. An initial ad hoc normalizer omitted other unittest class names; the corrected generic module/class/name comparison passed without rerunning tests. Raw run results are unchanged.

The measured Python was CPython 3.12.14, with the environment's built-in SQLite 3.53.1; executable, platform and actual source ID are in the replay records. Locked dev dependencies used this same interpreter. No SQLite download/build/additional install/swap or matrix was used. The first uv sync attempt found a read-only default cache and exited 2; `UV_CACHE_DIR=/tmp/c0-e1-uv-cache` allowed the same-interpreter locked sync to complete. The first draft verifier used an incorrect root-parent index and exited before tests; that helper-only path was corrected before the canonical baseline/fixed runs. `before.json`/`before-unittest.log` retain an earlier pre-format exploratory regression run (also 3 expected failures); use the canonical baseline/fixed pair for matching final test hashes.

`input-hashes.json` binds the changed emitter/tests and unchanged workflow/lock/configuration. Executions were development runs with a documented working-tree overlay on the frozen base; neither a clean release receipt nor a full-suite pass is claimed. The final PR records the published feature HEAD/tree and verified remote identity. `artifact-index.json` binds this evidence snapshot and changed source/test files; its own digest is necessarily excluded.

## Findings and limits

C0-E1 is fixed and has executable closure evidence; final independent reviewer acceptance remains pending. Full product pytest, installed wheel/sdist checks, Access/I4/I5 runs and release qualification were outside this limit-only change and were not rerun. The historical 59 failures plus 20 setup errors (79 non-success nodes) remain historical findings; this change does not claim to resolve or reclassify any of them. Hosted development checks are reported separately in the PR and do not establish full release acceptance.

The repository `ci-final-tree-verification` and `lessons-to-skills` skills were applied. No skill was added or edited: this bounded constant correction is an ordinary regression fix, and its exact-size fixture is retained directly in the relevant tests and replay helper.
