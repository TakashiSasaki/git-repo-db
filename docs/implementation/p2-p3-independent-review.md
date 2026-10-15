# Independent P2/P3 common-contract compatibility review

Verdict: **READY FOR P2/P3 OWNER REVIEW**, with **zero open material cross-domain findings** and **zero demonstrated owner-level architectural blockers**. This is review of the committed opt-in production adapters and their common dependency. It grants no merge, deployment, recovery activation or public runtime authorization.

## Exact reviewed source

| Role | Commit | Tree |
| --- | --- | --- |
| P2 | `8ce2fc4b41f2f7f5a1da9f2fcfbddb4c5cbabc8b` | f61a7d9053e73d2fdf4761577012c9f989b2ca92 |
| P3 | `5e3b373bfc16ff1cad8d8f093af42a7f00d3d320` | `5776bb9b0aa81c9d4a841e446cfea5f3744f4726` |
| Common dependency and actual sibling merge-base | `06a4ccd432476af15ee942e8cfcd9fbdf42357c7` | 58f627ff6acc5171d8620f606e366543eb3c7d02 |
| Committed disposable combination, including 20 independent compatibility tests | `b1b5f9cf11d9c0dd21302c5e22b881e1fcc39137` | `50f53c648425fa19515f63f514991f9d76c21656` |

The combination was clean before and after execution. It contains both sibling commits as ancestors; neither production branch contains the other's implementation. The reviewer wrote independent tests/reproductions only under the external evidence directory; the coordinator committed those tests onto this disposable combination. The reviewer did not edit production source or approve their own production changes. The exact final shared executable source was independently approved at `7ac94a9183eb18f54273fcaeb0a561b01d25048c`, tree `6905cd58843759333577adb6fe30dce4d2f9d25b`; its difference to `06a4ccd` is two evidence documents, with no executable change.

## Independent final execution

Python **3.12.14**, SQLite **3.53.1**, Git **2.52.0**, uv **0.12.19**.

```sh
uv run --no-sync pytest tests/integration/p2_p3_compatibility/test_production_pair.py tests/integration/p1/test_coordination.py tests/integration/p1/test_validation_stop.py tests/integration/p1/test_intrinsic_provenance.py tests/integration/p1/test_schema.py tests/integration/p1/test_disposition.py -q -o junit_family=xunit1 --junitxml /workspace/evidence/cross-review/final-combined-junit.xml --journal /workspace/evidence/cross-review/final-combined-journal.jsonl
uv run --no-sync python /workspace/evidence/cross-review/inspect_combination.py
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
```

**107 selected, executed and passed; zero failed/skipped**, 18.16 seconds. JUnit and journal reconcile exactly 107 unique node IDs, each with one passed setup/call/teardown. Per-file counts are **20** independent production-pair adversaries, **46** coordination, **5** persisted-validation stop, **4** immutable original-provenance, **15** schema and **17** disposition. The schema commands independently confirm 46 target tables, all 84 baseline tables / 625 columns routed, and no unclassified target.

Evidence: `final-combined-receipt.json`, `final-combined-junit.xml`, `final-combined-journal.jsonl`, and `final-combination-static.json`. The receipt includes exact commands, source binding, runtime versions, all node IDs and artifact SHA-256 values. The static inspection script initially needed an explicit Git path separator; its corrected successful execution is recorded, not represented as an uninterrupted first attempt. No duplicate-journal wrapper was used.

These are local focused development checks. This reviewer did not execute hosted CI, full release acceptance, complete P4 acquisition, P5 Exchange, P6 public readers/Search, P7 recovery activation, P8 initialization, production migration, or any real-user catalog operation. Root's broader combined run and the separate Git/Context reviewers' executions are distinct evidence and are not added to these 107 nodes.

## Task E results

| Boundary | Independent evidence and result |
| --- | --- |
| Exact portable identities and common schema | Git blob comparison proves all frozen ports, Context/Coverage/coordination values, schema composition, all six DDL resources/fingerprint manifest and coordination adapter are identical across common, P2, P3 and combination. AST comparison proves all 17 existing P1 Core classes unchanged, including OID, Capture, original provenance, scalar/group keys and scope values. |
| No duplicate identity or conflicting owner | New `Metadata` and Context modeled observations compose existing P1 values; no alternate OID/Capture/Coverage authority. Sibling changed-file set intersection is empty. Production source changes remain in the assigned Core and Context files. |
| Core-only and independently durable Context | Actual production adapters reopen their own separate authoritative stores with the other authority absent. Neither requires Operational/Search. |
| Original-identity retry | Both native formats: actual Core Capture and OID commit; injected Context failure rolls back every Context row. Repeating both callbacks twice retains one original Capture/OID and one exact Context field/reference, with original provenance. |
| Portable absent/resolved dependency | Both formats: an unavailable original Context report preserves original clock/time/provenance, remains explicitly `required=False` and `available=False`, and leaves a sound certified pair. Later original-OID admission and validated required linking resolve nominal availability without creating checked Git truth or discarding the attributed report. |
| Coherent paired snapshots | Both formats: a new actual P2/P3 write occurs after an old pair is pinned. The old Core count, Context current candidate and content token remain mutually consistent; the new pair sees both updates and a different token. No claim of crash-atomic multi-WAL commit. |
| Coverage scope ownership | Physical `table_xinfo` confirms exactly five actual columns, with none generated/hidden. Core object-metadata scope and Context resource-comments scope retain separate claims and qualified unknown/partial results. Existing schema/proof/cross-scope adversaries pass. |
| Derivative loss | Both formats: deleting Operational/Search leaves the exact authority token and current Context candidates unchanged, and Core metadata remains readable. |
| Persistent corruption stop | Actual retained native bytes are damaged outside the supported boundary; selected-byte reading detects authoritative corruption. Subsequent standalone Context and paired writes fail; deleting derivatives does not clear or rewrite the persistent marker. Real persisted invalid UTF-8 validation and swallowed-error capability cases also stop; healthy progress-handler cancellation does not. |
| No ordinary file body | Both formats: ordinary blob metadata-retention admission fails, neither retained table gains a body, and the catalog remains sound. Legitimate exact Context text with the same octets remains in its own domain and grants no Git body-retention permission. |
| Native physical boundary | Six correctly hashed/OID/size-bound but malformed commit/tree/tag representations are rejected through actual supported coordinator SQL callbacks, with both stores rolled back and no false corruption marker. |
| Public runtime / architecture unchanged | Exact changed-file review and the repository's strengthened absolute/relative import audit show no public Schema 21 initialization, accepted ADR or workflow change. No new surrogate/Publication owner or cross-database FK exists. |

## Material findings and disposition

1. **High — Original-report verification laundering.** Supported callback SQL could attach an intrinsic marker to prior original reported scalar/group evidence. Shared physical guards now require separate receiver-intrinsic provenance, retaining the original unchecked report. Independently reviewed and executed all four SHA-1/SHA-256 scalar/group cases, then revalidated on final combination.
2. **High — Honest unavailable Context reference triggered recovery.** The initial P3 report path inserted into required `core_references`, so frozen paired validation treated ordinary missing acquisition as corruption. P3 now uses original-clock/current-field report evidence distinct from validated required links. Both-format combined tests verify sound pairing, honest unavailable resolution, original evidence and later original-OID resolution.
3. **High — Existing malformed UTF-8 escaped persistent stop.** Independently reproduced actual Provider JSON corruption causing `integrity_check` semantic UDF `SQLITE_ERROR` with no marker, and P3 reviewer separately reproduced field JSON. The one shared correction classifies existing-authority failures narrowly, not incoming refusals, and immediately notifies read capabilities before errors can be swallowed. Actual corruption, derivative-loss and noncorrupt cancellation controls independently pass on final common and combination.
4. **High — Hash-valid malformed native representation bypass.** Independent six-case execution on earlier committed combination `a83a233f2e84053795c98a5c01f7c4b2e8be9d64`, tree `5e5c12b97a45ac84ad21b6dfcd89d6d8376c9c3e`, failed all six intended `AdmissionFailure` assertions: malformed native bytes committed. The P2-owned SQLite native UDF now checks full metadata grammar as well as hashes, and actual selected metadata reads parse again. The same six independent tests now pass in final committed combination. Earlier failure evidence remains `before-native-guard-junit.xml`; it is not relabeled success.

The Git and Context reviewers additionally investigated and executed standalone typed-row decoding, wrong-store capabilities, in-flight result completion, retained-text proof/integrity and detailed Git semantics. This reviewer inspected the final completion fences and typed decode/native guards in their cross-domain scope; the domain reviewers' exact executions remain their own evidence. No open issue is hidden behind a green baseline suite.

## Reusable lessons and next stages

Recommend updating the existing `three-store-invariants` skill, rather than creating duplicates, with (a) unavailable attributed reports versus required cross-store dependencies, (b) independent tests at physical SQL and typed adapter boundaries, (c) malformed persisted semantic UDF/UTF-8 faults versus malformed incoming units, and (d) in-flight result completion versus check-before-read. The material corrections above and their before/after executable evidence establish these procedures. This read-only reviewer did not mutate a skill or policy.

P2/P3 can be submitted for owner review as siblings of the same corrected P1 dependency. Their common compatibility is verified. This does not approve unfinished P4/P5/P6/P7/P8 responsibilities or switch the public runtime. No architectural contradiction requiring a new owner decision was demonstrated.
