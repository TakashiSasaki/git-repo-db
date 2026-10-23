# Independent archive reviewer evidence

Reviewed source HEAD `8cd89a3d25c811ee32d117ec32fe76a6022e6d94`, tree
`0f42e9d0e498e249bc2cc02f6b96df9ef87106a0`. The stdlib probe imports only
the reviewed validation script and uses disposable synthetic files. It performs
no product import, network use, database access, dependency install, or extraction.

Run from the repository root:

```sh
python docs/implementation/evidence/adr0033-independent-review-20261023/archive/probe_archive.py --output docs/implementation/evidence/adr0033-independent-review-20261023/archive/results.json
```

Actual final process exit: **1**, intentionally signaling seven unexpected
acceptances among 38 independent cases. This is a completed diagnostic run, not
a test crash. `results.json` contains all observations and Python identity;
`findings.json` contains three scoped candidate findings (two Medium, one Low).
All valid controls, exact 2 MiB/8 MiB/512 boundaries, and one-unit-overflow
rejections behaved as expected. Invalid paths, duplicate logical members, multiple
roots, symlink/hardlink/device/FIFO members, unexpected ZIP/log/executable paths,
required resource omissions, changed product bytes, and missing `.gitignore` or
`PKG-INFO` were rejected. A standalone CLI invalid-path control exited 1 and
saved a failed receipt; it performed no extraction. Four independently invoked
CLI counterexamples instead exited 0 with passed receipts, as retained in JSON.

The PAX finding concerns unknown extension data and bounded parsing. The existing
regular-file logical byte total is numerically correct; PAX headers are not
regular files. No actual backend artifact is alleged to contain the synthetic
hidden payloads or malformed metadata. Integrated wheel metadata equality is
an additional defense for the Low metadata finding.

A first harness invocation failed before importing the validator because the
script used `parents[6]` (resolved `/workspace` instead of checkout root). That
harness path was corrected to `parents[5]`; the final results are from the
correctly bound validator, whose file SHA-256 is recorded. An earlier 35-case
probe completed with exit 0 before the three gzip-integrity controls and explicit
nonzero finding exit were added. The final 38-case run supersedes that harness
version; it does not relabel an earlier product result.
