#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { buildFitAwareTextOperationsWithRewrite } from "../text-fit/fit-text-operations.js";
import { createOllamaSlotRewriter } from "../text-fit/llm-rewriter.js";

const args = process.argv.slice(2);
const useOllama = args.includes("--ollama") || process.env.ENABLE_OLLAMA_REWRITE === "1";
const rewriteFittingText = args.includes("--rewrite-fitting");
const positional = args.filter((arg) => !arg.startsWith("--"));
const [deckJsonPath, requestsPath, outputPath] = positional;

if (!deckJsonPath || !requestsPath) {
  console.error("Usage: npm run text:fit:rewrite -- <deck.json> <text-requests.json> [output.json] [--ollama] [--rewrite-fitting]");
  process.exit(1);
}

const deck = JSON.parse(await fs.readFile(path.resolve(deckJsonPath), "utf8"));
const requests = JSON.parse(await fs.readFile(path.resolve(requestsPath), "utf8"));
const result = await buildFitAwareTextOperationsWithRewrite(deck, requests, {
  rewriter: useOllama ? createOllamaSlotRewriter() : null,
  rewriteFittingText,
});
const outPath = outputPath
  ? path.resolve(outputPath)
  : path.resolve(
      path.dirname(requestsPath),
      `${path.basename(requestsPath, ".json")}.rewrite-fit-operations.json`,
    );

await fs.mkdir(path.dirname(outPath), { recursive: true });
await fs.writeFile(outPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputPath: outPath,
  rewriteProvider: useOllama ? "ollama" : "none",
  operations: result.operations.length,
  ...result.summary,
}, null, 2));

