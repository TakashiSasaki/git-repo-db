# Independent I6-A requirement matrix

Reviewed #145 `08fbb956c2e470e245146b0dbae747ed0690ea40`, tree
`7072f952975a8537f74ced1bbc2a4a31d7aa3690`. Overall verdict is in REPORT.md.
PASS below describes only the stated measured boundary; DEFERRED never means
successful execution of the later application route.

| Requirement | Independent measurement / result | Evidence / remaining owner |
| --- | --- | --- |
| R01 / U4 / B3 | PASS: child-first global and PR-scoped Document with absent namespace, no semantic Parent; I7/I8 alternatives retained | originals/probe_originals.py, results-final.json; no new domain authority/table |
| R02 versioned v5 | DEFERRED: I6-B codec not implemented; existing v4 route remains guarded | failure-audit and CI actual I6-C stacks; v5 acceptance unexecuted |
| R03 strict original input | FAIL for the typed original declaration: missing/invalid state serializes as explicit NULL after carrier mutation | ORIGINALS-M1; constructors and pure validator reject, public intake accepts |
| R04 bounded actual work | PASS in existing source/installed I6-A bound cohorts; independent revocation preserves consumed work | authorization/sql-observations.json; whole v5 planner limits remain I6-B/C |
| R05 identification | PASS local global/scoped/duplicate identity vectors; namespace presence supplies no Parent | originals/results-final.json; v5 seven-column roundtrip deferred |
| R06 whole generic reports | PASS existing local I6-A cohort and multiple Parent probe; no automatic reconstruction after referent arrival | originals and installed safety; wire/Collection closure deferred |
| R07 Source/Coverage | PASS existing local finite Source/OID/claim checks in safety cohort; whole application export/import not accepted | source and installed safety; I6-C preserves positives/real terminals/five columns |
| R08 original Parent | PASS missing coordinate/time, independent Parent21/P/22 vs Event900/E/901, exact lookup, changed-time replay, explicit resupply | originals 19 probes; wire/recovery reconstitution deferred |
| R09 original Provider endpoints | FAIL ORIGINALS-M1, initial and exact replay. Normal one-sided/null/provider-only/truncation vectors PASS | source and both installed forms; 4 safety failures per form, 2 normal fence controls pass |
| R10 service-bound authority / I5-A1 / I6-L1 | PASS forged/copied/foreign contexts, principal mutation, no service/context, expired/read-only, export-only writes denied | authorization 27 source +27 direct +27 sdist, finite independent principal policy |
| R11 current grants and commit lease | PASS permission/selection and replay rechecks, revoked policy, active lease at actual COMMIT | authorization SQL traces; trusted policy adapter must conform to port contract |
| R12 refusal order and no disclosure | PASS authority/selection before content lookups in independent probes; pure local expired/read-only preflight | authorization; ORIGINALS-M1 correction must preserve authority order |
| R13 bounded dependency closure | PASS scoped local enumerator cohorts; generic sender/receiver expansion DEFERRED | no namespace traversal authority inferred; I6-B/C owns integrated planner |
| R14 original replay | PASS current permission/Parent/received-set revalidation; FAIL nested declaration revalidation | ORIGINALS-M1; cached package routes guarded pending I6-C |
| R15 SQL/transaction / I5-D1 | PASS actual second endpoint INSERT failure, actual deferred-FK COMMIT failure, revocation and KeyboardInterrupt full rollback; FAIL complete original pre-bind validation | authorization traces + ORIGINALS-M1; no product fix mixed into review |
| R16 both fences / I5-F1 | PASS exact packaged definitions and normal refusal, normal-route malformed-original controls retain fences | authorization + originals + installed schema probes |
| R17 Recovery | DEFERRED, 14 actual I7 composition failures (unbound ContextStore caught into receipts), no intentional stage API acceptance | failure-audit per-node trace; I7 must wire finite trusted salvage authority and preserve Stop |
| R18 Query/Search | DEFERRED I8 Transfer/semantic-parent integration; migrated Core-only assertions remain meaningful | failure-audit AST review; no acceptance beyond first reached refusal |
| R19 integrated activation | NOT MET: both fences retained, no normal Transfer activation, all later integrated acceptance remains | I6-B/C, I7/I8 then separate integrated/distribution review and authorized retirement |

Installed identity, CLI doctor/module launch, all product file types (including
GraphQL), RECORD, schema/fences, FK and integrity are covered by fresh independent
artifact executions. Hosted Development is static success; hosted Access remains
failed. Neither is a release acceptance result.

Full ordinary raw: 5,656 PASS / 276 FAIL / 42 ERROR across 5,974, exit 1.
Pristine original 743: 444 PASS / 279 FAIL / 20 ERROR in one invocation.
Corrected cache 22: 18 PASS / 4 FAIL; exact serial timeout repeat: 1 PASS.
Latest node-wise 5,974 outcomes (5,675 / 279 / 20) span these distinct invocations and are
not a corrected single full run or release receipt. See the final report addendum.
