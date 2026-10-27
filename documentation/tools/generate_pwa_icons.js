#!/usr/bin/env node
// Generate the seven checked-in PWA PNG icons from the two master SVGs.
// Uses Linux directory handles (the documented local bootstrap environment).
// All rendering and staging finishes before publication; rendering/write failures
// leave the existing icons intact. Each publication rename is atomic, but a
// publication error/process interruption may leave a mixture of old and new
// complete icons. Rerun after correcting the error; no seven-file transaction
// or cross-platform execution has been verified. Existing Puppeteer is required
// for the CLI; tests inject a browser without installing dependencies.
import { constants, openSync, closeSync, fstatSync, readFileSync, writeFileSync, renameSync, unlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { randomBytes } from "node:crypto";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const targets = [
  ["icon.svg", "icon-512.png", 512], ["icon.svg", "icon-192.png", 192],
  ["icon.svg", "icon-180.png", 180], ["icon.svg", "favicon-32.png", 32],
  ["icon.svg", "favicon-16.png", 16], ["icon-maskable.svg", "icon-maskable-512.png", 512],
  ["icon-maskable.svg", "icon-maskable-192.png", 192],
];

function openIcons(root) {
  // Anchor every operation at an opened directory and refuse linked ancestors.
  let fd = openSync("/", constants.O_RDONLY | constants.O_DIRECTORY);
  try {
    for (const part of join(resolve(root), "documentation/content/assets/images/icons").split("/").filter(Boolean)) {
      const next = openSync(`/proc/self/fd/${fd}/${part}`, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
      closeSync(fd);
      fd = next;
    }
    return fd;
  } catch (error) { closeSync(fd); throw error; }
}

function readSource(path) {
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1) throw new Error(`Invalid SVG input: ${path}`);
    return readFileSync(fd, "utf8");
  } finally { closeSync(fd); }
}

export async function generateIcons({root = ROOT, launch} = {}) {
  if (process.platform !== "linux") throw new Error("Safe icon writes require Linux directory handles");
  const dir = openIcons(root);
  const anchored = `/proc/self/fd/${dir}`;
  const staged = [];
  try {
    // Validate both sources and all existing outputs before launching or writing.
    const sources = Object.fromEntries(["icon.svg", "icon-maskable.svg"].map(name => [name, readSource(join(anchored, name))]));
    for (const [, name] of targets) {
      try {
        const fd = openSync(join(anchored, name), constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
        try { const st = fstatSync(fd); if (!st.isFile() || st.nlink !== 1) throw new Error(`Invalid output: ${name}`); }
        finally { closeSync(fd); }
      } catch (error) { if (error.code !== "ENOENT") throw error; }
    }
    if (!launch) launch = (await import("puppeteer")).default.launch;
    const browser = await launch({args: ["--no-sandbox", "--disable-setuid-sandbox"], headless: true});
    try {
      const page = await browser.newPage();
      for (const [source, name, size] of targets) {
        await page.setViewport({width: size, height: size, deviceScaleFactor: 1});
        await page.setContent(`<!DOCTYPE html><html><head><style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:${size}px;height:${size}px;overflow:hidden;background:transparent}svg{width:100%;height:100%;display:block}</style></head><body>${sources[source]}</body></html>`, {waitUntil: "domcontentloaded"});
        const png = await page.screenshot({type: "png", omitBackground: true, clip: {x: 0, y: 0, width: size, height: size}});
        const temporary = `.icon-${randomBytes(16).toString("hex")}.tmp`;
        const fd = openSync(join(anchored, temporary), constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
        staged.push(temporary);
        try { writeFileSync(fd, png); } finally { closeSync(fd); }
      }
    } finally { await browser.close(); }
    // Each rename replaces the directory entry itself, never follows a leaf symlink.
    // The complete seven-file publication is not an atomic transaction.
    for (let i = 0; i < targets.length; i++) {
      renameSync(join(anchored, staged[i]), join(anchored, targets[i][1]));
      staged[i] = null;
    }
  } finally {
    for (const name of staged) if (name) unlinkSync(join(anchored, name));
    closeSync(dir);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  generateIcons().catch(error => { console.error("Failed to generate PWA icons:", error); process.exitCode = 1; });
}
