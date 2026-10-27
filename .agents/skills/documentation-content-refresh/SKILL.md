---
name: documentation-content-refresh
description: Refresh derived project documentation against a selected product revision while separating runtime, opt-in implementation, accepted architecture, and historical evidence. Use for milestone or periodic documentation reconciliation, not product feature work.
---

# Bounded documentation content refresh

Follow [documentation/AGENTS.md](../../../documentation/AGENTS.md), root AGENTS.md
and ADR 0035. This procedure grants no merge, publication, allowlist expansion,
or change to product or design authority.

1. Pin the selected product commit and tree once; record the documentation
   commit/tree separately. Inspect concurrent work. Do not chase moving main.
2. Inventory entry pages and dated guides. Classify each consequential claim as
   actual normal runtime, implemented opt-in, accepted target, or historical
   evidence. Trace runtime/activation claims to parser, service, adapters and
   DDL, and design claims to accepted ADRs and scoped supersessions. Mark an
   unknown as unknown; a previous test count is not proof of current behavior.
3. Update derived guides and navigation with audience, source scope, and exact
   revision links. Keep historical reports and receipts intact; do not introduce
   a second editable ADR or publish new source files by widening the staging
   allowlist. Correct known false claims without making documentation currency a
   product check. Preserve existing source revision/date provenance and avoid
   implying that schema IR validation verifies all handwritten explanations.
4. Test documentation in its own locked environment, including affected runtime
   reference tests, site staging/build, safety, provenance, sitemap and PWA
   configuration as appropriate. Product validation, if needed, must use the
   verified product environment. Report skipped rendering, failed setup, and
   unverified runtime or release scope. Never turn old non-successes into passes.
5. Request independent review of exact commit/tree and evidence. Do not merge or
   deploy without separate authorization. In handoff record source SHA/tree,
   changed scope, tests, unknowns, remaining target and historical limitations.

A demonstrated recurring hazard is conflating three normal schema formats, four
opt-in P1 factory entries and five accepted responsibility boundaries as file
counts or default activation. Inspect the actual initialization and lazy-open
paths and the separate Access CLI; verify with the documentation runtime reference
tests when the verified product environment is available. ADR 0035 does not
require every product change to wait for a documentation build.
