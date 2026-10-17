# Access consent storage: revoke before ABA, validate before joins

Applicability: opt-in Access settings and consent persistence, not Core mutations
or proof that a remote executor/human is authenticated. Read the current ADR index
and Access contract before using these procedures.

- An inner join can hide a dangling parent by returning no candidates. Test a
  previously open handle after a privileged fixture deletes a parent with FKs off.
  A supported read must diagnose the corrupted reference, not report ordinary
  unconfigured access or choose a different route. Validate the actual snapshot
  before selection; the current small-registry adapter uses full schema/domain/FK
  validation and explicitly accepts its scan cost.
- Comparing reviewed options with current options does not prevent A -> B -> A
  permission resurrection. Revoke affected current grants transactionally on
  material changes. Verify scope context, profile, binding, assignment and route
  controls, including toggling back. A no-op/label-only edit is a counterexample:
  do not invalidate consent merely because a statement ran.
- An SQLite authorizer must allow DELETE on the current-grant table when trusted
  update triggers invalidate consent. Keep other deletes denied; granting generic
  DML or making locator history mutable is not the fix. Exercise the original
  registry handle as well as the extended settings handle.
- A corruption-injection UPDATE may be rejected by a JSON-reading trigger before
  the read detector is exercised. Preserve this setup failure and choose a fixture
  that actually stores the intended corruption without weakening product guards.
  Distinguish setup errors from assertion detections in mutation experiments.

Reproduce on the supported SQLite binding:

```sh
python -m pytest -q tests/integration/access/test_connections.py
```

The A1b implementation report names the original failure, successful fixture,
positive tests and seven deliberately removed defenses. These are author-run
counterexamples, not independent review or remote execution qualification.
