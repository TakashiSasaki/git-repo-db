#!/usr/bin/env node
// Generates high-resolution PNG icons from master SVG files using Puppeteer.
// Produces 16x16, 32x32, 180x180 (Apple touch), 192x192, 512x512 PNGs and maskable variants.

import puppeteer from "puppeteer";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const ICONS_DIR = join(ROOT, "docs", "site", "assets", "images", "icons");

const ICON_SVG = join(ICONS_DIR, "icon.svg");
const ICON_MASKABLE_SVG = join(ICONS_DIR, "icon-maskable.svg");

const TARGETS = [
  { src: ICON_SVG, filename: "icon-512.png", size: 512 },
  { src: ICON_SVG, filename: "icon-192.png", size: 192 },
  { src: ICON_SVG, filename: "icon-180.png", size: 180 },
  { src: ICON_SVG, filename: "favicon-32.png", size: 32 },
  { src: ICON_SVG, filename: "favicon-16.png", size: 16 },
  { src: ICON_MASKABLE_SVG, filename: "icon-maskable-512.png", size: 512 },
  { src: ICON_MASKABLE_SVG, filename: "icon-maskable-192.png", size: 192 },
];

async function generateIcons() {
  console.log("Generating PWA PNG icons from SVGs using Puppeteer...");
  if (!existsSync(ICONS_DIR)) {
    mkdirSync(ICONS_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
    headless: true,
  });

  try {
    const page = await browser.newPage();

    for (const target of TARGETS) {
      if (!existsSync(target.src)) {
        throw new Error(`Source SVG not found: ${target.src}`);
      }

      const svgContent = readFileSync(target.src, "utf-8");
      const html = `<!DOCTYPE html>
<html>
<head>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: ${target.size}px; height: ${target.size}px; overflow: hidden; background: transparent; }
    svg { width: 100%; height: 100%; display: block; }
  </style>
</head>
<body>
  ${svgContent}
</body>
</html>`;

      await page.setViewport({
        width: target.size,
        height: target.size,
        deviceScaleFactor: 1,
      });

      await page.setContent(html, { waitUntil: "domcontentloaded" });

      const outPath = join(ICONS_DIR, target.filename);
      const pngBuffer = await page.screenshot({
        type: "png",
        omitBackground: true,
        clip: {
          x: 0,
          y: 0,
          width: target.size,
          height: target.size,
        },
      });

      writeFileSync(outPath, pngBuffer);
      console.log(`  ✓ Generated ${target.filename} (${target.size}x${target.size}, ${pngBuffer.length} bytes)`);
    }

    console.log("All PWA PNG icons generated successfully.");
  } finally {
    await browser.close();
  }
}

generateIcons().catch((err) => {
  console.error("Failed to generate PWA icons:", err);
  process.exit(1);
});
