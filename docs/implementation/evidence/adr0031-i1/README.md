# ADR 0031 I1 execution and review evidence

See the [implementation report](../../adr0031-i1-canonical-resource-identity.md)
for scope, APIs, boundaries, outcomes, deferred failures and stage limitations.
Files here preserve actual execution receipts; paths/commands in raw receipts
describe the original environment rather than a portable installed product.

- `boundary-audit.json`: frozen production constructor/factory/decoder inventory.
- `codec-review/`: non-author I1a review, exact independently authored script,
  actual runtime observations, original manifest and losslessly compressed
  pytest logs/JUnit. The script text is unchanged; its `.py.txt` suffix denotes
  a preserved executable input, not production code.
- `integration-review/`: non-author I1b review, exact reproduction script,
  runtime observations and frozen source hashes.
- `author/summary.json`: final nine-module collection/execution counts and
  reconciliation on both genuine SQLite runtimes. All 564 cases execute per
  runtime; 561 pass and three deferred-I2 cases fail. No skips or xfails.
- `author/receipts.tar.gz`: complete author raw receipts, including the aborted
  instrumentation attempt, original logs, JUnit, journals, selected/executed
  node IDs, commands/exits and metadata. Its 48 indexed raw files are verified
  by `author/receipt-manifest.json`; archive SHA-256 is
  `77ac439f7aaae6054a2da1928a722fe0baf7275d9fb4f3c7525f306ee64fbf67`.
- `author/*-sql-runtime.json`: actual version/source ID, connection pragmas,
  compile options and all 37 disposable comparison-case IDs. These record
  execution; JUnit/journal supplies pass/failure outcomes.
- `author/*production-smoke*`: additional existing packaged scalar/scoped
  ContextStore controls; no generalized production DDL claim.
- `i1a-development-ci.zip` and `i1a-ci-summary.json`: actual hosted bounded
  receipt and verified binding/index. Hosted runtime pytest/distribution stages
  were skipped; local supported-runtime evidence remains separate.

The author execution freeze `e0e5c0ed37ac9d6c860db185415616c60161b30d`
and published implementation `174880c113fcd37dad14a8083e85e987a32ae7c6`
have identical tree `b6484a7185e9f410a8d05ff5bd4fa574e6dc45e2` and the
same exact I1a parent. Publication commit metadata differs; frozen runtime/test
input hashes do not. Later docs-only commits add receipts and reporting.

## Reproduce focused observations

Select actual interpreters and independently query `sqlite_version()` and
`sqlite_source_id()` before assigning a runtime label. The historical builder
`../context-resource-design/g3-a/build-minimum.sh` can provision the minimum
library without editing old evidence. Its dynamic library only changes a
Python that dynamically links SQLite; it does not replace an embedded runtime.
Do not spoof version strings or treat a skipped case as executed.

From a checkout with pytest/dependencies installed, the full recorded cohort is:

```sh
python -m pytest tests/unit/test_resource_identity.py tests/unit/test_resource_key_identity.py tests/unit/test_github_identity_boundaries.py tests/integration/p1/test_resource_identity_sql.py tests/integration/p1/test_context.py tests/integration/p1/test_context_relations.py tests/integration/p1/test_coverage.py tests/integration/i2/test_provider_intake.py tests/integration/i3/test_selective_exchange.py -q
```

Expect the three reported I2 failures until those later production constraints
are implemented. The author `run_validation.py.txt` and work-only event journal
are exact recorded instrumentation inputs. They retain original paths/freeze;
adapt those selectors explicitly for another workspace rather than interpreting
historical paths as installed API. The event journal captures its JSON serializer
before codec tests temporarily replace the shared module attribute.

For the unchanged independently authored codec script, create
`work/i1a-review-tree` at published I1a and copy `counterexamples.py.txt` into
`work/i1a-independent/counterexamples.py`; it imports that sibling frozen tree.
Run it with each genuine interpreter. For the independent integration script,
create a detached worktree at published I1b implementation, then run:

```sh
python docs/implementation/evidence/adr0031-i1/integration-review/reproduce.py.txt work/i1b-review-result.json 3.53.1 work/i1b-review-tree
```

Use the actual expected runtime as argument two (for example `3.51.3` with the
minimum interpreter). All SQL files/databases are disposable test data. These
commands neither implement later stages nor authorize product activation,
live Provider operations, real catalog changes, release or merge.
