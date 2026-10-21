# Semantic-gap experiment evidence

Start with the [three-gap report](../../../context-resource-u3-cprime-semantic-gaps.md).
This extends the original experiment without rewriting old receipts or accepted
architecture. All fixtures are synthetic.

## Reproduce

```sh
sh docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/reproduce.sh /tmp/cprime-gaps-rerun
```

Use detached executable freeze `9eeacb28f7e4a426114a9ce40e2324b4da302817` for exact
reproduction. [Prerequisites/runtime overrides](../README.md#reproduce) apply.
The wrapper runs baseline controls, all earlier author scenarios and the focused
[probe](probe.py) on actual SQLite 3.53.1 (this environment) and 3.51.3. Output
must be outside the repository. Setup verifies the official archive hash, without
spoofing runtime checks or changing project dependencies.

| Evidence | Meaning |
| --- | --- |
| [input-freeze.json](input-freeze.json) | Exact candidate/harness/source hashes and composed SQL hash |
| [author current](results/corrected-author/current/results.json), [minimum](results/corrected-author/minimum/results.json) | 15 prior groups / 163 steps each, with explicit encoding and structural-only T06 I8 diagnostic |
| [focused current](results/corrected-author/focused-current/results.json), [minimum](results/corrected-author/focused-minimum/results.json) | Three gap groups / 46 steps each; SQL errors, transaction traces, vectors and rowsets |
| [baseline current](results/corrected-author/baseline-current.json), [minimum](results/corrected-author/baseline-minimum.json) | Nine packaged-baseline controls each |
| [original current](results/original-current/results.json), [minimum](results/original-minimum/results.json) | Original-candidate defects reproduced; expected defects are not corrected successes |
| [original probe](results/original-probe.py) | Exact author counterexample script before correction |
| [development failure](results/development-01/results.json) | 14/15 groups: T08 incorrectly bound eight SELECT columns into seven writable columns after adding a generated projection |
| [development inputs](results/development-01/inputs/reproduction/run.py) | Failed harness; neighboring candidate/reproduction files retain its other exact inputs |
| [independent final review](independent-review/final-review.md) | Separate frozen reruns and independently authored cases |
| [independent source review](independent-review/semantic-source-review.md) | Accepted/proposed contract interpretation and precise G3 question |

The development fixture was corrected to select seven writable Resource columns
explicitly; no constraint was relaxed. Its failure is preserved. Receipts contain
runtime source IDs/options/pragmas and actual errors. Supported-state checkpoints
are clean; intentional misconfiguration controls retain their violations.

To reproduce original author counterexamples, create a separate checkout at
`22b58ce7ff59478f1a4c8c8ef89b17d2f0068590`, place preserved `original-probe.py` at
`docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/probe.py`
there, and run it with `--output /tmp/original-gaps`. Do not overlay the corrected
checkout. Its G1 refusals and G3 admission are historical results. Receipt script
and input hashes identify exactly what ran.

## Suggested reusable skill addition, not policy

When comparing reversible identity encoders, prove each separately and test
their union: `F(V)=N(J(V))` may alias different native identities even though each
encoder is injective. Select one explicit format; reject the alternative against
the same semantic coordinates. Never infer native-contract truth from JSON shape.
Pair positive global/composite identities with missing known-contract negatives
and explicit no-fallback admission. Bind receipts to exact encoder/fixture bytes.
Do not use this procedure to settle unresolved identity or qualification policy.
