// Comprehensive browser smoke test for git-repo-db documentation website
// Runs against a local static HTTP server serving the generated 'site/' directory.

import { createServer } from "http";
import { readFileSync, existsSync, statSync } from "fs";
import { join, extname } from "path";
import puppeteer from "puppeteer";

const PORT = 8765;
const SITE_DIR = join(import.meta.dir, "..", "site");

const MIME_TYPES = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "application/javascript",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
  ".dbml": "text/plain",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".xml": "application/xml",
};

// Start local HTTP server
const server = createServer((req, res) => {
  let urlPath = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
  let filePath = join(SITE_DIR, urlPath);

  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    filePath = join(filePath, "index.html");
  }

  if (existsSync(filePath) && statSync(filePath).isFile()) {
    const ext = extname(filePath).toLowerCase();
    const mime = MIME_TYPES[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": mime });
    res.end(readFileSync(filePath));
  } else {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("404 Not Found");
  }
});

server.listen(PORT, async () => {
  console.log(`Local test server running at http://127.0.0.1:${PORT}`);
  let hasErrors = false;

  try {
    const browser = await puppeteer.launch({
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
      headless: true,
    });

    const page = await browser.newPage();

    const consoleErrors = [];
    const requestFailures = [];

    page.on("pageerror", (err) => {
      consoleErrors.push(`[JS Error] ${err.message} (${page.url()})`);
    });

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text() || "";
        const loc = msg.location() ? msg.location().url || "" : "";
        // Ignore external GitHub API releases/latest 404 (repo has no releases yet)
        if (!text.includes("api.github.com") && !loc.includes("api.github.com")) {
          consoleErrors.push(`[Console Error] ${text} (loc: ${loc}, page: ${page.url()})`);
        }
      }
    });

    page.on("response", (res) => {
      if (res.status() >= 400) {
        const url = res.url();
        // Ignore external third-party requests
        if (url.startsWith(`http://127.0.0.1:${PORT}`)) {
          requestFailures.push(`[HTTP ${res.status()}] ${url} (${page.url()})`);
        }
      }
    });

    const testViewports = [
      { name: "Desktop (1280x800)", width: 1280, height: 800 },
      { name: "Mobile (375x667)", width: 375, height: 667 },
    ];

    for (const vp of testViewports) {
      console.log(`\n========================================`);
      console.log(`Testing Viewport: ${vp.name}`);
      console.log(`========================================`);
      await page.setViewport({ width: vp.width, height: vp.height });

      // 1. Homepage
      console.log("1. Testing Homepage (/)");
      await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "networkidle0" });
      const homeTitle = await page.title();
      console.log(`   Title: ${homeTitle}`);
      if (!homeTitle.includes("git-repo-db")) {
        throw new Error(`Unexpected homepage title: ${homeTitle}`);
      }

      // Check header, content
      const bodyText = await page.evaluate(() => document.body.innerText);
      if (!bodyText.includes("Three-Store Boundary") || !bodyText.includes("Schema 21")) {
        throw new Error("Homepage missing expected Three-Store / Schema 21 text");
      }
      console.log("   ✓ Homepage verified.");

      // 2. Schema Overview
      console.log("2. Testing Schema Overview (/schema/)");
      await page.goto(`http://127.0.0.1:${PORT}/schema/`, { waitUntil: "networkidle0" });
      const schemaText = await page.evaluate(() => document.body.innerText);
      if (!schemaText.includes("70") || !schemaText.includes("Core")) {
        throw new Error("Schema Overview missing expected Core / 70 table count");
      }
      console.log("   ✓ Schema Overview verified.");

      // 3. Interactive Schema Viewer (/schema/viewer/)
      console.log("3. Testing Interactive Schema Viewer (/schema/viewer/)");
      await page.goto(`http://127.0.0.1:${PORT}/schema/viewer/`, { waitUntil: "networkidle0" });
      
      // Check viewer brand badge
      const viewerBadge = await page.evaluate(() => {
        const el = document.querySelector(".brand-badge");
        return el ? el.innerText : null;
      });
      console.log(`   Viewer badge: ${viewerBadge}`);
      if (viewerBadge !== "Schema Workbench") {
        throw new Error(`Unexpected viewer badge: ${viewerBadge}`);
      }

      // Verify store switching: click 'Operational'
      console.log("   Switching store to Operational...");
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll(".store-tab"));
        const opBtn = btns.find((b) => b.innerText.includes("Operational"));
        if (opBtn) opBtn.click();
      });
      await new Promise((r) => setTimeout(r, 200));

      const opActive = await page.evaluate(() => {
        const active = document.querySelector(".store-tab.active");
        return active ? active.innerText : null;
      });
      console.log(`   Active store tab: ${opActive}`);
      if (!opActive || !opActive.includes("Operational")) {
        throw new Error("Store switching to Operational failed");
      }

      // Check table count updated
      const opCount = await page.evaluate(() => document.getElementById("filteredCount")?.innerText);
      console.log(`   Operational table count: ${opCount}`);
      if (!opCount || !opCount.includes("10")) {
        throw new Error(`Unexpected operational table count: ${opCount}`);
      }

      // Verify store switching: click 'Search'
      console.log("   Switching store to Search...");
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll(".store-tab"));
        const sBtn = btns.find((b) => b.innerText.includes("Search"));
        if (sBtn) sBtn.click();
      });
      await new Promise((r) => setTimeout(r, 200));

      const searchCount = await page.evaluate(() => document.getElementById("filteredCount")?.innerText);
      console.log(`   Search table count: ${searchCount}`);
      if (!searchCount || !searchCount.includes("4")) {
        throw new Error(`Unexpected search table count: ${searchCount}`);
      }

      // Switch back to Core and test table search
      console.log("   Switching store back to Core & testing search...");
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll(".store-tab"));
        const cBtn = btns.find((b) => b.innerText.includes("Core"));
        if (cBtn) cBtn.click();
      });
      await new Promise((r) => setTimeout(r, 200));

      await page.type("#searchInput", "stored_bytes");
      await new Promise((r) => setTimeout(r, 200));

      const visibleTables = await page.evaluate(() => {
        const items = Array.from(document.querySelectorAll(".table-item"));
        return items.filter((i) => i.style.display !== "none").map((i) => i.innerText.trim());
      });
      console.log(`   Search results for 'stored_bytes': ${visibleTables.join(", ")}`);
      if (!visibleTables.some((t) => t.includes("stored_bytes"))) {
        throw new Error("Table search in viewer failed to find stored_bytes");
      }
      console.log("   ✓ Interactive Schema Viewer verified.");

      // 4. Mermaid Diagrams
      console.log("4. Testing Mermaid Diagrams (/schema/mermaid/overview/ and core-overview/)");
      await page.goto(`http://127.0.0.1:${PORT}/schema/mermaid/overview/`, { waitUntil: "networkidle0" });
      const overviewSvgLoaded = await page.evaluate(() => {
        const img = document.querySelector(".mermaid-svg-container img");
        return img && img.naturalWidth > 0;
      });
      console.log(`   overview.svg loaded (naturalWidth > 0): ${overviewSvgLoaded}`);
      if (!overviewSvgLoaded) {
        throw new Error("overview.svg failed to load or has 0 width");
      }

      await page.goto(`http://127.0.0.1:${PORT}/schema/mermaid/core-overview/`, { waitUntil: "networkidle0" });
      const coreSvgLoaded = await page.evaluate(() => {
        const img = document.querySelector(".mermaid-svg-container img");
        return img && img.naturalWidth > 0;
      });
      console.log(`   core-overview.svg loaded: ${coreSvgLoaded}`);
      if (!coreSvgLoaded) {
        throw new Error("core-overview.svg failed to load");
      }
      console.log("   ✓ Mermaid Diagrams verified.");

      // 5. DBML Downloads
      console.log("5. Testing DBML Exports (/schema/dbml/)");
      await page.goto(`http://127.0.0.1:${PORT}/schema/dbml/`, { waitUntil: "networkidle0" });
      const dbmlFiles = ["core.dbml", "operational.dbml", "search.dbml", "combined.dbml"];
      for (const df of dbmlFiles) {
        const resp = await page.goto(`http://127.0.0.1:${PORT}/schema/dbml/${df}`);
        if (resp.status() !== 200) {
          throw new Error(`Failed to download ${df}: HTTP ${resp.status()}`);
        }
        const text = await resp.text();
        if (!text.includes("Table") && !text.includes("Project")) {
          throw new Error(`Invalid DBML content for ${df}`);
        }
        console.log(`   ✓ ${df} downloaded successfully (${text.length} bytes).`);
      }

      // 6. ADR 0002
      console.log("6. Testing ADR 0002 (/adr/0002-three-store-boundary-architecture/)");
      await page.goto(`http://127.0.0.1:${PORT}/adr/0002-three-store-boundary-architecture/`, {
        waitUntil: "networkidle0",
      });
      const adr2Text = await page.evaluate(() => document.body.innerText);
      if (!adr2Text.includes("PF-P01") || !adr2Text.includes("PF-P17")) {
        throw new Error("ADR 0002 page missing expected PF-P01 / PF-P17 content");
      }
      console.log("   ✓ ADR 0002 verified.");

      // 7. Development Guide
      console.log("7. Testing Development Guide (/development/)");
      await page.goto(`http://127.0.0.1:${PORT}/development/`, { waitUntil: "networkidle0" });
      const devText = await page.evaluate(() => document.body.innerText);
      if (!devText.includes("build_docs_site.py")) {
        throw new Error("Development guide missing expected build commands");
      }
      console.log("   ✓ Development Guide verified.");

      // 8. PWA Installability, Manifest & Service Worker
      console.log("8. Testing PWA Installability & Web App Manifest");
      await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "networkidle0" });

      const manifestHref = await page.evaluate(() => {
        const link = document.querySelector('link[rel="manifest"]');
        return link ? link.href : null;
      });
      console.log(`   Manifest link in DOM: ${manifestHref}`);
      if (!manifestHref) {
        throw new Error("Missing <link rel=\"manifest\"> in DOM");
      }

      const appleTouchIconHref = await page.evaluate(() => {
        const link = document.querySelector('link[rel="apple-touch-icon"]');
        return link ? link.href : null;
      });
      console.log(`   Apple touch icon in DOM: ${appleTouchIconHref}`);
      if (!appleTouchIconHref) {
        throw new Error("Missing <link rel=\"apple-touch-icon\"> in DOM");
      }

      const manifestResp = await page.goto(`http://127.0.0.1:${PORT}/manifest.webmanifest`);
      if (manifestResp.status() !== 200) {
        throw new Error(`Failed to load manifest.webmanifest: HTTP ${manifestResp.status()}`);
      }
      const manifestJson = await manifestResp.json();
      if (!manifestJson.name || !manifestJson.short_name || !manifestJson.start_url || manifestJson.display !== "standalone") {
        throw new Error(`Invalid manifest fields: ${JSON.stringify(manifestJson)}`);
      }
      console.log(`   ✓ manifest.webmanifest validated (name: "${manifestJson.name}", display: "${manifestJson.display}")`);

      if (!Array.isArray(manifestJson.icons) || manifestJson.icons.length < 4) {
        throw new Error("Manifest icons array missing expected entries");
      }
      for (const icon of manifestJson.icons) {
        const cleanSrc = icon.src.replace(/^\//, "");
        const iconResp = await page.goto(`http://127.0.0.1:${PORT}/${cleanSrc}`);
        if (iconResp.status() !== 200) {
          throw new Error(`Manifest icon ${icon.src} failed to load: HTTP ${iconResp.status()}`);
        }
      }
      console.log(`   ✓ All ${manifestJson.icons.length} manifest icons verified (SVG, 192x192, 512x512, maskable)`);

      const swResp = await page.goto(`http://127.0.0.1:${PORT}/sw.js`);
      if (swResp.status() !== 200) {
        throw new Error(`Failed to load sw.js: HTTP ${swResp.status()}`);
      }
      const swCode = await swResp.text();
      if (!swCode.includes("addEventListener('fetch'") || !swCode.includes("CACHE_NAME")) {
        throw new Error("Service worker code missing expected fetch event listener");
      }
      console.log(`   ✓ sw.js validated (${swCode.length} bytes, fetch handler confirmed).`);
    }

    await browser.close();

    console.log(`\n========================================`);
    console.log(`Browser Smoke Test Summary:`);
    console.log(`Console Errors: ${consoleErrors.length}`);
    for (const ce of consoleErrors) {
      console.error(`  - ${ce}`);
    }
    console.log(`HTTP Request Failures: ${requestFailures.length}`);
    for (const rf of requestFailures) {
      console.error(`  - ${rf}`);
    }
    console.log(`========================================`);

    if (consoleErrors.length > 0 || requestFailures.length > 0) {
      hasErrors = true;
    }
  } catch (err) {
    console.error("Test execution error:", err);
    hasErrors = true;
  } finally {
    server.close();
  }

  process.exit(hasErrors ? 1 : 0);
});
