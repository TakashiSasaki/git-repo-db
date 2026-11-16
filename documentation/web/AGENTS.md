# Semantic explorer frontend

Apply [root instructions](../../AGENTS.md) and
[documentation instructions](../AGENTS.md). This directory is the static
technical-documentation frontend, separate from the Python application.

- Root `index.html` is the Vite entry. `main.js` imports the shared CSS and
  `../content/design/semantic-model.json`, then calls `renderApp(model)` from
  `app.js`. Keep presentation and interaction in `app.js`, styling in `style.css`.
- The MkDocs `/design/semantic/` page uses the same renderer, styling and model
  through `../tools/semantic_viz.py`. Change the shared sources rather than a
  generated `dist/`, `.build/` or `site/` copy. Preserve the rest of the MkDocs
  site and its explicit staging boundaries.
- The private root `package.json` and lockfile own Node/Vite dependencies.
  Run `npm ci`, `npm run dev`, `npm run build`, or `npm run preview` from the
  repository root. Building the frontend does not verify the complete MkDocs
  site, product runtime, or RDF pilots.
- The running page needs no API keys, backend, external fetches or retained user
  data. Dependency installation can use the npm registry. Do not add product
  dependencies, initialize catalogs or read real user databases for UI work.
- Model content is a derived analysis. Preserve pinned source revisions and
  citations, qualified identities, and distinctions between runtime behavior,
  accepted design, structural RDF, and the bounded instance pilots. Do not
  infer unsupported guarantees or complete semantic coverage from a diagram.
- Use the frontend build and relevant documentation checks for the changed
  scope. For interaction/layout changes, inspect the affected controls and
  narrow/mobile layout in a browser when available. Product tests are relevant
  when product code or inputs change, not as a routine frontend gate. Report
  the actual verification scope; an external editor import is verified only
  when it has actually been performed.
