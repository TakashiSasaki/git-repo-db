# Resource Atlas website branch

This orphan `web` branch owns website presentation, not the Python application or
canonical design decisions. The product and canonical contracts live on `main`:
https://github.com/TakashiSasaki/resource-atlas/tree/main . Follow ADR 0042 there.

Keep at most 1,000 tracked files; run `node scripts/check_web_tree.mjs`. Never
commit node_modules, private checkouts, retained catalogs, build outputs or secrets.
Google AI Studio imports and commits target `web`; do not merge its tree into main.

For UI work run `npm ci`, `npm run dev` and `npm run build`. Root index.html and
website/web share the renderer with the full MkDocs site. This path needs no
Python, product checkout, network API, credentials or live database at runtime.

For full-site/schema work, product-source.json follows ref main. Preparation
resolves it once per attempt and records actual inputs automatically. No manually
maintained product SHA or matching-current-main gate is required. Web lag/failure
never blocks main; prefer deterministic generation and review only changed text.
Use `python scripts/refresh_web.py` for update detection, necessary schema
generation and a persistent manual-review report. `--check` only reports a plan.
Reports/state stay in website/.build/verification/refresh, outside public outputs.
The inspected main revision and actually reused extraction source are separate
diagnostic facts. Pending review is bookkeeping, never a main/release gate.
Run `python scripts/prepare_product.py` to prepare a separate verified product
checkout and source-bound IR, then use website/.venv for Python checks/builds.
See website/README.md. Source SHA/tree, web SHA/tree and neutral IR hash are
different identities. Preserve all citation and provenance checks. Canonical
meaning is changed on main; refresh this branch asynchronously when useful.

Production deployment is a separate manual opt-in, never an ordinary push side
effect. website/AGENTS.md and website/web/AGENTS.md contain the scoped UI rules.

For a cloud CLI credential failure, the verified Git-data fallback procedure is
[github-git-data-publication](.agents/skills/github-git-data-publication/SKILL.md).
The historical relocation ledger is `source-migration.json`.
