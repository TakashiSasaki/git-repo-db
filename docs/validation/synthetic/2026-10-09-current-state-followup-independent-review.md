# Current-state follow-up independent review

Baseline: PR #13, `db3a5ecfbf95b4c1318198aa308ca6dc749876a1`. The reviewed follow-up is an
uncommitted Schema 15 worktree. This receipt binds the exact inspected
source, complete packaged DDL, tests and packaged parser certificate by SHA-256;
it does not identify a submitted PR HEAD or hosted acceptance.

**Scoped verdict: passed.** No remaining reproduced defect was found in the
inspected current-resource follow-up scope after the corrections below.

## Final executed evidence

- **107 passed, zero failures/errors/skips**, in 46.21 seconds: 64 new adversarial
  cases and 43 existing independent-review cases.
- Python 3.12.14 / SQLite 3.53.1. All catalogs were disposable synthetic data.
- The final command explicitly removed `REPO_CATALOG_TEST_BOOTSTRAP` and used the
  genuine packaged parser certificate. Source/test/certificate hashes were unchanged
  before and after execution.
- Complete packaged DDL SHA-256:
  `20ec2e5c3b2fe7a064aa4e9a122d6b452d0f6b1a5be00113ce1dbd948f8f3826`.
- Packaged parser verification SHA-256:
  `d60e33e92facfcfb6a55103ea553b01f5180410f7a2f0fa8304498b27a054293`.
- Generated JSON guards equal the packaged SQL. Ruff, formatting and whitespace
  checks passed.

```sh
env -u REPO_CATALOG_TEST_BOOTSTRAP uv run --no-sync pytest \
  tests/integration/test_current_followup_adversarial.py \
  tests/integration/test_current_state_independent_review.py \
  -q --tb=short \
  --junitxml=/tmp/git-repo-db-followup-independent/final-independent.xml
```

The [machine-readable receipt](2026-10-09-current-state-followup-independent-review.json)
contains every executed testcase identity, exact inspected file hashes, JUnit
byte hash, runtime and scope limits. Test definitions are in
[test_current_followup_adversarial.py](../../../tests/integration/test_current_followup_adversarial.py)
and [test_current_state_independent_review.py](../../../tests/integration/test_current_state_independent_review.py).

## Behaviors checked

The production DDL, real admission and `Graph.receive` were exercised for sparse/full
ordering, older field filling, nested metadata contradictions and scalar replacement,
partial live responses against unseen body conflicts, staged per-field evidence
strengthening with another unresolved variant, receiver-local check times and
transferred field provenance. Admission and direct-SQL attacks checked canonical
knowledge paths, ancestor proofs, review capture ownership, profile capabilities and
signed int64 evidence times. Four malformed Graph timestamp variants retained an
invalid diagnostic while admitting an independent valid sibling.

## Additional counterexamples and corrections

The independent review reproduced six additional boundary defects before correction:

1. Replacing a tied nested metadata object with a newer scalar carried invalid old
   descendant proofs into pre-merge validation and could not dominate obsolete paths.
2. Review field capture could point to another PR or repository.
3. Field attribution could use an existing profile without the resource capability.
4. A leaf-only metadata proof bypassed a newer scalar ancestor and changed its shape
   through admission and exchange.
5. SQL accepted out-of-int64 JSON integer time tokens that SQLite extracted as REAL.
6. Invalid field times escaped as `TypeError`/`ValueError` during exchange and rolled
   back an independent valid sibling.

Each is covered by executable regressions and passed in the final run. The last two
were found after earlier green focused runs; those runs are superseded by this final
source-bound receipt. No green count was used to suppress a reproduced counterexample.

## Limits

This agent changed tests and these new receipts only. Production corrections and
certificate generation were performed by their respective owners. Complete ordinary
acceptance, packaging, live acquisition, performance and hosted CI were not executed
by this agent and require their own receipts. These 107 cases are part of any full
suite that includes them; the existing 43 must not be counted twice. Historical
validation receipts were not edited.
