# Schema 21 jobs/cache/Search remediation evidence

PR: https://github.com/TakashiSasaki/git-repo-db/pull/91
Dependency: https://github.com/TakashiSasaki/git-repo-db/pull/93

- Untouched main: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`.
- Test-contract checkpoint: `b6e0ba5b67ab9b0a318d1c5bb557698cef244179`, tree `5d82739e97e362e1fb9b75a29967440857684043`.
- Stacked test-contract source exposing hidden defect: `172342bc7490d3594aa71aa5c27c3d861ae52d3a`. `src/repo_catalog/adapters/sqlite/index.py` has exactly the same Git blob as untouched main.
- Corrected source: `31b7bf3d734c92ad10d22cca233d4318932dfce3`, tree `e18c5e02ea6878f484b56229eb45453904093d47`.
- Ordinary collection-dependency merge: `c5db95520f2d54dac675c6d3aa3be8f955cad4e7`, tree `d9f8e7a7d9a6d59a2c99a724d15a27d4fa2d3339`. Production, all selected test modules and support Python inputs are byte-identical to the frozen corrected source; changed disposition JSON addresses other collection nodes.

## Proven causes and corrections

1. Jobs, attempts and cache SQL in old tests still addressed Core. Tests now observe the real Operational store, including installing atomic-result failure triggers on the same physical connection JobService writes. Frozen source plans, secret-reference protection, no-job-before-validation, partial/complete results, attempts and actual CLI restart behavior remain asserted.
2. Acquisition-progress-to-Git-acquisition joins crossed the physical boundary. Tests now resolve acquisition IDs in Operational and assert immutable acquisition facts in Core with explicit separate queries; no ATTACH is introduced.
3. Backup assertions expected retired `content_locations` and copied cache locators. PF-P08 excludes Operational state. Replacement assertions preserve exact durable Core rows, absent cache/search tables in the backup, no copied secondary files, fresh correctly owned empty Operational state and an unchanged source locator.
4. Search test SQL addressed Core. Routing it to Search exposed a real production defect: obsolete documents held by the previous generation were copied into every new generation. Rebuild now filters generation inputs using actual current projection keys from the pinned Core snapshot, preserves prior ready inputs until successful replacement, and prunes obsolete documents after retired membership cleanup. No DDL or Core fact changes.

`current-query.xml`/`.jsonl` proves the masked Search defect after SQL relocation on unchanged production. `search-fix-3.xml`/`.jsonl` records 2 passing regressions: the original behavioral assertion and a real 201-issue lifecycle. The latter crosses a wholly obsolete 200-row SQL batch, cancels after new generation creation and verifies the prior ready FTS/membership, repeats replacement twice, creates an empty generation after tombstones, and verifies historical Core text rows are unchanged.

`boundary.xml`/`.jsonl` records 2 passing controls: jobs physically isolated with no attached database, Operational loss preserves admitted source evidence and refuses the old Job, and attempt result/state roll back together on a genuine trigger failure.

`accepted-final-cohort.xml`/`.jsonl` is the clean final 13-module run at the dependency-merged source. See `source-binding.json` and reconciliation JSON for completion and exact nodes.

## Failed experiments and limits

All raw exploratory outputs are retained and must not be substituted for final acceptance. The direct Python invocation lacked virtualenv CLI PATH. Redundant broad pilots were interrupted when a hidden defect required source work; `focused` completed with 48 passed and the single masked Search production failure. Two adversarial test setup iterations used invalid provider ID zero and duplicated provider issue numbers, then corrected those fixtures to real distinct IDs/numbers.

Reviewer A investigated post-ready cleanup failure. A deterministic injected probe and separate real-reader lock counterexample show cleanup can fail while a ready generation exists. There is no binding global all-phase transactional-success contract; failure honestly reports incomplete housekeeping. A provisional warning experiment was discarded and its patch preserved. No cleanup-warning production expansion was committed. `search-final` describes only that discarded experiment, not acceptance source.

No P1–P7 activation, real catalog use, merge, auto-merge or release was performed. Development CI is not complete runtime or release acceptance. Full-repository, distribution and cross-stage acceptance belong to the integrated evidence PR.

The first complete frozen cohort hit the separate `/tmp` filesystem capacity: 87 passed, 3 failed and 14 setup errors, with explicit SQLite disk-full and Git initialization failures. That result remains preserved as `frozen-final-cohort.*`; it is not product acceptance. The clean retry uses `--basetemp=/workspace/jobs-test-temp` on the larger workspace filesystem. Only completed own disposable directories were removed after recording sizes, with raw execution evidence retained.

Final accepted cohort: **104 passed, 0 failed, 0 errors, 0 skipped** in 88.31s; exact JUnit/journal node/status equality. All 24 owned prior-228 nodes and the additional current-main fencing node pass. Existing live/benchmark marker policy remains; the nested pagination stress node is not executed. `accepted-final-reconciliation.json` lists exact nodes and artifact SHA-256. Final dependency evidence-only merge `1700ed37e82a6028cfa40c86b35db7621dd50404` / tree `62208ed7243aaacd45c3a9706dd957cbb1ebb222` includes foundation `7dc31256907aff4412170bc3f3ce3069b2ad89f2`; all `src`, `tests`, `scripts`, `pyproject.toml` and `uv.lock` inputs remain unchanged from tested c5db955.
