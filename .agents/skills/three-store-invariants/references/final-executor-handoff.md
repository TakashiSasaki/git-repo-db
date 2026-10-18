# Validate after the executor's final preparation, before application work

Scope: AccessWorkflow single-use local execution. This is a verified procedure,
not permission to dispatch arbitrary adapters or a cross-process atomicity claim.

A6 counterexamples on the A5 integrated tree showed that checking a deadline,
grant and cancellation before `bound.invoke(callback)` was insufficient: the
bound executor itself performs another potentially blocking filesystem check.
A change during that check let an expired/revoked/default-changed/cancelled request
start the application callback. Eight parameterized cases reproduced the gap in
both descriptor-only and reviewed-plan APIs, with real SQLite and bound directories.

Put the final application-admission checks inside the callback supplied to the
bound executor, after its preparation. Recheck session ownership, original deadline,
local/domain cancellation guard and the exact selected current grant. Recheck time
after a potentially slow DB read. Consume the token and close descriptors on every
failure. Do not re-resolve an in-flight request to another Locator, reset budgets,
or pretend to cancel a callback that has already begun.

Reproduce using the supported SQLite binding:

```sh
python -m pytest -q tests/integration/access/test_handoff_boundary.py
```

Test changes during the final executor evidence call, not only during the earlier
UI or database check. Also retain the existing in-flight-revocation test: a callback
which was admitted before a later revoke has different semantics. This correction
narrows one concrete handoff gap; it is not a global lock across Access, filesystem,
Core and another process, nor an independent security review.
