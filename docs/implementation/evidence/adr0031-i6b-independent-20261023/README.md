# PR #151 independent review evidence

Start with [REPORT.md](REPORT.md), [findings.json](findings.json) and
[MATRIX.md](MATRIX.md). Verdict is **FAIL**, Medium M01/M02, and I6-C readiness
is blocked pending Author correction and independent re-review.

- [Wire](wire/REPORT.md): strict v5/identification/originals/Source/Coverage and
  raw received-digest counterexamples.
- [Planner](planner/REPORT.md): independent graph/boundary/whole-unit oracles and
  configured work-budget counterexamples.
- [Admission](admission/REPORT.md): retained authority/fences/rollback and new
  foreign-context/COMMIT controls.
- [Distribution](distribution/REPORT.md): fresh publication builds, every archive
  member/metadata/RECORD and isolated execution, including honest Access smoke.
- `broad/`: actual full final-source execution, collection and typed phase records,
  matched diagnostics, independent AST and historical first-boundary comparisons.
- `ci/`: actual Author Development/Access run snapshots, original downloaded log
  ZIPs, verified indexed receipts, and original failed retrieval/parser attempts.
- [LESSONS.md](LESSONS.md): verified procedures and a targeted existing-skill
  maintenance recommendation without changing the frozen reviewed skills.

Raw paths named by subreports and command receipts describe the original
execution files. Large text logs, JUnit XML and JSONL journals are stored with
lossless gzip transport. `TRANSPORT.json` binds each original path/length/SHA256
to its actual transport path/length/SHA256. Existing historical compressed bytes
copied for comparison remain separately identified; compression changes no
process result. Verify or reconstruct a fresh external evidence directory:

```sh
python docs/implementation/evidence/adr0031-i6b-independent-20261023/transport_evidence.py.txt \
  verify docs/implementation/evidence/adr0031-i6b-independent-20261023
python docs/implementation/evidence/adr0031-i6b-independent-20261023/transport_evidence.py.txt \
  materialize docs/implementation/evidence/adr0031-i6b-independent-20261023 \
  --output /workspace/i6b-independent-evidence-materialized
```

The materializer requires a new destination and checks every byte/hash before
writing. Reproduction test scripts are `.py.txt` to keep repository collection
unchanged; copy them unchanged to an external `.py` file as each subreport
specifies. Use the same measured Python and retain the offline fixture. None of
these scripts installs an alternative SQLite engine or enables normal Transfer.

All authoritative evidence files are in Git; temporary synthetic catalogs,
venvs/wheelhouse, full source archives and >100 MB sdist remain outside the
checkout and are represented by complete inventories/hashes. Final review Git
HEAD/tree and CI binding are recorded externally in its Draft PR body, avoiding
a circular file self-hash.
