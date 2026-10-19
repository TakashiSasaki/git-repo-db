# I2 + I3 integration evidence

The start snapshots in `pr-107.json`, `pr-108.json`, `pr-109.json` record live
GitHub HEAD/tree/base/state/checks at the start of this task. All three matched
the owner's pinned commits, remained open Drafts, and had successful `offline`
and failed `registry-sqlite-3513` checks. Those failures are prior evidence,
not new integration results.

The integration is a real two-parent merge, described in
[the handoff](../../adr0030-i23-integration.md). Final runtime, packaging, hosted
CI and independent review receipts will be added after executing the published
source commit. No full release acceptance is asserted.
