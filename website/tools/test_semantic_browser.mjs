// Optional real-browser regression for the shared Vite/MkDocs semantic explorer.
// npm dependencies for this probe belong outside the Python product environment.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync, realpathSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve, dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const puppeteer = require(process.env.DOCS_PUPPETEER_MODULE || "puppeteer");
const here = dirname(fileURLToPath(import.meta.url));
const site = realpathSync(process.env.DOCS_SITE_DIR || join(here, "../site"));
const route = process.env.SEMANTIC_ROUTE || "/design/semantic/";
assert(route.startsWith("/") && !route.includes("?"), "Use a local absolute route");
const variant = route === "/" ? "vite" : "mkdocs";
const evidence = resolve(here, "../.build/browser-evidence");
const model = JSON.parse(readFileSync(join(here, "../content/design/semantic-model.json"), "utf8"));
mkdirSync(evidence, { recursive: true });
const types = { ".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json" };
const server = createServer((req, res) => {
  try {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (pathname === "/favicon.ico") { res.writeHead(204); res.end(); return; }
    let path = resolve(site, "." + decodeURIComponent(pathname));
    if (statSync(path).isDirectory()) path = join(path, "index.html");
    path = realpathSync(path);
    if (!path.startsWith(site + "/")) throw Error("outside preview");
    res.setHeader("Content-Type", types[extname(path)] || "application/octet-stream");
    res.end(readFileSync(path));
  } catch {
    res.writeHead(404); res.end("not found");
  }
});
await new Promise((done) => server.listen(0, "127.0.0.1", done));
const base = `http://127.0.0.1:${server.address().port}`;
const failures = [];
const checks = [];
let browser;
try {
  browser = await puppeteer.launch({ headless: true, executablePath: process.env.DOCS_BROWSER || "/usr/bin/chromium", args: ["--no-sandbox", "--disable-setuid-sandbox"] });
  const page = await browser.newPage();
  page.on("pageerror", (error) => failures.push(String(error)));
  page.on("response", (response) => {
    if (response.url().startsWith(base) && response.status() >= 400)
      failures.push(`${response.status()} ${response.url().slice(base.length)}`);
  });
  await page.setRequestInterception(true);
  page.on("request", (request) => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + "/")) {
      failures.push(`External runtime request: ${request.url()}`);
      request.abort();
    } else request.continue();
  });
  const count = (selector) => page.$$eval(selector, (nodes) => nodes.length);
  async function click(selector) {
    // Settle scrolling before a real pointer action; rapid automation can
    // otherwise click yesterday's coordinates during the UI's smooth scroll.
    await page.$eval(selector, (node) => node.scrollIntoView({ behavior: "instant", block: "center" }));
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
    await page.click(selector);
  }
  async function noOverflow() {
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "Page must not scroll horizontally");
  }
  async function contextCoreArrow() {
    const geometry = await page.evaluate(() => {
      const path = document.querySelector('.graph-edges path[data-source="context"][data-target="core"]');
      const endpoint = path.getPointAtLength(path.getTotalLength());
      const point = new DOMPoint(endpoint.x, endpoint.y).matrixTransform(path.getScreenCTM());
      const target = document.querySelector(".graph-node.core rect").getBoundingClientRect();
      return { gap: point.x - target.right, targetWidth: target.width, insideVerticalSpan: point.y > target.top && point.y < target.bottom };
    });
    assert(geometry.insideVerticalSpan, "Context→Core must point toward the target's side");
    assert(geometry.gap > 0.1 && geometry.gap < geometry.targetWidth * 0.2, "Context→Core endpoint must remain just outside Core, leaving its arrowhead visible");
    return geometry.gap;
  }
  async function applicationMap() {
    assert.equal(await count(".semantic-cluster"), model.domains.length);
    assert.equal(await count(".semantic-node"), model.concepts.length);
    assert.equal(await count(".semantic-edge"), model.relations.length);
    const ids = await page.$$eval(".semantic-node", (nodes) => nodes.map((node) => node.dataset.mapConcept).sort());
    assert.deepEqual(ids, model.concepts.map((c) => c.id).sort());
    // Arrow endpoints must stay outside their target cards at every angle.
    const outside = await page.$$eval(".semantic-edge", (edges) => edges.every((edge) => {
      const path = edge.querySelector(".edge-line");
      const point = path.getPointAtLength(path.getTotalLength());
      const screen = new DOMPoint(point.x, point.y).matrixTransform(path.getScreenCTM());
      const rect = document.querySelector(`.semantic-node[data-map-concept="${edge.dataset.target}"] rect`).getBoundingClientRect();
      return screen.x < rect.left || screen.x > rect.right || screen.y < rect.top || screen.y > rect.bottom;
    }));
    assert(outside, "Every semantic arrow must end outside its target card");
    const path = model.reading_paths.find((p) => p.id === "access-request");
    await page.select("#reading-path", path.id);
    await selected(path.steps[0]);
    assert.equal(await count("#path-guide [data-map-concept]"), path.steps.length);
    assert.equal(await count(".semantic-node.in-path"), new Set(path.steps).size);
    assert.equal(await count(".semantic-edge.emphasized"), path.steps.length - 1);
    assert(await page.$eval("#path-guide", (node) => node.textContent.includes("読む順番")));
    await page.select("#map-concept", "approval");
    await selected("approval");
    assert.equal(await page.$eval("#map-inspector > h3", (node) => node.textContent), model.concepts.find((c) => c.id === "approval").label);
    assert(new URL(page.url()).hash.includes("view=map"));
    await page.goBack();
    await selected(path.steps[0]);
    assert.equal(await page.$eval("#reading-path", (node) => node.value), path.id);
    await page.goForward();
    await selected("approval");
    await page.select("#relation-filter", "execution");
    assert.equal(await count(".semantic-edge:not(.is-hidden)"), model.relations.filter((r) => r.kind === "execution").length);
    await click("#map-nearby");
    assert.equal(await count(".semantic-edge:not(.is-hidden)"), model.relations.filter((r) => r.kind === "execution" && [r.source, r.target].includes("approval")).length);
    // The complete inspector list remains available under a diagram filter.
    assert.equal(await count("#map-inspector .map-relations > li"), model.relations.filter((r) => [r.source, r.target].includes("approval")).length);
    const index = model.relations.findIndex((r) => r.source === "approval" && r.target === "acquisition-request");
    await page.$eval(`.semantic-edge[data-relation="${index}"]`, (node) => node.focus());
    await page.keyboard.press("Enter");
    await page.waitForSelector(".selected-relation");
    assert(await page.$eval(".selected-relation", (node, note) => node.textContent.includes(note), model.relations[index].note));
    const citations = await page.$$eval(".selected-relation .sources a", (nodes) => nodes.map((node) => node.href));
    assert(citations.length && citations.every((href) => href.includes(`/blob/${model.source_revision}/`)));
    await click("#map-reset");
    await selected("repository");
    assert.equal(await count(".semantic-edge:not(.is-hidden)"), model.relations.length);
    const fits = await page.evaluate(() => {
      const graph = document.getElementById("semantic-graph"), view = document.getElementById("map-viewport");
      return graph.getBoundingClientRect().width <= view.clientWidth + 1 && graph.getBoundingClientRect().height <= view.clientHeight + 1;
    });
    assert(fits, "Fit control must fit the full graph inside its scroll viewport");
    const before = await page.$eval("#map-zoom", (node) => parseInt(node.value));
    await click("#map-zoom-in");
    assert(await page.$eval("#map-zoom", (node) => parseInt(node.value)) > before);
    await page.$eval('.semantic-node[data-map-concept="git-claim"]', (node) => node.focus());
    await page.keyboard.press("Space");
    await selected("git-claim");
    await page.select("#map-concept", "worktree-external-link");
    const href = page.url();
    await page.goto(href, { waitUntil: "networkidle0" });
    await selected("worktree-external-link");
    assert.equal(await page.$eval('.semantic-node[data-map-concept="worktree-external-link"]', (node) => node.getAttribute("aria-pressed")), "true");
    await noOverflow();
  }
  async function capture(selector, label, width) {
    // Capture the intended section after scrolling, independently of smooth UI
    // animation. A screenshot taken immediately after scrollIntoView races it.
    await page.$eval(selector, (node) => window.scrollTo({ top: Math.max(0, scrollY + node.getBoundingClientRect().top - 24), behavior: "instant" }));
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
    await page.screenshot({ path: join(evidence, `semantic-${variant}-${label}-${width}.png`) });
  }
  async function selected(id) {
    const concept = model.concepts.find((item) => item.id === id);
    await page.waitForFunction((label) => document.querySelector("#concept-detail h3")?.textContent === label, {}, concept.label);
    assert.equal(await page.$eval(".semantic-key", (node) => node.textContent), concept.key);
    const text = await page.$eval("#concept-detail", (node) => node.textContent);
    for (const condition of concept.invariants) assert(text.includes(condition));
    const hrefs = await page.$$eval("#concept-detail .sources a", (nodes) => nodes.map((node) => node.href));
    assert(hrefs.length > 0 && hrefs.every((href) => href.includes(`/blob/${model.source_revision}/`) && /#L\d+$/.test(href)));
  }
  for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 812 }]) {
    await page.setViewport(viewport);
    await page.goto(base + route, { waitUntil: "networkidle0" });
    await page.waitForSelector(".domain-card");
    assert.equal(await count(".domain-card"), 7);
    assert.equal(await count(".graph-node"), 7);
    assert.equal(await count(".concept-card"), 25);
    assert.equal(await count(".workstream"), 6);
    assert.equal(await count(".result-grid article"), 4);
    // Returning to the initial empty hash must restore the initial selection,
    // rather than leave the last selected concept under an unrelated URL.
    await selected("repository");
    await applicationMap();
    await capture("#model-map", "map", viewport.width);
    // Start the pre-existing explorer checks from a fresh initial URL.
    await page.goto(base + route, { waitUntil: "networkidle0" });
    await selected("repository");
    await click('.concept-card[data-concept="git-object"]');
    await selected("git-object");
    await page.goBack();
    await page.waitForFunction(() => location.hash === "");
    await selected("repository");
    const contextCoreGapPx = await contextCoreArrow();
    await noOverflow();
    await capture("#overview", "overview", viewport.width);

    await page.select("#domain-filter", "filesystem");
    assert.equal(await count(".concept-card"), model.concepts.filter((concept) => concept.domain === "filesystem").length);
    await page.type("#concept-search", "no-semantic-match-67249");
    assert.equal(await count(".concept-card"), 0);
    assert(await page.$(".empty"));
    await click("#reset");
    assert.equal(await count(".concept-card"), model.concepts.length);
    assert.equal(await page.$eval("#concept-search", (node) => node.value), "");

    // A core-scoped selection and a cross-domain relation remain fully navigable.
    await page.select("#domain-filter", "core");
    await click('.concept-card[data-concept="coverage"]');
    await selected("coverage");
    await click('#concept-detail [data-concept="resource"]');
    await selected("resource");
    assert.equal(await page.$eval("#domain-filter", (node) => node.value), "all");
    await page.goBack();
    await selected("coverage");
    await noOverflow();

    await page.goto(base + route + "#concept=filesystem-entry", { waitUntil: "networkidle0" });
    await selected("filesystem-entry");
    await noOverflow();
    await capture("#concept-detail", "concept", viewport.width);

    // SVG domain nodes expose the same action to keyboard-only readers.
    // Puppeteer's ElementHandle.focus rejects SVGElement before calling the DOM;
    // the browser's SVG focus API supports tabindex and real keyboard input.
    await page.$eval('.graph-node[data-domain="worktrees"]', (node) => node.focus());
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-domain")), "worktrees");
    await page.keyboard.press("Enter");
    assert.equal(await page.$eval("#domain-filter", (node) => node.value), "worktrees");
    assert.equal(await count(".concept-card"), model.concepts.filter((concept) => concept.domain === "worktrees").length);
    assert.equal(await page.$eval('.graph-node[data-domain="worktrees"]', (node) => node.classList.contains("active")), true);
    await noOverflow();
    checks.push({ viewport, initialCounts: true, wholeApplicationMap: true, semanticArrowGeometry: true, readingPath: true, relationFilter: true, mapHistory: true, mapKeyboard: true, mapZoomAndFit: true, mapDeepLink: true, initialHistoryBack: true, contextCoreArrow: true, contextCoreGapPx, filterAndEmptySearch: true, reset: true, semanticKeysAndConditions: true, pinnedCitations: true, crossDomainRelation: true, deepLink: true, back: true, svgKeyboard: true, noPageOverflow: true });
  }
} catch (error) {
  failures.push(error.stack || String(error));
} finally {
  if (browser) await browser.close();
  await new Promise((done) => server.close(done));
}
const summary = { status: failures.length ? "fail" : "pass", variant, route, checks, failures };
writeFileSync(join(evidence, `semantic-${variant}-summary.json`), JSON.stringify(summary, null, 2) + "\n");
console.log(JSON.stringify({ status: summary.status, variant, viewports: checks.length, failures: failures.length, evidence: `website/.build/browser-evidence/semantic-${variant}-summary.json` }));
if (failures.length) process.exitCode = 1;
