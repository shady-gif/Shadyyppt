import assert from "node:assert/strict";
import test from "node:test";
import { applyOperation, applyOperations, validateOperation } from "../src-node/operations/deck-operations.js";

function sampleDeck() {
  return {
    meta: { slideCount: 2 },
    slides: [
      {
        id: "slide-a",
        index: 0,
        elements: [
          {
            id: "title",
            type: "text",
            text: {
              raw: "Original title",
              paragraphs: [{ raw: "Original title", runs: [{ text: "Original title", style: { bold: true } }] }],
              runs: [{ text: "Original title", style: { bold: true } }],
            },
          },
        ],
      },
      { id: "slide-b", index: 1, elements: [] },
    ],
  };
}

test("moves slides and reindexes", () => {
  const updated = applyOperation(sampleDeck(), { type: "MOVE_SLIDE", slideId: "slide-a", toIndex: 1 });
  assert.deepEqual(updated.slides.map((slide) => slide.id), ["slide-b", "slide-a"]);
  assert.deepEqual(updated.slides.map((slide) => slide.index), [0, 1]);
});

test("replaces text while preserving first run style", () => {
  const updated = applyOperation(sampleDeck(), {
    type: "REPLACE_TEXT",
    slideId: "slide-a",
    elementId: "title",
    text: "New title\nSecond line",
  });
  const element = updated.slides[0].elements[0];
  assert.equal(element.text.raw, "New title\nSecond line");
  assert.equal(element.text.originalRaw, "Original title");
  assert.equal(element.text.paragraphs[0].runs[0].style.bold, true);
  assert.equal(element.text.paragraphs[1].runs[0].text, "Second line");
});

test("clones and deletes slides", () => {
  const updated = applyOperations(sampleDeck(), [
    { type: "CLONE_SLIDE", sourceSlideId: "slide-a", newSlideId: "slide-a-copy", index: 1 },
    { type: "DELETE_SLIDE", slideId: "slide-b" },
  ]);
  assert.deepEqual(updated.slides.map((slide) => slide.id), ["slide-a", "slide-a-copy"]);
  assert.equal(updated.slides[1].cloneOf, "slide-a");
  assert.equal(updated.meta.slideCount, 2);
});

test("validation reports bad operation without mutating", () => {
  const result = validateOperation(sampleDeck(), {
    type: "REPLACE_TEXT",
    slideId: "missing",
    elementId: "title",
    text: "Nope",
  });
  assert.equal(result.ok, false);
  assert.match(result.errors[0], /could not find slide/);
});

