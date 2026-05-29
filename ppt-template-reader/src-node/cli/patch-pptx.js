#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { patchPptxWithOperations } from "../exporters/ooxml-patcher.js";

const [sourcePptxPath, deckJsonPath, operationsPath, outputPptxPath] = process.argv.slice(2);

if (!sourcePptxPath || !deckJsonPath || !operationsPath || !outputPptxPath) {
  console.error("Usage: npm run patch:pptx -- <source.pptx> <deck.json> <operations.json> <output.pptx>");
  process.exit(1);
}

const deck = JSON.parse(await fs.readFile(path.resolve(deckJsonPath), "utf8"));
const operations = JSON.parse(await fs.readFile(path.resolve(operationsPath), "utf8"));
const finalDeck = await patchPptxWithOperations({
  sourcePptxPath: path.resolve(sourcePptxPath),
  deck,
  operations,
  outputPptxPath: path.resolve(outputPptxPath),
});

console.log(JSON.stringify({
  outputPath: path.resolve(outputPptxPath),
  operations: operations.length,
  slides: finalDeck.slides.length,
  slideOrder: finalDeck.slides.map((slide) => slide.id),
}, null, 2));

