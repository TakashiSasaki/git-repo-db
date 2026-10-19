# Independent read-only ADR 0030 I4 review

Reviewed corrected remote feature HEAD `f948cc6c764689154734f6386a10f97db6923e7a`, tree `0dd55440469be7bb1a2d341ef9c2bc6419f631b0`, branch `impl/adr-0030-i4-query-search-backup-20261019`. Direct `git ls-remote` matched the pushed head; local object tree matched. Base is PR #110 `8519056d5b9484eb0cc4dcf9f693285b4e65518a`, tree `a77503505127367e9378c57c5ab9ee9ae11767f3`.

The reviewer made no repository, branch or GitHub changes. Source was exported with `git archive` into an external directory, using a separate locked editable Python 3.13.5 environment. All 13 changed exported files were byte-compared to the frozen Git objects; hashes are in `final-changed-inputs.json`. Actual imported module/config paths are recorded in `pytest-final-binding.json` and `final-runtime.json`. The actual loaded SQLite is 3.51.3, source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`, through the dynamic binding and supplied library; no reported version was replaced.

## Verdict

No remaining material finding in the reviewed I4 scope. The source-backup recovery-stop failure described below was independently reproduced on the first pushed head and is closed on the corrected pushed head. This is focused independent implementation review, not complete I5/release qualification or independent validation of the implementer's broad/hosted receipts.

## Closed finding: missing source Stop after proven Provider-scope corruption

Severity: high. Initial pushed HEAD `b4caae054326a60f4aeb0e5f71e8b042f2c132f9`, tree `f010a70f23c25a76893031ce47b41a48a319d660`.

`pytest tests/integration/i4 tests/integration/p6` independently returned **75 passed, 1 failed, 0 errors, 0 skipped**. The exact failing node was `tests/integration/i4/test_query_search_backup.py::test_invalid_authoritative_provider_scope_stops_service[backup]`. A disposable authoritative Context stored a Provider-role scope naming Repository 2 while its declared member named Repository 1. Backup refused, but no `p1-recovery-stop.json` was written. The generic cause classifier treated the trusted decoder's ValueError as an indeterminate implementation exception. Evidence: `focused.log`, `focused.xml`.

The correction introduces `StoredContextInvariantError` only at the trusted stored relation decoder boundary and preserves its underlying cause. Diagnosis recognizes this deterministic invariant proof while arbitrary adapter exceptions, locks, IO and budgets remain indeterminate. Final independent verification passed all four I4 source corruption operations and all 16 P7 source-diagnosis controls. No blanket ValueError-to-corruption rule was introduced.

## Independent executed evidence on the corrected source

Command (from `final-source`, own locked environment):

```sh
LD_LIBRARY_PATH=/workspace/i4-runtime .venv/bin/python -m pytest \
  -c /workspace/i4-independent/final-source/pyproject.toml \
  tests/integration/i4 tests/integration/p6 \
  tests/integration/p7/test_source_diagnosis.py \
  /workspace/i4-independent/final_external_probes.py -q \
  --basetemp=/workspace/i4-independent/final3-test-temp \
  --junitxml=/workspace/i4-independent/final3-focused.xml
```

Result: **96 passed, 0 failed, 0 errors, 0 skipped**: I4 26, P6 50, P7 source diagnosis 16, independent external probes 4. All 50 P6 nodes now run successfully, including the 27 formerly blocked by retired fixture API. No Context API shim was restored. `core.admit_repository()` remains a distinct legitimate Core operation.

The four external counterexamples independently exercise:

- Strictly newer comparable explicit NULL removes current mapped membership and filtered paired-list membership.
- Equal-clock NULL and a mapped alternative coexist, suppressing the convenience UUID while retaining the qualified candidate.
- An index document key forged while preserving row count causes authoritative fallback with identical hits and no P7 Stop.
- Contradicted transient Disposition evidence is reflected in recomputed authoritative Search summaries even when indexed text stays the same, and cannot continue another evidence set's cursor.

`final-binding.log` separately records four successful source-Stop cases under a session-start plugin that asserts the imported corrected validator path and presence of the new invariant type. `review_binding_plugin.py` is an external reviewer artifact, not a production change.

Both direct wheel and sdist-derived wheel built and installed outside the checkout passed `scripts/verify_access_distribution.py` independently on the corrected source. Both loaded site-packages modules and actual SQLite 3.51.3, found 19 Context tables and matching fingerprint `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`, and passed installed I2→I3→I4 Query/Search/Disposition/fresh paired restore smoke. Evidence: `final-distribution.log`, `final-source/artifacts/access-registry/distribution.json`.

Independent audits passed: Ruff lint, Ruff format (387 files), composed DDL/fingerprint build check, schema audit, Context registration audit, call-site dependency audit and implementation-boundary audit. Evidence: `final-audits.log`. `git diff --check` against the base also passed.

## Static review conclusions

Read repository-wide AGENTS, accepted ADR 0029/0030, I1 contract/freeze, I2 intake, I3 Exchange, I23 integration, I4 contract, final-tree skill and relevant code/tests/workflow changes.

Current ownership/base/head and repository filtering use typed `provider_repository_roles(..., evidence=...)`. Retained Core-target relations are separately exposed as historical evidence and do not provide implicit fallback. Mapping conflict, NULL, absence, unmapped Provider, comparable/equal/incomparable/unknown clocks and transient Disposition qualification remain represented. Complete keys/provenance are serialized, and cursor filters bind transient qualification.

Search document identity includes complete role scope and original provenance, preventing equal-clock distinct-Provider alternatives from colliding. Stored Core-target summaries carry an explicit historical kind. Search candidates are checked against authority; summaries are rebuilt from pinned authority on reads. Derivative damage cannot issue Mapping qualification or Stop a sound catalog. Existing deterministic ordering, snapshot fences and bounded SQL/rows/documents remain in use.

Backup uses whole paired SQLite snapshots, so both new tables and full ClaimKey/Disposition/Transfer/Provider/Source/Coverage dependencies are retained. Restoration revalidates schema/fingerprint, FK and stored semantic invariants before fresh activation. Tests compare full Context row multisets, not only maximum clocks or table counts. Access, Operational and Search remain outside paired domain backup; Git-only scope remains independent. Bad restored candidates do not Stop the healthy source. Proven source corruption now does Stop service.

The minimum-SQLite workflow extends the existing cohort, retaining previous targets and avoiding repeated P1 modules. Installed smoke now tests I4. No skip/xfail, deletion of failing tests, merge/release/P8/catalog action was observed in the reviewed diff.

Skill additions correctly distinguish role summaries from mapping authority and trusted stored-invariant proof from arbitrary errors. They are procedure guidance and do not expand execution authorization.

## Preserved harness failures and limits

External probe development initially expected a known-NULL clock to dominate an unclocked Provider report and expected contradicted evidence to produce `single_candidate`. Those expectations were wrong: unknown clocks are incomparable and contradicted evidence yields `evidence_contradictory`. The corrected assertions pass; original errors remain in `probes-initial-harness-errors.log`.

One attempted final command named nonexistent `test_diagnosis.py`; no tests ran (`final-focused.log`). Another command included an external path above the frozen checkout, causing pytest to select the parent archive's config and old source. That interrupted run (`final2-focused.log/xml`, if emitted) is not corrected-tree evidence. Explicit `-c` plus source-binding assertions repaired the harness; `final3-focused.*` is the valid run. Recommend extending the existing final-tree skill with this external-path/rootdir pitfall.

The reviewer did not independently rerun the entire expanded cohort, hosted CI, complete I2/I3/I23 suites, all Core/Access suites or full release acceptance. Those remain implementer/CI evidence to bind and report separately. I5 must freeze the intended assembled integration tree, recheck effective ancestry, mixed selection/qualification/recovery flows, Core/Access separation and installed artifacts. Later evidence-only commits require executable-input equality before carrying this review forward; production-code changes need renewed review.
