#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { buildTextSlotReport } from "../text-fit/text-slots.js";

const [deckJsonPath, outputPath] = process.argv.slice(2);

if (!deckJsonPath) {
  console.error("Usage: npm run text:slots -- <deck.json> [output.json]");
  process.exit(1);
}

const deck = JSON.parse(await fs.readFile(path.resolve(deckJsonPath), "utf8"));
const report = buildTextSlotReport(deck);
const outPath = outputPath
  ? path.resolve(outputPath)
  : path.resolve(
      path.dirname(deckJsonPath),
      `${path.basename(deckJsonPath, ".json")}.text-slots.json`,
    );

await fs.mkdir(path.dirname(outPath), { recursive: true });
await fs.writeFile(outPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputPath: outPath,
  ...report.summary,
}, null, 2));

