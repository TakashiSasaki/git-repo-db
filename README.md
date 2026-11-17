# Resource Atlas website

This is the independent `web` branch for website authoring and Google AI Studio.
The application and canonical design documents are on
[main](https://github.com/TakashiSasaki/resource-atlas/tree/main).

```sh
npm ci
npm run dev
npm run build
node scripts/check_web_tree.mjs
```

The standalone semantic explorer uses the same renderer/model as the full site.
Editing it needs no product checkout, Python or API keys. Root `index.html` is the
Vite entry; sources live in `website/web/`. This branch stays below 1,000 files.

Full-site work uses `product-source.json` and `python scripts/prepare_product.py`
to obtain verified product inputs in a separate checkout. See
[website/README.md](website/README.md) for source-bound schema/site checks. Update
canonical meaning on main and deliberately refresh the selected product SHA here.

The original source snapshot and all 89 relocations are recorded in
[source-migration.json](source-migration.json). This is a historical move ledger,
not a second editable source for product design.
