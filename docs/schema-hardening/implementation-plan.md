# Catalog3 operational runtime stride

Starting implementation: `3af3df84372354e972772b5c9600dfeeae0f0e15` (PR #1 head), incorporated by fast-forward from the original checkout at `9a4110185d7e7abffc291f9cfd118ca71587f998`.

## Work in progress

1. Package the final catalog3 schema; implement a mutable runtime store and explicit import finalization.
2. Move ordinary source discovery and Git/GitHub persistence to catalog3, sharing domain rules with offline salvage where useful.
3. Integrate ordinary queries/search and doctor/backup/restore/cache maintenance.
4. Keep one resumable, guarded offline v2 importer, with retained archive/evidence and no historical phase compatibility requirements.
5. Simplify CI to one working toolchain and risk-proportionate selections.
6. Validate fresh/imported runtime, incremental/resume, preservation/recovery and installed artifacts; write the functional handoff.

Functional subsystems evolve together without additional approval gates. Focused checks run during development; coherent final acceptance runs on the combined tree. Historical test counts, exact minimum SQLite lanes and converter predecessor reenactments are retired requirements.

## Preservation and scope

Only synthetic fixtures are used. Source DB/cache bytes, meaningful identities, exact raw values and observation history remain protected. Optional missing content is reported as partial; critical identity corruption prevents finalization. Queries do not acquire or repair. Runtime writable caches are separate from imported source evidence.

The separately authorized real-data dry run, deployment and active-catalog cutover remain outside this stride. Final implementation status and actual executed checks will be recorded in `runtime-handoff.md`.
