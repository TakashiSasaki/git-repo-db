# Independent review of the final C′ experiment

**Verdict: DEMONSTRATED for the stated bounded experimental obligations on
SQLite 3.51.3 and 3.53.1, with the declared FK/CHECK/trigger/admission/evaluation
division.** This is not product implementation, a new accepted design, arbitrary
Provider semantic qualification, authentication, or release acceptance.

The reviewer is a separate agent from the candidate, author harness, baseline
control and design authors. The full owner task and accepted constraints were
read before review. The reviewer did not edit candidate SQL, validators, author
tests, product code or accepted ADRs. Earlier independent findings caused
corrections by the author, followed by a new frozen checkout and new executions.

## Exact final input

| Coordinate | Identity |
| --- | --- |
| Product baseline | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree `117d580b31098ecb8287281bd843894fdfad71fc` |
| Reviewed executable freeze | `e9aba86f4530b2e683c77e23a4fe58bdf02192c5` |
| Reviewed tree | `7db7773f4cc2860b3818856b048a5832cdb00d6b` |
| Input-manifest SHA-256 | `866c1a521bafac657aba63a6662ea46b3a12f36aa70b5643f4553c99cb837c96` |
| Composed candidate SQL SHA-256 | `c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee` |
| Author admission/test harness SHA-256 | `12dfaee585ebe67c846e446594ae926f90191a282e22768c876dfa4a78d091b3` |

Every manifest input hash and the composed SQL hash was checked in a detached
checkout. The final schema/row-local predicates are unchanged from the second
freeze; final corrections concern the experimental typed-admission helper and
tests. Later prose is not treated as a new execution of the candidate.

## Executed independent verification

The reviewer independently ran the documented driver against the frozen checkout
on Python 3.12.14 / SQLite 3.53.1 and Python 3.13.5 / SQLite 3.51.3. On each,
the author's 15 grouped cases/163 recorded steps and 9 baseline controls passed.
Collected/executed author IDs match, and the rerun receipts bind the exact frozen
inputs. This repeats author cases; it does not add another 15 distinct tests.

The separately written [reviewer probe](final-probe.py) uses independent fixture
identities and direct SQL, plus 11 explicitly identified calls to the frozen
typed-admission routine. It records **75 expected observations on each runtime**
with no unexpected outcome. Some deliberately demonstrate enforcement limits,
such as fabricated event types passing SQL; they are not 75 pure SQL guarantees.
The same checks repeat across runtimes, overlap author cases, and are not added
to author counts. [Current](final-current.json) and [minimum](final-minimum.json)
receipts contain actual errors, SQL traces, transaction state, rowsets, runtime
source IDs/compile options/pragmas, input hashes and checkpoint results.

The final independent checks include a second-endpoint failure after the first
endpoint has actually been inserted. An actual FK error rolls back the whole
Transfer report group and both endpoint rows while retaining the previously
admitted Event, Issue and Parent report. The trace records both attempted
endpoint INSERTs. This extends the author's unit-cut/preflight coverage.

## Eight feasibility obligations

| Obligation | Independent result |
| --- | --- |
| 1. Complete E9 exists before I7 | Demonstrated. No semantic Parent FK remains in Resources; E9's complete identifying coordinates survive. |
| 2. Typed Parent report waits for actual referents | Demonstrated by real target/source FKs. Parent arrival does not synthesize withheld reports; actual re-supply is needed. |
| 3. Transfer cites exact admitted typed Parent report | Demonstrated by full composite FKs carrying the support report's complete semantic key and `timeline_event`/`issue` properties. Parent alone is insufficient. |
| 4. Wrong Event/kind/namespace, missing support, incomplete keys cannot bypass structural admission | Demonstrated with actual FK errors, separate CHECK/cardinality/NULL controls and immutable conflict-path rejection. |
| 5. Actual normalized event semantics are checked at admission | Demonstrated: a structurally coherent wrong event type passes SQL but is rejected by typed admission. Neither layer authenticates the Provider. |
| 6. Attributable alternatives survive | Demonstrated. The support index includes the full report key; there is no broad unique Event or Event/Parent restriction. Each dependent report identifies supplied support without choosing a winner. |
| 7. Original identity, clocks, provenance and atomic grouping survive | Demonstrated for original NULL/known times, independent Parent/Transfer attribution and clocks, exact replay, one-sided units, selected cuts, missing members, and actual mid-unit rollback. |
| 8. No new authority/surrogate/hidden Parent authority | Demonstrated by schema inventory/source inspection: same 19 table names, unchanged five Coverage claim columns, no new Parent/Event-header/Mapping/Witness/history table or surrogate relationship key. |

## Enforcement inspection

- **FK:** actual target Resource, typed source Document, full Parent support key,
  exact event-report group and existing Repository endpoint registration. Valid
  syntax with an absent referent reaches `SQLITE_CONSTRAINT_FOREIGNKEY`; Python
  prevalidation does not conceal these checks.
- **CHECK/generated projection:** identity grammar/canonicalization, known common
  document coordinates, singleton membership, support completeness and endpoint
  inclusion. Bounded deterministic Python functions inspect only row-local
  syntax; none perform a database lookup or application callback for existence.
- **Trigger:** immutable UPDATE/DELETE/REPLACE, original observation binding,
  whole EventReportKey payload, and pre-conflict immutable-payload comparison.
  Required recursive triggers were enabled. These are not labeled as FKs.
- **Typed admission/savepoint:** normalized event type, strict original Python
  observation types, complete supplied endpoint set, declared Provider-member
  existence, validated replay, and whole-unit rollback. SQL INTEGER affinity
  does not prove pre-affinity input types.
- **Application/evaluation:** arbitrary general member existence, selected
  dependency closure and whole-group withholding; any semantic qualification
  among competing reports. Exact support linkage does not resolve that policy
  or infer external truth.

Ordered multi-member general relations remain intact. Unknown resource kinds
use the common format without receiving inferred typed Parent meaning. The
reserved typed singleton Parent contract applies to the baseline common document
kinds; it does not purport to know every Provider's relation vocabulary. Known
malformed document input cannot fall through the generic Resource path.

Direct SQL can store an event-report declaration before all endpoint rows are
present, and can name an absent member in an arbitrary generic JSON group. Those
are deliberately identified admission-layer obligations; they are not claimed
as reverse endpoint-set FKs or arbitrary-array FKs. Supported structurally valid
checkpoints return no FK violations and `integrity_check = ok`; that does not
authenticate an externally fabricated but internally consistent report.

## Findings closed without rewriting their evidence

| Finding | First observed freeze | Final independent result |
| --- | --- | --- |
| IR-F01: Parent/Transfer provenance and clock were forced equal | `2f40e52` | Explicit Parent provenance plus independent original scope clock succeeds; cross-pairing and incomplete support still reject. |
| IR-F02: changed Resource identification metadata could be ignored | `2f40e52` | INSERT, IGNORE, REPLACE, DO NOTHING and DO UPDATE reject changed immutable payload; exact no-op replay retains the original. |
| IR-F03: declared Provider member absent from Resources was admitted | `d9d6860` | Missing member withholds the whole unit without staging or invented registration; actual selected member arrival alone creates no report; re-supplying the original succeeds and deduplicates. |
| IR-F04: bool/float/numeric-string observations reached SQLite affinity | `d9d6860` | Existing strict validator rejects each before SQL, equality or replay; original accepted times remain intact. |

[Round one](round1-review.md) and [round two](round2-review.md), their scripts and
runtime receipts preserve the original counterexamples. They are not relabeled
as passes. During the final reviewer run, a reviewer expectation incorrectly
named `ValueError`; the existing time validator correctly raised `TypeError`
before SQL. The [initial script](reviewer-development/initial-final-probe.py) and
[mismatch receipt](reviewer-development/expectation-mismatch.json) retain that
fixture correction. No candidate input changed to make the test pass.

## Documentation and remaining scope

The reviewer inspected the main experiment report, evidence README and appended
immutable-replay lesson in the existing invariants skill. Their inspected hashes
are separately recorded in [prose inputs](prose-review-inputs.json); this prose
was outside the executed freeze. The lesson accurately describes the observed
conflict-ignore issue and its trigger/FK distinction. It does not authorize new
product behavior or architecture decisions. Later editorial completion of the
verdict and links is not part of that exact prose hash.

No new architectural decision is demonstrated necessary by these corrections.
Whether a given independently attributed Parent report qualifies semantically
for an operation remains a separate validation/evaluation question, expressly
outside the FK's claim. Product writers/readers, Exchange, stored integrity and
paired backup/recovery for this candidate remain unimplemented, as required by
the task's isolation. The experimental reconstruction/snapshot evidence is not
product end-to-end acceptance. No real catalogs or Provider account data were
used, and production source/DDL/fingerprints, accepted ADRs and defaults remain
unchanged.

Reproduce the independent probes using this preserved script and a detached
checkout of the final executable freeze:

```sh
python final-probe.py --repo /path/to/frozen-checkout --output /tmp/review-final-current.json
LD_LIBRARY_PATH=/tmp/u3-sqlite-runtime/minimum/lib /usr/bin/python3 \
  final-probe.py --repo /path/to/frozen-checkout --output /tmp/review-final-minimum.json
```

[Independent author-driver rerun](final-author-rerun.json) is separate from the
new reviewer probe receipts and retains exact input/runtime binding.
