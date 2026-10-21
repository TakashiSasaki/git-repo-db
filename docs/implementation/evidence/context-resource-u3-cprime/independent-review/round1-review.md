# Independent review, first frozen candidate

Reviewer: separate `independent_review` agent; not an author of the candidate,
author harness, baseline controls, or proposed design. The reviewer read the
owner's complete task, root guidance, ADR index/policy, ADRs 0017/0028/0029/0030,
baseline schema/adapters, Transfer domain contracts, selective Exchange and
stored recovery validation before assessing the candidate. No candidate or
product input was edited by this reviewer.

## Exact reviewed input

- Commit: `2f40e5262c6ccdb776b9f82fcba33d42c323a4e8`.
- Tree: `ae711e0b6fb24423259f7ddea6760096e84c9376`.
- Input manifest SHA-256:
  `95a9beaf478b308027047339366bcbc5c08e01fa51db18fa40212def8fcce7fe`.
- Candidate composed SQL SHA-256:
  `88a128313076bdf970d4b2aca31ce6fc10b84d0a613f1bf640c6ff135d628b74`.

The reviewer created a detached worktree at this commit, verified every frozen
input hash, and repeated the documented driver. Both real runtimes passed the
author's 12 grouped scenarios (128 recorded steps), plus the 9 baseline controls.
The independent probe uses separately written fixtures and direct SQL, with two
explicit calls to the frozen experimental typed-admission routine. Its 56
checks were repeated on Python 3.12.14 / SQLite 3.53.1 and Python 3.13.5 /
SQLite 3.51.3. Runtime source IDs and compile options are in the receipts.
Repeats and overlaps are not added into a distinct-case total.

## Findings requiring correction or a narrower conclusion

| ID | Finding | Executed evidence | Consequence |
| --- | --- | --- | --- |
| IR-F01 | Parent support reuses the Transfer's provenance and requires equal clocks, rather than carrying the independently supplied Parent provenance/clock | IR31 has an admitted Parent report but an independently attributed Transfer fails `SQLITE_CONSTRAINT_FOREIGNKEY`; IR32 preserves the Parent scope and gives the Transfer a different original clock, failing `SQLITE_CONSTRAINT_CHECK` | The candidate cannot preserve those genuine independent report coordinates. It must not fix this by rewriting either report's provenance/clock or by declaring a new architecture rule. A full explicit support key within existing tables is a plausible engineering correction, not yet verified in this round. |
| IR-F02 | `INSERT OR IGNORE` of a Resource's existing immutable key with changed non-key identification namespace is silently ignored | IR33 returns success and retains the old row, with no error | No invalid row is persisted, but the established immutable replay-rejection contract is not preserved for this write path. A trigger must compare immutable payload before conflict-ignore, or the claim must remain unproven. |

The machine receipts' `matches_expectation` field characterizes what SQLite
actually did. The final three checks deliberately expect the observed failure
or silent-ignore behavior; **56 matched observations do not mean 56 fulfilled
contract obligations**. These counterexamples prevent an unqualified
DEMONSTRATED verdict for this frozen candidate. Neither demonstrates that C′ is
impossible or calls for a new authority table.

## Confirmed structural scope

The candidate retains exactly the baseline's 19 tables and five Coverage claim
columns. `resources` no longer has its semantic Parent columns/FK; its only FK
is to Provider registration. Identification namespace columns remain
consistency-checked values, not Resource referents. No table, surrogate relation
key, Event header, Mapping/Witness history or hidden second Parent authority was
found.

Actual real composite FKs enforce the typed Parent target Resource, typed source
Document, exact Parent support report, and exact coherent event-report row.
Missing Parent, missing support, ordinary Comment and wrong Event probes reach
`SQLITE_CONSTRAINT_FOREIGNKEY`, separately from row-local CHECK rejection.
Required support coordinates reject NULL; generated projections are not
independently editable. The unique support index includes the original full
report key and typed projections; it does not impose `UNIQUE(event)` or
`UNIQUE(event,parent)`. Distinct attributable Parent/Transfer alternatives
survive without choosing a winner.

The committed rowsets retain one-sided reports, original NULL observation time,
exact recursive string-array identities, distinct empty coordinates, ordered
general multi-member groups and immutable payloads except IR-F02's refusal gap.
No test claims SQLite discovers that an empty identity is genuine upstream.

## Enforcement limits verified directly

- Identity grammar, canonicalization, cardinality and row-local scope/member
  syntax use CHECKs backed by deterministic Python UDFs. Those UDFs do not query
  a database. They are not mislabeled as FKs.
- Immutable evidence and exact report/endpoint observation agreement use
  triggers; direct UPDATE/DELETE/REPLACE and changed endpoint support with
  `ON CONFLICT DO NOTHING` were rejected.
- Arbitrary general relation member existence remains an admission obligation;
  IR25 inserts a syntactically valid missing generic member directly and passes
  FK/integrity checks. The typed Parent member uses a real FK instead.
- SQL admits a structurally coherent `event_type='closed'` report and endpoint;
  typed admission rejects it (IR26–IR28). Neither layer authenticates the
  Provider or proves an external event occurred.
- Direct SQL can store the event-report group before its endpoint rows; no
  reverse endpoint-set FK or commit hook exists (IR29). Complete endpoint sets
  and selected-unit cuts are enforced by the typed admission transaction (IR30),
  not by `PRAGMA foreign_key_check`.
- Experimental snapshot/reconstruction evidence is not product Exchange/backup
  acceptance. Product fingerprints, decoders, and paired recovery contracts
  still expect the frozen product schema and were not changed.

All reviewer FK/integrity checkpoints on supported structurally valid fixtures
returned no FK violations and `ok`. Those checks do not erase the semantic and
replay findings above.

## Reproduction and evidence

Check out the reviewed commit into a separate directory, then run the preserved
reviewer script with that directory as `--repo`:

```sh
python round1-probe.py --repo /path/to/frozen-checkout --output /tmp/review-current.json
LD_LIBRARY_PATH=/tmp/u3-sqlite-runtime/minimum/lib /usr/bin/python3 \
  round1-probe.py --repo /path/to/frozen-checkout --output /tmp/review-minimum.json
```

[Current receipt](round1-current.json), [minimum receipt](round1-minimum.json),
[independent script](round1-probe.py), and
[author-driver rerun binding](round1-author-rerun.json). The script hash is
embedded in each independent receipt. Later candidate corrections require a
new frozen-input review; these first-round observations must remain intact.
