# Catalog3 operational runtime stride

Starting implementation: `3af3df84372354e972772b5c9600dfeeae0f0e15` (PR #1 head), incorporated by fast-forward from the original checkout at `9a4110185d7e7abffc291f9cfd118ca71587f998`.

## Implemented functional paths

1. Packaged the shared final catalog3 schema, mutable runtime store and evidence-based import finalization.
2. Ordinary source discovery and Git/GitHub persistence now use catalog3; REST/GraphQL history, sealed listings and restart boundaries remain functional.
3. Ordinary queries/search and doctor/backup/restore/cache/index maintenance now use catalog3 transaction snapshots.
4. One packaged resumable guarded offline v2 importer retains typed archive/evidence; phase/predecessor compatibility machinery is retired.
5. CI uses one working toolchain, changed-file selection and every surviving ordinary test file; minimum-version and historical count gates are retired.
6. Focused synthetic fresh/imported, incremental/resume, preservation/recovery and installed-import checks passed. Complete hosted acceptance and installed wheel/sdist checks are pending; results will be recorded in the functional handoff.

Functional subsystems evolve together without additional approval gates. Focused checks run during development; coherent final acceptance runs on the combined tree. Historical test counts, exact minimum SQLite lanes and converter predecessor reenactments are retired requirements.

## Preservation and scope

Only synthetic fixtures are used. Source DB/cache bytes, meaningful identities, exact raw values and observation history remain protected. Optional missing content is reported as partial; critical identity corruption prevents finalization. Queries do not acquire or repair. Runtime writable caches are separate from imported source evidence.

The separately authorized real-data dry run, deployment and active-catalog cutover remain outside this stride. Final implementation status and actual executed checks will be recorded in `runtime-handoff.md`.
