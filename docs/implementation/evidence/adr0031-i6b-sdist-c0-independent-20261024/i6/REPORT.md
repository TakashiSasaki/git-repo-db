# Independent retained I6-A/B contract review

The examined non-scanner I6-A/B contracts pass these bounded checks at published
PR155 HEAD `fee364c6d61a5feebf08dbdd830a5a57ee2d872b`, tree
`ace7e44cd89194d189a30a0aa6cf513a45b3b87c`. No new Critical, High, Medium or Low
finding was established in this lane. The separate scanner study controls its
own R04/R13 disposition and the parent report controls the integration verdict.
This lane does not supply an overall PASS or override a scanner finding.

After the retained-contract runs, this reviewer independently confirmed the
parent's admission-scanner finding through a second minimal observer and normal
both-fenced facade. `confirm_queue.py` and `queue-confirmation.json` are the
separate cross-check; it supports the parent's Medium R04/R13 finding and
therefore its overall FAIL. The non-scanner result above does not close that
finding. It is counted once in the parent findings, not duplicated here.

The review used the fresh published-source checkout, AGENTS, the repository
investigation/invariant/CI skills, Accepted ADR0001/0031/0032, I6 requirements,
vectors and handoff, the historical #152 findings, #153 correction and #154
admission/wire re-review. It accessed no Task A workspace or unpublished change.
No product, existing test/assertion, workflow, ADR or historical evidence changed.

## Executions and reproducibility

| Separate invocation | Observed result | Raw evidence |
| --- | --- | --- |
| Retained source wire/admission/fence/capability/coordinator/I6-A cohort | 446 PASS; exit0; zero skip/xfail | `raw/existing.*`, `raw/collection.*` |
| New independent bounded contract script | 58 recorded checks PASS; exit0 | `probe_contract.py`, `raw/independent.*` |
| Unchanged prior independent admission probe | 13 PASS; exit0 | `raw/reused/` |
| Existing actual second-INSERT/deferred-COMMIT nodes, rerun with SQL observations | 2 PASS; exit0 | `raw/actual-sql/` |
| External direct-wheel retained I6 cohort | 446 PASS; exit0 | `raw/installed-direct/` |
| External sdist-derived-wheel retained I6 cohort | 446 PASS; exit0 | `raw/installed-derived/` |

These invocations overlap and are never added into a unique full-suite count.
The 58 entries are standalone recorded checks, not pytest nodes. Five entries
are individual finite-authority checks inside the script's admission group;
the enclosing group is also recorded. No performance comparison is claimed.

`commands.json` retains commands, attribution and exits. `audit_evidence.py`
independently checks journal starts, exactly one passing setup/call/teardown per
node, terminal normal exit and JUnit identities. Collection matches all446 and
all13 nodes exactly. The targeted2 nodes are explicitly named and reconcile
JUnit/journal; their identities also occur in the independently collected446.
`reconciliation.json` retains all identities and phase counts. Assertions inside
the original tests remain unchanged.

`source-binding.json` measures177 entries: all160 product files, build/fixture/
selected-test inputs, and the copied historical probe. Every live input matches
the frozen published Git blob. All160 product files and selected tests/fixtures
match direct base154; `pyproject.toml` is the measured distribution-only input
difference. The copied13 probe is byte-identical to the #154 published file.
These hashes bind actual source; they do not authenticate anyone's observations.

The distribution lane separately ran the exact new script from each real
installed direct/sdist-derived wheel, outside checkout with PYTHONPATH unset:
58 recorded PASS/exit0 each. Its artifact and import-origin receipts remain in
that lane. These executions are attributed to the distribution reviewer, not
new source invocations claimed here.

For the full retained installed cohort, this lane extracted the published Git
test/script/config inputs into a separate external directory with no `src`
tree. All327 inputs match their frozen blobs in `installed-harness-binding.json`.
Each wheel's own interpreter/CLI executes the unchanged446 selected nodes with
`-o pythonpath=`. The `installed_origin.py` observer asserts that every actually
loaded product module originates in that wheel's external site-packages and
records hashes plus actual SQLite identity. Each final installed collection
precedes its execution; actual selected/JUnit/journal node and phase multisets
match exactly. No installed-node count is inferred from source success.

The initial direct attempt exited4 during conftest bootstrap because `jsonschema`
was absent; no product test executed. `raw/failed-initial-direct/` retains it.
The five exact lock-hashed test-dependency wheels were installed offline in both
artifact venvs, with no SQLite dependency or runtime replacement; their binding
is `installed-testdeps.json`. The first completed installed446 executions each
passed, but used only the earlier frozen source collection. They remain in
`initial-execution/`; after collecting independently in each installed runtime,
the unchanged446 cohort was repeated to make the final per-lane order explicit.
These repetitions do not add unique nodes or erase the bootstrap failure.

`installed-scope.json` combines each installed446 cohort with the distribution
reviewer's separately executed217 I4 and29 I5 nodes. Their node sets are disjoint:
each artifact's ordinary-source union is exactly692 of6497, leaving5805 ordinary
nodes unexecuted there. Exact mapped/unexecuted rosters are retained in the
`installed-*-source-nodes.txt.gz` files. The separate58 script checks, CLI doctor
and original generated Access smoke are not added as ordinary source nodes.

## Independent vectors and oracle limits

`probe_contract.py` imports no Author/test helper or product canonical encoder
for its expected bytes. It manually specifies the accepted stdlib JSON profiles,
seven named Resource fields, v5 envelope and finite local policy. It covers the
four meaningful empty identities, recursive Unicode identities, global Documents,
and a scoped Event without a namespace Resource or Parent report. Each missing
Resource field, four inconsistent scoped coordinates and eight invalid identity
spellings refuse. No native namespace is converted into a semantic Parent.

For each of five selection-set dimensions, duplicate and permuted inputs refuse
with `DIGEST_MISMATCH` under the original checksum and `INVALID_SELECTION` after
independent raw-dictionary rehashing. `sys.setprofile` observes the actual
production selection constructor without replacing it: zero calls before the
stale-digest refusal, exactly one for each rehashed selection refusal. Caller
input remains unchanged. Unsupported versions and strict work-limit primitive
mutations also refuse. This supports the retained M02 correction within tested
bounds; it is neither sender authentication nor semantic admission authority.

The finite local authority vector grants exactly one declared Resource and its
Provider registration. An identically principalled foreign service handle and a
copied issued handle refuse before policy invocation. Same-handle replay after
revocation refuses and charges work again. Explicit empty Resource selection
omits the unit; replacing an issued selection refuses before policy invocation.
No unrestricted authorization fixture is used by these new vectors.

The retained446 cohort exercises ordered relations/Collections, actual
complete-empty/partial/unknown terminals, immutable alternatives, Source positive
pairs, strict Source terminal booleans, all five Coverage columns and exact proof
terminal coordinates. Its Source and Collection builders and the expected
product validators remain reused coverage, not independent oracles. The new58
checks supplement that coverage rather than relabeling it independent design.

## Originals, policy and actual SQL boundaries

Source inspection confirms v5's exact seven-column Resource profiles, complete
endpoint reference fields, full-key Parent lookup, independent Parent/Event
original times/provenance and exact received endpoint declarations. The446
cohort exercises missing/mutated originals at first intake and replay, native-I7
versus lawful-but-ineligible I8, Provider-only/explicit-null/one-sided/two-sided
states, and rejects truncation without borrowing stored endpoints. Unknown kinds
cannot repair malformed known identification. A checksum supplies no current
permission or Provider authenticity.

The isolated Transfer positives use the existing fresh-memory factory. It
verifies full packaged schema/UDFs/PRAGMAs, records/checks the two exact fences,
drops exactly those fences only on that expiring private in-memory connection,
and closes it afterward. Every other CHECK/FK/recursive-trigger rule remains.
This is a reused test capability, not ordinary Transfer activation. Its builders
and `dependencies(report)` grant construction are explicitly attributed; the
finite policy never expands grants on demand or retries denial with more scope.

The targeted actual second-endpoint abort reaches Event=1/first-endpoint=1
inside the real trigger, raises `SQLITE_CONSTRAINT_TRIGGER`1811, performs rollback
and leaves Event/endpoints=0/0, no transaction, original Parent observation51.
The separate actual outer COMMIT failure reaches Event=1/endpoints=2 with9
active leases and one deferred FK violation, raises
`SQLITE_CONSTRAINT_FOREIGNKEY`787, explicitly rolls back and leaves0/0 plus no
deferred row. Their actual SQL traces and observations are retained.

The reused13 probe additionally records Store/facade first/replay foreign-handle
denial with no SQL, revocation from the actual second INSERT, denied actual
SAVEPOINT RELEASE, finite same-request replay exhaustion, and actual deferred
COMMIT failure with leases active. Complete preexisting table snapshots remain
unchanged after refusals. Failed/rolled-back work stays charged.

The independent scanner cross-check uses no shared scanner observer or test
fixture. Actual C `list.extend` entry/return events show pending2 becoming1002,
including exactly1000 supplied ResourceKey references, while cumulative used
work remains10000 after prior9992. The next charge refuses at10001. The
published loop charged one popped container, checked its length only against
the total10000 ceiling, and performed no reservation for its1000 queued entries.
This is unreserved allocation before refusal, not post-refusal processing.
The fixed root queue at already exhausted work is separately bounded bookkeeping
and is not this finding. Observer introspection adds overhead, so no wall-time or
total-allocation claim is made. The normal facade keeps both exact fences,
never reaches the no-grant policy, rolls back and leaves zero relation rows.

Normal both-fence inspection, each absent/altered/unreadable fence state,
required connection settings and expiring fixture scope run in the446 cohort.
Malformed or missing schema is `UNSUPPORTED_SCHEMA`, never permission to operate.
Ordinary Provider unit/units/batch and Exchange export/import/cached-success
routes still refuse before their existence-sensitive work. Their retained
refusals intentionally leave downstream application assertions unexecuted.

## Limits and next checkpoint

Actual runtime: CPython3.12.14 using its loaded SQLite3.53.1; full source ID,
compile options, module origins, FK/recursive-trigger settings, integrity/FK
checks and actual fence SQL are in `runtime.json`. No engine was downloaded,
built, swapped or spoofed. No live Provider or real catalog was touched.

This review does not prove an unlimited absence of malformed inputs. Scanner
budget/allocation semantics are the separate study; distribution/archive/C0,
Git provenance, broad failure comparisons and hosted CI are separate lanes.
I6-C/I7/I8, normal route integration, original Access success, full hosted
runtime/Release acceptance and fence retirement remain deferred. Existing299
failures are neither closed nor used here as an automatic scoped FAIL.

Next checkpoint: disposition of every established scanner finding, then a
separately assigned Author correction and fresh non-Author review where needed;
later assigned I6-C integration still requires current authority, exact originals
and both-fence preservation. No merge, release, deployment or incorporation of
unpublished I6-C follows from these results. Existing skills already describe
the retained canonical-digest/actual-COMMIT lessons; this lane found no new
verified procedural correction requiring a skill mutation.
