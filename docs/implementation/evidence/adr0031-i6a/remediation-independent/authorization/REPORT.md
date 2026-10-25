# Independent authorization and transaction review

Reviewed product: `08fbb956c2e470e245146b0dbae747ed0690ea40`, tree
`7072f952975a8537f74ced1bbc2a4a31d7aa3690`.

Result for this bounded review: **PASS WITH CONDITIONS**. The 27 independent
cases pass in source, direct-wheel and sdist-derived-wheel lanes (0
failed/error/skipped each). No Critical/High/Medium/Low I6-A defect was
identified in these audited paths. This is neither release acceptance nor
acceptance of the unconnected Provider/Exchange/Recovery composition.

## Independence and reproduction

`test_independent_authorization.py` defines a new finite, exact-principal policy,
new refusal tests, SQL fault injection and cancellation probes. It imports the
frozen P3 report constructors/base-row setup and the explicit isolated in-memory
connection scaffold, rather than reimplementing their original evidence grammar.
It does **not** use `FixturePolicy`, `FixtureContext`, `fixture_service` or the
Author's test assertions. Frozen helper reuse is a limit on independence of data
generation; the policy, injected faults and outcomes are independent.

From the reviewed checkout, with the prepared runtime:

```sh
python -m pytest docs/implementation/evidence/adr0031-i6a/remediation-independent/authorization/test_independent_authorization.py -q -o addopts= -p scripts.ci_journal --junitxml=AUTH_OUT/junit.xml --journal=AUTH_OUT/journal.jsonl
```

The first execution had 23 passing cases. Four further controls added no-service,
missing-context, missing-owned-transaction and exact normal-schema fence checks;
the final execution ran all 27 with exit 0. Both executions are preserved. Timings
are operational observations, not comparable benchmark evidence (other review
work may have run concurrently).

Python 3.12.14; executable `/workspace/review-runtime/bin/python`; SQLite 3.53.1,
source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
This lane imports `/workspace/i6a-independent/src/repo_catalog/__init__.py`.
No SQLite component was installed, replaced or built. This is the source lane;
the two separate installed-artifact lanes also establish their own origins.

The exact independent test module was copied byte-for-byte to
`/workspace/review-installed-safety-work/outside/test_independent_authorization.py`.
Both artifact venvs run from that external harness, with its explicit
`pytest.ini` (empty product pythonpath), `--rootdir=. --confcutdir=.`, and only
that external harness on `PYTHONPATH`. The root review's harness hooks verify
the wheel's Python/SQL/JSON file hashes and every loaded product module at session start and
finish. Direct and sdist imports both resolve under their respective venv's
`lib/python3.12/site-packages/repo_catalog`. No product source checkout enters
those installed pytest processes. `direct-imports.json`/`sdist-imports.json`
retain those guards; `executions.json` retains the exact commands and module hash.

Direct installed: **27 PASS**, exit 0; sdist-derived installed: **27 PASS**, exit
0. These are overlapping behavior checks, not 54 additional ordinary source
identities. Each lane has exactly 27 unique journal starts, matching 27 JUnit
identities, 81 successful setup/call/teardown phases and a completed exit-0 finish.
Both installed node sets are equal (`node-reconciliation.json`). An initial
preparatory copy command used an incorrect relative source path from the outside
working directory and exited 1 before any tests; it was corrected to an absolute
path, and external-module byte equality was verified. No product failure was
hidden by that correction.

## Measured outcomes

| Boundary | Independent evidence |
| --- | --- |
| Exact service-issued context | Constructed, copied, dataclass-replaced and foreign-service contexts refuse before policy calls or content reads. |
| Principal, selection, budget tampering | Mutation of principal subject, selection limits and budget limits refuses before policy/content access. |
| Authentication diagnostics | Invalid credential yields only `PERMISSION_DENIED`, with no explicit chained authentication cause. |
| No implicit authority | No service, no context and no commit-owned transaction refuse; finite grants remain unchanged. |
| Current permissions and selection | Initial and exact-replay cases separately reject a missing Event Resource grant, missing selected Resource and export-only operation; no content read occurs. |
| Session/policy revocation | Reusing the same formerly accepted context after all grants are removed refuses replay; already admitted historical rows remain `(1 Event, 2 endpoints)`. |
| Actual second endpoint SQL failure | Trigger runs after the Event and first endpoint exist `(1,1)`, then raises real `SQLITE_CONSTRAINT_TRIGGER`; all new Event/endpoint rows roll back. |
| Actual deferred FK COMMIT failure | A real packaged Source–Repository FK is deferred. COMMIT is attempted with `(1,2)` Transfer rows and live leases, then `SQLITE_CONSTRAINT_FOREIGNKEY`; all rows and FK violations disappear after rollback. |
| Revocation before COMMIT | Epoch changes after actual `(1,2)` writes; precommit denies, no COMMIT occurs and rows roll back. Actual work remains charged. |
| Cancellation | `KeyboardInterrupt` after actual writes rolls back the whole Transfer; no open transaction or live lease remains. |
| Commit lifetime | Both successful insertion and exact duplicate replay reach COMMIT with positive active lease count. |
| Expired/read-only facade | Capability shell with SQL/auth objects that fail on any access refuses with `CAPABILITY_EXPIRED`/`READ_ONLY` before touching them. |
| Normal product remains fenced | Both exact packaged fence SQL definitions match. Normal schema refuses Transfer and retains zero Event/endpoint rows and both fences. |

`sql-observations.json` contains complete SQL traces and in-trigger/at-commit
observations. JUnit and journal retain actual identities and all measured phases.

## Code audit and scope

The complete product delta from #143 to #145 is only 12 added lines in
`adapters/sqlite/context_admission.py` and `production_context.py`: the mutation
wrapper invokes a pure local capability check; the facade checks `_active` and
`_writable`. No policy issuance, grants, lookup, DDL or transaction logic is
added by remediation. No fixture helper is imported under `src/`.

`ContextAdmissionService.validate_context` binds issued object identity, issuer
registry, principal state, operation, selection identity/state and budget limits.
`authorize` leases current policy before selection and retains the lease in the
outer `ExitStack`. `admission_checked` authorizes typed dependencies before
existence-sensitive lookups and duplicate handling. `admission_transaction`
checks live leases before COMMIT and rolls back on `BaseException`; facade and
coordinator retain their respective outer commit fences.

The policy port is trusted local composition infrastructure. Its contract must
serialize policy changes with the real commit; the service cannot turn a
nonconforming policy implementation into a correct atomic authority. These tests
use such an explicit policy rather than interpreting Provider assertions as
authority. Deliberate access to private service/SQL infrastructure and arbitrary
Python privileges are outside the supported caller boundary. Pure-capability
shell tests establish refusal order, not an installed filesystem/snapshot path.
Transfer-positive tests use only the scoped disposable in-memory fixture; they
do not authorize Transfer on normal catalogs. Cancellation and revocation tests
prove the single Context Transfer unit, not atomicity of separately committed
Core and Context phases in Recovery.

No existing PR, accepted ADR, frozen evidence or product/test source was edited.
No real Provider/catalog, merge, release or deployment was used. No operation was
denied, pending approval or left with an uncertain outcome in this subtask.
