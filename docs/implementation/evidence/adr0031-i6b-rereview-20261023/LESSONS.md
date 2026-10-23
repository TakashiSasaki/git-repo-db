# Verified reviewer lessons and scope

Existing investigation, CI-final-tree, three-store and lessons-to-skills
procedures were used. The reviewed tree and its existing skills remain unchanged.
No new general-purpose skill is created: their existing guidance covers typed
preconditions, preservation of harness mistakes, exact input/node bindings and
actual traceback comparison.

One concrete recommendation for a future authorized update to the existing
CI-final-tree skill is to preflight observational serializers against test
monkeypatches. Capture the original encoder once before tests, then temporarily
replace `json.dumps` with a raising function and emit a record through the
observer. Restore it immediately and parse the record. This review's
`broad/observer-preflight.json` and reused `broad_receipt.py.txt` verify that
procedure. Do not modify product or test serializers to accommodate observation.
Keep observer output/exit and disclose incomplete observations. This procedure
does not establish safety for arbitrary other monkeypatched dependencies.

Actual ExceptionInfo frames and AST assertion-statement entry are stronger
evidence for the specific observed questions than rendered traceback labels or
passing counts. Keep the latter raw data too: this review retains 299 rendered
traceback differences and one shifted physical coordinate while independently
verifying stable failure semantics. Statement entry is not proof of every
subexpression, other-thread or child-process assertion.

Historical cohort labels may not be directory names: I4 217/I5 29 are the p3
SQL/admission modules in safety626. The initial unmatched directory-prefix
selector output is retained beside the corrected actual-node selector; neither
changes any execution. Require exact expected identities, then assert the count.

New probe fixture errors remain honest evidence. Establish the real typed input
precondition before measuring downstream behavior; arbitrary Provider config or
oversize provenance is correctly refused upstream. Fault injection after a
facade's exact-schema validation may be needed to reach an intended transaction
boundary. Do not weaken that validation or silently relabel an earlier rejection.
