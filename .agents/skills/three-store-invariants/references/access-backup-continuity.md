# Access snapshots: keep history, remove authority, publish without overwrite

Applicability: the explicit Linux Access maintenance adapter, not Core/P7 same-DB
repair, approval attestation, raw archive extraction or general cloud backup.
Read the current ADR index and A1/A5 contracts before reuse.

- Protect a coherent source read transaction during SQLite Backup API copying.
  Test with a writer held open, wal_autocheckpoint=0, a committed WAL registration,
  and a later writer commit during copying. The artifact must include the former
  but not mix in the latter. Copying only the live main file is not a substitute.
- Sanitization belongs on a private validated copy. Removing local grants must
  not mask source corruption or modify source history/consent. Restore disables
  route controls before publication; replay or reenabling cannot resurrect a grant.
- Test renameat2 NOREPLACE against an EMPTY directory raced into place after the
  initial existence check. Ordinary replacing rename can silently erase it.
  After successful rename followed by parent-fsync failure, retain the completed
  target and report uncertain durability instead of cleaning up or claiming success.
- Copying S1/T1 rows to S2/T1 invents a registration history. A fork copies current
  settings, all disabled, and inserts a genuinely new explicit registration only.
  Preserve source history and verify rollback on target conflict/limit/COMMIT error.
- Corruption fixtures must actually reach the intended validation path. Changing
  all A->B->A timestamps to zero first collides on the direct PK; change ONE row to
  test invalid time, preserving every product guard outside that injected defect.
- Repository tests install a network guard via PYTHONPATH. Child-process source
  tests should retain that guard and append the exact checkout's src path, or use
  an explicitly installed build. Do not remove the network guard to fix imports,
  and never call a source-overlay smoke an installed-distribution result.

Reproduce with real SQLite >=3.51.3:

```sh
python -m pytest -q tests/unit/test_access_backup_values.py tests/integration/access/test_backup.py
```

The implementation report and exact-HEAD PR receipts distinguish main-agent tests,
removed-defense counterexamples, hosted packaging and independent review. A killed
process test is not a hardware power-cut test. SHA-256 is not sender authentication.
