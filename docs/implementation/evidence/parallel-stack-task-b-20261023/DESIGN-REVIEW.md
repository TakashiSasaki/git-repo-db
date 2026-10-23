# Fixed-snapshot review scope and I8 parallelization audit

This is a read-only Task B contract/binding audit, not a new product acceptance
run. `audit_bindings.py` completed with exit 0; `binding-results.json` records
17 SHA-256 input bindings and `commands.json` records commands, source objects,
output hashes and exits. No pytest, wheel build, product operation, SQLite setup,
merge or existing-branch mutation was performed by this subtask. JUnit and pytest
journal are inapplicable because no tests were invoked. Historical measured
results below are attributed to their own reports; they were not rerun here.

## Independent reviews and their exact validity boundaries

The latest API and actual Git trees agree with all three assigned frozen review
HEADs. Recomputing each reviewed-source-to-review-publication diff found only
new evidence files (16 / 102 / 64 respectively); `src` subtree IDs and all
protected source/test/script/workflow/ADR/skill/config inputs are unchanged.

| Review publication | Source actually reviewed | Scope and retained qualification |
| --- | --- | --- |
| #149 `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`, tree `e7ca7e361b8b766f1976a12fc84d5cc50ac32232` | #148 `268025f67841285d105737b5a0d7bd15b1a6f59c`, tree `e5fa0437f19f31fa414d488ec10f483ef68f03fa`; Author execution freeze `f777d195bd219398a51d2a90553377f61fb39370`, tree `7ccc8685e06253e2102d46369110c7150d34a587` | Scoped I6-A PASS closes ORIGINALS-M1/I6A-IR-L01 and satisfies the independent-review prerequisite for beginning I6-B. The saved full ordinary run remains 5,777 PASS / 279 FAIL / 20 ERROR, exit 1; its remaining 299 nodes are classified 242 I6-C / 14 I7 composition / 43 Transfer stage. Both fences remain. It does not accept I6-B/C/I7/I8, normal Transfer or Release. |
| #144 `ededcd83eb2d99a602ba18c8fe3c177125c825ac`, tree `2c721a0e8a58ebe8d1f795da821ea4e317b73e7e` | #142 `59307c40ea65554736e131cedd00f04c9906551b`, tree `5ea93707d62b542c84632515392ac6a35c36cd65` | Archive hardening PASS; overall PASS WITH CONDITIONS. Preserve 79 inherited product failures/errors, original installed Access refusal, Draft state and independent combined-tree verification. Reported broad 3,058 PASS / 59 FAIL / 20 ERROR, exit 1; 2,344 ordinary nodes unrun locally. No combined I6/C0 or full Release acceptance. |
| #147 `e7762952e18061de8c8235beaeddf42f20ad9f5a`, tree `9c220c6606703aa36606896eb52d0a8966914a36` | #139 `3e2609baa07a9e92c8f2dc4dd1608f311021a1cb`, tree `43f0c017d5f922f7e1caf7e4a1605ec4ae7ace1c` | Scoped C0-E1 PASS for the actual closed compressed ZIP 2 MiB boundary. Reported 280 pytest PASS plus 57 subtests and separate real ZIP boundary experiments; it did not rerun full product/Access/I4/I5/installed-wheel/sdist or inherited 79 failures. No new hosted Access overflow/upload experiment or Release acceptance. |

Source reports: [I6-A](https://github.com/TakashiSasaki/git-repo-db/blob/ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00/docs/implementation/evidence/adr0031-i6a/originals-binding-independent-20261023/REPORT.md),
[sdist](https://github.com/TakashiSasaki/git-repo-db/blob/ededcd83eb2d99a602ba18c8fe3c177125c825ac/docs/implementation/evidence/adr0033-hardening-rereview-20261023/REPORT.md),
[C0-E1](https://github.com/TakashiSasaki/git-repo-db/blob/e7762952e18061de8c8235beaeddf42f20ad9f5a/docs/implementation/evidence/c0-e1-independent-20261023/REPORT.md).
Evidence-only publication binding permits attribution of unchanged executable
inputs; it does not transfer acceptance to new combined input bytes. Different
failure baselines (79 at #133/sdist versus 299 at current I6-A) must remain
separate; compare the combined tree to each relevant frozen lineage and reconcile
node/phase/assertion changes explicitly.

## Historical branch reviews are not current acceptance

#119 `cb49836aa855da8503f02370b9a60dddac5d6113`, tree
`9f23c6eaaf9b1bdc4dfdf9da0590213d765ea248`, publishes a bounded I1 review of
#117 `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` and #118
`9ea69ba8804a368802457950601a5a4027174c52`, not generalized persistence/wire
acceptance. It reported global-Document identification loss through triple /
dataclass reconstruction as an I2/I6 dependency and all four installed Access
smokes failed. Its two-engine execution is historical fact predating ADR 0032;
it supplies no instruction or permission for a new SQLite acquisition, build,
replacement or version matrix. It is not an ancestor of any current fixed
review HEAD; the actual merge-base with each is #118 `9ea69ba...`.

#137 `7f9c7ad7c418da3b7a638fe20048e13a7701e3d9`, tree
`af9714da837516719997ffa4165aea8ac3762119`, is explicitly a prerequisite report:
**implementation review NOT STARTED**, no implementation HEAD/tree/build/test or
severity assessment. Its observed proposed ADR at old #135
`217cf2008a10a5911275e5c9d6617586fa017641` was true at that historical check and
does not negate later owner acceptance at #135 `18ba867d...` or #144's fresh
independent implementation review. #137 is a sibling, not an ancestor of #144;
their actual merge-base is `217cf2008a10a5911275e5c9d6617586fa017641`. Its
merge-base with I6-A/C0 is #133 `f16e5b1...`.

## I8-A after I6-B: conditional parallel work only

The accepted handoff says basic reads may proceed from I1–I3 while Transfer
consumers/final integration must agree with I4–I7. The later reviewed I6 design
narrows the actionable starting point to **frozen non-Author-reviewed I6-B**:
the graph branches from B review to basic generic reads, while C review leads
through I7 into Transfer Query/Search integration. See
[handoff lines 200–204](https://github.com/TakashiSasaki/git-repo-db/blob/ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00/docs/implementation/context-resource-design-handoff.md#L200-L204),
[I6 graph and scope lines 97–106 / 187–204](https://github.com/TakashiSasaki/git-repo-db/blob/ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00/docs/implementation/adr0031-i6-change-map-and-handoff.md#L97-L106),
and [R17–R19 lines 453–483](https://github.com/TakashiSasaki/git-repo-db/blob/ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00/docs/implementation/adr0031-i6-wire-admission-exchange.md#L453-L483).

Possible after that freeze: an independently authorized, bounded I8-A PR for
generic unknown/global/scoped/nonleaf reads and explicit identifier namespace
versus attributed semantic Parent views. Its receipt must identify the exact
persistent I1–I6-B contracts and the basic-query subset of T23–27 it actually
executes. The name I8-A is a proposed work split, not a new accepted stage or
blanket product guarantee.

Additional conditions: pin reviewed I6-B's HEAD/tree/input hashes; do not chase
its moving development branch. Inventory modifications against C/I7 consumers
before starting and freeze shared interfaces. Preserve current caller permission,
Source positives/Coverage alternatives, snapshot/generation fences and existing
Recovery Stop behavior. Query cannot infer semantic Parent from identifier
namespace, choose a report winner, resolve Provider-only endpoints, use ineligible
I8 support for an I7-native Event, or trust stored/Search flags as authority.
Any scope requiring a new persistent form, new stored semantic validation or
Transfer-effective interpretation must wait for the relevant reviewed C/I7 work.
I7 still must independently validate original reports, full endpoint references,
native-I7/full support, actual terminals, Source/Coverage, pairing, corruption
stop and current-authorized salvage. No new basic read may bypass those rules.

Not yet possible as accepted normal product behavior: Transfer summary/effective
Transfer Search, full recovery compatibility, final Query/Search scan/fallback/
rebuild equivalence for Transfer, or fence retirement. Those require reviewed
C/I7, the independent integrated gate and both installed forms. Task B implements
none of I6-B/C/I7/I8 and grants no future implementation or retirement permission.

Recheck when I6-B is complete: fresh API/object/ref/duplicate review lookup;
non-Author B verdict and exact tested/publication input equality; persistent
schema/code changes relative to this I6-A snapshot; actual whole-unit v5 outputs
and refusals; shared files and merged tree against sdist/C0; module/package-data
inventory; normal fence states; dependency/permission/rollback and original
failure inventories. Recompute conflicts if any of those bytes change. No mutual
wait or moving I6-B monitoring is required for the present fixed-snapshot audit.

## Required post-integration validation plan

1. Freeze the actual combined source HEAD/tree and all input/artifact SHA-256s.
   Retain current product files dynamically; do not target #144's historical
   155-file / 677,902-byte numbers. The fixed I6-A source already adds
   `adapters/sqlite/context_admission.py`, `domain/context_admission.py` and
   `domain/ports/context_authorization.py` to the 155-file sdist-series product
   roster. Its reported 158 product inputs / approximately 123 MB broad sdist
   are different source/distribution states, not equivalence failures to erase.
2. Re-run archive hardening, finite decompression and complete-source membership
   checks on the integrated current roster. Preserve all Python, SQL, JSON and
   GraphQL resources and explicitly allowed backend metadata. Build direct wheel
   and sdist-derived wheel independently; rebuild with backend-only dependencies,
   no Git/product installation/checkout/test/scripts access. Compare actual
   wheel member bytes, metadata and full RECORD roster/digests/sizes. Small size
   or equal counts are insufficient. Never remove evidence from Git to shrink
   the sdist. Accepted ADR 0033 remains the authority.
3. Install each artifact into its own outside-checkout venv with the explicitly
   selected environment Python. Record actual executable/module origins,
   Python/SQLite/source ID/options/PRAGMAs; test all current product input hashes,
   packaged DDL/UDF/fingerprint/foreign-key/integrity behavior, CLI and SQL/JSON/
   GraphQL resource availability. Run current I4/I5 and I6-A authorization,
   originals, replay, malformed carriers, policy-handle, second-INSERT and
   deferred-COMMIT controls on both forms, preserving exact node/JUnit/journal/
   process-exit reconciliation. Do not acquire or replace test SQLite.
4. Keep ordinary normal product tests on the exact schema with both Transfer
   fences and expected typed Transfer refusals. Separately label disposable
   isolated positives that verify composed schema/UDF/PRAGMAs and remove only
   the two exact stage fences, retaining all other safety/FK/CHECK/recursive
   triggers. Such fixtures are never reopened as normal catalogs and their PASS
   is not normal Transfer acceptance. Original failing smokes must retain their
   nonzero exits; compare actual first reached failure and unexecuted assertions.
5. Re-run C0 compressed ZIP boundaries and actual emitter/index/binding behavior
   with integrated receipts; test fallback failure propagation and ensure
   `always()` upload semantics remain. Recompute changed-path workflow/planner
   selection and the independent SQLite-policy check. Development Success only
   states that selected development checks passed; complete independent local
   and hosted Release acceptance remains separate and unexecuted here.
6. For later separately authorized normal Transfer acceptance, require frozen
   non-Author acceptance of A/B/C/I7/I8, T01–27, normal end-to-end Provider and
   Exchange routes/current authorization, recovery and Query/Search, full
   regression/assertion reconciliation, both installed artifacts and exact
   integrated-tree review. Only a separately authorized coherent retirement
   change may then remove both SQL fences and corresponding application guards
   together and re-run normal routes plus unsupported/tampered schema controls.
   Task B does not perform or authorize that retirement.

No blocked/denied/pending/uncertain mutation occurred in this read-only subtask.
An early path discovery guessed nonexistent `scripts/verify_distribution_artifact.py`;
`git show` reported it missing; its numerical exit was not separately captured,
and the shell pipeline returned 0 from `head`.
It was not a test or defect verdict; subsequent explicit tree listing discovered
the real `scripts/check_sdist_contract.py` / `verify_*_distribution.py` paths.
The structured final audit uses subprocess exit checks without that pipeline.
