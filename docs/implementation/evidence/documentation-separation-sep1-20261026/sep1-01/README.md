# SEP1-01 formatter correction

The original c1bdf76a source failed locked Ruff0.16.10 format checking on schema_inventory.py and test_schema_inventory.py. `format-before.log` preserves the reproduced exit1 finding. Applied only the locked formatter to those two files; both complete ASTs are unchanged. Ruff0.16.10 format --check and lint now pass on all four touched Python files. Focused tests rerun:32 passed, no failures/skips (`focused.xml`).

IR, all16 rendered artifact hashes and audit JSON/Markdown still exactly equal the original-main snapshot in ../output-hashes.json. Original source/evidence and reviewer failure remain history; this correction does not imply previous formatting passed. `summary.json` binds new source hashes without self-referential commit metadata. PR source SHA/tree is pinned in PR metadata.

No SEP0 rebase, cutover, adopted ADR, main/settings change or broad release qualification. Source remains stacked on original ab7b5334; corrected SEP0 design125d4af9 is a separate reviewed dependency to reconcile later.
