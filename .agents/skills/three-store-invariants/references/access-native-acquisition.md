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

## Independently verified configuration and metadata-input boundaries

Git ignores one UTF-8 BOM at byte zero of a configuration file. A raw anchored
`[include]`/`[includeIf]` regex missed that prefix and allowed indirect reads outside
pinned storage. Inspect the same BOM-free lexical prefix that Git recognizes,
without normalizing or replacing the original file/token. Test valid and malformed
external include files and conditional includes: all must be refused before the
first Git command, while an ordinary BOM-prefixed safe configuration still works.

For external `GitMetadataInput`, inspect every repository-owned nested value:
RepositoryClaims, observations, Notes captures/claims/groups and repository
Coverage (including claims/proofs). Resolve Capture Coverage against its actual
original owner; global OID/field facts do not imply repository membership. Keep
Core/Operational seed+instance pairing separate from the selected Repository UUID.
Freeze original source/time and complete semantic input in request progress, using
declared native OID/type/size/digest rather than raw body staging. Repeat delivery
still costs actual work. An explicit new request may add compatible facts under
the same original Capture pair; changing an old request must fail before admission.

For live Notes inside metadata input, give standalone and paired preparation the
exact `request_scope(target, actual_instance, attribution, notes_source.scope)`.
Persist that supplied source scope/format in semantic intent too: explicit caller
work/progress bypasses durable-ledger scope checks. An independent counterexample
returned A's cached discovery after changing the supplied source to B. Do not
require an attributed external Capture.source to equal outer intake attribution.
Before admission compare every supplied Notes Capture with an existing same-pair
binding (owner/source/ref/root), including units without Capture Coverage. Core's
later immutable refusal otherwise leaves earlier standalone rows behind. Charge
actual indexed lookups and retain paired rollback controls.

Use a typed Core reader for that comparison, not application-level generic SQL.
Independent corruption probes showed raw UTF-8 errors and invalid stored source
being mislabeled as incoming mismatch; missing Capture parents were even recreated
by later admission. Reconstruct canonical ref/UUID/OID/source under `_stored` and
the decoded-read/completion fence, check required repository/root parents in the
same snapshot, and stop before writes. Valid incoming conflict is not corruption.
Test exact-schema synthetic damage and unchanged suspect file bytes in both paths.

Use `python -m pytest -q tests/integration/access/test_review_corrections.py`.
The independent R0/R1/R2 probe also demonstrates that Exchange still needs an
explicit repository-set selection/acceptance contract; do not remove its mismatch
guard to make a nonseed test pass. See the
[review and remaining contract](../../../../docs/implementation/access-a6-independent-review.md).
