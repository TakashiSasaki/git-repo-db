# PR155 initial hosted CI audit

All three initial runs reached terminal outcomes at exact feature `fb5d7b5a0c4b92c8a282daac154e66fa6d361e64`, tree `d2010275a90ae6b6cb728344d5708057a79110cd`. Actual checkout `c915fc731bd60339e681a6af8f86a470058a5e06` has ordered parents frozen154 `91827360c185cbf813277bf32a6627d894b1b20a` and this feature; its effective tree equals the feature tree. Later evidence-only heads require their own CI audit.

| Run | Terminal outcome | Actual scope |
|---|---|---|
| [Development40002761103](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40002761103) | SUCCESS | `development_checks_passed`, `full_acceptance=false`;0 product pytest,232 required/unexecuted files. Static/smoke/schema/lightweight sdist passed. Separate policy infrastructure unittests31+4 PASS. |
| [Access40002761153](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40002761153) | FAILURE | Main2786:2487PASS/279FAIL/20ERROR. Broad3148:2849PASS/279FAIL/20ERROR. All zero skip. Main is wholly inside broad: actual unique ordinary union3148, never summed. |
| [Pages40002761106](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40002761106) | SUCCESS |8 documentation tests PASS; deployment job and production Pages upload/configuration skipped. Preview artifact uploaded. |

The same-tree source inventory has6497 ordinary nodes. Actual main collection equals its JUnit identities. Actual hosted main+broad union omits3349 nodes/143 files; all154 newly added integration nodes are omitted. Exact lists are in `hosted-node-union.json`. The reviewed README parameter replacement is explicitly mapped in `access-omissions.json` (+154/-1, net153), retaining runtime assertions while selecting the new lightweight sdist preparation. No removed assertion is treated as a hidden resolution.

Separate overlapping source I4(217)/I5(29) and each fresh installed direct/derived I4(217)/I5(29) pass. Installed I2/I3 probes and origin/runtime checks pass. Both original Access smokes in the I5 verifier exit1; separate direct/derived Access distribution smokes also exit1 with empty stdout and `AdmissionRefused: PERMISSION_DENIED` at installed `application/exchange.py:397`. Whole-wheel equality, metadata/RECORD and actual isolated installation remain measured; both wheel SHA256 values `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`. These preserved I6-C refusals are not Transfer activation or acceptance.

Access failed steps: main runtime, I4/I5 broad orchestrator, historical79 comparator, installed distribution orchestrator, original Access distribution verifier and Access acceptance-ledger reconciliation. Later evidence generation, runtime audits, formatting and upload continued. The old comparator measures baseline79/current299, resolved0/additional220, same_nodes=false: it is an honestly failed old-scope comparison, not evidence of a new regression against154.

## Verified receipts and source comparison

- Development receipt89520 bytes, SHA256 `666e08b3818cd465b3e64cc2c70db6e5be86dfb23b1018fc9f512cc1c4017d29`; all24 indexed payloads, BEGIN/DATA/END, ZIP and actual run/feature/checkout/tree bindings verified.
- Access receipt1992791 bytes, SHA256 `65ab48ba62dad77faa806632c268fb642064e08ad59edf27d0bfd6c6b94c017d`; all123 indexed payloads and actual binding verified. It is below2097152: this run did **not** exercise actual hosted receipt overflow.
- Retained source154 review6344/6045PASS/279FAIL/20ERROR versus each current hosted main/broad: exactly299 non-success identities, all phases/outcomes/primary messages/typed-refusal token sets match. Full rendered messages280/299 and rendered project-frame projections131/299 match. Raw traceback text differs. Hosted actual ExceptionInfo/assertion-entry sidecars are absent, so no actual hosted frame-function or reached-assertion equality is inferred. Fresh6497 source execution remains the parent's separate validation. See `source154-hosted-comparison.json` and compressed entries.

Hosted product Python3.12.15 uses its built-in SQLite3.53.1/source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`. No SQLite component was downloaded/built/swapped by this audit. Development's actual sdist is702494 compressed bytes,6041897 regular bytes,164 members/160 product files,6174720 tar-stream bytes; SHA256 `9d228f889f9507cdc5a166b9658e80873fcbd48255c6c958eb90e33954014b54`. The retained contract contains every member hash and source inventory.

The first Access parser omitted one line-leading BOM-prefixed DATA record, causing a strict length/hash failure. Raw log, initial parser and failure remain saved. Accepting one optional BOM only before the actual timestamp recovers the exact original ZIP without repairing payloads. Twelve external parser controls PASS and preserve rejection of missing/duplicate/reordered/corrupt DATA, malformed base64, payload/double BOMs and tampered index. They are not product tests. `LESSON.md` gives review-ready existing-skill guidance.

## Artifacts, access limits and unexecuted work

Actual upload logs and API metadata agree: Development artifact12521924254 is88763 bytes/digest `a92b06c59754c21d58ce253226c3a9156adf72860d4167434c6024a1c8ec19ff`; Access12522818279 is795331408 bytes/digest `6ec6ce1360db62b499664cbae16f1c8e44c562fe658bbb30043229a76928794e`; Pages12522517787 is4576330 bytes/digest `4e46773c2962547637a96818a4e62e635f8d2750697fba049fcc085ef5f475a9`. Their downloaded bytes/hashes could not be independently checked.

Read actions for each exact artifact ZIP above were attempted once and denied at signed Azure endpoints (`Forbidden`, exit1,0 downloaded bytes). A separate Access raw CLI job-log read was likewise denied/0bytes; preferred GitHub plugin logs succeeded. No denied operation was retried. Errors retain denial/target but ephemeral signed URL queries were redacted and raw-error lengths/hashes recorded. This is an access limitation, not a missing upload or permission bypass. Indexed log receipts were independently verified instead.

No workflow dispatch/rerun/cancellation, remote write, deployment, main merge, Release execution or product/checkout mutation occurred. Receipt-parser controls are the only tests executed by this support agent. Actual hosted overflow/download success remains unexecuted; broad installed/runtime acceptance remains bounded by the observed refusals and omitted nodes. Development success is not Release acceptance. Evidence is external to the checkout and indexed by `ARTIFACTS.json`; copying/renaming helpers requires a fresh index.
