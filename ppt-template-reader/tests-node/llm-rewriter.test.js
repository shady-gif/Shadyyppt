import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFitAwareTextOperationsWithRewrite,
  fitTextForSlotWithRewrite,
} from "../src-node/text-fit/fit-text-operations.js";
import {
  buildSlotRewritePrompt,
  sanitizeRewriteResponse,
} from "../src-node/text-fit/llm-rewriter.js";

function slot(overrides = {}) {
  return {
    slideId: "s1",
    slideIndex: 0,
    elementId: "title",
    role: "title",
    name: "Title",
    editable: true,
    capacity: {
      maxChars: 13,
      maxWords: 2,
      maxLines: 1,
      maxWeightedChars: 12.5,
    },
    ...overrides,
  };
}

test("builds a strict slot-aware rewrite prompt", () => {
  const prompt = buildSlotRewritePrompt({
    text: "A complete introduction to automated PowerPoint generation",
    slot: slot(),
  });
  assert.match(prompt, /Max characters: 13/);
  assert.match(prompt, /Max words: 2/);
  assert.match(prompt, /Do not add new facts/);
  assert.match(prompt, /Output only the rewritten text/);
});

test("accepts a fitting mocked LLM rewrite", async () => {
  const fitted = await fitTextForSlotWithRewrite(
    "A complete introduction to automated PowerPoint generation",
    slot(),
    {
      rewriter: async () => "Smart Decks",
    },
  );
  assert.equal(fitted.strategy, "llm-rewritten");
  assert.equal(fitted.text, "Smart Decks");
  assert.equal(fitted.validation.status, "fit");
});

test("trims a mocked LLM rewrite if it is still too long", async () => {
  const fitted = await fitTextForSlotWithRewrite(
    "A complete introduction to automated PowerPoint generation",
    slot(),
    {
      rewriter: async () => "Automated PowerPoint generation system",
    },
  );
  assert.match(fitted.strategy, /^llm-/);
  assert.equal(fitted.validation.status, "fit");
  assert.notEqual(fitted.text, "Automated PowerPoint generation system");
});

test("builds operations with mocked rewrite metadata", async () => {
  const deck = {
    slides: [
      {
        id: "s1",
        index: 0,
        elements: [
          {
            id: "title",
            type: "text",
            w: 8,
            h: 1,
            style: { fontSize: 64 },
            text: { raw: "CREATIVE" },
          },
        ],
      },
    ],
  };
  const result = await buildFitAwareTextOperationsWithRewrite(deck, [
    {
      slideId: "s1",
      elementId: "title",
      text: "A complete introduction to automated PowerPoint generation",
    },
  ], {
    rewriter: async () => "Smart",
  });

  assert.equal(result.operations[0].text, "Smart");
  assert.equal(result.report[0].strategy, "llm-rewritten");
  assert.equal(result.report[0].rewrite.accepted, true);
});

test("sanitizes common model wrappers", () => {
  assert.equal(sanitizeRewriteResponse('"Smart Decks"'), "Smart Decks");
  assert.equal(sanitizeRewriteResponse('{"text":"Smart Decks"}'), "Smart Decks");
  assert.equal(sanitizeRewriteResponse("```text\nSmart Decks\n```"), "Smart Decks");
});

