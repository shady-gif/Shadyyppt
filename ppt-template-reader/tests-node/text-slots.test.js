import assert from "node:assert/strict";
import test from "node:test";
import {
  buildTextSlotReport,
  classifyTextRole,
  estimateTextCapacity,
  logicalTrimToFit,
  validateTextFit,
} from "../src-node/text-fit/text-slots.js";

function element(overrides = {}) {
  return {
    id: "e1",
    name: "TextBox 1",
    type: "text",
    x: 1,
    y: 1,
    w: 8,
    h: 1.4,
    style: { fontSize: 24 },
    text: { raw: "Lorem ipsum dolor sit amet, consectetur adipiscing elit." },
    ...overrides,
  };
}

test("classifies protected placeholders", () => {
  assert.equal(classifyTextRole(element({ placeholder: { type: "footer" } })), "footer");
  const report = buildTextSlotReport({
    slides: [{ id: "s1", index: 0, elements: [element({ placeholder: { type: "slideNumber" } })] }],
  });
  assert.equal(report.slots[0].editable, false);
});

test("classifies long text as body and huge short text as title", () => {
  assert.equal(classifyTextRole(element({ text: { raw: "This is a long body paragraph with enough words to clearly behave like a body text box in a presentation." } })), "body");
  assert.equal(classifyTextRole(element({
    style: { fontSize: 180 },
    h: 4,
    text: { raw: "INTRODUCTION" },
  }), { largestFontSize: 180 }), "title");
});

test("estimates strict body capacity from original template text", () => {
  const body = element({
    w: 9.8,
    h: 3.2,
    style: { fontSize: 24 },
    text: { raw: "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut nisl tortor, tincidunt ut lobortis id, accumsan eget diam." },
  });
  const capacity = estimateTextCapacity(body, "body");
  assert.ok(capacity.maxChars <= 130);
  assert.ok(capacity.maxWords <= 38);
  assert.ok(capacity.maxLines >= 3);
});

test("validates and trims overflowing text", () => {
  const capacity = { maxChars: 45, maxWords: 8, maxLines: 1, maxWeightedChars: 42 };
  const overflow = "This sentence is definitely too long for the tiny title slot.";
  assert.equal(validateTextFit(overflow, { role: "title", capacity }).status, "overflow");
  const trimmed = logicalTrimToFit(overflow, { role: "title", capacity });
  assert.equal(validateTextFit(trimmed, { role: "title", capacity }).status, "fit");
});

