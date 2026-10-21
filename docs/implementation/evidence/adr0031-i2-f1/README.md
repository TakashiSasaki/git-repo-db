# C-F1 design correction and independent re-review handoff

Start with the [before/after design contract](I2-F1-ADDENDUM.md) and
[author verification](AUTHOR-VERIFICATION.md). The predecessor
[Task D report](../adr0031-i2-independent-review/REPORT.txt) and
[minimal SQL](../adr0031-i2-independent-review/F1-reproduction.sql) are unchanged.
This new directory supersedes only Task C's incomplete temporary Transfer fence.

Executable proposal inputs are [fence.sql](fence.sql),
[compose_f1.py](compose_f1.py) and the external normalized
[stage routing model](stage_contract.py). [probe_f1.py](probe_f1.py) exercises
the actual SQL separately from the model. [run_f1.py](run_f1.py) freezes inputs,
runs both real libraries and records their actual process exits.

No product file imports these helpers. The author evidence is ready for
independent Task D re-review, not evidence that such a review already occurred.

## Reproduce on the exact published tree

Obtain the new PR's exact HEAD from its description, check it out in a fresh
clone, and confirm its parent/base is PR #121
`03ff484eca32bf6ed76b4b9fd472c99052f7d8b6`. Do not run against a moving branch.
Use a dynamic Python interpreter; loading the intended library must be confirmed
by SQL, not a Python version constant. Both runtime source IDs are recorded in
the summaries and receipts.

From that checkout, with a new scratch directory:

```sh
f1_scratch=$(mktemp -d)
cp docs/implementation/evidence/adr0031-i2-f1/prepare_runtime.py "$f1_scratch/"
/usr/bin/python3.13 "$f1_scratch/prepare_runtime.py"
/usr/bin/python3.13 docs/implementation/evidence/adr0031-i2-f1/run_f1.py \
  "$f1_scratch/results" --runtime-root "$f1_scratch/runtime" \
  --python /usr/bin/python3.13
```

The output directory must not already exist. Both probes assert the actual
`SELECT sqlite_version()` result; receipts include `sqlite_source_id()`, all
compile options and pragmas. Expected final author-runner exit is **0** with
119/119 case groups in each lane. The exact old minimal SQL is expected to
succeed on the before composition and refuse on the corrected composition;
both observations are successful diagnostic cases. An unexpected SQL acceptance,
Python error, changed source input or failed child process must remain a failure.

For a single library, set `LD_LIBRARY_PATH` to its build directory and
`PYTHONPATH` to the frozen checkout's `src`, this directory and
`../adr0031-i2-preparation`; invoke
`probe_f1.py NEW_EMPTY_DIRECTORY 3.51.3` (or `3.53.1`). The unmodified Task D
minimal SQL is loaded from the reviewed repository path and executed verbatim
statement by statement; the receipt stores each statement and full rowsets.

## Independent acceptance targets

1. Inspect the new trigger and actual schema delta. Confirm Resources and the
   existing endpoint fence are unchanged; there must be one added trigger only.
2. Re-execute the Task D minimal counterexample independently on both actual
   runtimes. Require report INSERT refusal 1811 with identical pre/post rowsets,
   zero I7 Resource/Parent/endpoint prerequisites, and no published report.
3. Independently vary conflict verbs, malformed payloads, no-op replay and
   generic-to-reserved UPDATE/UPSERT-update. Inspect their errors and rollback,
   including diagnosed injected-state tests without treating injection as a
   supported write path.
4. Confirm a lawful common I8 Parent report survives without native I7 existence;
   retain ordinary alternatives/multi-member/opaque reports and child identity.
   Do not claim this supplies I3 typed-report or I4 Transfer support guarantees.
5. Inspect the stage constraints across every real future API, normalized import,
   duplicate shortcut, reader/export/query/Search route. Model successes are
   bounded design evidence, not evidence those product consumers were changed.
6. Bind the exact final commit/tree, all source/SQL/UDF hashes, process exits,
   SQLite source IDs/pragmas and complete rowsets. State any new gaps and issue
   the review's own verdict; do not inherit the author's all-pass count.

The [original base manifest](base-input-manifest.json) binds all 3,745 predecessor
files. New input/output hashes, archive integrity and source preservation are in
[publication-binding.json](publication-binding.json) and the new
[artifact index](artifact-index.json). Full SQL receipts,
including initial attempts, are in `c-f1-evidence.zip`; readable summaries are
[minimum-summary.json](minimum-summary.json) and [newer-summary.json](newer-summary.json).
The [new evidence ZIP](c-f1-evidence.zip) is 379,898 bytes, SHA-256
`f60d3b65569c67e09a2de8eb854b8cb0119fd9d48e2ea038a72d0f3e9da784e9`;
all 46 indexed files verify (47 members including the index). Official source
download URLs and every source/library hash are recorded; new runtime binaries
are not bundled. Rebuild them with the commands above for a separate review.

The original Task C/Task D evidence is frozen. This PR adds a new contract and
receipts without editing their commits, branches or artifacts. Complete I2
product implementation and independent review, later I3–I8 guarantees, installed
distributions, merge, release and deployment remain outside this PR.
