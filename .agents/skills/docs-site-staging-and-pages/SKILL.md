---
name: docs-site-staging-and-pages
description: Stage, build, and publish developer documentation sites for multi-store SQLite architectures with explicit publication allowlists, MkDocs Material directory URLs, standalone HTML viewer collision avoidance, build-time Mermaid SVG rendering, and GitHub Actions Pages deployment isolation. Use when adding or updating public documentation, managing GitHub Pages workflows, or debugging static asset routing.
---

# Documentation Staging, Build, and GitHub Pages Invariants

When deploying public developer documentation websites containing database schema visualizations, standalone HTML workbenches, and Architecture Decision Records (ADRs), adhere to these verified engineering procedures.

---

## 1. Explicit Publication Allowlist vs. Full Tree Exposure

### Symptom & Hazard
Directly pointing MkDocs `docs_dir` to the repository `docs/` or building the repository root exposes unreviewed historical proposals, internal validation logs, draft schemas, private scripts, and unvetted artifacts to the public internet.

### Rule & Invariant
- **Never publish unvetted repository files**: Build through an explicit staging directory (`.build/docs-source/`).
- Only allowlist approved public technical documents: homepage, architecture overview, ADR 0001/0002, schema README, and schema workbench assets.
- Validate the generated distribution (`site/`) with an automated allowlist checker verifying file extensions (`.html`, `.css`, `.js`, `.svg`, `.dbml`, `.json`) and rejecting forbidden patterns (`*.sqlite3`, `*.py`, `*.sh`, `*.key`, `*.pem`, `*.env*`).

---

## 2. Standalone HTML Viewer & Index Collision Avoidance

### Symptom
A documentation directory contains both `docs/schema/README.md` and `docs/schema/index.html`. MkDocs transforms `README.md` into `index.html`, causing a filename collision that either overwrites the standalone workbench or breaks the directory index.

### Rule & Invariant
- **Partition URLs during staging**:
  - Stage `docs/schema/README.md` as `schema/index.md` (serving the schema overview at `/schema/`).
  - Stage `docs/schema/index.html` as `schema/viewer/index.html` (serving the standalone viewer at `/schema/viewer/`).
- Preserve the standalone viewer's self-contained HTML/CSS/JS without wrapping it in MkDocs theme templates.
- Update internal navigation links in `schema/index.md` to reference `viewer/index.html`.

---

## 3. MkDocs Directory URLs & Relative Asset Resolution

### Symptom
With MkDocs `use_directory_urls: true` (default), a page `schema/mermaid/overview.md` compiles to `site/schema/mermaid/overview/index.html`. An embedded raw HTML tag `<img src="overview.svg">` fails to load (404) because the browser resolves `overview.svg` relative to the subfolder `overview/`, while the asset was placed in `schema/mermaid/overview.svg`.

### Rule & Invariant
- For each generated diagram `<slug>.svg`, place the asset in **both**:
  1. `schema/mermaid/<slug>.svg` (for direct link access and parent index references).
  2. `schema/mermaid/<slug>/<slug>.svg` (for relative `<img src="<slug>.svg">` inside the directory URL).
- Alternatively, reference `../<slug>.svg` from the page Markdown. Populating both paths guarantees zero 404s across all navigation modes.

---

## 4. Headless Mermaid Rendering under Linux Containers

### Symptom
Running `@mermaid-js/mermaid-cli` (`mmdc`) fails in CI runners or containerized Linux environments with:
`Fatal: No usable sandbox! If you are running on Ubuntu 23.10+ ... try using --no-sandbox.`

### Rule & Invariant
- Always pass a Puppeteer configuration file enabling `--no-sandbox` and `--disable-setuid-sandbox`:
  ```json
  { "args": ["--no-sandbox", "--disable-setuid-sandbox"] }
  ```
- Invoke with `-p puppeteer-config.json` via `mmdc`, `bunx`, or `npx --yes @mermaid-js/mermaid-cli@12.0.0`.

---

## 5. YAML Navigation Colons & Escaping

### Symptom
Unquoted Japanese or English navigation labels containing colons (e.g. `Core: 全体構造マップ: schema/mermaid/...`) cause YAML scanner errors: `mapping values are not allowed here`.

### Rule & Invariant
- Wrap all `mkdocs.yml` navigation labels containing colons in double quotes:
  ```yaml
  nav:
    - "Core: 全体構造マップ": schema/mermaid/core-overview.md
    - "ADR 0001: 開発・リリース検証ライフサイクル": adr/0001-validation-lifecycle-architecture.md
  ```

---

## 6. Root `/site/` vs. Subdirectory `site/` in `.gitignore`

### Symptom
Writing `site/` without a leading slash in `.gitignore` causes Git to ignore any subdirectory named `site/`, including `docs/site/`, silently excluding documentation sources from commits.

### Rule & Invariant
- Use `/site/` with a leading slash in `.gitignore` to match only the build output directory at the repository root.

---

## 7. GitHub Actions Pages Security & Concurrency Boundaries

### Invariants for `pages.yml`
1. **Separation of Concerns**:
   - `build` job requires only `permissions: contents: read`. No deployment credentials permitted.
   - `deploy` job runs strictly for `github.ref == 'refs/heads/main' && github.event_name != 'pull_request'`.
   - `deploy` job requires `pages: write` and `id-token: write` under the `github-pages` environment.
2. **Concurrency Safety**:
   - Concurrency group: `pages-${{ github.event.pull_request.number || github.ref }}`.
   - Set `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`: allow fast cancellation on PR iterations, but **never** cancel an in-flight deployment on `main`.
3. **Artifact Deployment**:
   - Deploy only the prepared static directory (`site/`) using official `actions/upload-pages-artifact@v3` and `actions/deploy-pages@v4`.
   - Never push directly to a `gh-pages` branch. Never upload repository root.
   - Do not commit or upload a `CNAME` file when Pages custom domain is already managed via repository settings.

---

## 8. PWA Installability & Web App Manifest Assets

### Invariants for PWA Support
1. **Web App Manifest**:
   - Provide `manifest.webmanifest` (and `manifest.json`) at the site root with `name`, `short_name`, `start_url: "/"`, `display: "standalone"`, and icons.
   - Whitelist `.webmanifest` in `PUBLIC_ALLOWLIST_EXTENSIONS`.
2. **Icons Specification**:
   - Vector master: SVG icon (`icon.svg`) and maskable SVG (`icon-maskable.svg` with 80% safe zone).
   - High-resolution PNGs: 192x192, 512x512, 180x180 (Apple touch icon), 32x32, 16x16.
   - Generated reproducibly via `scripts/generate_pwa_icons.js` using Puppeteer.
3. **Template & Viewer Injection**:
   - Inject `<link rel="manifest">`, `<link rel="apple-touch-icon">`, and `<meta name="theme-color">` via `overrides/main.html` for MkDocs pages.
   - Inject identical head tags during staging for the standalone schema viewer at `/schema/viewer/index.html`.
4. **Service Worker (`sw.js`)**:
   - Register at root scope `/` via `pwa.js`.
   - Provide network-first navigation caching with offline fallback and stale-while-revalidate for static assets.
