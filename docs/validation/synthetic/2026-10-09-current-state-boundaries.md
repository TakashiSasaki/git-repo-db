# Schema 16 conflict-boundary acceptance receipt

This is final local evidence for the implementation above PR #14 HEAD
`3f76d4873d14604b918198ac06c1660d0fa9e1b9`. The working HEAD still named that
baseline while the changes were uncommitted. The [JSON receipt](2026-10-09-current-state-boundaries.json)
records exact runtime/test/script input hashes and raw report hashes. The
submitted commit/tree and hosted CI are recorded in the stacked PR body after
publication; a historical HEAD label is not a claim that the baseline contains
these fixes.

| Executed final check | Actual result |
|---|---|
| Complete ordinary acceptance | **1,509 passed**, 237.55 seconds, four workers |
| Isolated offline Wheel and sdist-derived Wheel installs | **2 passed**, 45.02 seconds, sequential |
| Unique selected cases | **1,511**, exactly matched to collected IDs and JUnit |
| Final failures / errors / skips | **0 / 0 / 0** |
| Available / excluded cases | 1,512 available; one opt-in live case excluded; zero benchmark cases |
| Independent review and execution | **59 passed**, 29.28 seconds, no bootstrap, unchanged before/after input hashes |
| Genuine built-in parser certificate | 13 capabilities, generated from **434 passing relevant cases** in 20 modules |
| Final large pagination | 101 threads and 10,201 comments; **22.22-second call**, original 60-second CLI deadline |
| Fresh complete DDL | Schema 16; 103 tables, 48 queried views, 108 accessed named indexes, 500 installed triggers |
| Trigger DML compilation | INSERT/UPDATE/DELETE compiled for all 97 trigger tables; not a claim of every branch execution |
| FK / integrity / JSON | No FK violations; `ok`; 57 registered JSON fields across 15 categories; regenerated guards byte-equal |
| Static / prose checks | Ruff lint and format, `git diff --check`, report validation and doctor passed |

The independent cases overlap ordinary acceptance; they are not added to the
1,511 unique count. All final ordinary, installed and independent execution ran
without `REPO_CATALOG_TEST_BOOTSTRAP`. The 434-case preliminary execution used
the explicit synthetic bootstrap solely to produce real test evidence before
certificate generation. The generator checked that the pre-run definition
snapshot still matched the exact implementation and complete DDL.

Certificate SHA-256:
`70ff010b7fab399483539b4deeb96d4fbeb3eb9c39adf68f5b766988a842bf61`.
DDL SHA-256:
`d29295ce86ee60c67d0abb1b88bf5e8d94d9da5bb0b60b5d1e2e56fc02640aed`.
Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19, Linux.

The two new modules contain 57 cases. Against an isolated unchanged PR #14
checkout, **38 failed and 19 controls passed** without bootstrap. During
development, independent review exposed unproven child-membership projection,
missed dating of transferred alternatives, JSON bool/number proof equivalence
and typed deletion normalization; all were corrected and rechecked. One
preliminary 434-case run failed the older test that permitted a sender's local
check field on the wire. The strengthened contract rejects that field, so its
test now asserts omission, normal import and rejection without altering the
receiver's local check. The entire preliminary suite was rerun: 434 passed.
No failed report contributed to the genuine certificate.

The executable final commands were:

```sh
env -u REPO_CATALOG_TEST_BOOTSTRAP uv run --no-sync python scripts/ci_execute.py \
  current --lane tests --plan artifacts/current-state-boundaries/plan.json
env -u REPO_CATALOG_TEST_BOOTSTRAP uv run --no-sync python scripts/ci_execute.py \
  current --lane packaging --plan artifacts/current-state-boundaries/plan.json
uv run --no-sync python scripts/validate_remaining_contracts.py \
  --output artifacts/current-state-boundaries/schema-checks.json
uv run --no-sync python scripts/audit_current_state.py \
  --output artifacts/current-state-boundaries/inventory.json
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync python scripts/ci_execute.py reports
```

The JSON receipt records the exact independently executed command and every
ordinary/package command argument. Raw XML/profiles are in the ignored
`artifacts/current-state-boundaries/` directory; retained checked-in inventory,
hashes and reproduction scripts describe what they establish. Ordinary suite
behavior and baseline probes complement trigger installation/compilation;
compilation alone does not establish that all 500 trigger branches executed.

No retained user catalog was modified, and no live authenticated Source,
physical power-loss test or non-Linux restore publication was exercised. No
physical body deletion/GC policy, optional archive retention lifetime, new
cross-repository conflict wire format, merge or release was implemented.
The [implementation and remaining specifications](../../current-state-boundaries.md)
and [text retention measurement](2026-10-09-current-state-boundaries-retention.json)
separate these limits from the completed R1/R2 corrections.
