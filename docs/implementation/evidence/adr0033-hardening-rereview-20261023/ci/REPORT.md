# Independent final CI audit — PR #142

Reviewed feature HEAD `59307c40ea65554736e131cedd00f04c9906551b`, effective Git tree `5ea93707d62b542c84632515392ac6a35c36cd65`. Review only: no product, existing evidence, workflow, branch, PR, merge or automation changes. Only this new `ci/` directory was written.

The final [tests run 39892052621](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39892052621) is **completed / success**. The final [Access run 39892052634](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39892052634) is **completed / failure**, not pending. Authoritative live run JSON and job/step inventories are retained here. Development success does **not** establish product or release acceptance.

Both jobs checked out GitHub test merge `e0c60765bd0d99b8276a8d0528dabfa7f4d6971a`. GitHub's commit endpoint independently verifies its parent includes the reviewed feature HEAD and its tree equals the feature tree. These separate identities must not be conflated. Both receipt bindings match run ID, attempt 1, checkout and tree; tests additionally binds the exact feature SHA. `independent-audit.json`, `test-merge-commit-live.json` and `feature-commit-live.json` retain the checks.

## Executed and unexecuted scope

| Final hosted scope | Actual result |
| --- | --- |
| Development offline job | Static lint/format, SQLite doctor/FTS/schema and report checks passed. No selected pytest files; 0 pytest nodes executed, all 213 acceptance files unexecuted. `full_acceptance=false`, `acceptance_status=development_checks_passed`, `evidence_status=local_evidence_unavailable`. |
| Independent sqlite-policy job | Policy detector and stdlib unittest suites ran successfully. Development `coverage.executed=0` describes the planned pytest lanes and does not erase these separate checks. |
| Final Development sdist gate | Skipped: the synchronize comparison is evidence-only `aaee34d31d2511cfec95d0bfa41a3a9733ac43e4` → final test merge. Unknown evidence JSON/ZIP paths select static/smoke but do not select `sdist_inputs`. Packaging and wheelhouse preparation also skipped. This is not a claim of a fresh sdist run. |
| Access focused source cohort | 2,775 nodes: 2,696 passed, 59 failed, 20 errors, no skips. |
| Access broad source cohort | 3,137 nodes: 3,058 passed, 59 failed, 20 errors, no skips; process exit 1. Selected IDs, JUnit IDs and journal starts match exactly as multisets; journal has one terminal failed/exit-1 event. |
| Overlap / ordinary gap | All 2,775 focused nodes are inside broad. Thus unique executed ordinary nodes = 3,137 of 5,888, leaving **2,751 ordinary nodes unexecuted**. `access-unexecuted-ordinary-nodeids.txt` is the exact gap. Collection-only offline inventory did not execute its remaining cohorts (`runs={}`). |
| Source I4 / I5 focused subsets | I4 217 passed and I5 29 passed; both overlap broad and do not add unique source coverage. |
| Installed direct wheel | I4 217 passed; I5 29 passed; I2 and I3 helpers exit 0. Access smoke exit 1 at `ProviderAcquisition.admit_batch` → `_preflight_units`, `I2_TRANSFER_UNSUPPORTED: Provider Transfer intake requires reviewed I3-I5 support`. |
| Installed sdist-derived wheel | Same independently installed I4 217 passed / I5 29 passed, I2/I3 exit 0, Access smoke exit 1 at the same retained Transfer guard. |
| Separate Access distribution verifier | Both wheel and sdist-wheel installed smoke checks fail at the retained Transfer guard; distribution result has both lane exit codes 1. |
| Pages | No Pages run is associated with final feature HEAD. PR #142 changed paths miss the existing Pages trigger allowlist. Access's allowlisted `build_docs_site.py --no-mermaid` step succeeded with placeholder diagrams; no deployment or full Pages render was executed. |

The source and installed scopes are distinct; installed results are not added to the source ordinary inventory. Live and benchmark coverage is not claimed. This audit did not launch pytest, a workflow, a release validation or a deployment.

## Inherited failure comparison

Freshly parsed emitted broad JUnit was compared with the preserved I4 `author-evidence.zip` member `author-3.51.3/regressions.xml`; that historical entry label is a source selection, not a newly required SQLite version. All **79** non-success node identities, phases (59 call failures / 20 setup errors), stage-refusal strings and parsed repository trace-path/function sequences match. There are no additional or resolved non-successes in that comparison.

The complete 79-node old/new messages, phases, refusal strings and frame arrays are retained in `independent-inherited-failure-comparison.json`; `failure-comparison-per-node.md` is its readable index. Exactly 75 messages match byte-for-byte. The four P5 installed packaging messages differ: historical Python 3.13 versus hosted 3.12 formatting, temporary/user/worker paths, source excerpt/caret rendering and nested `selective_exchange.py` line 662 → 664. All four still report `I2_IDENTIFICATION_WIRE_UNSUPPORTED: explicit identification wire requires I6`. These are **not** asserted to have identical raw trace signatures. Matching inherited failures does not make either failed run pass.

## Receipt and input verification

GitHub connector `github_fetch_workflow_job_logs` retrieved the complete three job logs. Actual timestamped output blocks were selected, excluding echoed shell source. Strict base64 decoding verified matching BEGIN/END SHA-256 and exact byte length, unique safe ZIP paths, exact index membership, and every indexed member's length and digest:

| Receipt | ZIP SHA-256 | Indexed files |
| --- | --- | --- |
| tests | `3f799c38ad843d05b7fee4a57609ba124ad400e36e7447728aa0d62e2673e202` | 21 |
| Access | `4665b1fd502f42e137e32dc6d38b502ff70a884a313b22da2564f9b36df73c8f` | 102 |

Recomputed from the frozen Git tree: `policy_hash=aa0824102fea5d177781ffa27615cbc56d02bc7a9f79bb389d85b4ff45a58ed2`, `tree_hash=0b42f0e737e2de0705814e88ce99b1bfd6539176ab10bf279c7ae83ce6fe5a64`, and `acceptance_input_hash=8413e49bbfd35224c6c864680809a8956a2eda4f1324b04c3247e792b32ebdaf` all match the emitted plan/manifest. All 459 source input hashes in each before/after and I5 binding map match local frozen bytes; the offline binding's three files also match. All 158 sdist source files' lengths/digests and the aggregate source inventory digest match.

Access's sdist contract passes: 677,902 compressed bytes, 5,921,698 unpacked bytes, 6,051,840 tar-stream bytes and 159 members/raw headers. Its source inventory digest is `7d93a7c4b2d3d6a7411f0fc98a42901a83b508a63d2e15e44c2f6f2674f21934`. Build binding reports identical direct/sdist-derived wheels (`22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`, 762,725 bytes); separate distribution records agree. Artifact binaries are not included in the bounded emitted receipt: this CI audit independently rehashed receipt/source bytes, but did **not** independently download and rehash the hosted wheel/sdist binaries. Preserve that limit when using their reported artifact hashes.

Runtime receipts record product Python 3.12.15 with its actual SQLite 3.53.1/source ID. Dependency, docs, final and both installed-distribution probes retain the same base interpreter, SQLite module hash and SQLite identity within this invocation. No SQLite installation, substitution, matrix or exact-version startup gate was introduced by this review.

## A-CI-01 follow-up

The fresh disposable Git-repository probe exits 0 and reproduces the existing **Low / nonblocking advisory**: README blob and tree hash change, `preparation.sdist_contract=selected`, selected pytest files stay empty, but `acceptance_input_hash` does not change. A second complete minimal source fixture calls the actual `source_inventory` helper before/after the README-only commit: its complete source rows and emitted-encoding `source_inventory_sha256` are recorded in `readme-sdist-inventory-result.json`, and the aggregate sdist source hash **does change**. The reason remains `README.md`'s prose classification in `ci_dependencies.json` and the runtime acceptance hash predicate in `ci_plan.py:461`.

This is a documented hash-scope distinction, not a demonstrated stale-acceptance bypass. `ci_execute.verify_local_receipt` additionally checks exact commit/tree (`ci_execute.py:285` onward), while the sdist receipt independently includes README in `source_files`. Preserve that distinction or add a separate complete sdist input digest without expanding ordinary hosted pytest selection. No new blocking CI finding was established.

## Reproduction, sanitation and limits

Run `python docs/implementation/evidence/adr0033-hardening-rereview-20261023/ci/audit_receipts.py` (exit 0) and `python docs/implementation/evidence/adr0033-hardening-rereview-20261023/ci/probe_readme_binding.py` (exit 0). The latter uses only a disposable temporary repository. `command-records.json` records executed read-only authoritative API/Git requests; `operations.json` records connector retrievals, audit/probe exits and reviewer-parser corrections. Earlier verifier failures were reviewer path/serialization/JUnit identity assumptions, not product test executions; their stderr is preserved.

`raw-log-index.json` maps each compressed complete log to job/run identity and raw/compressed hashes. `sanitization-check.json` records the supported credential-pattern scan and signed-query handling; GitHub's existing masked values remain masked. Receipt ZIPs retain full indexed JUnit/journal/log evidence. No API credentials, cookies or authenticated request headers were collected.

Skills used: `ci-final-tree-verification`, `docs-site-staging-and-pages`, and handoff assessment with `lessons-to-skills`. Existing guidance already covers bounded receipt recovery and Development-versus-release separation. Suggested read-only handoff lesson: when imported tests are replayed under another collection module, reconstruct JUnit node identity from `classname` plus `name`; its `file` attribute may identify the original function definition and collapse distinct replay nodes. The exact selected/JUnit/journal comparison verifies this here. No skill file was changed under the review-only scope.

No blocked, denied or pending action remains in this audit. Full runtime/release acceptance remains unestablished because actual inherited failures and unexecuted coverage remain.
