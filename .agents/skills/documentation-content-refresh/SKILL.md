---
name: documentation-content-refresh
description: Refresh derived project documentation against a selected product revision while separating runtime, opt-in implementation, accepted architecture, and historical evidence. Use for milestone or periodic documentation reconciliation, not product feature work.
---

# Bounded documentation content refresh

Follow [website/AGENTS.md](../../../website/AGENTS.md), root AGENTS.md
and ADR 0035. This procedure grants no merge, publication, allowlist expansion,
or change to product or design authority.

1. Pin the selected product commit and tree once; record the documentation
   commit/tree separately. Inspect concurrent work. Do not chase moving main.
   When the request says latest, compare the initial checkout with the remote
   default branch before pinning it. A prepared environment can lag behind merged
   work, including entire newly added modeling tools. Fetch and select the agreed
   source safely; do not infer current tool absence from an older checkout.
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

## Directory reconciliation

Before moving a guide, run `website/.venv/bin/python website/tools/inventory_content.py`
from the repository root to enumerate tracked roles. Map every changed path's imports, generated inputs, tests,
workflow filters and links. Keep canonical contracts, machine-consumed inputs and
historical evidence in their existing locations unless a separately reviewed
contract authorizes change. Preserve historical body bytes when updating navigation banners. Update the explicit inventory when
adding any new file, and run the ownership/link tests;
never classify an unknown location by guessing. Review the final file inventory
and any exception rather than assuming a directory name establishes authority.

## Shared interactive diagrams

For semantic explorer interaction/layout changes, check both the root Vite build
and the MkDocs renderer. Use `website/tools/test_semantic_browser.mjs` with
`DOCS_SITE_DIR=dist SEMANTIC_ROUTE=/` for Vite, and with `DOCS_SITE_DIR` pointing
to the built site for MkDocs (default route `/design/semantic/`). Supply an
available Chromium through `DOCS_BROWSER` and a separately installed Puppeteer
through `DOCS_PUPPETEER_MODULE`; keep browser tooling out of the Python product.

A verified narrow-screen failure let 375px pass while Fit clipped the SVG at
360px: a fixed minimum zoom exceeded the scale required by the actual viewport.
Keep the fit scale reachable below manual zoom defaults. Check the SVG's rendered
width/height and the scroll viewport's internal overflow at 320px and 360px,
in addition to wider interaction checks. Page-level overflow alone misses a
clipped diagram inside an intentionally scrollable region. This procedure is
for changed diagram behavior, not a browser gate on unrelated prose updates.

Cite the meaning of a relation directly, rather than only the existence of its
endpoints. For example, a typed Context-to-Git reference and the non-authority of
a Search projection need their code/decision clauses, not just key/table shapes.
