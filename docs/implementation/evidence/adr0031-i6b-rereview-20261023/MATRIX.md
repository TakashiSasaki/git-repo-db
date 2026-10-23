# Independent I6-B re-review allocation at #153

Target HEAD `61e44291e293f773904a0127606e20c8cb83c95e`, tree
`4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`. Owners below are the fixed I6
change-map allocations, not newly assigned implementation work. Tests that belong
to C/I7/I8 remain deferred even when a B codec precursor passes.

`new61` means this lane's new independent probes. `normal208` means the unchanged
prior independent wire157/planner28/admission19/resolved-V07-4 source lane.
`saved33` and `Author34` are separately replayed attributed lanes. Their source
results are 61/208/33/34 PASS, each exit0 with exact phase/node reconciliation.
Distribution, full-suite, admission-retention and CI evidence are separate review
lanes; their results must be read from those receipts rather than summed here.

| Requirement | Sole authority / meaning inspected | Independent re-review evidence and limit |
| --- | --- | --- |
| R02 | `exchange.FORMAT`, exact envelope/section sets; `exchange_rows.ROW_KEYS` | normal208 rejects rehashed wrong/missing versions and extra/missing envelope/resource/representative-row fields. Only v5 accepted; unknown Resource kind does not mean unknown wire version. |
| R03 | `_canonical_dictionary`, strict `_parse_json`/`_bounded_json`; identity/report encoders | new61 received-dictionary/ordering/nested-digest/UTF8/duplicate/coercion controls; saved digest30 now refuses `DIGEST_MISMATCH`; Author new40 are separate full-suite/installed cases. Received noncanonical selections refuse; SHA-256 authenticates no sender. |
| R04 | `resource_identity` intrinsic caps, common wire hard caps, planner `spend` | normal planner28 and saved work3 pass unchanged. M01 reviewer independently measures zero/exact/over/depth/byte/cycle/allocation boundaries. C database-read/continuation budget composition remains deferred. |
| R05 | `ResourceKey` three coordinates + `ResourceIdentification.columns` seven named row fields | normal208 exact child/global/scoped/empty/Unicode/recursive corpus; known malformed profiles never fall back; namespace components create no Parent or traversal edge. |
| R06 | `ResourceRelation` original ordered unique members/key/time; Collection header and real terminal authorities | normal208 preserves order and same-time alternatives, rejects rebinds/duplicates; genuine complete-empty differs from partial-empty/unknown/absence. Planner withholds whole reports and terminal groups. No union or manufactured terminal. |
| R07 | Source UUID/service/positive-pair inventory; `CoverageScope`, terminal and proof validators | normal208/Author34 Source known positives/terminal/state and five-column claim/proof mutation controls pass. Partial inventory cannot delete R2; proof binds exact original terminal/claim/scope. No durable Source route newly implemented. |
| R08 | Full `ParentReportKey` and its actual immutable observation | normal208 transports independent Parent/Event clocks/provenance/times (including lawful nullable Parent time), refuses missing/different exact originals. No Event-derived Parent fallback. Current dependency eligibility stays A/C. |
| R09 | Original nine-field Event scope + `ProviderEndpointDeclaration`, complete endpoint references/supports | normal208 one-sided/two-sided/truncation/Provider-only/multiple-resolved-alternative controls pass. Endpoints are original declarations, never inferred from surviving or stored rows. No C route completion claimed. |

| Vector | Actual B / retained-A evidence | Deferred boundary |
| --- | --- | --- |
| V01 | normal208 and Author34 global Document full identity/seven columns, nonleaf/cycle controls | Durable Provider normalization/route composition C. |
| V02 | normal208 scoped Event child-first, exact canonical namespace TEXT, no synthetic Parent | Later durable Parent arrival/resupply C. |
| V03 | normal208 independent original Parent full-key/time; admission19 trace/readback | Normal Provider/Exchange original production C. |
| V04 | normal208 genuinely one-sided explicit NULL with exact original reference | Normal Transfer remains fenced. |
| V05 | normal208 two-sided complete/truncated declarations, inherited admission SQL rollback controls | Normal multi-route complete-unit composition C. |
| V06 | normal208 unresolved Provider-only report preserves actual Provider ID, no fake Core/null | Current mapping and Provider acquisition C. |
| V07 | separate resolved4 inside normal208 preserves multiple exact MappingClaimKey alternatives and support | Receiver current qualification remains A/C; checksum never proves it. |
| V08 | normal208 rechecksummed malformed schema/ID/time/originals; new61 canonicality/digest corpus | Durable PackageKey content replay and untrusted route coverage C. |
| V09 | normal208/Author34 ordered generic members, terminal alternatives/empty/partial/unknown and Source/Coverage | Durable late/onward/reverse composition C; query I8. |

| T ID | Fixed owner / requirements | Re-review evidence and explicit scope |
| --- | --- | --- |
| T01 | A/B; R03–05 | normal208 identity corpus + preserved source cap tests; M01 hard-bound controls. No new SQL/BINARY schema claimed from pure codec. |
| T02 | A/B/C; R01/05/08/14 | normal208/Author34 seven fields, child-first and namespace-independent planner. Durable export/import/later explicit resupply C. |
| T03 | A; R08 | normal208 exact original Parent/Event clock/provenance/time and alternative-parent refusal. Retained admission controls own actual writes. |
| T04 | A; R01/08/15 | Existing native-I7/full-original I4 safety guards are unchanged and independently replayed by admission/distribution lanes. C route composition remains deferred. |
| T05 | A/B/C; R09 | normal208 one/two-sided declaration/truncation and full endpoint references; admission lane owns actual transaction atomicity. |
| T06 | A/B/C; R09/12 | normal208 separates explicit NULL, Provider-only and resolved alternatives; wrong/truncated support refused. Current authority/normal Provider intake C. |
| T07 | A/C; R10–12 | Admission reviewer tests per-dependency policy denial. B codec constructs no policy/context; normal route composition C. |
| T08 | A/C; R10–12/14 | admission19 in normal208 reruns foreign-context/replay/COMMIT denial; broader lease/current replay retained A suite. Cached receipt/route replay C. |
| T09 | A/C; R10/13 | normal planner28 empty-selection controls; retained A explicit local selection controls. Disjoint sender/receiver composition C. |
| T10 | B/C; R02/03/09/11 | new61 + saved digest30 + normal208 rehashed invalid semantic/version/row cases. Valid digest grants no authenticity/authority. |
| T11 | B/C; R04–06/13 | normal planner28 cycle/closure/whole-unit oracle, saved work3 and independent M01 fresh boundary corpus. Database reads/route cumulative work C. |
| T12 | B/C; R06/07 | normal208/Author34 real terminal alternatives/order/known-empty/partial/absent and whole completeness withholding. No older-complete fallback manufactured. |
| T13 | A/B/C; R07/11 | normal208/Author34 exact Source service/positive pairs/scope/claim/proof tests. Durable Source-current grant composition C. |
| T14 | C; R10–14 | B whole-unit withholding precursor passes normal208. Full disjoint selections/local authorized dependency orchestration C unexecuted. |
| T15 | C; R08/13/14 | B adds no queue/auto-replay; source diff audited. Two/three-catalog late/reverse/onward C unexecuted. |
| T16 | C; R13/14 | B planner original Parent-before-whole-Transfer precursor passes; actual durable route permutations C unexecuted. |
| T17 | A; R15 | admission19 in normal208 reruns actual COMMIT denial/rollback and policy lease checks; admission lane rechecks second INSERT/deferred-COMMIT traces. |
| T18 | A; R15 | Existing I4 217 and I5 29 covered as subsets of retained safety626/full-suite/installed lanes; no assertion or SQL guard changed. |
| T19 | A; R16 | Retained both/single-missing/altered/unreadable/reopen fence controls in admission/distribution evidence. B pure codec activates nothing. |
| T20 | A/I7; R15–17 | Existing PRAGMA/UDF/fingerprint/connection controls retained in safety/installed lanes. I7 stored decoder/source Stop semantics unexecuted. |
| T21 | I7; R17 | B preserves full original wire forms only. I7 trusted retained-data corruption/source Stop/restore refusal unexecuted. |
| T22 | I7; R17 | No paired restore/salvage/activation implementation performed or tested by B. |
| T23 | I8; R18 | No new query/Search implementation or acceptance claimed. |
| T24 | A/B/C/I7/I8; R19 | Separate direct and sdist-derived installation reviewer runs same new61/saved/normal/Author/focused cohorts and all-member/RECORD/origin audits. This is scoped packaging verification, no Release acceptance. |
| T25 | All; R19 | Parent owns single ordinary full source, existing299 node/phase/refusal/actual traceback/assertion-entry comparison. Original Access smoke stays failed with later assertions unreached; no summed totals. |
| T26 | A/C/I7; R10/16/17 | Retained unconnected Provider/Exchange/facade fail-closed in admission lane. C/I7 complete untrusted route integration unexecuted. |
| T27 | A/B/C; R06/08/14 | normal208 immutable report time/scope/order conflict; new61 changed dictionary integrity; retained current replay checks. Durable route PackageKey replay C remains unexecuted. |

Closing M02 does not by itself authorize C. Overall B readiness also requires the
other independent lanes, especially M01 and unchanged safety. Nothing in this
matrix starts C/I7/I8, integrates sibling branches, changes authority or retires
either Transfer fence.
