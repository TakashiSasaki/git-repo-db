# ADR 0030 I5 independent acceptance

This is new I1–I5 implementation acceptance evidence. Historical ADR/design and
I1–I4/Access reports are unchanged. No production Python/SQL/fingerprint changed
in I5. All PRs remain Draft; no main merge, release, P8/public-runtime switch,
real Catalog/credential operation or live Provider acquisition was performed.

## Exact reviewed source

Draft [#112](https://github.com/TakashiSasaki/git-repo-db/pull/112) is based on
#111 branch `impl/adr-0030-i4-query-search-backup-20261019`.

| Coordinate | Value |
| --- | --- |
| Main observed | `6780088befd33e711230d570bb291edb2ee40cbf` |
| Base #111 HEAD | `a54cb218226e3c91c44e979ee0df0543ea459502` |
| Base #111 tree | `cc2eafaaeb8e3305270c17e74ae69edc42c0a50b` |
| First I5 source | `20198151a6af2f8eefa43e85074307e9d77527b7` |
| Corrected frozen I5 source | `c2c3735439a714bbc9d4128421e7be2c0e88f5b4` |
| Corrected frozen I5 tree | `fdafb830ba63a7f547c5882fe677f9d25ae36bd3` |
| First-source GitHub test merge | `36a68ca0b28949d83ab244e46ef9880960935a41` |
| Corrected-source GitHub test merge | `356f7d44a6c55582ba4b4346c9c91312d4f3cfd8` |

The source test-merge tree equals the source feature tree. The local
main/#112 source merge simulation also yields that tree. See the
[owner merge plan](adr0030-i5-merge-plan.md) for every parent HEAD/tree,
failed intermediate checks, complete ancestry and the proposed future sequence.
I3's six exclusive commits already reach #110 via its second merge parent.

I4 source `f948cc6…` and submitted #111 have identical 422 executable inputs.
I5 changes only its new tests, inventory helper, CI orchestration, skills and
verification documentation. Of 419 pre-existing runtime/test/script/dependency inputs (excluding three
workflow files), 418 are byte-identical to #111. One existing installed P5 test
fixture is corrected for the already accepted I2/I3 contracts; no production
API is restored or changed. The workflow adds I5, four installed P5 nodes,
locked-wheel preparation and parallel quiet execution. Before/after
and Git-blob manifests bind each execution to these inputs. Evidence follow-ups
change documentation and receipts only; they are not claimed as rerun tests or
unchanged complete-sdist bytes. Final PR HEAD/tree must be read from GitHub,
with the frozen-source and final unchanged-input binding kept distinct.

## Full node inventory and local execution

**Local applicable acceptance: PASS after the explicit test-fixture correction.**
Collected4934; successful unique nonlive nodes4933; prohibited live unexecuted1.
The successful-node Counter exactly equals the final nonlive Counter, without
missing/duplicate nodes. This is a source-bound union, not one monolithic run at
the final HEAD. Original failed executions remain failed in their own receipts.

| Executed set | Collected / executed | Pass | Fail | Error / skip / xfail / xpass |
| --- | ---: | ---: | ---: | --- |
| Original focused CI | 2329 /2329 | 2329 | 0 | 0 /0 /0 /0 |
| Additional ordinary, original fixture | 2583 /2583 | 2579 | 4 | 0 /0 /0 /0 |
| Local benchmark | 1 /1 | 1 | 0 | 0 /0 /0 /0 |
| New I5 E2E | 20 /20 | 20 | 0 | 0 /0 /0 /0 |
| Corrected installed P5, author retest | 4 /4 | 4 | 0 | 0 /0 /0 /0 |
| Corrected installed P5, read-only retest | 4 /4 | 4 | 0 | 0 /0 /0 /0 |
| Live smoke | 1 /0 | 0 | 0 | 0 /0 /0 /0 |

The four original failures are the two Git formats × two artifacts for
`tests/packaging/test_p5_distribution.py::test_p5_installed_acquisition_and_exchange`.
A separate triage reviewer reproduced the TypeError at #111 and a passing same
node on main. The fixture used I2's deliberately retired `repository_uuidv4`
producer argument before reaching intake; it also retained pre-I3 implicit
selection/permission intent. A separate author corrected only that fixture using
genuine Provider Repository payloads and an explicit Mapping claim, full
support-key assertions and explicit v4 selectors/Request/permission. All10 old
embedded assertions survive, with18 total assertions strengthening the installed
contract.
No product compatibility API, weakened assertion, skip or xfail was introduced.
The first correction attempt's additional wrapper-type assertion mistake is
retained separately; final four-node author and independent reruns both pass.

Successful distinct coverage is2329+2579+1+20+4=4933; corrected4 replace only the
same four failed logical keys. Do not add overlapping independent reruns to this
unique total. Beyond the repository nodes, independently authored external
probes pass30 security boundaries,4 backup-scope controls and2 Access connected
scenarios;7 helper controls are separate assertion-based cases. Root's8 docs-build
unit reruns and Access82 existing-node reruns overlap repository coverage and
are recorded separately. Exact process exits, phase/node reconciliation,
environment and attempts are retained in the component reports.

The former 2329-node minimum-SQLite CI cohort was not the full tests directory.
The base has 4914 nodes: 2329 focused +2583 additional ordinary +1 benchmark
+1 live. The additional ordinary nodes comprise integration2273, unit237,
e2e49 and packaging24, including architecture spikes and earlier/public-runtime
contracts; exclusion from focused CI did not make them obsolete. Their complete
node lists and per-directory mapping are in `tests/` evidence.

The frozen I5 adds20 nodes: all4934, ordinary4932, nonlive4933 and expanded
focused2353 (the initial I5 cohort was2349 before adding the corrected installed4). Exact normalized Counters establish the disjoint4933-node nonlive
union, not just matching counts. The sole live GitHub smoke is unexecuted because
the task forbids real-network acquisition/credentials. It is neither skipped nor
passed. No acceptance node is removed, xfailed or relaxed.

Exact local runtime: Python3.13.5, actual SQLite3.51.3, source ID
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
The official sqlite3.c SHA3-256 is
`32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e`.
The build command, actual library/interpreter hashes, packages and process argv
are retained. No version override was used. Inspected Python/packaging children
use the explicit interpreter/UV_PYTHON; artifact probes independently query their
own source ID. Parent version alone is not asserted for arbitrary subprocesses.

Setup failures are preserved separately: incomplete docs dependencies caused a
PyYAML collection error; missing venv/bin PATH caused CLI FileNotFoundError;
missing wheelhouse was found and prepared before packaging. Fixed-PATH repros
passed1 and independently3 nodes. Exploratory interrupted runs are not passing
cohorts, and partially written JUnit is not counted as completed execution.
Independent test-authoring mistakes and their original logs remain in the E2E,
Access and reviewer evidence. No such mistake established a product defect.

## Independent E2E and safety boundary evidence

The new20-node suite uses actual native Git+Notes and I2 REST/GraphQL payloads,
selective I3 exchange into independently seeded Catalogs, then I4 Query/Search
and fresh restore. It reuses only low-level synthetic Git/store builders; its
payloads and acceptance assertions are new. All fixtures are disposable.

| Boundary | Executed acceptance evidence |
| --- | --- |
| R/O/C and Repository permission | Eight independent selection combinations, omitted/empty/all distinction, shared OID captures, selected Source inventory/whole Coverage; no dependency registers an unselected Repository |
| Mapping and current ownership | Full ClaimKeys, all three Dispositions/replacement keys and genuine transient evidence; sender-qualified effect stays unconfirmed at plain receiver/restore; newer unresolved Provider owner excludes old Core-target history from current Query/filter/Search |
| Transfer identity and scope | Decimal versus opaque Node IDs; actual transferred/TransferredEvent only; missing/null/unresolved/permission cuts; one/two-ended units; exact EventReportKeys prevent endpoint mixing |
| Search derivative boundary | Missing/invalid database, stale snapshot, forged text and same-count forged matching key all fall back to authority; explicit rebuild restores verified projections; no Context mutation or false P7 Stop |
| Paired restore | Every one of19 Context tables populated; compare full PK descriptors and complete row multisets including generated FK columns, Mapping/Disposition, Coverage, Source membership, OID references, original times/provenance, Capture/Notes and retained bytes; no Access/Operational/Search authority restored |
| Package Binding and crashes | Reexecuted I3 eight exception-cut commit/checkpoint windows, two real process exits, binding race, same-key/different-digest refusal, retry from actual facts; independent new crash-after-binding probe |
| Budget/Operational | Existing retry and empty-package zero-ceiling counterexamples; old Request cannot resume after Operational loss; independent Operational reconstruction cannot clear P7 Stop |
| Invalid input and SQLite | I23 invalid scope/FK/subtype/provenance/Coverage prebinding checks, including unselected/disabled Context; independent time/type/provenance probes and raw REPLACE/UPSERT/UPDATE/DELETE controls with FK/recursive triggers enabled |
| Corruption versus rejection/IO | All P7 and source-diagnosis controls, malformed backup candidates versus corrupt retained authority, persistent source Stop, no Stop inferred from lock/IO/budget/unexpected errors |
| Access | Actual approved non-seed native+Notes→selective cross-seed exchange in SHA1/SHA256; unchanged grants/configuration bytes, no Access creation/transplant/reactivation; four forged execution-authority wire sections rejected |
| Backup scope | Independent4 controls: Core-only/Git-only works without Context; paired refuses missing Context; Context-only source and checksum-valid Context-only manifest refused; no standalone Context-only full-domain guarantee |

Detailed new scenario provenance, full keys and assertions are in
`tests/integration/i5/test_independent_e2e.py` and `e2e/README.md` evidence.

## Distribution and static audits

Frozen-source source checkout, isolated direct wheel and isolated sdist-derived
wheel pass identical production behavior probes on actual SQLite3.51.3.
Two further dependency-complete isolated installs from the verified local
wheelhouse pass the same smoke and dependency checks, entirely offline.
These are **five scenario executions**, separate from pytest unique-node totals.
Minimal --no-deps environments also prove offline surface isolation; they do not
claim live transport acceptance. All package origins are outside the checkout
and recorded. Four composed P1 DDLs, Access DDL,19 Context tables, six typed roles,
Exchange v4, Query, Search and backup/restore agree across environments.

| Frozen-source artifact | SHA-256 |
| --- | --- |
| Direct wheel and sdist-derived wheel (745869 bytes each) | `2ec7c49a81734088ef6f15564c548448f7e79b1786ef86d12bf828c1dd3969cc` |
| Sdist (29458319 bytes) | `6d420078e1b8c44a64536a0c66a0f51813e109af459b18fe90735c5dbd358c04` |

The wheels have equal member sets and all bytes, not just equal version labels.
Context DDL fingerprint:
`fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`.
All store fingerprints, package/member hashes, source ID/Python/import origins and
exact commands are in `distribution-corrected/`. Later documentation changes may
change a rebuilt full sdist; the tested artifact hash above remains historical.

All8 frozen-source static commands pass: full Ruff lint and format, schema build
check, schema audit, callsite dependency, implementation boundary, Context
registration and Access acceptance ledger audits. No generated product file was
modified. The reviewer separately runs7 read-only archive audits. These audits
complement behavior tests and do not establish stronger authenticity guarantees.

## Access ledger and independent review

Historical requirement11 remains `partial`, requirement15 `deferred`; the ledger
and governance/review/owner/P8 fields are unchanged. New evidence reexecutes82
existing requirement11/boundary nodes and adds2 connected approved non-seed
acquisition→cross-seed exchange probes (both Git formats), all successful.
The original #11 seed-only Exchange/selector/receiver-target gap is resolved in
ADR0030's accepted synthetic scope. Recommend a separately reviewed ledger
amendment referencing these new receipts, `covered`/`gaps: []` and exact verified
scope. This record does not rewrite old results. #15 has no legacy extractor or
real-data source-preservation evidence and stays deferred.

The read-only reviewer is `/root/independent_review`, distinct from the
production and I5 test/correction authors. Its own git archives and locked
editable environments assert parent and child import origins/configuration and
actual SQLite source ID. At first freeze2019815 it independently passed449
(I3 66 +I23 34 +I4 26 +P7 255 +P1 relations38 +new external30), then final I5
20 and backup-scope4:473 distinct nodes, all pass with no failures/errors/skips/
xfails. It ran7 archive audits and7 helper validity/tampering controls.

On corrected freeze `c2c3735439a714bbc9d4128421e7be2c0e88f5b4`, tree
`fdafb830ba63a7f547c5882fe677f9d25ae36bd3`, it separately reviewed the correction
and executed all4 installed permutations from its own archive. Every child
reported Python3.13.5, real SQLite3.51.3 and site-packages; wheels match2ec7c49….
It verified all original assertions retained, the2353-node CI inventory, final
workflow/skill/merge-plan delta, no product/DDL/dependency/ledger changes, and
reconciled the original2579-pass/4-fail receipt rather than rewriting it.

**Independent verdict: PASS in the reviewed boundaries; unresolved material
findings0.** Its original and corrected-tree reports remain separate. Across
these stages it executed477 distinct pytest nodes; most overlap the4933-node
repository union. It did not independently rerun the entire supplementary2583
or claim another hosted execution. Independent corroboration of manifests/JUnit
is explicitly distinguished from new execution.

## Hosted checks and acceptance limits

Corrected-source [offline run39296461619](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39296461619)
passes. Its decoded, length/SHA-verified bounded receipt and each indexed member
bind featurec2c3735/test-merge356f7d4/tree `fdafb830…`.
It is `development_checks_passed`, `full_acceptance=false`; it does not execute
all runtime pytest nodes or establish release acceptance.

Corrected-source [minimum-SQLite run39296461636](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39296461636)
passes **2353 collected/executed/passed,0 failed/error/skip/xfail**, on
Python3.12.15/actual SQLite3.51.3 with the same official source ID. Actual
selection and JUnit Counters match each other and local current-CI selection
exactly, without duplicates. All424 archived executable inputs match the
corrected frozen commit; the actual test-merge tree equals the feature tree.
Artifact12208397003 is40552846 bytes, SHA-256
`d51d9860b7402052681e42704bc37fcb90a96c4cf1b07d8e942e3d95b4c31595`,
recomputed against the bytes and upload-log digest. Installed artifacts, audits,
format and allowlisted docs build pass; no deployment ran. Authoritative source
archive members were compared in memory, not blindly extracted/executed.

The #111 prior submitted HEAD is also independently re-fetched, not merely
quoted: hosted run39287566981/artifact12204800854 has2329 exact collected/JUnit
passes; all422 archived inputs matcha54cb2, actual test merge320fe9a/treecc2eaf.
Its artifactSHA isbaa31d2e9e8edd34af520c5977c6cc58fb1654e2ccb00c7ff13de6352cb0134e.
First-I5 run39295441831 also passes2349 before the installed4 were added. These
are distinct executions; a focused badge never covers the omitted supplementary
nodes. Direct job-log redirects failed403; the supported gh-run log retrieval
and GitHub artifact-download connector succeeded. Signed redirect URLs are not
committed. Full ZIPs/libraries/binaries stay outside the PR; selected text
receipts and their verified digests are retained.

For the final evidence-only commit, reread PR HEAD/tree/checks and verify all424
executable inputs equal this tested corrected source. Its final GitHub run and
read-only evidence-tree review are recorded in the PR body after publication;
adding those metadata there avoids pretending a report can contain its own Git
commit SHA. No later tree is called rerun merely because inputs match.

Local/hosted wall times use concurrent workloads and are not comparable
sequential benchmarks. Crash tests simulate exceptions/process termination,
not physical host power loss. UUIDs, Source labels, SHA-256, cloned stores and
sender flags do not authenticate a Provider or Mapping issuer. Mapping effect
needs genuine caller-supplied currently available operation evidence; no Witness
or historical check ledger is added. Package binding history intentionally has
Operational-loss limits. Application guards assume supported connections and do
not protect against a privileged actor replacing files/DDL.

**Acceptance recommendation: accept ADR0030 I1–I5 implementation within the
executed synthetic/offline scope after the explicit fixture correction.** No
unresolved product defect or applicable local test failure remains. The sole
prohibited live test, no physical power-loss qualification, Access15 deferral,
intermediate PR check failures and future protection/owner/P8/release gates are
explicit limits. Full release qualification and public activation are not claimed.

The owner plan recommends **#112 → main** as one final assembled integration
after a separately authorized aggregate retarget/review and exact-tree green
checks, preserving all parent history and the I5 installed-fixture correction.
If individual stage integration is required, use **#107 → #109 → #110 → #111 →
I5**, with each stage's checks resolved first. Never merge #108 again after #110.
Every route needs a fresh main/ref/protection/approval snapshot and parent/tree
verification. No merge permission follows from this evidence.

## Reproduction and evidence transport

Prepare dependencies online before the isolated offline workload:

```sh
uv sync --locked --group dev --group docs --python /path/to/dynamic-python
uv run --no-sync python scripts/prepare_wheelhouse.py
# Set the verified SQLite shared-library loader path if this interpreter needs it.
/path/to/exact-sqlite-python scripts/verify_i5_offline.py \
  --output /new/empty/evidence-directory --workers 4 --execute
/path/to/exact-sqlite-python scripts/verify_access_distribution.py
```

Query the loaded SQLite version and source ID before attributing a minimum-version
run; an embedded binding may ignore LD_LIBRARY_PATH. Preserve the venv/bin PATH
for CLI children. The helper refuses a nonminimum source ID, incomplete
collection, altered wheelhouse/input hashes, test failures and node/phase
reconciliation mismatch. It records all selection sets and prohibits live
execution; it is not a release receipt. Xdist workers use independent Catalogs,
the local benchmark is separate, and full logs/JUnit/journal are saved while
console output remains bounded. The focused workflow uses2 workers and logs35
summary lines without swallowing pytest's exit code. Whole-suite supplementary
execution remains explicitly visible outside the narrower hosted cohort.

`evidence/adr0030-i5/index.json` binds each committed transport file by byte count
and SHA-256, plus original uncompressed bytes for gzip. Executable external probes
are transported as `.py.txt.gz`; restore their original name before deliberately
running them. No synthetic databases, venvs, compiled libraries, packages,
credential values or full source archives are committed. Reports state which
cohorts overlap; do not sum independent reruns into distinct test coverage.
