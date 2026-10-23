# Independent Parent / Event / Endpoint audit

Reviewed commit `08fbb956c2e470e245146b0dbae747ed0690ea40`, tree
`7072f952975a8537f74ced1bbc2a4a31d7aa3690`. This reviewer did not author
the implementation. Product source and frozen Author evidence were not changed.

## Independent measurements

`probe_originals.py`: **19 PASS**, exit 0. These are standalone assertion
probes, not pytest nodes. They use newly designed synthetic original coordinates
(Parent clock 21 / provenance P / time 22, Event clock 900 / provenance E /
time 901), exact schema/UDF/PRAGMA validation, the existing explicitly scoped
fresh-memory isolated fixture, and finite fixed Resource/Provider grants. The
schema/authority helper is reused infrastructure; vectors and assertions are new.

The probes independently cover missing required Parent/declaration/endpoints,
omitted versus explicit-NULL Parent time, constructor truncation and selection
omission, genuinely one-sided versus two explicit-NULL endpoints, unresolved
Provider-only endpoints, exact initial/replay roundtrip, changed Parent time on
replay, attempted Event-coordinate substitution for Parent, absent exact Parent
and explicit resupply after late Parent arrival, simultaneous lawful I7/I8
Parents with permanent rejection of I8 Transfer support and no Parent winner,
replay rewriting a two-sided report, old rows failing to rescue a truncated unit,
all three required Parent-scope coordinates missing/NULL, and global/scoped
Document child-first registration with no namespace Resource or semantic Parent.
Known scoped identity metadata remains mandatory on duplicate registration.

The first run had **18 PASS / 1 FAIL**, exit 1: the reviewer's Document vector
used an Issue namespace, whereas the accepted known Document contract permits a
PR namespace. This was a reviewer setup error before product admission. Its raw
failure is retained in `results-initial.json`. The vector was corrected to an
absent PR namespace; all final 19 probes pass. No product assertion was removed.

## Finding ORIGINALS-M1 — original declaration is not revalidated at store intake

**Medium, open; I6-A R09/R15 acceptance gap.** It is present at reviewed #145
and inherited from #143, not introduced by the remediation diff. The ordinary
Transfer product route remains fenced. This finding is about the local typed
carrier boundary that I6-A implements and its required isolated acceptance;
it is not a claim of remote Provider forgery, permission escalation, a network
exploit or permission to activate Transfer.

`probe_invalid_carrier.py` reproduces **4 failed safety predicates**, exit 1:
two independently invalid nested declarations (`None`, an invalid string), each
on initial admission and exact replay. Construct a valid report, then change its
caller-owned `endpoint_declaration.from_endpoint` with `object.__setattr__`.
The public store accepts the object: initial calls return `insert`, replay calls
return `duplicate`. The stored/readback declaration is `explicit_null`, while the
supplied original was missing/invalid. Both actual endpoint rows are present;
this is not a missing received-row or selection test.

The direct constructor, `dataclasses.replace(report)` and the existing pure
`validate_originals(report)` all correctly reject the same carrier with
`INCOMPLETE_ORIGINAL_REPORT`. There is no simpler constructor-accepted malformed
vector in this finding. The problem appears after construction because public
intake checks only parts of the carrier and never invokes the existing complete
original validator. Frozen dataclasses prevent ordinary assignment; they do not
seal caller-owned nested fields against deliberate mutation. This boundary's
existing tests explicitly use `object.__setattr__` for nested context/session
tampering (`tests/unit/test_context_admission.py:504,519`), though those tests
cover invocation authority rather than original-evidence payloads. This review
does not assume that arbitrary in-process Python is sandboxed from database or
service internals; the supported claim is strict revalidation of the supplied
typed input, comparable to the store's existing pre-bind checks.

Root cause and source anchors at the reviewed commit:

- `domain/p1_context.py:1855` revalidates the total declaration only inside
  `TransferEventReport.__post_init__`.
- `adapters/sqlite/context_admission.py:126` charges/enumerates the input and
  checks authority, but does not call `validate_originals`.
- `adapters/sqlite/p1_context.py:340` manually rechecks times, native Parent and
  received endpoints, without revalidating the nested declaration.
- `domain/p1_context.py:1790,1799,1972` maps any non-Resource value to a missing
  Provider ID while treating any value other than `not_reported` as reported.
  Hence invalid `None` serializes as a reported role with NULL Provider ID;
  `from_stored_scope` at line 2055 reads this as `explicit_null`.
- `domain/context_admission.py:658` already provides complete validation via
  `replace(unit)`. Repository search finds no product callsite, only its
  definition and recursive self-call. A test invokes it directly.

The result does not depend on omission of the Provider declaration, stripping
endpoint rows, obtaining new grants, a raw caller-owned transaction or weakened
SQL constraints. Actual typed admission, its trusted service/context, exact
scope/FKs and commit owner execute. SQL cannot reject the serialized result:
it has already been converted into a valid explicit-NULL representation.

Two additional normal-route controls restore both exact packaged Transfer
fences and return `I2_TRANSFER_UNSUPPORTED` with unchanged rows and no open
transaction. Their success is recorded separately, not used to dismiss the
isolated I6-A validation failure.

Required correction: after bounded input accounting and appropriate authority
ordering, revalidate the complete mandatory original carrier on every public
admission, before content lookup, serialization, write or duplicate success.
Preserve constructor refusal, both stage fences and finite authority. Add both
initial/replay invalid nested original tests, and require
`INCOMPLETE_ORIGINAL_REPORT`, unchanged rows and no dependency-existence leak.
Re-run this counterexample and the 19 positive/negative probes. No fix is made
in this evidence-only review.

## Limits and handoff

No new Critical/High/Low issue was found in this audit scope; this is not a
whole-repository absence claim. Parent originals, alternatives, identity/Parent
separation and normal endpoint-state vectors pass the independent probes above.
The malformed nested carrier gap prevents unconditional acceptance of R09.
The root reviewer decides the overall I6-A verdict using other audit results.

I6-B/C must retain mandatory original declarations and exact Parent keys in wire
and composition; current isolated probes do not accept unimplemented wire,
Provider, Exchange, permutation/onward/reverse import or I7 recovery paths.
Original Provider authenticity remains deliberately unauthenticated. No live
Provider/catalog operation, existing PR modification, merge, release or deploy
was performed. No action in this audit was denied, pending approval or uncertain.

Reproduction from the frozen checkout:

```sh
PYTHONPATH=src:. <review-venv>/bin/python \
  docs/implementation/evidence/adr0031-i6a/remediation-independent/originals/probe_originals.py \
  /tmp/originals-results.json
PYTHONPATH=src:. <review-venv>/bin/python \
  docs/implementation/evidence/adr0031-i6a/remediation-independent/originals/probe_invalid_carrier.py \
  /tmp/invalid-carrier-results.json
```

The second command intentionally exits 1 while the defect remains. Raw output
contains only synthetic identifiers and SQL. Python **3.12.14**, the actual
built-in SQLite **3.53.1**, and the parent's locked review environment were used;
no SQLite component was obtained, built, substituted or matrix-tested.

Reusable lesson recommendation (no skill edited because this review's changes
are restricted to its new evidence directory): when a public boundary promises
strict typed-input validation, verify that the validator is called by the real
path, then challenge a previously valid nested carrier after construction. A
direct unit test of the pure validator does not establish intake revalidation.
