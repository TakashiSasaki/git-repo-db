# Independent Resource Atlas website workspace

The orphan `web` branch contains editable website sources. Canonical ADRs,
contracts, product code, ownership inventories and the current runtime guide
belong on `main`. This branch's `product-source.json` follows `ref: main`. Preparation
resolves it once per attempt; no product SHA is maintained in this branch.
See ADR 0042 on main.

## Frontend editing (Google AI Studio)

```sh
npm ci
npm run dev
npm run build
node scripts/check_web_tree.mjs
```

The Node/Vite frontend uses the existing shared `website/web/app.js`, CSS and
semantic JSON. It needs no product checkout, Python or credentials. Never commit
node_modules, dist, private checkouts or generated build directories. Keep the
tracked branch below 1,000 files.

## Complete documentation and schemas

Run the product preparation helper separately from ordinary frontend editing:

```bash
python scripts/prepare_product.py
website/.venv/bin/python website/tools/schema_viz.py --ir website/.build/inputs/inventory.json --format all
website/.venv/bin/python website/tools/schema_viz.py --ir website/.build/inputs/inventory.json --check
```

The helper resolves refs/heads/main once, obtains full history in an external
cache, establishes the verified product Python, runs the neutral schema
producer in a fresh product subprocess, and transfers checked inputs privately.
It also creates the independent `website/.venv` with its locked dependencies.
For local/offline work use `--product-root /absolute/product/path`. This uses
that checkout's HEAD and records local-override mode, without claiming observation
of remote main. A cached checkout with inconsistent bytes is left untouched.
The private product-location.json records requested ref, selection mode, actual
commit/tree and retrieval time after successful preparation. Build tools keep
that snapshot for their whole process; later main updates require no restart.

Build and verification commands obtain source IDs automatically from the
prepared snapshot and this web checkout:

```bash
website/.venv/bin/python -m pytest -q website/tests
website/.venv/bin/ruff check website/tools website/tests scripts
website/.venv/bin/ruff format --check website/tools website/tests scripts
website/.venv/bin/python website/tools/build_docs_site.py --no-mermaid --check
website/.venv/bin/python website/tools/verify_documentation.py --preview
```

`--no-mermaid`/`--preview` produces explicitly labelled placeholders and cannot
establish complete release acceptance. Omit those flags for complete Mermaid
rendering. Web commit/tree, selected product commit/tree and the complete neutral
IR digest remain separate. Input/source hashes, private-output confinement,
pinned citation bodies and the existing publication allowlist remain enforced.
Product work does not wait for this site. Complete release evidence still needs
independent local and hosted product and website obligations, including the moved
main ownership/runtime-reference tests; a green Vite build alone proves neither.

## Updates and publication

Change canonical meaning on main. Refresh this lower-priority branch when useful:
prepare current main, regenerate affected machine-derived outputs and review only
changed explanations. Routine refreshes need no LLM generation. Lag or failure on
web never blocks main. Actual schema changes may need regenerated presentation;
a build record does not certify all handwritten explanations. Generated
copies never become editable ADR authorities. Historical citation paths/revisions
remain exact even if main has since moved a file. The normal/full-model viewers,
semantic explorer, PWA, sitemap and schema URL partition retain their existing
publication boundaries. The current custom domain is unchanged.

The web workflow tests/builds on push and retains preview/verification evidence.
Its runner Python only starts preparation; the product bootstrap selects the
verified Python/SQLite used for extraction and the isolated website environment.
Do not add `setup-python` loader overrides to this bootstrap path: the product
guard correctly refuses them rather than changing the loaded SQLite.
For manual execution, select branch `web` in Actions → pages → Run workflow.
Main retains only a same-path registration notice required by GitHub; running
that notice on main stops with branch-selection instructions and performs no build.
With a working GitHub CLI, complete hosted verification without deployment is:

```sh
gh workflow run pages.yml --ref web -f deploy=false
```

An explicitly authorized production deployment uses the same command with
`-f deploy=true`. The `deploy` input defaults to false. A normal push, migration
or successful build does not publish a new site. The migration's local preview
checks do not claim that a hosted manual dispatch or deployment has been run.
