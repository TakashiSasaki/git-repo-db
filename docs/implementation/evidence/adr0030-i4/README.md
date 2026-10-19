# ADR 0030 I4 execution evidence

Base: PR #110 `8519056d5b9484eb0cc4dcf9f693285b4e65518a`, tree
`a77503505127367e9378c57c5ab9ee9ae11767f3`. Protected ancestor PRs and main
are not modified. This directory will bind frozen source, raw receipts, actual
SQLite runtime, distribution checks and independent read-only review.

The initial actual SQLite 3.51.3 P6 execution reproduced 27 failures and 23 passes;
there were no skips/errors. All 50 nodes passed after the first projection/fixture
update. Subsequent I4 development runs exposed test setup errors (invalid stale
index injection, wrong budget keyword, order-dependent assertion and a missing
parameter decorator/import); their raw failed attempts are retained separately
from final acceptance. No skip, xfail or failing-node deletion is used.

Final expanded verification, pushed HEAD/tree and review verdict are pending at
this source-freeze checkpoint. This checkpoint does not claim completed runtime
acceptance. See [the implementation contract](../../adr0030-i4-query-search-backup.md).
