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
