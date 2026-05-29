#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { parseDeck } from "../parsers/deck-parser.js";

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath) {
  console.error("Usage: npm run inspect:pptx -- <deck.pptx> [output.json]");
  process.exit(1);
}

const deck = await parseDeck(path.resolve(inputPath));
const outPath = outputPath
  ? path.resolve(outputPath)
  : path.resolve("outputs/node-inspect", `${path.basename(inputPath, ".pptx")}.deck.json`);

await fs.mkdir(path.dirname(outPath), { recursive: true });
await fs.writeFile(outPath, `${JSON.stringify(deck, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputPath: outPath,
  slides: deck.slides.length,
  layouts: deck.layouts.length,
  masters: deck.masters.length,
  assets: deck.assets.length,
  packageEntries: deck.package.entries.length,
}, null, 2));

