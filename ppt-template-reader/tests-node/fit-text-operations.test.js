import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFitAwareTextOperations,
  fitTextForSlot,
} from "../src-node/text-fit/fit-text-operations.js";
import { validateTextFit } from "../src-node/text-fit/text-slots.js";

function slot(overrides = {}) {
  return {
    slideId: "s1",
    slideIndex: 0,
    elementId: "e1",
    role: "body",
    name: "Body",
    editable: true,
    capacity: {
      maxChars: 70,
      maxWords: 12,
      maxLines: 2,
      maxWeightedChars: 62,
    },
    ...overrides,
  };
}

test("fits overflowing text before creating operations", () => {
  const deck = {
    slides: [
      {
        id: "s1",
        index: 0,
        elements: [
          {
            id: "e1",
            name: "Body",
            type: "text",
            w: 5,
            h: 1,
            style: { fontSize: 18 },
            text: { raw: "Short body text." },
          },
        ],
      },
    ],
  };
  const result = buildFitAwareTextOperations(deck, [
    {
      slideId: "s1",
      elementId: "e1",
      text: "This is a very long replacement paragraph that should be trimmed before it is allowed to become a PowerPoint text replacement operation.",
    },
  ], {
    maxCharsByRole: { body: 55 },
    maxWordsByRole: { body: 9 },
  });

  assert.equal(result.operations.length, 1);
  assert.equal(result.report[0].status, "fit");
  assert.notEqual(result.report[0].strategy, "unchanged");
  assert.equal(validateTextFit(result.operations[0].text, result.report[0]).status, "fit");
});

test("leaves already fitting text unchanged", () => {
  const fitted = fitTextForSlot("Clean concise summary", slot());
  assert.equal(fitted.strategy, "unchanged");
  assert.equal(fitted.text, "Clean concise summary");
});

test("compresses short slots without dangling punctuation", () => {
  const fitted = fitTextForSlot("A complete introduction to automated PowerPoint generation", slot({
    role: "title",
    capacity: {
      maxChars: 13,
      maxWords: 2,
      maxLines: 1,
      maxWeightedChars: 12.5,
    },
  }));
  assert.equal(fitted.strategy, "keyword-compressed");
  assert.equal(fitted.validation.status, "fit");
  assert.doesNotMatch(fitted.text, /[,;:]$/);
});

test("hard trims body text to a clean ending", () => {
  const fitted = fitTextForSlot("Instead of filling every available inch with dense text, the generator should create short, focused copy that respects the original design and leaves the slide feeling intentional.", slot({
    capacity: {
      maxChars: 145,
      maxWords: 23,
      maxLines: 3,
      maxWeightedChars: 125,
    },
  }));
  assert.equal(fitted.validation.status, "fit");
  assert.match(fitted.text, /\.$/);
  assert.doesNotMatch(fitted.text, /\b(feeling|and|with)\.$/i);
});

test("rejects protected slots by default", () => {
  const deck = {
    slides: [
      {
        id: "s1",
        index: 0,
        elements: [
          {
            id: "footer",
            type: "text",
            placeholder: { type: "footer" },
            w: 2,
            h: 0.4,
            style: { fontSize: 12 },
            text: { raw: "Footer" },
          },
        ],
      },
    ],
  };

  assert.throws(() => buildFitAwareTextOperations(deck, [
    { slideId: "s1", elementId: "footer", text: "Do not change" },
  ]), /protected/);
});

test("preserves original text for ultra-small slots when replacement cannot fit", () => {
  const fitted = fitTextForSlot("technology profile", slot({
    role: "body",
    originalText: "Play",
    capacity: {
      maxChars: 16,
      maxWords: 4,
      maxLines: 1,
      maxWeightedChars: 3.81,
    },
  }));
  assert.equal(fitted.strategy, "preserved-original");
  assert.equal(fitted.text, "Play");
  assert.equal(fitted.validation.status, "fit");
});
