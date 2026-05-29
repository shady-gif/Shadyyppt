import assert from "node:assert/strict";
import test from "node:test";
import { fitTemplateUpdates } from "../src-node/text-fit/fit-template-updates.js";

function deck() {
  return {
    slides: [
      {
        id: "256",
        index: 0,
        elements: [
          {
            id: "7",
            type: "text",
            w: 8,
            h: 1,
            style: { fontSize: 64 },
            text: { raw: "CREATIVE" },
          },
        ],
      },
      {
        id: "257",
        index: 1,
        elements: [
          {
            id: "14",
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
}

test("fits existing Python-style template updates", async () => {
  const result = await fitTemplateUpdates(deck(), [
    {
      slideIndex: 1,
      shapeId: "7",
      field: "title",
      newText: "A complete introduction to automated PowerPoint generation",
    },
    {
      slideIndex: 2,
      shapeId: "14",
      field: "body",
      newText: "This is a very long replacement paragraph that should be trimmed before it is allowed to become a PowerPoint text replacement operation.",
    },
  ], {
    maxCharsByRole: { body: 55 },
    maxWordsByRole: { body: 9 },
  });

  assert.equal(result.updates.length, 2);
  assert.equal(result.fitSummary.fit, 2);
  assert.equal(result.fitSummary.overflow, 0);
  assert.notEqual(result.updates[0].newText, "A complete introduction to automated PowerPoint generation");
  assert.equal(result.updates[0].originalNewText, "A complete introduction to automated PowerPoint generation");
  assert.equal(result.fitReport[0].field, "title");
  assert.equal(result.fitReport[1].shapeId, "14");
});

