# Disposable FS/WT instance value pilot

This bounded follow-on to PR-A tests **representation fidelity**, not a complete
instance validator or retained-catalog migration. No product files, DDL, runtime
requirements or required CI checks change. Run only the fixture generator: it has
no input database path, creates temporary databases and deletes them on exit.
Only its synthetic JSON and validation evidence are retained.

## Reproduce

Use the existing verified product environment, then the separate locked tool
Python described in README.md. No SQLite replacement or guard bypass is needed.

```sh
scripts/local-run.sh python tools/schema-model/instance_fixture.py > /tmp/instance.json
uv run --project tools/schema-model --locked --offline python \
  tools/schema-model/instance_model.py /tmp/instance.json /tmp/instance-result
INSTANCE_FIXTURE=/tmp/instance.json uv run --project tools/schema-model --locked --offline \
  python -m unittest discover -s tools/schema-model -p test_instance_model.py -q
```

Without INSTANCE_FIXTURE the optional suite explicitly skips, rather than using
system SQLite or silently constructing a fake product fixture. Do not interpret
that skip as product validation. Each new fixture has new random UUIDs, paths and
observation times. Determinism means the **same extracted input** produces the
same graph, not independently created observations have identical hashes.

## Precisely what is executed

The product producer initializes real Filesystem and Worktrees databases with
public APIs. It inserts two unfinished scans and four directory entries through
SQL on the disposable FS connection: empty root BLOB and non-UTF8 path BLOB in
each scan, huge positive native ns TEXT, negative ns TEXT and SQL NULL. This is
not scanner execution and makes no claim that an OS actually returned those
native times. Public FS verify/list/query checks those values. A fifth orphan
entry is rejected by SQLite's enabled physical FK. A separate disposable DB
accepts '+01' in SQLite but its public verifier rejects the native timestamp.

Worktrees discovery uses an actual new Git repository. The public reference API
records a syntactically valid external reference with no target FS database
supplied. WT verification accepts it. FS and WT databases close before read-only
extraction; each is read in a transaction. This is quiescent fixture extraction,
not an atomic cross-database snapshot facility. All 4 FS and 5 WT tables are
serialized, but only the declared subset has domain SHACL constraints.

Typed source cells preserve BLOB base64 plus length, SQL integer, text and NULL.
Each source row occurrence gets a distinct subject; semantic keys are separate.
Missing required projected fields are errors, never silently NULL. Original
records remain in graph literals. Optional external targets are always unresolved
in this pilot, even though an unrelated FS fixture exists; resolution is not
implemented. Native time canonical spelling is checked in Python using exact
integers, then preserved as RDF strings, not xsd:long or floating seconds.

The frozen shape closure has a separate digest manifest. Fixed fixture construction counts (not counts inferred from the graph) and
required table/target sets are checked before SHACL. Deliberate duplicate entry
rows remain distinct RDF subjects and fail the composite-key shape. Deliberate
orphan mutations of extracted JSON fail the parent shape. These two controls are
**synthetic graph counterexamples**, not claims that the public API admitted
invalid DB rows. Bad UUIDs, malformed encodings or missing extraction are
undetermined input-admission results, distinct from SHACL data failures.

## Added value and cost

Existing pytest already verifies non-UTF8 paths, independent FS references and
product constraints (see tests/filesystem/test_filesystem.py and
 tests/worktrees/test_worktrees.py). This pilot does not discover new product
coverage there. Its added value is exposing loss at the SQL→typed JSON→RDF
boundary, preserving duplicate occurrences, and testing the independent selected
SHACL constraints against intentional mutations. It lets agents consume explicit
representation and unresolved-reference evidence without pretending a single
PASS certifies the product.

The cost is a second small set of domain rules and a fixed fixture/shape contract.
SQL/API remains authoritative. A domain change requires reviewing extraction,
projection, shapes and controls together. Expansion is justified only if these
cross-representation regressions are useful; this pilot does not warrant a new
mandatory CI gate or a general ontology. It deliberately does not implement the
entire encoding-contract.json, arbitrary database extraction, terminal outcome
fixtures, external-target resolution, general UUID/path/hash semantics, all WT
physical FKs, OWL, concurrent transitions, scanner race checks or full pytest.

Scan/worktree key collisions are rejected by Python before reference linking;
they cannot silently collapse in the lookup dictionaries. OutcomeShape has zero
selected targets here, reported as not_applicable; terminal behavior has not
been exercised. The receipt counts the one completed checker invocation, not
individual engine evaluation sites.

Result family data_conformance covers only the submitted graph's selected
constraints. The other three families remain not_run; executed API assertions
and control-suite success are separate evidence, not proof of all operations.
Imported FS/WT Python source bytes are checked against the recorded HEAD; this
is not authentication of the whole interpreter or all transitive dependencies.
Exact source commit/tree, producer/code/shape/lock/input hashes and actual
Python/SQLite/SHACL versions are recorded. A digest is not authentication.

## Common result receipts

Every `result.json`, including input-admission failures, is validated against
[`result.schema.json`](result.schema.json). All four families have a status,
scope and reason. Definitive data results include source, tool, digest, coverage,
constraint, unformalized-scope and fixture-expectation fields. `fixture_expectation`
is null for an ordinary invocation; a negative control passing its test does not
change the submitted graph's `data_conformance=fail`.

Expected shape targets come from the producer's fixture counts; selected targets
come from the graph. `checker_invocations_completed` counts returned child checker
invocations with a supported definitive pass/fail report, matching the structural
runner. An unsuccessful exit or unusable report completes no supported check;
the process's `checker_returncode` is separate evidence. Unavailable checkers and
timeouts also complete no check, and all internal engine evaluation counts remain null. Constraint
records describe selected coverage; the combined verdict is not falsely copied
into separate per-constraint verdicts. Outcome targets remain explicitly
not_applicable for these incomplete scans.

Raw stdout/stderr are saved separately as `engine.stdout` and `engine.stderr`;
parseable worker reports are retained in `engine.json`. Timeout diagnostics retain
any bytes actually returned. The normalized family reason does not replace these
raw diagnostics. Use a fresh output directory for each invocation.

Malformed JSON (including nonfinite numeric constants), unreadable input paths
and invalid input objects emit an
`undetermined` receipt and exit 2 whenever the requested output can be written.
Missing identities or runtime data are not synthesized. The optional `--timeout`
argument accepts a finite duration in `(0,600]` seconds; malformed timeout text
also emits a failure receipt when input/output paths are supplied. Receipt
serialization rejects non-JSON values rather than copying them from rejected
producer metadata. As before, a conforming
graph exits 0 and detected nonconformance exits 1; none of these statuses evaluates
the other three result families.

`source` retains producer-supplied source commit/tree, producer digest, loaded
Python/SQLite identity, imported-product source bindings, declared scope and
expected extraction counts. `tool` identifies the runner checkout's commit/tree
and dirty status. `digests` binds the exact retained `source-input.json`, graph,
runner/worker/producer code, shape manifest, common result schema and lock inputs.
These are consistency/provenance claims, not authentication of the producer.

## F1-A: terminal outcome profile

The default `values` profile above remains the original representation pilot.
The additive `filesystem-outcomes-v1` profile retains its two unfinished scans
and adds real `scan()` complete, missing-root partial and controlled-interruption
witnesses. It also adds a SQL-only zero-entry partial witness; that case is not
scanner execution. The profile has six FS scans, eight entries and four outcomes.

```sh
scripts/local-run.sh python tools/schema-model/instance_fixture.py \
  --profile filesystem-outcomes-v1 > /tmp/outcomes.json
uv run --project tools/schema-model --locked --offline python \
  tools/schema-model/instance_model.py /tmp/outcomes.json /tmp/outcomes-result
OUTCOME_FIXTURE=/tmp/outcomes.json uv run --project tools/schema-model --locked --offline \
  python -m unittest discover -s tools/schema-model -p test_outcome_model.py -q
```

Construction counts and qualified scenario identities are checked before RDF
coverage. Missing required outcome occurrences are not legitimate zero-target
coverage for this profile. The original unfinished scans remain legitimate.
Selected shapes check terminal enum, positive finish time, same-scan counts,
SQL non-NULL error presence (including empty error strings), and complete-with-error
contradictions. `partial` does not imply a positive error count. Clock ordering
and atomic filesystem snapshots are not asserted. Original bytes, native times,
NULL and row occurrences retain the existing encoding.

The producer separately demonstrates SQLite rejection of invalid status and API
rejection of inconsistent counts/complete-with-errors, with guards enabled.
Counterexamples in `test_outcome_model.py` are mutations of extracted JSON, not
claims that public scan() admitted invalid observations. Existing result families
and raw diagnostics are unchanged; these tests do not evaluate a state model,
external-reference resolution, hash-state semantics or full implementation proof.
The producer helper is checked against HEAD and hashed separately; source hashes
are consistency bindings, not authentication. Use fresh output directories.

## F1-B: hash-state profile

`--profile filesystem-hash-v1` extends F1-A with real changed-during-read and
controlled read-error scans. Both retain no successful digest; enumeration and
hashing completion remain distinct. Three additional SQL-only rows cover a link,
a special entry and a complete file entry with a non-NULL error. These last rows
are DDL/API boundary witnesses, not claims of scanner execution. The fixed
profile contains nine FS scans, fifteen entries and seven outcomes, with all
five file kinds and all four persisted hash states selected.

```sh
scripts/local-run.sh python tools/schema-model/instance_fixture.py \
  --profile filesystem-hash-v1 > /tmp/hashes.json
uv run --project tools/schema-model --locked --offline python \
  tools/schema-model/instance_model.py /tmp/hashes.json /tmp/hashes-result
HASH_FIXTURE=/tmp/hashes.json uv run --project tools/schema-model --locked --offline \
  python -m unittest discover -s tools/schema-model -p test_hash_model.py -q
```

All profiles now project required kind, hash status, size and digest cells.
Selected SHACL tuple rules follow the current SQLite kind/state relationships:
only complete regular files have digests; files have a known nonnegative size;
failed/changed hashing has a non-NULL reason. The separate exact digest lexical
rule requires exactly 64 lowercase ASCII hexadecimal characters. The current
product DDL counts encoded bytes and explicitly rejects embedded NUL; the
selected SQL and graph controls therefore agree on these malformed values.
This is not general SQL equivalence or real-byte verification. Empty error text
is not NULL. Unknown is a file kind, not a hash state. Pending is not persisted.
Non-file size is not universally forbidden, and a complete entry may carry an
error, but the enclosing scan cannot claim complete while errors exist.

The positive hash profile checks fixed construction counts, state/kind coverage
and qualified case occurrences before graph generation. Each declared case name
must identify its required kind/state/size/digest/error tuple, including the
empty-error and non-file-size boundary witnesses. Swapping case identities or
removing a boundary cannot preserve positive-profile coverage merely because
aggregate counts are unchanged. These are fixed fixture requirements, not extra
universal catalog constraints. Synthetic negative tests
use the existing `values` projection profile with explicit synthetic scope, so
they do not simultaneously claim to be a complete set of positive hash witnesses.
The same shapes apply to every profile. Missing required extraction is still
undetermined; a correctly rejected counterexample has data_conformance=fail.

Fourteen SQLite invalid-tuple controls run with guards enabled. Explicit
length constraints reject a trailing newline even when the pattern engine
accepts its end anchor before that newline.

Three separately recorded SQL-only controls attempt 64 lowercase hex
characters followed by NUL, NUL plus `invalid`, and an interior NUL within
exactly 64 encoded bytes. The current product DDL rejects all three through
its encoded-byte-length, explicit NUL exclusion and lowercase-hex checks.
The producer retains the attempted full TEXT and UTF-8 encoding, SQLite's
text-length result, the actual CHECK rejection and a separate public verifier
check of the unaffected catalog in `api.hash_sqlite_nul_rejections`.
Paired synthetic graph controls independently require
`data_conformance=fail`; these attempted values are not scanner traces,
admitted entries or positive-profile witnesses.

Before this product fix, F1-B independently observed that SQLite `length()`
and `GLOB` admitted NUL-suffixed values while strict SHACL rejected them.
The original raw differential evidence and source identities remain frozen
under `review-evidence/f1-review-20261111/`; they document historical
behavior, not current admission or new executions. The current SQL-side
controls now require rejection without weakening the SHACL rule.

The actual empty
file digest is separately checked against known bytes. A syntactically valid but
incorrect digest deliberately passes the shape-only control: graph conformance
is not a real-byte equality proof. No general SQL/trigger proof, external target
resolution, atomic snapshot, exhaustive race verification, operation-state model,
retained-catalog checking or mandatory CI gate is introduced. Both helper sources
are checked against committed HEAD and retained in producer digest bindings.
