#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fitTemplateUpdatesFromPptx } from "../text-fit/fit-template-updates.js";

const args = process.argv.slice(2);
const useRewrite = args.includes("--rewrite") || process.env.ENABLE_FIT_REWRITE === "1";
const positional = args.filter((arg) => !arg.startsWith("--"));
const [pptxPath, updatesPath, outputPath] = positional;

if (!pptxPath || !updatesPath || !outputPath) {
  console.error("Usage: node src-node/cli/fit-template-updates.js <template.pptx> <updates.json> <output.json> [--rewrite]");
  process.exit(1);
}

const updates = JSON.parse(await fs.readFile(path.resolve(updatesPath), "utf8"));
const result = await fitTemplateUpdatesFromPptx(path.resolve(pptxPath), updates, {
  useRewrite,
});

await fs.mkdir(path.dirname(path.resolve(outputPath)), { recursive: true });
await fs.writeFile(path.resolve(outputPath), `${JSON.stringify(result, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  outputPath: path.resolve(outputPath),
  updates: result.updates.length,
  ...result.fitSummary,
}, null, 2));

