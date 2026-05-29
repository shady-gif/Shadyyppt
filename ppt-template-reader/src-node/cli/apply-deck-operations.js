#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { applyOperations } from "../operations/deck-operations.js";

const [inputPath, operationsPath, outputPath] = process.argv.slice(2);

if (!inputPath || !operationsPath) {
  console.error("Usage: npm run deck:ops -- <deck.json> <operations.json> [output.json]");
  process.exit(1);
}

const deck = JSON.parse(await fs.readFile(path.resolve(inputPath), "utf8"));
const operations = JSON.parse(await fs.readFile(path.resolve(operationsPath), "utf8"));
const updated = applyOperations(deck, operations);
const outPath = outputPath
  ? path.resolve(outputPath)
  : path.resolve(
      path.dirname(inputPath),
      `${path.basename(inputPath, ".json")}.ops.json`,
    );

await fs.mkdir(path.dirname(outPath), { recursive: true });
await fs.writeFile(outPath, `${JSON.stringify(updated, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputPath: outPath,
  operations: operations.length,
  slides: updated.slides.length,
  slideOrder: updated.slides.map((slide) => slide.id),
}, null, 2));

