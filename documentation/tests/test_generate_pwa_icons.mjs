import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, readdirSync, symlinkSync, linkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateIcons } from "../tools/generate_pwa_icons.js";

test("generates seven files at the documentation destination", async () => {
  const root = mkdtempSync(join(tmpdir(), "icons-"));
  try {
    const icons = join(root, "documentation/content/assets/images/icons");
    mkdirSync(icons, {recursive: true});
    writeFileSync(join(icons, "icon.svg"), "<svg/>");
    writeFileSync(join(icons, "icon-maskable.svg"), "<svg/>");
    let screenshots = 0;
    const launch = async () => ({newPage: async () => ({setViewport: async () => {}, setContent: async () => {}, screenshot: async () => Buffer.from(String(++screenshots))}), close: async () => {}});
    await generateIcons({root, launch});
    assert.equal(screenshots, 7);
    assert.equal(readdirSync(icons).filter(x => x.endsWith(".png")).length, 7);
    assert.equal(readFileSync(join(icons, "icon-512.png"), "utf8"), "1");
    assert.equal(existsSync(join(root, "docs/site")), false);
  } finally { rmSync(root, {recursive: true}); }
});

test("missing SVG fails before browser launch or writes", async () => {
  const root = mkdtempSync(join(tmpdir(), "icons-"));
  try {
    const icons = join(root, "documentation/content/assets/images/icons");
    mkdirSync(icons, {recursive: true});
    writeFileSync(join(icons, "icon.svg"), "<svg/>");
    let launched = false;
    await assert.rejects(generateIcons({root, launch: async () => { launched = true; }}));
    assert.equal(launched, false);
    assert.deepEqual(readdirSync(icons), ["icon.svg"]);
    assert.equal(existsSync(join(root, "docs/site")), false);
  } finally { rmSync(root, {recursive: true}); }
});

test("render failure preserves existing icons and removes only owned staging", async () => {
  const root = mkdtempSync(join(tmpdir(), "icons-"));
  try {
    const icons = join(root, "documentation/content/assets/images/icons");
    mkdirSync(icons, {recursive: true});
    for (const name of ["icon.svg", "icon-maskable.svg", "icon-512.png", "unrelated.tmp"]) writeFileSync(join(icons, name), "sentinel");
    let calls = 0;
    const launch = async () => ({newPage: async () => ({setViewport: async () => {}, setContent: async () => {}, screenshot: async () => { if (++calls === 2) throw new Error("render failed"); return Buffer.from("new"); }}), close: async () => {}});
    await assert.rejects(generateIcons({root, launch}), /render failed/);
    assert.equal(readFileSync(join(icons, "icon-512.png"), "utf8"), "sentinel");
    assert.deepEqual(readdirSync(icons).sort(), ["icon-maskable.svg", "icon-512.png", "icon.svg", "unrelated.tmp"].sort());
  } finally { rmSync(root, {recursive: true}); }
});

for (const alias of ["symlink", "hardlink"]) {
  test(`${alias} output is rejected without touching outside data`, async () => {
    const root = mkdtempSync(join(tmpdir(), "icons-"));
    try {
      const icons = join(root, "documentation/content/assets/images/icons");
      mkdirSync(icons, {recursive: true});
      writeFileSync(join(icons, "icon.svg"), "<svg/>");
      writeFileSync(join(icons, "icon-maskable.svg"), "<svg/>");
      const outside = join(root, "outside");
      writeFileSync(outside, "preserve");
      (alias === "symlink" ? symlinkSync : linkSync)(outside, join(icons, "icon-512.png"));
      let launched = false;
      await assert.rejects(generateIcons({root, launch: async () => { launched = true; }}));
      assert.equal(launched, false);
      assert.equal(readFileSync(outside, "utf8"), "preserve");
      assert.equal(readdirSync(icons).length, 3);
    } finally { rmSync(root, {recursive: true}); }
  });
}

test("a staging write error leaves previous images intact", async () => {
  const root = mkdtempSync(join(tmpdir(), "icons-"));
  const icons = join(root, "documentation/content/assets/images/icons");
  try {
    mkdirSync(icons, {recursive: true});
    for (const name of ["icon.svg", "icon-maskable.svg", "icon-512.png"]) writeFileSync(join(icons, name), "sentinel");
    const launch = async () => ({newPage: async () => ({setViewport: async () => {}, setContent: async () => {}, screenshot: async () => ({invalid: "not a PNG buffer"})}), close: async () => {}});
    await assert.rejects(generateIcons({root, launch}));
    assert.equal(readFileSync(join(icons, "icon-512.png"), "utf8"), "sentinel");
    assert.equal(readdirSync(icons).length, 3);
  } finally { rmSync(root, {recursive: true}); }
});
