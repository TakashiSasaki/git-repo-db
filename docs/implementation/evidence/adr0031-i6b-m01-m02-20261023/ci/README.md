# Exact final-HEAD CI verification helper

These read-only stdlib helpers inspect actual timestamped job logs and immutable
GitHub metadata snapshots. They perform no network request, workflow dispatch,
artifact download or remote mutation. The publication agent supplies the final
feature, actual temporary merge checkout, base and PR identities after publishing.
Final-run observations belong outside this immutable evidence commit and are
bound externally in the new Draft PR body.

`verify_development_receipt.py` verifies every indexed payload (currently 21),
marker length/SHA-256, actual ordered merge parents/effective tree, feature/run/
attempt bindings and the Development manifest. It requires
`development_checks_passed`, `full_acceptance=false`, and zero hosted product
pytest cases. Policy/runtime stdlib checks remain distinct from product tests.
`verify_access_receipt.py` verifies the actual indexed Access payloads without
converting a failed outcome into success. JUnit lanes are reported separately
and may overlap. No Release or independent runtime acceptance follows from
receipt consistency.

Example (all JSON snapshots come from supported GitHub read APIs):

```sh
python verify_development_receipt.py --logs actual-job.log \
  --run actual-run.json --feature-commit actual-feature.json \
  --checkout-commit actual-checkout.json --base BASE --pr PR \
  --output NEW_EXTERNAL_OUTPUT
```

The Access helper has the same arguments. It permits checked nested receipt
paths; no payload is executed or blindly extracted. An unreadable or truncated
view fails verification and remains recorded. Pending, failed and never-run
states must be reported directly. Do not download a large artifact simply to
replace available compact logs, retry a historical denied blob, bypass a read
restriction, infer missing bytes or trigger a Release workflow.

## Offline helper validation

`offline-controls-v4.log` records **20 passing stdlib controls**, exit 0. These
are helper checks, not additional product pytest cases. They reuse the existing
saved #151 Development and Access receipts and fresh read-only GitHub commit/run
metadata; no historical artifact was downloaded. The positive CLI verification
of Development is in `offline-positive.json`.

The fresh historical snapshots preserve #151 Development 39955068751 SUCCESS,
#151 Access 39955068823 FAILURE, and #152 Development 39963122681 SUCCESS.
They are historical status observations, not final-new-PR CI.

Earlier observer attempts are retained separately: `offline-controls.log`
failed before tests because a test class named a dictionary `run`, shadowing
`unittest.TestCase.run`; v2 passed 16 controls. Adding Access controls exposed a
wrong historical JUnit filename in the test harness (v3); correcting that path
without changing assertions produced v4's 20 PASS. Product source and tests were
unchanged by this CI helper work.
