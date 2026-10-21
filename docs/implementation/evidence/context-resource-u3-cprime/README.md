# Context U3=C′ SQLite experiment evidence

**Current follow-up:** [semantic gaps and new reproduction](semantic-gaps/README.md).
Freeze descriptions below concern the original experiment. Check out
`e9aba86f4530b2e683c77e23a4fe58bdf02192c5` for those exact executable bytes.
Running the current branch executes the corrected candidate; original receipts
and independent review remain unchanged.

This directory contains disposable experimental schema changes, synthetic
fixtures, execution receipts and independent review. It is not product DDL or a
migration. Start with the [experiment report](../../context-resource-u3-cprime-experiment.md),
[fixed contract/source map](contract-and-source-map.md),
[baseline controls](baseline-contracts.md), and
[candidate construction](candidates/README.md).

## Reproduce

From a checkout of this experiment branch, run this single command:

```sh
sh docs/implementation/evidence/context-resource-u3-cprime/reproduction/reproduce.sh /tmp/u3-cprime-rerun
```

The driver runs the actual packaged baseline and the candidate on both a current
supported interpreter and exact-minimum SQLite 3.51.3. It refuses to write results
inside the checkout. No database survives the harness's disposable directories;
the output contains bounded text receipts, SQL and inventories. The optional
minimum-runtime build downloads the pinned official source archive, verifies its
SHA-256, and builds outside the repository. It does not alter installed Python,
project dependencies or the default runtime.

Environment prerequisites: POSIX shell, Git, Python >=3.12 with SQLite >=3.51.3
for the current lane, and dynamically linked `/usr/bin/python3` >=3.12 for the
minimum lane. If the minimum library is absent, the build additionally needs
network access to sqlite.org, curl, tar, make and a C compiler. Override
`U3_CURRENT_PYTHON`, `U3_MIN_PYTHON`, and absolute `U3_MIN_RUNTIME` paths when
necessary. The script asserts the actual minimum SQLite version; setting a
library path is not itself proof that Python loaded that version. This Linux
environment's default Python embeds SQLite, whereas `/usr/bin/python3` loads
the external library. The receipts record the actual source IDs/compile options.

For a single available supported runtime, run:

```sh
python docs/implementation/evidence/context-resource-u3-cprime/reproduction/run.py --output /tmp/u3-cprime-single-runtime
```

That command does not establish an exact-minimum pass unless its actual runtime
is 3.51.3. The baseline-only command is in [baseline-contracts.md](baseline-contracts.md).
All data is synthetic; no account or Provider API calls are required.

## Input and result binding

The product reference and freshly observed main are both
`efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` / tree
`117d580b31098ecb8287281bd843894fdfad71fc`.
[Source bindings](results/source-bindings.json) also pins audit #113 and design
#114; neither branch is a code dependency of this experiment.

The corrected executable freeze is commit
`e9aba86f4530b2e683c77e23a4fe58bdf02192c5`, tree
`7db7773f4cc2860b3818856b048a5832cdb00d6b`.
[Final input freeze](results/input-freeze-final.json) gives every executable input hash
and aggregate manifest SHA-256
`866c1a521bafac657aba63a6662ea46b3a12f36aa70b5643f4553c99cb837c96`.
The compiled candidate SQL SHA-256 is
`c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee`.
The [first freeze](results/input-freeze.json) at
`2f40e5262c6ccdb776b9f82fcba33d42c323a4e8` is retained as reviewed intermediate
evidence; its independent provenance/clock restrictions and Resource replay gap
are documented in the [first review](independent-review/round1-review.md).
The author ran those exact bytes before committing them; the receipts honestly
record the preceding freeze Git HEAD plus the changed-file hashes. Report-only follow-ups do
not imply a new runtime execution on their commit.

| Evidence | Scope |
| --- | --- |
| [Author current results](results/author-current-v4/results.json) / [inventory](results/author-current-v4/inventory.json) / [complete SQL](results/author-current-v4/candidate.sql) | Python 3.12.14, SQLite 3.53.1; 15 grouped cases, 163 recorded steps |
| [Author minimum results](results/author-minimum-v4/results.json) / [inventory](results/author-minimum-v4/inventory.json) / [complete SQL](results/author-minimum-v4/candidate.sql) | Python 3.13.5, SQLite 3.51.3; the same 15 grouped cases and 163 steps |
| [Baseline current](results/baseline-current.json) / [minimum](results/baseline-minimum.json) | Nine baseline controls on each runtime, separately counted |
| [Final independent review](independent-review/final-review.md) / [current](independent-review/final-current.json) / [minimum](independent-review/final-minimum.json) | 75 independent observations on each runtime, plus a separate repeat of the author driver; counts overlap and are not summed |
| [Second review](independent-review/round2-review.md) | Intermediate application-boundary gaps, preserved with their counterexamples and corrected in the final freeze |
| [Runtime/source receipts](results/baseline-runtime-build.json) | Source hash, compiler/build inputs, official SQLite documentation and failed setup attempts |
| [Development 01](results/development-01/results.json) | 10/12 grouped cases; test-fixture errors retained, not a successful matrix |
| [Development 02](results/development-02/results.json) / [failed inputs](results/development-02/inputs/) | 10/12; actual non-key support payload conflict bypass plus fixture error-precedence mismatch |
| [Development 03](results/development-03/results.json) | First corrected 12/12 run; later author runs include additional cases within the groups |

Collected and executed IDs are listed and reconciled in each candidate receipt.
SQL traces, real exceptions, transaction state, final rowsets and FK/integrity
checkpoints are retained. Expected rejection is a passing control, not an
accepted invalid row. The deliberately unsupported FK-disabled database has
recorded violations and is explicitly excluded from the clean-state claim.
No author, baseline, rerun or reviewer counts are added together as distinct
cases. The failed candidate was also [actually replayed](results/failed-replay-check.json)
from its retained snapshots. Instructions for replaying the failed candidate are in
[candidate construction](candidates/README.md#retained-failed-candidate).

## Boundaries

Typed Parent and exact support existence are real composite FK guarantees;
syntax/cardinality and endpoint declarations use row-local CHECK predicates;
immutability and original observation binding use triggers. Actual event type,
whole Transfer unit admission and arbitrary-length general-member referents
remain explicitly identified application obligations. External truth and a
winner among competing reports are not inferred. Experimental reconstruction
and SQLite snapshot copying are not product Exchange or paired recovery tests.

Product source, packaged DDL/fingerprints, dependencies, existing tests,
workflows, accepted ADRs and runtime defaults are unchanged. No real catalog,
Provider account, merge, deployment or activation is involved.
