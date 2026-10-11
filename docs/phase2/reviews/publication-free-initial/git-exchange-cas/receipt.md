# Independent scope 3 partial review receipt

Frozen source: `/workspace/reviews/publication-free-git-exchange-cas`.

- Commit: `41dbe5550afaac248971d13994ae4a8c37274197`.
- Tree: `1a518382d4aefdbea1441cf0ae9965b7025b40bd`.
- Comparison baseline: `0bd5704caca2f6e3723bef22531b065cd4d7bad0`.
- Interpreter: Python 3.12.14; SQLite 3.53.1.
- Executed scripts verified `repo_catalog.__file__` as `/workspace/reviews/publication-free-git-exchange-cas/src/repo_catalog/__init__.py`.
- Independent reviewer did not author the implementation. Model/effort are not exposed by the available tool results.
- Only disposable in-memory catalogs were mutated. Production code, retained catalogs, and Git history were not edited. No authenticated collection or external target was used.

## Finding 1: selected collection export scans unrelated same-scope claim history

`src/repo_catalog/adapters/sqlite/exchange.py:912` retrieves all `coverage_claims` for each matching coverage scope. Lines 918–923 filter them by completion-marker UUIDs inside advisory JSON. The scope index does not index this marker dependency.

The independent `selected_coverage_scale.py` retains a selected complete collection and its complete claim, then admits 1,000 and 5,000 valid unrelated later partial claims in that same coverage scope. The selected output remains identical at 14 records and 302 executed statements, but exact SQLite VM steps increase:

| Unrelated claims | VM steps |
| --- | ---: |
| 0 | 10,102 |
| 1,000 | 19,055 |
| 5,000 | 55,055 |

`EXPLAIN QUERY PLAN` reports `SEARCH coverage_claims USING INDEX coverage_claims_fk_0 (coverage_scope_id=?)`; every row in the scope still participates. This is a deterministic work counter, not a concurrent wall-time comparison. One controlled workload ran at a time.

The existing selected growth test in `tests/integration/test_phase1_exchange_scaling.py` seeds collections/code/Git/current members but omits this claim-history dimension. A typed indexed claim-to-marker dependency can address the gap without recreating a generic Publication owner. No provider-trust or absence-deletion decision is implied.

Artifacts: `selected_coverage_scale.py`, `selected_coverage_scale.json`.

## Finding 2: canonical wide tree can be represented by one malformed row yet appear available

`src/repo_catalog/resources/git_facts.sql:36` defines `available_git_objects`; its tree branch at line 50 checks row count, summed byte length, contiguous offsets, mode and reconstructed bytes. It does not reject embedded NUL bytes in `tree_entries.raw_name`. `src/repo_catalog/resources/git_domain.sql` permits any nonempty blob for that name.

The independent `intrinsic_tree_spoof.py` constructs genuine canonical SHA-1 and SHA-256 raw tree bodies with 2 and 2,048 entries, then inserts only one intrinsic entry. Its malformed `raw_name` embeds the intervening NUL/OID/entry bytes, `entry_count` is 1, and `entry_length` is the whole body's size. All inserts use the composed production DDL without removing triggers or disabling foreign keys. The raw payload digest, canonical tree OID and declared size are valid.

For all four cases, `available_git_objects` returns 1; `PRAGMA foreign_key_check` returns an empty list and `PRAGMA integrity_check` returns `ok`. The full `verify_git_object_structure` rejects each case with `GIT_OBJECT_STRUCTURE: Stored intrinsic relation contradicts canonical Git bytes`.

Thus ordinary availability is weaker than the canonical structure contract: a count/size-spoofed partial intrinsic representation becomes visible before a full check. The normal canonical installer itself was inspected but was not demonstrated to produce these malformed rows. This finding concerns the schema/availability guard, not a claim that normal installation leaks this shape.

Artifacts: `intrinsic_tree_spoof.py`, `intrinsic_tree_spoof.json`.

## Reproduction commands

Run from the frozen worktree, sequentially:

```bash
cd /workspace/reviews/publication-free-git-exchange-cas
git rev-parse HEAD HEAD^{tree}
PYTHONPATH=/workspace/reviews/publication-free-git-exchange-cas/src:/workspace/reviews/publication-free-git-exchange-cas PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/git-exchange-cas/selected_coverage_scale.py
PYTHONPATH=/workspace/reviews/publication-free-git-exchange-cas/src:/workspace/reviews/publication-free-git-exchange-cas PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/git-exchange-cas/intrinsic_tree_spoof.py
```

An initial interpreter discovery command without the required `PYTHONPATH` resolved the shared checkout. No test or conclusion used that import; both executed probes used the frozen source as shown above.

## Covered and outstanding scope

Read root and Phase 2 `AGENTS.md`; reviewed the accepted decision register and implementation handoff. Design, ADR, implementation prompt and test disposition were requested/read in output that included truncation, so this receipt does **not** certify complete full-document consumption. Inspected the baseline diff summary, the Git intrinsic schema and parser/installer/verifier, Exchange vocabulary/admission/dependency authorization/selected export/promotion, coverage writer, and relevant existing selected-scale/Git/Exchange/CAS test definitions. The full implementation diff, schema-map and full test-disposition reconciliation were not completed.

Independently **executed** only the two probes above. No repository pytest suite, build, isolated package verification, Git crash/decoder/head-role counterexample, Exchange roundtrip/late/foreign/staged/reverse/onward counterexample, acquisition closure/list-ID check, backup/restore/CAS-41 probe, Source graph probe, selected-volume benchmark or snapshot concurrency probe was executed by this reviewer. Source inspection of those areas does not substitute for execution.

The review received repeated/restarted parent task instructions and was redirected to write this partial receipt before the remaining requested verification. These interrupted review attempts are disclosed; there is no scope 3 signoff or final acceptance. The two findings require correction and exact corrected-tree re-review, and remaining scope requires fresh independent verification.
