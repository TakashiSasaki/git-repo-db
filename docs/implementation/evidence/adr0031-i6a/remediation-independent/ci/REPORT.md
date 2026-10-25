# Independent hosted CI audit

Reviewed feature `08fbb956c2e470e245146b0dbae747ed0690ea40`, tree
`7072f952975a8537f74ced1bbc2a4a31d7aa3690`. API metadata, exact job steps and
decoded job logs were freshly retrieved on 2026-10-23. This is independent
inspection of hosted execution, not a new hosted runtime run.

| Run | Final state | Actual scope |
| --- | --- | --- |
| [39903868636](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39903868636) Development | completed / success | offline and sqlite-policy succeed; product pytest **0**, 223 required acceptance files unexecuted; `development_checks_passed`, `full_acceptance=false` |
| [39903868666](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39903868666) public-head Access | completed / failure | broad **2,849 PASS / 279 FAIL / 20 ERROR / 0 SKIP**; 3,148 selected/executed of 5,974 ordinary, 2,826 ordinary unexecuted |
| [39902230351](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39902230351) executable-source Access | completed / failure | same selected count, outcomes and unsuccessful node identities/phases/types/refusals/full frame projection |

Both Access runs actually execute source I4 217 and I5 29 (overlapping broad),
and independently installed direct-wheel and sdist-derived-wheel I4 217 plus
I5 29 per artifact. All six focused lanes pass. Equal counts were insufficient:
the auditor independently requires duplicate-free selected IDs, exact JUnit
identities, journal starts, exactly one setup/teardown and a call iff setup
succeeds, one terminal event, and agreement with the actual process exit.
The broad failed terminal event is correctly preserved as `status=failed`,
`exitstatus=1`; no failed run is changed into success.

The separate Access-focused JUnit contains **2,487 PASS / 279 FAIL / 20 ERROR**
across 2,786 nodes. Every focused node overlaps broad; all 299 unsuccessful
identities equal broad, so it is not added to unique execution coverage. Both
run job-step records preserve the same six failed steps: focused runtime tests,
broad regression, inherited-79 comparison, installed I2–I5 orchestrator, Access
distribution smoke, and acceptance-ledger reconciliation. The inherited
comparison truthfully reports 79 baseline nonpasses versus 299 current, zero
resolved and 220 additional; its nonzero result is not dismissed as a green
baseline match. The 220 require the separately documented I6-C/I7 disposition.

Each installed lane has collection and execution session-start/session-finish
import records. All four records have site-packages origins, all loaded product
modules under that origin, and all **156 Python/SQL/JSON file hashes** matching
the frozen product. The two original installed Access smokes fail at actual
installed `application/exchange.py:397` with `PERMISSION_DENIED`. Their deeper
assertions are unexecuted. The receipt does not prove full application Exchange
acceptance. The runtime is hosted Python 3.12.15 with actual built-in SQLite
3.53.1; no SQLite component is prepared by this review.

The public-head jobs tested merge
`f4ed9cb6b22fbd8305379fe534153a035d4ec45f`, whose API-retrieved parents are
the exact #143 base and public feature head, with the exact reviewed tree.
Source Access tested merge `8988a5c3f5bdbab4a54dc1ec35ed8365540c6fe9`, tree
`0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a`. All **478 executable/test/script/
workflow/configuration hashes** in each Access receipt match the independent
frozen checkout. Thus final public-head failure is measured directly, not
inferred from Development success or from the earlier source run.

The source/public comparison includes all 299 unsuccessful nodes and finds
299/299 equality in phase, exception type, refusal names and extracted complete
trace path/line/function projection. Message text and raw trace bytes are
preserved in both receipt ZIPs; temporary paths and fixture repr are not treated
as semantic regressions. This projection is separate from the task's deeper
I6-C/I7 semantic classification and the pre-remediation #143 comparison.
No additional public-head blocking failure is introduced relative to source
Access. Existing failed Provider/Exchange/Recovery application paths remain
failed and cannot be accepted from focused I4/I5 passes.

## Receipt integrity and evidence

`audit_ci.py` independently decodes exactly one log receipt, validates begin/end
SHA-256 and length, forbids duplicate ZIP members, verifies every indexed member
and rejects unindexed extras, then binds run/attempt/head/tree to fresh API
metadata. Full results are in `audit-results.json`.

The six new run/merge-commit API JSON snapshots are **redacted projections**,
not byte-identical raw API payloads: address-valued `email` fields and commit
author/committer `name` fields are replaced by explicit redaction markers.
Public GitHub login/account identifiers, SHAs, tree, parents, run/job identity,
statuses and all other fields remain unchanged. `privacy-projection.json`
lists the exact six files. The audit helper applies this projection to newly
retrieved commit snapshots on reproduction. Receipt ZIPs and frozen Author
evidence remain untouched; the provenance checks use the preserved SHA/tree/
parent/status fields.

The three tested-commit projections also omit `verification.signature` and
`verification.payload`: Git's raw commit payload embeds personal author/
committer strings, while neither omitted field is needed for the SHA, tree or
parent checks. No cryptographic signature-verification claim is made from these
projections. All recorded commit SHAs remain the authoritative API identifiers.

| Run | ZIP bytes | Payloads | ZIP SHA-256 |
| --- | ---: | ---: | --- |
| 39903868636 | 83,607 | 21 | `96f67fc23bf29ebd6de2ff535fd2c9e106bcb9925975b804bbeb061da260a932` |
| 39903868666 | 1,902,200 | 121 | `5a2a192c793afb57843228d7a0b441833b32b576c648291260e2d74b92f34c52` |
| 39902230351 | 1,907,143 | 121 | `2a7b364b120f88bc7ae7258ec7171d33fa02f408be30009a6b7e6e2dc9adab75` |

Source/public log receipts are distinct fresh hosted records. The older Author
`hosted-final` evidence contains the earlier source receipt; it is not used as
the public-head completed run here. No frozen Author artifact was altered.

CLI job-log redirects returned Forbidden on all four read requests. The
supported GitHub connector `fetch_workflow_job_logs` retrieved all four logs;
the denied redirect route was not retried. `retrieval.json` preserves the failed
actions with temporary URLs redacted. Logs are gzip-compressed; receipt ZIPs
remain byte-identical to their authenticated log bundle payloads. No credentials
or signed URLs are intentionally retained in these deliverables.

Three initial audit-parser failures are retained: a failed journal uses
`status=failed`, each installed record covers both collection and execution,
and the output audit log must be excluded from input-job-log globbing. They are
review tooling corrections, not new product runs or product defects.

Reproduce with the frozen checkout as cwd:

```sh
python docs/implementation/evidence/adr0031-i6a/remediation-independent/ci/audit_ci.py
```

This read-only audit requires the `gh` authenticated read capability to reread
the recorded merge commits. No workflow rerun/dispatch, PR modification, merge,
release or deployment was performed. No unresolved evidence retrieval blocker
remains for the three assigned runs.
