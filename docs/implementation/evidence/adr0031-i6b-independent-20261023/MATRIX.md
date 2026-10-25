# Independent I6-B contract allocation and execution map

This matrix binds to #151 `ef787a5ff8b13f118d6bf5107c7338f43fde56dc`.
The independent probes use fresh fixture values and oracles. Existing Author
tests and prior independent admission tests are attributed reuse. A passing
refusal establishes its reached boundary, not the later assertions it prevents.
See each subreport for exact selected IDs, commands, exits and phase records.
The lanes overlap; their counts are not a unique-coverage total.

| Requirement | I6-B responsibility | Independent evidence and disposition |
| --- | --- | --- |
| R02 | Exact v5 envelope/rows, no compatibility | `wire/test_independent_wire.py.txt`: correct-checksum wrong/missing versions, extra/missing envelope and row keys; source/installed codec lanes. |
| R03 | Strict UTF-8/JSON/types/canonical IDs and whole-dictionary digest | Wire malformed bytes, duplicate keys, surrogate/nonfinite/cyclic values, strict seven columns and rechecksummed noncanonical IDs pass refusal controls. **M02 FAIL:** selection deduplication/reordering before checksum changes the dictionary being hashed. |
| R04 | Intrinsic/outer limits and finite actual-work budgets | Author 212 reexecuted; independent planner oracle 28 passes depth/node/edge/unit/byte/work boundaries, SCC/caller cycles and withholding. **M01 FAIL:** complete embedded scan runs before max_work/prior_work check. |
| R05 | ResourceKey/ResourceIdentification sole authority, seven fields | Independent Unicode/scalar/array/empty/global/scoped/opaque identities; incomplete known profile never falls back; no synthesized namespace/Parent; installed byte/origin checks. |
| R06 | Whole ordered reports, real terminal alternatives | Independent relation order/empty/alternatives/rebind controls and Collection complete-empty/partial-empty/unknown/absent/reordered alternatives; planner whole-unit oracle. |
| R07 | Original Source positives, inventory and exact Coverage | Wire independent service/terminal/claim/scope/proof mutations and nonterminal controls; planner original complete-alternative group withholding. No durable Source mutation implemented by B. |
| R08 | Full independent original Parent lookup/time | Independent Parent and Event clocks/provenance/time (including lawful NULL Parent observation), missing/different original refusal; admission originals and rollback readback. |
| R09 | Complete original endpoint declaration/references | Independent one/two-sided, explicit NULL, unresolved Provider-only, wrong/truncated refs and no completion from other rows; whole Transfer withholding. Resolved mapping qualification remains current Admission authority. |

| Vector | B responsibility | Independent evidence / limit |
| --- | --- | --- |
| V01 | Global nonleaf Document identity | Wire Unicode/recursive/scalar/empty IDs and repeated complete canonical provider_document_id; no Parent prerequisite. |
| V02 | Scoped Document child-first identity | Wire canonical namespace TEXT and known scoped mismatch controls; planner namespace does not add an edge. Durable late delivery is C. |
| V03 | Independent Parent original | Wire distinct Parent/Event evidence and admission readback/replay. |
| V04 | Genuine one-sided explicit NULL | Wire constructor/codec original fixture and admission originals. |
| V05 | Complete two-sided declaration | Wire endpoint truncation and original-key controls, new COMMIT denial after two endpoints pending. |
| V06 | Provider-only unresolved state | Wire unresolved fixture retains Provider ID, no invented Core or NULL endpoint. |
| V07 | Resolved direct mapping supports | Reexecuted 212 checks full direct keys/missing-claim withholding; retained Admission suite checks current qualification. Normal Exchange composition is C. |
| V08 | Correct-checksum malformed semantic data | Independent canonical ID/version/type/schema mutations; **M02** independent checksum counterexamples show a separate acceptance gap. |
| V09 | Ordered terminals/Source/Coverage alternatives | Wire competing order/empty/state/proof mutations; planner whole real terminal group oracle. |

| Test ID | I6-B allocation and executed evidence | Deferred/shared conditions |
| --- | --- | --- |
| T01 | Wire independent identity corpus and Author exact/+1 intrinsic/outer caps reexecuted | API/SQL BINARY retained I1/I4, not a new schema implementation. |
| T02 | Independent seven-column child-first codec and namespace-independent planner | Durable import/export/later original resupply C unexecuted. |
| T03 | Independent full-key Parent/Event originals and retained original observation/replay | No receiver synthesis permitted. |
| T04 | Exact quoted support transported; retained native-I7/full-FK I4 controls | B does not activate Transfer or delete lawful I8 alternatives. |
| T05 | Independent complete declaration/truncation and planner whole unit | Actual stored atomicity tested in retained Admission lane. |
| T06 | Independent not-reported/explicit-null/Provider-only states and malformed target/ref refusals; Author resolved-support tests | Normal Provider intake/qualification composition C. |
| T07 | B creates no authority; retained per-dependency refusal tests | C sender/receiver route composition unexecuted. |
| T08 | Retained current replay/lease checks; new equal-principal foreign context/actual COMMIT denial/revocation | New codec never grants a policy handle. |
| T09 | Independent empty-selection planner; retained explicit local selection/current grant controls | End-to-end disjoint receiver grants C. |
| T10 | Independent rechecksummed malformed IDs/versions/rows; **M02** stale-checksum mutations | Sender checksum is not authentication. |
| T11 | Independent chain reachability oracle, 24-node SCC, self/caller cycles, boundary oracle; **M01** zero/low/exhausted-work failures | Database dependency-read budget integration C. |
| T12 | Independent real terminal alternatives/order/empty distinctions; withheld group consistency | Complete domain nested proof logic retains existing authority. |
| T13 | Independent Source terminal/service/positive-scope and Coverage proof mutations; no terminal invented | Durable Source association/repository-grant composition C. |
| T14 | Independent planner whole relation/terminal omission; no list shrinking | Full sender/receiver grants/local dependency composition C. |
| T15 | No automatic replay/pending payload added; source diff audit | Two/three-catalog late/reverse/onward execution C unexecuted. |
| T16 | Reexecuted pure planner dependency/Parent-before-Transfer unit checks | Durable route array/arrival permutations C unexecuted. |
| T17 | Retained actual first endpoint then second INSERT abort; deferred FK COMMIT; new SQLite-authorizer COMMIT denial | SQL trace proves reached writes/COMMIT and rollback, not only preflight. |
| T18 | I4 217/I5 29 inside source full and both installed safety626 lanes; strict typed wire refs | Existing assertions not weakened. |
| T19 | Retained both exact/each missing/each changed/both missing/unreadable/reopen controls, installed fences | Both absent only authorized isolated disposable test infrastructure. |
| T20 | Retained PRAGMA/UDF/fingerprint/connection controls and installed schema/integrity checks | I7 stored-corruption decoder acceptance unexecuted. |
| T21 | B supplies original wire forms; no recovery edits | I7 source Stop plus restore refusal unexecuted. |
| T22 | No paired restore/salvage implementation | I7 fresh paired activation unexecuted. |
| T23 | No Query/Search implementation | I8 generalized views/Transfer projections unexecuted. |
| T24 | Fresh publication source → direct wheel and publication sdist → derived wheel; all members/RECORD/product hashes/origins, normal refusal and positive/negative probes | These focused distribution runs are not full Release acceptance. |
| T25 | Final full ordinary source, exact node/phase comparison, AST audit, matched diagnostics, actual original Access smoke | Each invocation stands separately; setup/tool failures and unreached assertions retained. |
| T26 | Retained unconnected Provider unit/units/batch and Exchange export/import/cache fail closed; new foreign contexts | Complete normal route dispatch C/I7 unexecuted. |
| T27 | Independent immutable report time/scope/order conflict and retained current replay checks; **M02** package content/digest gap | Durable route PackageKey replay C unexecuted. |

**Readiness:** M01 and M02 prevent acceptance of the frozen I6-B contract.
I6-C must wait for an Author correction and separate independent re-review.
No I6-C/I7/I8 implementation, stack integration, fence retirement or Release
acceptance is performed by this review.
