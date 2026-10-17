# Access-approved native Git: separate catalog pairing from target identity

Use when connecting a saved Access route to native metadata/Notes acquisition or
extending acquisition beyond a catalog's seed repository. Read current accepted
Scope and request-budget contracts first; this procedure grants no execution rights.

- Trace every repository identity comparison, including NotesProgress and paired
  preparation. Do not simply delete the top-level seed comparison: preserve physical
  Core/Operational `(seed,instance)` pairing and validate the distinct target/source
  request scope. Test another genuine repository while keeping store identities
  unchanged, and reject a mismatched Operational file.
- Freeze the COMPLETE native request, not only OIDs/path/time. Claims, actual target,
  physical-copy coordinates and Notes settings can otherwise change under the same
  original request/capture. Test explicit in-memory progress as well as real durable
  ledgers; a ledger's scope check alone cannot protect every call path.
- Carry the descriptor and exact reviewed plan from activation into dispatch. Never
  re-resolve a new default or persist `/proc/self/fd/N` as source identity. Pin actual
  storage, restrict inherited Git config/selection/trace state, recheck before commands,
  and retain a stable fd-independent source token for continuation checks.
- Charge source inspection and bootstrap input against the actual request before
  consuming it. Failed input and repeated verification still cost work. Original
  request loss is unavailable continuation, not a reason to silently issue a new one.
- Test revocation/config replacement after the format probe and a stop after Core
  admission. Further commands/output must fail, while committed facts remain. Do
  not claim instantaneous cancellation of an already-running external process.
- For subprocess tests that clear PYTHONPATH, explicitly install the tested package
  or use a declared source-overlay virtualenv. Distinguish this from real wheel/sdist
  installation. Do not weaken the import isolation test or runtime SQLite minimum.

```sh
python -m pytest -q tests/unit/test_native_acquisition_values.py \
  tests/integration/access/test_git_acquisition.py
```

The A4a implementation report records exact scope, failed fixture diagnostics and
six removed-defense experiments. This is not a filesystem-owner sandbox, arbitrary
Git layout support, remote repository authenticity or an independent review.
