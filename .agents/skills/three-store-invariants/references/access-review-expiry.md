# Access review lifetime: check after validation, not only before it

Applicability: local review/activation sessions, not persisted registration-time
ordering, Core identity or an imported authority token. Read the A1 contract and
A2a workflow report before using this note.

An expiry check BEFORE database/executor validation is insufficient: validation
can finish after the deadline. Two executed counterexamples advanced a controlled
monotonic clock during the final DB lookup; the old implementation recorded consent
or invoked work instead of rejecting expiration. Check the lifetime again after
validation, immediately before starting the bounded approval/dispatch operation.
Do not fabricate registration timestamps, add a domain revision, or weaken TTL
just to avoid the test. Already admitted work has a separate cancellation boundary.

```sh
python -m pytest -q tests/integration/access/test_workflow.py::test_expiry_during_final_database_validation
```

Also cover token replay/cross-session use, grant ABA revocation, new-default races,
actual directory identity changes, callback failure cleanup and a rejecting catalog
stop guard. A real PTY tests terminal interaction but does not prove a human exists;
automated CI is not an independent agent review. Never deserialize session handles
or activate a local executor from a stored/imported approval boolean.
