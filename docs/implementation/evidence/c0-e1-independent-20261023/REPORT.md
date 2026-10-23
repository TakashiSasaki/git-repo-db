# Task B: independent C0-E1 acceptance

**Verdict: scoped PASS.** The correction in #139 satisfies Accepted ADR 0001
VAL-07's complete compressed ZIP limit in the independently executed cases below.
New findings: **Critical 0 / High 0 / Medium 0 / Low 0**. The pre-existing Low
C0-E1 from #136 is independently reproduced before the correction and accepted
as closed for this fixed source. No product-wide or release acceptance is claimed.

## Target, independence and authority

- Repository: <https://github.com/TakashiSasaki/git-repo-db>.
- Audit #136: `8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82`, tree
  `65e9311819ec354cbc3d6ede1cbc10ebd5c2ced9`.
- Reviewed #139 HEAD: `3e2609baa07a9e92c8f2dc4dd1608f311021a1cb`, tree
  `43f0c017d5f922f7e1caf7e4a1605ec4ae7ace1c`.
- This evidence branch starts directly at that #139 HEAD; its PR base is
  `fix/c0-e1-receipt-limit-20261023`.
- A new Codex review thread performed this work, independently of the #139
  implementation Author. The connected owner's GitHub account is the publication
  identity; a different human account is not claimed. No subagent was used.
- The owner authorized tests, evidence, commit, push and a new Draft review PR
  regardless of verdict. No merge, release, deployment or existing-PR edit occurred.

The repository AGENTS.md, ADR index, Accepted ADR 0001 VAL-07 and ADR 0032 were
read. Applicable local skills were `efficient-repository-investigation`,
`ci-final-tree-verification` and `lessons-to-skills`. Initial live GitHub metadata
showed #146 as the latest PR, #139 still at the fixed target, no comments or
independent acceptance PR for this base. `raw/github-initial.json` and
`raw/github-prepublication.json` retain the checks; the latter repeats the live
target, recent PRs and duplicate/ref search immediately before publication.
Other I6-A work is outside this review and was not incorporated or awaited.

## Independent reproduction

`verify_boundaries.py` obtains the historical emitter from its Git blob and the
fixed emitter from the separate pinned checkout. Each runs as a child Python CLI
against a freshly initialized disposable synthetic Git repository and artifact
directory, with real `git rev-parse` binding values. The helper was independently
written; it does not import or reuse the Author's tests or verification helper.
The existing tests are separately rerun below.

The final experiment varies the random seed and input prefix length until the
production emitter constructs the requested exact complete ZIP. It uses no
patched ZIP writer, no ZIP comment, no length mock and no production-limit change.
A read-only trace observes the actual `body` only after the ZIP handle is closed.
Construction probes exit 99 before the predicate and are recorded only as
calibration; **all boundary verdicts below come from subsequent full CLI runs**.
Each archive is checked for CRC, all-DEFLATED members, exact indexed roster,
member lengths/hashes, actual synthetic Git/run binding and selected input bytes.

| Measured complete ZIP bytes | Before exit | Fixed exit | Fixed stdout bytes | Result |
| ---: | ---: | ---: | ---: | --- |
| 2,097,151 | 0 | 0 | 3,285,724 | Allow |
| 2,097,152 | 0 | 0 | 3,285,724 | Allow |
| 2,097,153 | 0 | 1 | 0 | Refuse |
| 2,323,560 | 0 | 1 | 0 | Refuse |
| 18,795; expanded 6,120,583 | 0 | 0 | 29,625 | Allow compressed-under-limit input |

The old source incorrectly emits receipts for both oversize cases; the fixed
source emits exactly `CI receipt exceeds 2 MiB compressed; retrieve the uploaded
GitHub Actions artifact` to stderr, with a terminating newline and no partial
receipt on stdout. Successful outputs strictly decode from BEGIN/DATA/END;
BEGIN size/SHA-256, END digest, chunk limits, index and binding all match. The
complete fixed ZIPs are saved in `raw/boundaries/`. Full DATA stdout is measured
and hashed rather than duplicated into large text files; marker records and
counts are saved in `measurements.json` and can be reproduced with the helper.

All synthetic artifact file paths and bytes, including excluded directories and
suffixes, remain unchanged after each full observation. A separate **uninstrumented**
fixed CLI oversize control also exits 1, emits zero stdout, gives the fallback
diagnostic and leaves its input intact. The local receipt binding identifies the
disposable fixture; source hashes separately bind the historical/fixed scripts.
It is not misrepresented as a hosted execution of the fixture.

Code inspection confirms the production change is a named 2 MiB constant and a
post-close, pre-output comparison/diagnostic. Collection, binding/index generation,
hashing and the emitted format are unchanged. The unchanged Access workflow runs
the emitter before `actions/upload-artifact`, with **both steps `if: always()`**;
artifact name `access-registry-verification` and both evidence paths remain.
`raw/workflow-review.json` binds the workflow hash and exact step configuration.
This establishes configuration and actual local input preservation; no new hosted
Access overflow/upload job or live fallback-path download experiment was run.

## Related local execution

The worktree uses its own locked development environment and editable source.
Python **3.12.14** loads the environment's actual built-in SQLite **3.53.1**.
`raw/local-runtime.json` records executable/base executable, SQLite source ID,
compile options and loader identity. No SQLite acquisition, rebuild, substitution,
version spoofing or guard exception was used.

- The unchanged emitter, CI plan/profile/journal/Python-runtime/SQLite-policy unit
  files and CI execution integration file: **280 passed, 57 subtests passed**;
  zero failures/errors/skips, process exit 0. This includes #139's seven regression
  tests, distinct from the independently authored experiment above.
- Independent `reconcile.py`: collection, starts and JUnit have the same 280
  duplicate-free node IDs; every node has one setup/teardown and a successful call.
  All 897 phase reports pass, including the 57 extra call reports. JUnit's 337
  counter is not misreported as 337 independent ordinary test nodes. Session and
  process exits are both 0; frozen source hashes match before/after.
- Repository Ruff lint and format: pass; SQLite policy detector: pass. Reviewer
  helper lint/format and final report checks are also recorded with command exits.

Commands, selected node list, JUnit, journal and raw check logs are under `raw/`.
`input-hashes.json` binds all 458 tracked src/tests/scripts/workflow/config/lock inputs;
`checks.json`, `execution.json` and `reconciliation.json` bind their actual execution.
Timings are elapsed records, not performance-comparison claims.

Two failed reviewer helper attempts are retained: a length-only calibration
exhausted its candidates at limit+1 after completing the first two boundaries;
an optimized trace then failed to subscribe to target call events. Both exit 1
before the final experiment's completed result. Their helper snapshots, logs and
earlier completed ZIPs remain in `raw/`. Correcting only the reviewer helper gave
the final successful measurements. A dependency-inventory command also initially
hit the read-only default uv cache; the task cache fixed that invocation. These
are not suppressed product failures or acceptance passes.

## Actual Hosted development evidence

The existing #139 [run 39887549016](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39887549016)
was read again through live GitHub APIs. Both `offline` and `sqlite-policy` are
completed Success. The actual normal run-log ZIP was retrieved and its timestamped
receipt parsed independently; echoed shell marker source is excluded by the parser.

- Complete receipt **71,313 bytes**, SHA-256
  `ecd164beb7edfed98a97c342684590ae926b405630c21e88aaa2bca2945b52bb`;
  BEGIN/DATA/END, strict base64, all **21 indexed members** and binding verify.
- Actual hosted checkout `6d649500319f404da210a92151a88f37bbd60fc2` has ordered
  parents #136 HEAD / #139 HEAD and exactly the reviewed #139 tree above. Manifest
  run, attempt 1, feature/base/tested SHA and tree all agree.
- Manifest: `development_checks_passed`, `full_acceptance=false`, **0 product
  pytest IDs executed**, **212 required test files unexecuted**. Selected static,
  configuration, doctor/schema checks and separate policy unit steps are recorded
  in the live job metadata. This does not convert hosted runtime coverage to 280.
- The supported GitHub connector now returned artifact 12472429473 and its normal
  file reference was actually retrieved **HTTP 200**, **71,124 bytes**, SHA-256
  `d43c9ea6d19dd3744b6b44778ba015cde281e8a8e5ae766b3591039a4d080cb1`.
  The digest matches GitHub's current artifact metadata; ZIP CRC verifies and all
  **20 shared receipt/artifact files are byte-identical**. The artifact has 22
  members including two runtime records. The historical Author-side 403 remains
  historical; this review did not assume its outcome or bypass a restriction.

`verify_hosted.py`, live metadata/logs, retrieved ZIPs,
`artifact-download-result.json` and `author-hosted-verified.json` retain the evidence.
No signed download URL or credential is stored. This is the normal tests workflow
receipt, rather than an Access overflow receipt. Review-PR CI is checked separately
after publication against its actual feature HEAD and merge tree, and reported in
the PR description/final handoff without changing these frozen target results.

## Limits and handoff

No Critical/High/Medium/Low new defect was found within this C0-E1 scope. The known
**79 unsuccessful nodes (59 failures + 20 setup errors)** are not rerun, resolved,
reclassified or accepted by this review. Full product pytest, Access/I4/I5 runtime
lanes, wheels/sdist installations, live acquisition and release qualification were
not executed here. Hosted development Success is not product-wide acceptance.

Only this new evidence directory is added; all 3,901 predecessor tracked files
remain byte-identical. Existing source/tests/workflows,
Accepted ADRs, Author evidence and audit PRs are unchanged. `LESSONS.md` recommends
a reusable skill update while preserving the frozen reviewed skill files. The
artifact index binds all new payload files except itself; the publication Git tree
binds the index. The Draft PR and final handoff carry verified publication HEAD/tree.
There is no remaining blocker to this scoped review publication.
