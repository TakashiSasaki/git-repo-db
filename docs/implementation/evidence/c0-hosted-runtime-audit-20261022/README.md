# Task C0: hosted-runtime audit submission

This PR publishes the C0 audit that was previously retained only in the shared
workspace. It is an **evidence-only submission** stacked on existing Draft
[PR #133](https://github.com/TakashiSasaki/git-repo-db/pull/133), not another
runtime implementation or a fresh product-test execution. The user explicitly
requested publication of the audit results after the distinction was clarified.
No source PR, I6 document, accepted ADR or historical evidence is changed.

## Audited result and remaining finding

**The hosted runtime incompatibility is removed by #133.** The original
setup-python CPython 3.12.15 loaded SQLite 3.45.1, and the unchanged product
guard correctly refused it before pytest collection. Missing XML and the ledger
failure were consequences of that refusal, not 79 executed functional failures.

#133 selects the ordinary upstream complete python-build-standalone CPython
3.12.15 Linux x86_64 distribution, release 20261021. Independent GitHub release
metadata confirms its 34,479,606-byte archive and SHA-256
`6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772`.
No SQLite component is separately downloaded, built, installed or substituted;
there is no fixed SQLite-release gate. The executing Python demonstrates
SQLite 3.53.1 and passes unchanged Access/P1 safety guards and STRICT, JSON,
FTS5/trigram and WAL probes. Product source, DDL/UDFs, assertions and compatibility
floors remain unchanged from #132. No ADR 0032 exception was executed.

**C0-E1 remains open, Low:** `scripts/emit_ci_evidence.py:64` permits a 4-MiB
compressed in-log receipt, while accepted ADR 0001 VAL-07 specifies 2 MiB.
A clearly synthetic counterexample emitted 2,323,560 compressed bytes without
refusal. The actual final Access receipt is 1,632,586 bytes, within 2 MiB, so this
does not invalidate the observed runtime/test evidence. Recommended correction:
restore the 2-MiB cap, test exact-limit/limit+1 behavior and preserve the uploaded
artifact fallback. This publication records the finding; it does not implement
the correction or relabel earlier independent reviews. See [findings.json](findings.json).

## Exact source and evidence bindings

| Coordinate | Commit / tree |
| --- | --- |
| Audited baseline #132 | `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37` / `1fa9c2624a3913d97439f16fcd6bc8641c56b17f` |
| Audited implementation #133; sole parent of this submission | `f16e5b1713bde9a2f18263a25397c4b450fd5773` / `6bfa580baafa9f6a117b7a0b610c4e65cd031b86` |
| Actual hosted execution merge | `b5f5026b07826b551cbd35ec39ac0ef3ca214a99`; parents exact #132 + #133; same effective tree as #133 |
| Earlier evidence publication audited | `14b7901c95b01b1ad2fc162f76e0210abc049a96` |
| I6 Author branch, untouched | `418ee68046fdfd03a0e84cc840e5d52fce176b81` / PR #134 |

The final publication HEAD/tree and GitHub test-merge binding are recorded in
this Draft PR's description, outside the self-referential file tree. Those
coordinates identify evidence publication, not another runtime execution.

Live refresh before publication also found an adjacent final audit on evidence
branch commit `4cd083b` and a separate proposed ADR 0033 PR #135. Neither is this
submission's parent or authority to change accepted policy. The original audit
archive and its original source/evidence pins are preserved byte for byte.
The adjacent audit remains [separately attributed](https://github.com/TakashiSasaki/git-repo-db/tree/4cd083b0f7295a2bbaa2597ef483af46e77f5463/docs/implementation/evidence/adr0032-host-runtime-20261022/final-audit).

## What was independently checked

- All **150** outer published payload entries and every indexed member of the
  three inner receipts match recorded sizes/SHA-256 values. Fresh GitHub Access
  and tests job-log receipts are byte-identical to the published copies.
- All **456** recorded execution input hashes match the frozen #133 Git blobs.
  The complete existing 12-file implementation diff and changed-file hashes are
  in the archive; no new implementation was made by C0.
- Eight hosted runtime receipts agree on resolved base executable, binary hash,
  built-in SQLite/source ID, compile options and mappings. Loader overrides are
  NULL, with no separate SQLite mapping. Both actual installed artifact venvs
  invoke their own site-packages product factories.
- Selected nodes, JUnit identities, journal starts, expected setup/call/teardown
  phases and finish/process status reconcile for the 29/217/3,137-node cohorts.
  Test parameters containing IPv6 or `ext::` remain literal during comparison.
- All **79** inherited broad non-successes match #132's frozen
  `run-3594f47/i5/regressions.xml` by node, phase, stage refusal and source frame
  sequence including line numbers: **0 added, 0 resolved**. Four raw assertion
  messages differ in temporary installation/worker paths; raw differences are
  retained rather than described as byte-identical messages.

## Actual executions and limits

| Execution | Observed result |
| --- | --- |
| [Original Access 39795283696](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39795283696) | Unsafe SQLite 3.45.1 refused before collection; subsequent artifact runtime refusals and missing-XML ledger failure |
| [Fixed Access 39799299209](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39799299209) | Job remains **failed**, preserving functional failures |
| Original Access pytest selection | 2,775 nodes: 2,696 passed, 59 call failures, 20 setup errors, zero skips; exit 1 |
| Broad regression cohort | 3,137 nodes: 3,058 passed, same 59 failures/20 errors, zero skips; exit 1 |
| Source bounded I4 / I5 | 217/217 and 29/29 passed; exit 0 |
| Direct and sdist-derived wheels, separately | Runtime/origin/file checks, I2/I3 probes, I4 217 and I5 29 pass; original Access smokes still fail at inherited Transfer refusal with exit 1 |
| Access acceptance ledger | Refuses actual failed/error nodes; no missing-XML success is fabricated |
| [Fixed tests 39799299296](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39799299296) | Policy/tool tests and ordinary development checks pass; full product acceptance is not claimed |
| Fresh local C0 checks | 31 policy tests + four runtime-binding tests pass; policy detector 0 violations; local product runtime probe/child check pass |

Fresh local C0 checks used the already selected managed Python 3.12.14 and its
actual SQLite 3.53.1. No Python/SQLite installation, new hosted workflow or new
product-suite/distribution execution was performed by this audit. The inherited
coverage register still discloses 2,316 ordinary nodes, one live and one benchmark
node unexecuted across the implementation task. No complete release acceptance,
merge, release, deployment, P8 or real Provider/catalog operation follows.

The initial `gh run view --log` retrievals returned successful empty files;
normal GitHub run-log ZIP API retrieval supplied the actual logs. Empty attempts
are retained. Early audit-helper trials also failed on whole-message comparison,
parameter parsing and a local variable shadow; corrected helper output and failed
trials are preserved and are not attributed to product failures.

## Submitted files and hashes

| File | Purpose |
| --- | --- |
| [audit.json](audit.json) | Machine audit, runtime facts, cohorts, source bindings, artifact hashes and limits |
| [findings.json](findings.json) | Open C0-E1 and concrete recommendation |
| [failure-comparison.json](failure-comparison.json) | Lossless JSON rendering of all 79 original TSV rows, including node/phase/refusal comparisons and raw-message equality flags |
| [handoff.txt](handoff.txt) | Original complete audit and separate non-Author review instructions |
| [audit-evidence.zip](audit-evidence.zip) | Original 32-member audit payload plus its internal index: raw logs/receipts, source diff/inventory, hashes, runtime data, helper and synthetic counterexample |
| [artifact-index.json](artifact-index.json) | Publication file size/SHA-256 manifest; excludes itself |

Original audit archive: **11,725,377 bytes**, SHA-256
`dac876bf5c56902971f6424d1c910dac26ebe29403a80dac4cd15bf6b9fbca12`.
The nested earlier payload is **5,285,592 bytes**, SHA-256
`e38171c16b5e58cfa222f281ea87406645ae85876cc05aa9f34f055749a76176`.
All wheel/sdist/source-archive hashes are in `audit.json` and the archived
`artifact-hashes.json`; byte hashes are retained build receipts, not a claim
that this audit rebuilt/downloaded the original artifact binaries.
The expanded comparison uses JSON to preserve multiline messages without TSV
CRLF/trailing-whitespace presentation problems. The original TSV remains unchanged
inside the original ZIP. The original audit points to body extraction at emitter
line 63; the precise cap predicate is line 64, used in the new findings register.

This evidence addition changes full repository/sdist inputs under the current
packaging rules. It does not retroactively make the publication sdist tested.
Audited execution source and later evidence publication remain separate, as
required by the inherited I4-E1 evidence-scope carryover. Product runtime blobs
and prior receipts remain unchanged.

## Recheck and independent-review handoff

From this evidence directory, a stdlib-only integrity check can read the archives
without extracting paths or executing their contents:

```python
import hashlib
import io
import json
from pathlib import Path
import zipfile

for name, entry in json.loads(Path("artifact-index.json").read_text()).items():
    raw = Path(name).read_bytes()
    assert len(raw) == entry["bytes"]
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]

with zipfile.ZipFile("audit-evidence.zip") as audit:
    index = json.loads(audit.read("bundle-index.json"))
    for name, entry in index.items():
        raw = audit.read(name)
        assert len(raw) == entry["bytes"]
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    payload = audit.read("published-payload.zip")
    manifest = json.loads(audit.read("published-artifact-index.json"))
    assert hashlib.sha256(payload).hexdigest() == manifest["payload"]["sha256"]
    with zipfile.ZipFile(io.BytesIO(payload)) as published:
        for name, entry in manifest["members"].items():
            raw = published.read(name)
            assert len(raw) == entry["bytes"]
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
```

A non-Author reviewer should inspect the frozen source/receipt bindings, independently
recompute node and phase comparisons, confirm both installed origins and smoke
failures, and review C0-E1 before claiming all reporting-policy obligations clear.
The archived `audit_evidence.py` records the actual original audit and its absolute
workspace locations; inspect it before rerunning, recreate those disposable
source/audit paths or adapt only the paths, and do not present the reproduction
as new hosted execution. The synthetic cap counterexample is explicitly labeled
and is not a real GitHub receipt. No reviewer PASS is invented by publication.

Applied procedures: managed cloud runtime guidance and repository
`ci-final-tree-verification`, `efficient-repository-investigation`, and
`lessons-to-skills`. No new runtime repair or reusable skill change is claimed.
