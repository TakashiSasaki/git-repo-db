// Optional real-browser regression. No product state or external web access.
// DOCS_PUPPETEER_MODULE=/absolute/node_modules/puppeteer-core node ...
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve, dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.DOCS_PUPPETEER_MODULE || "puppeteer");
const here = dirname(fileURLToPath(import.meta.url));
const site = resolve(process.env.DOCS_SITE_DIR || join(here, "../site"));
const evidence = resolve(here, "../.build/browser-evidence");
mkdirSync(evidence, { recursive: true });
const types = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
};
const server = createServer((req, res) => {
  try {
    const route = new URL(req.url, "http://localhost").pathname;
    let path = resolve(site, "." + decodeURIComponent(route));
    if (!path.startsWith(site + "/") && path !== site)
      throw Error("outside preview");
    if (statSync(path).isDirectory()) path = join(path, "index.html");
    res.setHeader(
      "Content-Type",
      types[extname(path)] || "application/octet-stream",
    );
    res.end(readFileSync(path));
  } catch {
    res.writeHead(404);
    res.end("not found");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await puppeteer.launch({
  headless: true,
  executablePath: process.env.DOCS_BROWSER || "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
});
const failures = [],
  checks = [];
try {
  const page = await browser.newPage();
  page.on("pageerror", (err) => failures.push(String(err)));
  page.on("response", (r) => {
    if (r.status() >= 400 && r.url().startsWith(base))
      failures.push(`${r.status()} ${r.url()}`);
  });
  async function click(selector) {
    await page.click(selector);
    await page.waitForFunction(() => document.querySelector("#result h2"));
  }
  async function heading(text) {
    await page.waitForFunction(
      (t) => document.querySelector("#result h2")?.textContent === t,
      {},
      text,
    );
  }
  async function noOverflow() {
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
  }
  for (const vp of [
    { width: 1280, height: 800 },
    { width: 375, height: 667 },
  ]) {
    await page.setViewport(vp);
    await page.goto(base + "/design/", { waitUntil: "networkidle0" });
    await heading("5つの責務");
    assert.equal(
      await page.$$eval("#result .grid article", (x) => x.length),
      5,
    );
    await noOverflow();
    await page.screenshot({
      path: join(evidence, `overview-${vp.width}.png`),
      fullPage: false,
    });
    await click('#result a[href*="store=core"]');
    await heading("Core の内部");
    await click('#result a[href*="entity=design%2Fcore%2Fref_observations"]');
    await heading("RefObservation");
    await click('#result a[href*="level=constraints"]');
    await heading("RefObservation — 意味キー・制約");
    assert(
      await page.$eval("#result", (x) =>
        x.textContent.includes(
          "(observation_origin_uuidv4, ref_observation_uuidv7)",
        ),
      ),
    );
    await noOverflow();
    await page.screenshot({
      path: join(evidence, `constraints-${vp.width}.png`),
      fullPage: false,
    });
    await page.click("#back");
    await heading("RefObservation");
    assert(await page.$("#result .flow"));
    await noOverflow();
    const positioned = await page.$eval(
      "#result .flow",
      (flow, mobile) => {
        const rects = [...flow.children].map((x) => x.getBoundingClientRect());
        return mobile
          ? rects[0].bottom <= rects[1].top && rects[1].bottom <= rects[2].top
          : rects[0].right <= rects[1].left && rects[1].right <= rects[2].left;
      },
      vp.width < 640,
    );
    assert(positioned);
    await page.screenshot({
      path: join(evidence, `relationships-${vp.width}.png`),
      fullPage: false,
    });
    // A relation moves with its fully qualified model/store/entity route.
    await click('#result a[href*="entity=design%2Fcore%2Frepositories"]');
    await heading("Repository");
    await page.click("#back");
    await heading("RefObservation");
    await page.click("#list");
    await page.waitForSelector("#result table");
    assert(await page.$("#result table"));
    assert.equal(
      await page.$eval("#list", (x) => x.getAttribute("aria-pressed")),
      "true",
    );
    // Same name in two stores must keep the selected store in a deep link.
    for (const store of ["core", "context"]) {
      await page.goto(
        base +
          "/design/#" +
          new URLSearchParams({
            model: "accepted-design",
            store,
            entity: `design/${store}/coverage_claims`,
            view: "diagram",
          }),
      );
      await heading(store === "core" ? "Core Coverage" : "Context Coverage");
      assert(
        await page.$eval(
          "#result .identity",
          (x, s) => x.textContent.includes(`design/${s}/coverage_claims`),
          store,
        ),
      );
    }
    await page.goto(
      base +
        "/design/#" +
        new URLSearchParams({
          store: "access",
          entity: "design/access/scope_locators",
          level: "constraints",
        }),
    );
    await heading("Scope Locator registrations — 意味キー・制約");
    assert(
      await page.$eval("#result", (x) => x.textContent.includes("P 実装提案")),
    );
    const href = await page.$eval("#result .citations a", (x) => x.href);
    await page.goto(href, { waitUntil: "networkidle0" });
    assert((await page.title()).includes("ADR 0029"));
    assert(await page.$("h1"));
    await page.goBack({ waitUntil: "networkidle0" });
    await heading("Scope Locator registrations — 意味キー・制約");
    // Search and view changes retain scope; a wrong model fails visibly.
    await page.goto(base + "/design/");
    await page.type("#query", "Notes");
    await page.click("#list");
    assert((await page.url()).includes("q=Notes"));
    await page.goto(base + "/design/#model=unknown");
    assert(
      await page.$eval("#result", (x) =>
        x.textContent.includes("見つかりません"),
      ),
    );
    checks.push({
      viewport: vp,
      designSelection: true,
      relationships: true,
      back: true,
      constraints: true,
      qualifiedNames: true,
      citations: true,
      search: true,
      noPageOverflow: true,
    });
  }
  // Exercise the implemented viewer's actual navigation and implicit composite FK
  // renderer with disposable in-memory browser data, without changing neutral IR.
  await page.goto(base + "/schema/viewer/", { waitUntil: "networkidle0" });
  const runtime = await page.evaluate(() => {
    const before = JSON.stringify(SCHEMA_DATA);
    const fixture = structuredClone(
      SCHEMA_DATA.stores.core.tables.repositories,
    );
    SCHEMA_DATA.stores.operational.tables.repositories = fixture;
    navigateTable("operational", "repositories");
    const qualified =
      currentStore === "operational" && currentTable === "repositories";
    navigateTable("core", "repositories");
    const other = currentStore === "core" && currentTable === "repositories";
    SCHEMA_DATA.stores.core.tables.fixture_parent = {
      primary_key: ["origin", "observation"],
    };
    const implicit = referencedColumns({
      target_table: "fixture_parent",
      to_columns: [null, null],
    });
    const explicit = referencedColumns({
      target_table: "fixture_parent",
      to_columns: ["b", "a"],
    });
    delete SCHEMA_DATA.stores.operational.tables.repositories;
    delete SCHEMA_DATA.stores.core.tables.fixture_parent;
    return {
      qualified,
      other,
      implicit,
      explicit,
      neutralUnchanged: JSON.stringify(SCHEMA_DATA) === before,
    };
  });
  assert.deepEqual(runtime, {
    qualified: true,
    other: true,
    implicit: ["origin", "observation"],
    explicit: ["b", "a"],
    neutralUnchanged: true,
  });
  assert.deepEqual(failures, []);
  writeFileSync(
    join(evidence, "results.json"),
    JSON.stringify(
      { browser: await browser.version(), checks, runtime, failures },
      null,
      2,
    ) + "\n",
  );
  console.log(
    `Browser checks passed: ${checks.length} viewports; qualified runtime navigation and implicit composite FK; ${await browser.version()}`,
  );
} finally {
  await browser.close();
  server.close();
}
