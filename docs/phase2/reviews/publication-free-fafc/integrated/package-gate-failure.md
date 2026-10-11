# Actual fafc installed-package gate failure

The complete local package profile is **failed**, not acceptance evidence: both `test_wheel_sdist_cli[wheel]` and `[sdist-wheel]` failed, exit 1, on frozen `fafc1b2d4d2e1986768143cc71a0e55cba943ba3`, Python 3.12.14 / SQLite 3.53.1, with no tracked changes.

The failing command targets the disposable **receiver**, at `tests/packaging/test_distribution.py:440`. The new `whole_inventory` check permits exit 2, but the unchanged CLI presenter returns **3** for an ordinary partial result. The installed CLI independently returned global `status=partial`, exit 3, only `inventory_incomplete` gaps, and four valid hits. The corresponding explicit repository query returned complete/exit 0 with the same four hits. Full catalog check returned exit 0. Both actual installed variants were independently checked; their module paths are under their own isolated installation, with the final DDL fingerprint.

This is a fixture exit-code port error. The correct narrow repair is `accepted_codes=(3,)`, preserving all newly added completeness/gap/hit assertions. The backup call later defaults to the original sender, which retains its complete Source roster; the restored unqualified assertion must not be changed on the basis of the receiver's incomplete inventory. An earlier reviewer message inferred the restore flow incorrectly; the actual call and failed command corrected that inference before any source change.

Reproduction: run `recheck_installed_package_scope.py` from the containing scope-4 artifact directory with the shared venv. The exact actual installed commands, module/runtime/DDL binding, exit codes, gap details and usable hit counts are preserved in `package-installed-scope-recheck.json`. Original complete package XML/profile/logs remain in `/workspace/git-repo-db/artifacts/publication-free/fafc1b2d4d2e-final/`.

No production query change or Source-wide completeness inference is requested. Overall acceptance remains blocked until the corrected exact-source package and ordinary/hosted gates complete successfully.
