# Catalog3 operational runtime stride

Starting implementation: `3af3df84372354e972772b5c9600dfeeae0f0e15` (PR #1 head), incorporated by fast-forward from the original checkout at `9a4110185d7e7abffc291f9cfd118ca71587f998`.

## Implemented functional paths

1. Packaged the shared final catalog3 schema, mutable runtime store and evidence-based import finalization.
2. Ordinary source discovery and Git/GitHub persistence now use catalog3; REST/GraphQL history, sealed listings and restart boundaries remain functional.
3. Ordinary queries/search and doctor/backup/restore/cache/index maintenance now use catalog3 transaction snapshots.
4. One packaged resumable guarded offline v2 importer retains typed archive/evidence; phase/predecessor compatibility machinery is retired.
5. CI uses one working toolchain, changed-file selection and every surviving ordinary test file; minimum-version and historical count gates are retired.
6. Focused synthetic fresh/imported, incremental/resume, preservation/recovery and installed-import checks passed. Hosted acceptance at `edce04b646e7b5006f1b15048cab765e3c416bfa` passed 330 ordinary tests and two isolated installed wheel/sdist checks; reconciliation found no unexecuted ordinary files. [Run 37412761695](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37412761695) and the functional handoff record the actual environment and checks. A subsequent prose-only update reports its runtime checks unexecuted rather than repeating the full suite.
7. One scoped public Git trial at application commit `04f23c7082b1b9d0cd96df1062459b7b71049bb0` passed collection, unchanged re-sync, independent commit/blob comparisons and offline backup/restore. [Durable Markdown/JSON evidence](../validation/real-world/2026-10-06-museum-portal-git-04f23c7.md) records scope, enforced budgets, requests, sizes, diagnostics and query digests. API/PR and real v2 salvage trials remain pending.

Functional subsystems evolve together without additional approval gates. Focused checks run during development; coherent final acceptance runs on the combined tree. Historical test counts, exact minimum SQLite lanes and converter predecessor reenactments are retired requirements.

## Preservation and scope

Ordinary acceptance uses synthetic fixtures; separately scoped real-world trials retain durable repository evidence. Source DB/cache bytes, meaningful identities, exact raw values and observation history remain protected. Optional missing content is reported as partial; critical identity corruption prevents finalization. Queries do not acquire or repair. Runtime writable caches are separate from imported source evidence.

Real-data dry run, deployment and active-catalog cutover remain outside this stride and require separate authorization. Final implementation status and actual executed checks are recorded in `runtime-handoff.md`.
