# Task B publication and evidence

This directory publishes the completed non-author review of exact I1b #117 and
validation #118. Original completion and source coordinates remain those in
[REPORT.md](REPORT.md); this later publication does not repeat execution.

- [Original report](REPORT.md), SHA-256
  `b90d9dcf3da2171b26aab54c30b003731f9d056f2556038cf5b3c915e6a73ed1`.
- [Original evidence archive](independent-review-evidence.tar.gz), 57 members,
  SHA-256 `1f179831e2c52e3443beb1dc72648c5a710ce8724ed3621b7db02998005a05b5`.
- [Original artifact index](artifact-index.json), [runtime provenance](provenance.json),
  [node reconciliation](reconciliation.json),
  [distribution outcomes](independent-distribution-summary.json) and
  [reviewed Git bindings](final-git-binding.json).
- [Independent identity/API/SQL probes](counterexamples.py),
  [Exchange probes](exchange_probes.py), [lane runner](run_review.py),
  [execution journal](review_journal.py) and [reconciliation helper](reconcile.py).
- [Publication binding](publication-binding.json) records each verbatim copy and
  verifies all 56 original indexed archive entries. The archive additionally
  contains its own original index.

The original archive contains the full retained outputs, JUnit, journals,
selected-node lists, command/exit receipts, hosted Access log and unexecuted-node
inventories. Large raw receipts stay in that unchanged archive. It excludes venvs,
catalog databases and cloned Git objects. The preserved [original README](README.txt)
explains the execution layout and runtime preparation. Workspace paths in original
receipts are historical observations, not paths installed by this publication.

For reproduction, obtain clean detached checkouts of the exact commits in the
report and prepare separate locked environments. The probe entry points accept
`CHECKOUT OUTPUT.json`; choose fresh disposable output paths. The minimum runtime
requires an actually dynamically bound interpreter and the correct SQLite source
ID. The lane runner retains its original workspace layout; restore that layout
in a disposable workspace or adapt a separate working copy. Extract the verified
#118 cohort manifest as described in the original README. Never rewrite the
frozen evidence to make a new execution appear historical.

No reviewed implementation/test/ADR/PR metadata was changed by the review.
The owner's later request now authorizes publishing this separate Draft report
PR. It does not modify #117/#118 or authorize merge, release or full acceptance.
