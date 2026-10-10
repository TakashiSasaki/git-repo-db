# Reviewer C — original PR #20 Exchange findings

This is the independent Exchange review against the initial PR #20 revision, before corrective integration. It records the defects and measurements found at that revision; a separate corrected review covers the later integrated state.

## Source identity and evidence

- Initial PR #20 HEAD: `f9bff8b2dc17ddffd6b3f7662791022f25175c44` (feature tree checkpoint `319738f3586240c80d5fa4d6d5fab3099352a7ff`).
- Comparison baseline: original `main` at `47fd5b88355b98019c0c04408449081e16ab4505` (tree `e7a41038e26eb93c89b921a9a9d0bf1d2c54a310`). These are different revisions; all defect repros below refer to initial PR #20.
- Preserved source snapshots: [initial PR #20 exchange.py](https://github.com/TakashiSasaki/git-repo-db/blob/f9bff8b2dc17ddffd6b3f7662791022f25175c44/src/repo_catalog/adapters/sqlite/exchange.py), SHA-256 `7fd55a03c001441358c14148459efd395958f0227bf4c8262becf3c1cf26431a`; [original main exchange.py](https://github.com/TakashiSasaki/git-repo-db/blob/47fd5b88355b98019c0c04408449081e16ab4505/src/repo_catalog/adapters/sqlite/exchange.py), SHA-256 `de34f1058d1cce1c80821d6faa0c4b4b966deac2ead21fc9ec38f472ecb1fe46`.
- Preserved synthetic benchmark scripts: [repository export scan](exchange-performance.md#original-harnesses), [reverse-order Git-object promotion](exchange-performance.md#original-harnesses), and [admission-context scan](exchange-performance.md#original-harnesses).
- Review context: relevant retirement ADR and implementation docs were read. Source inspection was against the exact initial PR #20 commit above. No edits were made by this reviewer to tracked files.

## Finding 1 — invalid domain evidence can authorize rejected API originals

**Severity: High. Affected paths:** `Graph.original_root`, `required_original_keys`, `receive`, `_admit`, `_promote` in the initial PR #20 `exchange.py` (notably `original_root` around lines 342–388).

**Reproduction A: fake terminal-complete marker.** Using the existing `catalog()` and `fixture(src)` helpers from `tests/integration/test_catalog3_exchange.py`, take a fixture with a real API fetch occurrence. Construct an otherwise normal exchange unit containing the repository identity/binding records and that fetch's `fetch_occurrences`, `payloads`, and `stored_bytes`. Add a `completion_markers` record whose `asserted_state` is `complete` and whose evidence is:

```json
{"terminal":true,"fetch_occurrence_uuidv4s":["<the fixture fetch UUID>"]}
```

Use the fixture's real resume scope and fetch collection, but do not include a valid completeness proof. In the observed repro, `proof_requirements("completion_markers", marker)` returned `None`; nevertheless the marker passed `original_root`, and `required_original_keys` selected six carrier keys including the API bytes. `Graph(dst).receive(unit)` returned `received_records=12`, `rejected_records=0`, `admitted_records=11`, `staged_records=1`. The target retained one `stored_bytes` row and one fetch occurrence; the fake marker itself was staged with `missing_completeness_proof`.

**Expected result:** the invalid marker must not authorize original API bytes. A valid independently admitted domain/proof root may retain its necessary dependency closure; this marker is not one.

**Reproduction B: inconsistent publication manifest.** Start from `Graph(src).export(repo)` for the same style of fixture. Mutate the `parsed_result_publications.fact_manifest_json` value to `[ {"table":"document_observations","key":["missing-observation-uuid"]} ]`, and remove the corresponding `document_observations` record from the unit. The publication passed `original_root`, while admission later staged it with `constraint:parsed output fact manifest incomplete or inconsistent`. The target still admitted one API `stored_bytes` row and fetch occurrence, but no observation or publication.

**Reproduction C: rejected malformed domain record.** Start with a valid fixture export, mutate a `document_observations.values.deleted` value to `2`, and remove its publication/selection records. Structural exchange validation allowed the candidate; SQLite rejected it with `CHECK constraint failed: deleted IN (0,1)`. `receive()` returned `received_records=21`, `rejected_records=0`, `admitted_records=20`, `staged_records=1`; the target nevertheless retained one API `stored_bytes` row and fetch occurrence while no document observation was admitted.

**Root cause / invariant:** `original_root` classified broad domain-fact shapes as roots before successful semantic/SQL admission. `required_original_keys` then authorized API `fetch_occurrences`/`payloads`/`stored_bytes` based on those roots before `_admit` knew whether the domain candidate was valid. This violates Phase 1 R4/R6: rejected API input cannot persist as raw originals or delayed-retry material. It also lets advisory or malformed evidence grant retention.

**Correction direction:** derive original dependency authorization from a successfully validated domain proof/root, with validation over the combined incumbent plus incoming record overlay so valid out-of-order dependencies still stage and promote. Never let envelope `requires` or a structurally plausible but rejected fact authorize API bytes. Keep actual proven historical terminal/304 and publication dependencies that remain required by the retained domain path.

**Fake-marker follow-up for integration:** the minimal unit is the ordinary fixture repository/fetch carrier closure plus the single invalid marker shown above; it exercises the exact receive path rather than inserting into private in-memory state. Filtering roots to markers for which `proof_requirements` returns valid requirements should reject this fake marker. Existing valid historical terminal/304 tests pass on initial PR #20 under the existing broad implementation (the focused suite below includes them). I did not execute a modified implementation. Source-level expectation is that those tests remain valid if the filter computes proof requirements against the source/current-plus-incoming overlay; a receiver-only lookup that cannot see delayed dependencies could incorrectly stop valid out-of-order proof staging, so that distinction requires regression coverage.

## Finding 2 — repository-scoped export/promotion performs global scans

**Severity: Medium (material scalability regression). Affected paths:** `local_original_context` around lines 501–595; `original_intake_context` around lines 597–603; repeated promotion calls from `_promote` around lines 2872–2900.

`local_original_context(repository_uuidv4=...)` still materializes all rows from `git_object_payloads` and traverses related payload and byte data, even when exporting one unrelated repository. `original_intake_context` selects and parses every `exchange_admissions.record_json` without narrowing to the selected repository. `_promote` reconstructs this context on promotion passes, repeating the scans.

**Synthetic export reproducer:** create one selected empty repository and N unrelated valid Git blob objects, each with a `git_object_payloads`, `payloads`, and `stored_bytes` row. Export only the empty repository. The exported unit remains one record, but PR #20 scans scale with all unrelated Git objects.

**Recorded results:**

| Revision | Unrelated Git objects | Elapsed | SQLite trace statements | Python `tracemalloc` peak | Export records |
|---|---:|---:|---:|---:|---:|
| Initial PR #20 `f9bff8b` | 1,000 | 0.6361 s | 10,365 | 7.37 MiB | 1 |
| Initial PR #20 `f9bff8b` | 5,000 | 3.2346 s | 50,365 | 35.90 MiB | 1 |
| Original main `47fd5b8` | 1,000 | 0.0479 s | 205 | 4.63 MiB | 1 |
| Original main `47fd5b8` | 5,000 | 0.0203 s | 205 | 0.59 MiB | 1 |

Main timing/peak values at these small sizes vary with allocator/cache state; the stable evidence is that main used 205 traced statements in both runs while PR #20 used roughly 10 statements per unrelated object and retained per-object Python memory.

**Synthetic promotion reproducer:** construct N legitimate SHA-1 Git blob objects with stored bytes and Git descriptors; send the valid dependency closure in reverse logical order (`git_object_payloads`, `payloads`, `git_objects`, `stored_bytes`) to exercise durable staging and promotion. At N=5,000, the unit has 20,001 records.

| Revision | Elapsed | SQLite trace statements | Admitted | `local_original_context` calls |
|---|---:|---:|---:|---:|
| Initial PR #20 `f9bff8b` | 3.3281 s | 436,039 | 20,001 | 4 |
| Original main `47fd5b8` | 2.1711 s | 420,250 | 20,001 | not applicable |

The uninstrumented PR #20 timing was 3.5064 s with the same 436,039 statements and admitted count. Main has no new original-context method; the comparison harness omits that instrumentation when the method is absent.

**Admission-context reproducer:** prepopulate a fresh catalog with N legitimate unrelated repository admission receipts, then call `original_intake_context(repository_uuidv4=selected)` and `required_original_keys` for an empty selected repository.

| Initial PR #20 receipts | Elapsed | SQLite trace statements | Python peak | Context rows parsed | Required keys |
|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.1114 s | 21 | 12.97 MiB | 10,000 | 0 |
| 50,000 | 0.7337 s | 21 | 64.87 MiB | 50,000 | 0 |

**Root cause / correction direction:** closure/context builders scan and materialize all candidate state before applying repository scope, and repeated promotion reconstructs the same context. Scope candidate Git roots/closure to the requested repository, filter receipts before JSON parsing, and reuse a validated context across promotion passes with invalidation when relevant state changes. Keep valid late Git delivery and missing-dependency staging; do not solve cost by dropping domain evidence or changing retention/completeness policy.

## Verification and environment

- Environment recorded: Python 3.12.14, in-memory SQLite synthetic catalogs initialized from the revision's production `schema_sql()`. Synthetic data was prepopulated before timing/tracing. Timers use `time.perf_counter`; memory is Python allocation peak via `tracemalloc`; SQL counts use `sqlite3.Connection.set_trace_callback` (statement trace count, not VM-step count). SQLite runtime version was not separately recorded.
- Focused existing suite command: `uv run --no-sync pytest -q tests/integration/test_catalog3_exchange.py tests/integration/test_catalog3_selective_exchange.py tests/integration/test_catalog3_exchange_integrity_audit.py tests/integration/test_phase1_exchange_retirement.py tests/integration/test_catalog3_current_exchange.py tests/integration/test_current_exchange_followup.py` — **110 passed in 56.67 s** against initial PR #20. This is not a full acceptance run and does not cover the attacks above; those were separate adversarial repros.
- The synthetic benchmark programs are reproduced in the performance appendix; immutable source snapshots are available at the Git commit links above. The benchmark values above are the results recorded during the original review; no new test or benchmark run was performed while preserving this evidence.
