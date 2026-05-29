#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { buildFitAwareTextOperations } from "../text-fit/fit-text-operations.js";

const [deckJsonPath, requestsPath, outputPath] = process.argv.slice(2);

if (!deckJsonPath || !requestsPath) {
  console.error("Usage: npm run text:fit -- <deck.json> <text-requests.json> [output.json]");
  process.exit(1);
}

const deck = JSON.parse(await fs.readFile(path.resolve(deckJsonPath), "utf8"));
const requests = JSON.parse(await fs.readFile(path.resolve(requestsPath), "utf8"));
const result = buildFitAwareTextOperations(deck, requests);
const outPath = outputPath
  ? path.resolve(outputPath)
  : path.resolve(
      path.dirname(requestsPath),
      `${path.basename(requestsPath, ".json")}.fit-operations.json`,
    );

await fs.mkdir(path.dirname(outPath), { recursive: true });
await fs.writeFile(outPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputPath: outPath,
  operations: result.operations.length,
  ...result.summary,
}, null, 2));

