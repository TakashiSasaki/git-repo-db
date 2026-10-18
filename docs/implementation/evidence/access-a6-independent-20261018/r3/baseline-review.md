# R3 independent baseline review: Context, Exchange and Access backup

Reviewer: R3, separate from the implementation author and the root correction owner.
Started at 2026-10-18 12:35:56 JST. All baseline findings below concern commit
`f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60`, tree
`a7b4521fb7fa6562c8e0bf67e2766743e0b82c5b`, in the read-only worktree
`/workspace/access-review-ro`. `git status --porcelain=v1` was empty before and
after the probes. Source files were not changed. Evidence and synthetic databases
were created only under `/workspace/access-review-evidence/r3`.

## Runtime and reproduction

Actual loaded runtime: Python 3.13.5, Git 2.52.0, SQLite 3.51.3;
`SELECT sqlite_source_id()` returned
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
The root reviewer built and checked the official SQLite artifact; R3 independently
recorded the actually loaded SQLite and source ID. R3 used:

```sh
LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 \
  /workspace/access-review-ro/.venv-minimum/bin/python \
  /workspace/access-review-evidence/r3/probe_baseline.py \
  /workspace/access-review-evidence/r3/baseline-synthetic-v2

LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 \
  /workspace/access-review-ro/.venv-minimum/bin/python \
  /workspace/access-review-evidence/r3/probe_backup_adversarial.py \
  /workspace/access-review-evidence/r3/baseline-synthetic-v2 \
  /workspace/access-review-evidence/r3/backup-adversarial-v2
```

The first completed probe ran 12:39:18–12:39:20 JST. The adversarial backup probe
completed at 12:41:52 JST. Both commands exited 0; their JSON logs deliberately
record both accepted controls and expected refusals. These are independent short
synthetic API/SQL experiments, not a rerun of the whole pytest/CI cohort.

## Findings before correction

| ID | Severity | Source at the fixed tree | Reproduced result | Required disposition |
| --- | --- | --- | --- | --- |
| R3-01 | Medium | `src/repo_catalog/application/acquisition.py:818` | A registered non-seed R1 `GitMetadataInput` is refused with `REPOSITORY_SCOPE` because it differs from catalog seed R0. No claims or objects are inserted. | Separate selected permanent Repository identity from actual Core/Operational seed+instance pairing. Preserve target selection and cumulative request fencing. |
| R3-02 | High | `src/repo_catalog/application/acquisition.py:849` and `:853` | A unit claiming target R0 accepts a RepositoryClaim for already-registered R1 and persists it. The report still says R0/known_empty. The seed-only guard fails to enforce nested repository ownership. | Before any admission, reject repository-owned nested claims/observations/Notes captures/coverage for another selected Repository. Do not merely remove the seed check. |
| R3-03 | Medium, known documented implementation gap | `src/repo_catalog/application/exchange.py:306`, `:327`, `:367`, `:1319`; `src/repo_catalog/domain/exchange.py:195` | Actual native R1 acquisition in seed-R0 Core succeeds; export uses envelope Repository R0 while including R1 observations/claims and both R0/R1 registry rows. Seed-R2 receiver rejects it with `REPOSITORY_MISMATCH`; zero Core objects are inserted. A same-seed-R0 receiver imports and re-exports the original R1 claim and observation exactly. | Keep mismatch/pairing guards. Report incomplete non-seed/cross-seed interchange and define an explicit repository selection/import contract before expanding Exchange semantics. |

R3-02 is a target-selection defect, not a claim that RepositoryClaim's stored UUID
was rewritten: the unwanted R1 row remains correctly attributed to R1. The defect
is accepting a row outside the explicitly selected R0 acquisition request and
returning an R0 result. The minimal demonstrated case is in
`baseline-probe-v2.stdout`, steps `seed_unit_with_registered_foreign_claim` and
`mixed_claim_sql`. Foreign observations, Notes captures and coverage are statically
the same missing preflight family; their additional runtime checks belong in the
correction regressions and independent re-review.

### Minimal synthetic inputs

R0, R1, R2 are respectively
`10000000-0000-4000-8000-000000000000`,
`10000000-0000-4000-8000-000000000001`,
`10000000-0000-4000-8000-000000000002`.
Initialize seed-R0 Core+Operational using `p1_schema.initialize`, then register R1
through `GitCore.admit_repository(R1)`.

```python
# R3-01: this registered target still fails on the baseline.
unit = GitMetadataInput(
    R1, str(uuid4()), str(uuid4()), "original-r1-source", 17,
    repository_claims=(RepositoryClaim(R1, "endpoint", "ssh://source.example/R1", prov),),
    nominal_objects=(OID("sha1", "1" * 40),),
)
GitAcquisition(catalog, operational=catalog).acquire_metadata_only(unit, new_request=True)

# R3-02: the declared R0 request accepts a foreign R1 claim on the baseline.
mixed = GitMetadataInput(
    R0, str(uuid4()), str(uuid4()), "declared-r0-source", 23,
    repository_claims=(RepositoryClaim(R1, "name", "foreign-to-unit-r0", prov),),
)
GitAcquisition(catalog, operational=catalog).acquire_metadata_only(mixed, new_request=True)
```

The executable probe includes construction, actual native Git acquisition,
unmodified Exchange export, seed-R2 refusal, same-seed positive control and raw
read-only SQL results. The exact untrusted package is retained as
`baseline-synthetic-v2/r0-envelope-r1-payload.json`. No package header is relabeled
to force acceptance.

## Why the Exchange gap is not fixed by deleting one check

`ExchangeSelectionScope` selects OIDs, Notes refs, ResourceKeys, Source UUIDs and
section/body inclusion. It has no Repository selector. `export_package` accepts no
selected Repository argument and emits all repository-scoped Core rows. The
single envelope `repository_uuidv4` currently comes from physical store identity;
the import API has no separately declared receiver target.

An explicit singular target could be added as engineering vocabulary, but it does
not by itself define the contents of an already-multi-repository package. A safe
contract must specify all of the following:

1. Whether the singular header is one selected domain Repository or a catalog
   seed, and the authorized receiver target independently of its physical seed.
2. Whether a package can select one or several Repositories; exact rules for
   foreign/missing repository registrations, captures, observations, claims and
   repository/capture Coverage.
3. How globally keyed OID facts, shared objects and unowned metadata are included
   without fabricating repository membership from OID equality.
4. How Context transfer, detached resource identities and competing repository
   candidates are selected without dropping original evidence or inventing a
   unique repository owner.
5. The preserved Core/Context/Operational seed+instance pairing, original Capture
   provenance, cumulative work and idempotent replay behavior.

ADR 0003 explicitly leaves DS-R05 cross-repository ownership Exchange deferred
(`docs/adr/0003-append-only-git-core-and-context-store.md:83`). This review does not
invent that deferred contract, treat the seed as permanent domain identity, or
make Exchange completion a blocker for correcting independent metadata defects.

## Independently verified positive boundaries

| Boundary | Actual experiment and assertion | Result |
| --- | --- | --- |
| Native non-seed acquisition | Build a real bare SHA-1 repository with commit/tree; target R1 while store seed remains R0. SQL observes R1 attribution and immutable R0 physical identity. | Confirmed in finite probe. |
| Same-seed R1 onward facts | R0-envelope package with R1 facts imports into separate seed-R0 catalog; re-export compares RepositoryClaim and GitObservation rows exactly. | Exact provenance and values retained; no domain-row misattribution observed. |
| RepositoryClaim direct JSON | Nine genuinely distinct original provenance coordinates cover empty/one-character names, Unicode path, URL, object format, NULL/positive observation, equivalence/cancellation. Repeat import and reverse export compare exact SQL keys and wire rows. | Exact SQL and re-export equality. |
| Unselected Context registration | Put `credential_ref` in an otherwise exact provider envelope, rechecksum the package, set `include_context=False`, and add a nominal Core object. Import into Core-only receiver. | `CONTEXT_REGISTRATION`; zero Core objects, no Access file or corruption stop. |
| WAL preservation and coherent cut | Hold a real WAL writer; commit an earlier registration, then commit another after `_live` yields its validated read transaction and before SQLite Backup API starts copying. | Earlier registration included, later registration absent from snapshot and still present in source. |
| Full history and consent removal | History includes A/T1, B/T2, A/T3 and same-time alternative; backup then restore through actual APIs. Compare all registration rows and bundle member bytes. | All history retained, source rows/grant unchanged at completion of first probe, snapshot/restored grants zero, restored enabled routes zero, input bundle bytes unchanged. |
| Strict members/hash/manifest | Extra WAL member, modified payload without hash update, and an unknown manifest key with a recomputed manifest digest. | Rejected; no destination; complete input-member hash maps unchanged. |
| Rechecksummed CHECK/domain and FK | Copy a synthetic bundle, bypass checks solely to construct a NUL label or missing referenced profile, recompute payload/manifest hashes. | `CORRUPT`; no publication and input unchanged. Hash agreement does not bypass receiver validation. |
| Existing destination | Restore twice into same target; inspect preserved rows. | `EXISTS`; destination unchanged. |
| No-replace publication race | Create an empty target inside the final `_publish` boundary, then execute the actual `renameat2(RENAME_NOREPLACE)`. | `EXISTS`; empty target retained, no owned stage left behind. |
| Failed durability after publication | Inject fsync error only after actual successful rename; inspect the resulting target. | `PUBLICATION_UNCERTAIN`; target preserved with exactly DB+receipt, `integrity_check=ok`, zero grants/routes. |

The second script makes its own private SQLite copy of the synthetic live source.
Its successful concurrent test neither mutates a reviewed source file nor changes
the input bundle. The first failed backup-probe attempt added two extra synthetic
source rows before its fixture error; the original first-probe JSON/wire results
remain intact and are not represented as a later database snapshot.

## Preserved setup failures and limits

- The first baseline script reused the same immutable provenance coordinate for
  two different `name` claims. The production replay guard correctly rejected it
  with `INCOMPATIBLE_REPLAY`; this is a fixture error, not a product regression.
  `baseline-probe.stdout` and `.stderr` preserve it. The corrected fixture uses
  distinct genuine original coordinates, like the domain requires.
- The first adversarial backup script tried changing an assignment key to create
  an FK violation. The immutable-key trigger correctly rejected fixture setup.
  `backup-adversarial.stdout` and `.stderr` preserve that error. The corrected
  fixture removes a referenced profile with FK checks disabled only during fixture
  construction, then restores through the unmodified receiver defenses.
- The initial backup timestamp mutation also broke an FK, so that refusal was
  reference evidence rather than an isolated CHECK assertion. The corrected
  NUL-label fixture keeps all FK coordinates intact.
- R3 did not run a heavy pytest cohort, Git SHA-256 version of its new standalone
  Git probe, installed wheel/sdist tests, MkDocs, CI jobs, power-cut tests or
  performance qualification. Root and other reviewers own their separately bound
  execution evidence. No execution is inferred from existing test names or reports.
- Static review covers backup fork semantics/rollback tests and the actual
  implementation, but R3's new standalone experiments do not independently execute
  fork or process-kill cases. Those remain distinct from its positive evidence.
- All data is synthetic; no real catalog, backup, credential or remote endpoint
  was read, extracted, migrated, activated or modified. R3 performed no push,
  parent/main change, PR operation, merge, tag, release or deployment.

## Re-review and reusable lesson

The implementation author/root owns the fix and new product regressions. R3 must
re-run material baseline counterexamples against the corrected exact tree before
closing R3-01/R3-02. R3-03 remains explicitly partial unless a separately reviewed
selection contract is implemented. No whole-ADR acceptance or merge approval is
implied by this report.

Recommended existing-skill addition: when removing a catalog-seed restriction,
test a registered non-seed positive input AND a seed-shaped outer input containing
a foreign nested RepositoryClaim/observation/capture/coverage. Keep physical pair
identity separate from selected domain identity and compare actual admitted SQL
rows, not only a successful report. This lesson is based on R3-01/R3-02; the fix
owner should add it to `three-store-invariants` after correction verification.
