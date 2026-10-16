# Shared correction execution evidence

All catalogs/Git repositories used by these runs were disposable test fixtures.
No real catalog, backup, main ref, migration or runtime activation was changed.

- `3e82802/`: initial committed run; 827 selected, 826 passed, one cancellation
  test fixture signature failure; source-index audit also failed. The receipt's
  hardcoded before-status is corrected in the shared correction report; do not
  treat it as a clean-worktree proof. Kept as failure history, not acceptance.
- `2d4f5d4/`: clean corrected full shared selection, 828 passed, no skip/failure.
  Includes P1–P4, exactly 20 existing P2/P3 compatibility tests, snapshot helpers,
  and P1–P4 wheel/sdist-wheel variants. Every requested local check passed.
- `f17dd21/`: clean final executable focused selection, 77 passed, no skip/failure.
  Includes classified time/schema/validation-stop/snapshot and native signed-byte
  regressions. All requested local checks passed. Full final combined sibling
  validation is a separate root-owned receipt, not inferred here.
- `f23dfda/`: final test-purpose-only update, 79 passed, no skip/failure;
  same production source as f17dd21, plus both correctly isolated P1/P3
  missing-clock negative controls. All requested checks passed.
- `independent-review/`: independent exact-source findings and revalidation,
  reviewer-owned counterexample source and raw logs/selection/JUnit/journals;
  `shared-review.md` and `shared-review-reconciliation.json` explain per-run
  identities, overlap and the earlier rerun journal. Design review is separately
  bound to design commit 7d2e736.
- `docs-only-input-identity.json`: actual equality of 307 source/test/script and
  project/lock file hashes with final executed f23dfda. The docs/skill/evidence
  commit changes none of those declared 307 code/test/build files; the aggregate
  maps paths to exact SHA-256 values. This deliberately narrower scope does not
  assert equality of the live CI planner acceptance-input hash.

Each local revision includes collection IDs, exactly-once execution starts, three
phases per node, reconciled JUnit identities, raw logs, exact command arguments,
environment versions, source bindings and artifact hashes. Journals and JUnit are
losslessly gzip-compressed (`gzip -dc <file.gz>`); receipt hashes of raw originals
remain valid after decompression. `reconciliation.json` also hashes stored
compressed artifacts. Runner copies are evidence text, not new runtime scripts.

Counts overlap across revisions and independent selections. They must not be
summed to claim additional unique passing coverage. Unselected full-repository
suites, hosted Development CI and Release Acceptance are not claimed; the five
historical Schema 21 fixture cases are classified separately at final integration.

The conservative live `scripts.ci_plan` acceptance hash includes evidence files
under this directory, which the current policy does not classify as report-only.
It is `3ad6043771fd28e09bee80fa53f23dcedbe26c0d40dc5d015302777ae7d5f919`
at executed `f23dfda` and
`9cc20503acece5edfb752ba6e2ae0c37f29a49acabc1ac25b0635c482bfdfe07`
at documentation/evidence commit `f3cd1c9`. The 22 changed accepted Git inputs
are all added evidence files; the exact paths and blob identities are retained in
`independent-review/evidence-ci-inputhash-delta.json`. Later evidence/document
additions can change that live hash again. No CI policy/whitelist was weakened,
and no full-CI-hash equality is claimed from the scoped 307-file identity proof.
