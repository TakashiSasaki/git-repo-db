# Independent I6-A retention review at I6-B

Scoped PASS for the retained I6-A admission and fence obligations examined here.
No new Critical, High, Medium or Low finding was established. These results do
not qualify the deferred Provider/Exchange integration, ordinary Transfer, I7,
I8 or Release acceptance.

## Identity, scope and independence

The frozen product is PR #151 HEAD
`ef787a5ff8b13f118d6bf5107c7338f43fde56dc`, tree
`a3ed2628a98db134bdc65d13da905f5ddf25e972`, based on #149
`ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`.
The eight inspected production admission, Store/facade, coordinator, stage and
application route modules have byte equality with #149. `source-binding.json`
compares the current bytes, frozen #151 Git blobs and #149 Git blobs. The
`test_admission.py` fixture changes are bound to #151 separately; they are not
claimed unchanged from #149.

This separate review task read the repository guide, relevant invariant and
efficient-investigation skills, ADR 0001/0031/0032, I6 boundary/vectors/handoff,
I6-B Author scope, and #149 Task C independent report. The production tree,
accepted ADRs, historical evidence and existing assertions were not edited.
The reused 27-case independent authorization suite is copied byte-for-byte from
`adr0031-i6a/remediation-independent/authorization/test_independent_authorization.py`;
its prior authorship is explicitly retained. Existing report/SQL fixtures provide
synthetic finite setup. The 19 new cases below use a newly written exact-principal
finite policy; none confers general allow-all authority.

## Actual executions

The lanes are separate invocations and overlap in their behaviors. They must
not be added to the complete-suite count.

| Invocation | PASS | FAIL / ERROR / skip / xfail | Exit | Evidence |
| --- | ---: | ---: | ---: | --- |
| Existing admission, coordinator, bounds, refusal-order, fences, OID, and both `tests/integration/i6a` files | 237 | 0 | 0 | `inherited.*`, `inherited-sql-observations.json` |
| Newly written cases plus attributed reused authorization suite | 46 = 19 new + 27 reused | 0 | 0 | `new-and-reused.*`, `new-observations.json`, `reused-sql-observations.json` |

All 237 and 46 collection IDs respectively equal their journal start multisets.
Each node has exactly one passed setup, call and teardown; normalized JUnit
module/function identities match the journal, with no duplicates. Both journals
finish normally with exit zero. The 19 new nodes include 18 behavioral cases and
one evidence writer; the reused 27 include their own evidence writer.
Reconciliation details are retained in the two `*.reconciliation.json` files.

The selected interpreter is `/workspace/git-repo-db/.venv/bin/python`, CPython
3.12.14, using its actual built-in SQLite 3.53.1. The measured source ID is
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Actual imported source modules, capabilities, compile options, required PRAGMAs,
exact both-fence definitions, clean FK/integrity checks and input SHA-256 values
are in `source-binding.json`. No SQLite was installed, built, replaced or matrix
selected. Durations are execution records, not sequential benchmark claims.

## Independent counterexamples and observations

- Twelve new Store/facade initial/replay attacks use an otherwise equal-valued
  principal issued by another service, an independently reconstructed context,
  or a mutated operation on the real context. Each refuses `PERMISSION_DENIED`
  before policy callback and content SQL, with full persistent rowsets unchanged.
- Four new Store/facade initial/replay cases use the real SQLite authorizer to
  deny preparation of the actual outer `COMMIT`. Before denial, the Event and
  both endpoints are pending and policy leases remain active. SQLite reports
  `SQLITE_AUTH` (23); the owned boundary issues `ROLLBACK`, releases every lease,
  preserves all preexisting rows, and retains charged work. Replay does not
  bypass the actual commit boundary. A clean catalog is not marked corrupt.
- Two new Store/facade cases successfully admit the first complete Transfer unit,
  then revoke its Event grant and attempt a second unit in the same transaction.
  The second unit refuses current authorization, the first pending unit rolls
  back, no `COMMIT` occurs, all rowsets match the pretransaction state, and work
  is not refunded.
- Attributed reused controls additionally cover forged/copied/foreign/mutated
  principal/selection/budget handles, credential denial, missing authority,
  replay permission/selection/read-operation denial, same-context revocation,
  genuine second-endpoint INSERT failure, deferred-FK COMMIT failure, policy
  revocation after writes, cancellation, and lease retention through successful
  and duplicate COMMIT.
- Existing tests separately execute both exact normal fences; either missing;
  either definition changed; both missing; unreadable schema; normal reopen;
  wrong PRAGMAs/UDF flags; expired/disk/foreign isolation capabilities; Provider
  unit/units/batch refusal; Exchange export refusal; and initial/cached-receipt
  import refusal. Normal Transfer remains `I2_TRANSFER_UNSUPPORTED`.

The actual second-INSERT observation is Event=1/endpoint=1 inside the aborting
trigger, followed by `ROLLBACK TO` and whole-transaction rollback. The deferred
FK failure reaches outer COMMIT with Event=1/endpoints=2 and active policy leases,
then explicitly rolls back. These are saved executed SQL observations, not tests
that stop at preflight. Parent originals remain unchanged.

## Requirement and test mapping

| Requirement / vector / test ownership | Independently exercised evidence |
| --- | --- |
| R10–R12 / T07–T09, T26, retained I6-A | New identity attacks; inherited per-dependency denials/current authority/selection/privacy; reused finite policy suite |
| R08/R09 / V03–V07, T03–T06, T27, retained I6-A originals | Existing independent Parent original clocks/provenance/time and complete endpoint/replay tests, both originals-revalidation file and saved SQL observations |
| R11/R14/R15 / T08, T17–T18 | New COMMIT-authorizer and second-unit revocation probes; inherited actual second endpoint/deferred COMMIT; reused cancellation/revocation and successful/duplicate COMMIT |
| R16 / T19–T20 | `test_context_fences_i6a.py`: both exact, unilateral/total missing, altered, unreadable, reopen, expiry, disk fixture, PRAGMA/UDF profiles |
| R16 / T26, retained fail-closed routes | `test_unconnected_provider_routes_refuse_before_resource_lookup`; `test_unconnected_exchange_export_refuses_before_identity_or_context_lookup`; `test_unconnected_exchange_import_refuses_before_progress_and_cached_success` |
| R19 / T24–T25 | This source-bound lane; separate packaging and broad-suite review artifacts own installed/broad acceptance claims |

## Reproduction and limits

Use the command list in `commands.json`. Copy the two `.py.txt` probes into a
fresh external directory with their original `.py` basenames. Run that directory
as a whole with `-c /absolute/frozen/pyproject.toml -p tests.conftest`, using the
same source-bound environment and `I6B_ADMISSION_OBSERVATIONS` pointing to a new
writable JSON file. The original conftest's offline guard remains active. The
reused evidence writer writes next to its copied module. The new script imports
only product modules and existing synthetic report/SQL setup.

Two receipt-tool observations are preserved independently of product tests:
the initial source summarizer assumed `_sqlite3.__file__` existed and exited 1
because this runtime embeds the extension; the correction reports `<built-in>`
without changing the interpreter or library. An individual-file collection
command produced `::function` IDs, different from the directory execution's
module-qualified IDs. Its raw output is retained; recollecting the exact executed
directory target restores exact multiset equality. No test was rerun or outcome
rewritten to repair either receipt-tool issue.

No independent installed result is claimed by this source report; distribution
review owns those separate results. No real catalog, Provider acquisition,
Release validation, merge or later implementation stage was performed here.
