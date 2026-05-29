import { parseDeck } from "../parsers/deck-parser.js";
import { buildFitAwareTextOperations, buildFitAwareTextOperationsWithRewrite } from "./fit-text-operations.js";
import { createOllamaSlotRewriter } from "./llm-rewriter.js";

export async function fitTemplateUpdatesFromPptx(pptxPath, updates, options = {}) {
  const deck = await parseDeck(pptxPath);
  return fitTemplateUpdates(deck, updates, options);
}

export async function fitTemplateUpdates(deck, updates, options = {}) {
  if (!Array.isArray(updates)) {
    throw new Error("Template updates must be an array.");
  }

  const requests = updates.map((update) => updateToRequest(deck, update));
  const fitResult = options.useRewrite
    ? await buildFitAwareTextOperationsWithRewrite(deck, requests, {
        ...options,
        rewriter: options.rewriter || createOllamaSlotRewriter(),
      })
    : buildFitAwareTextOperations(deck, requests, options);
  const operationByKey = new Map(
    fitResult.operations.map((operation) => [
      updateKey(operation.slideId, operation.elementId),
      operation,
    ]),
  );
  const reportByKey = new Map(
    fitResult.report.map((item) => [
      updateKey(item.slideId, item.elementId),
      item,
    ]),
  );

  return {
    updates: updates.map((update) => {
      const request = updateToRequest(deck, update);
      const operation = operationByKey.get(updateKey(request.slideId, request.elementId));
      if (!operation) {
        throw new Error(`No fitted operation for slide ${update.slideIndex}, shape ${update.shapeId}.`);
      }

      return {
        ...update,
        originalNewText: update.newText,
        newText: operation.text,
        fit: operation.fit,
      };
    }),
    fitSummary: fitResult.summary,
    fitReport: fitResult.report.map((item) => {
      const request = requests.find((candidate) => {
        return String(candidate.slideId) === String(item.slideId)
          && String(candidate.elementId) === String(item.elementId);
      });
      return {
        ...item,
        slideIndex: request?.source?.slideIndex ?? item.slideIndex,
        shapeId: request?.source?.shapeId ?? item.elementId,
        field: request?.source?.field ?? null,
      };
    }),
    operations: fitResult.operations,
  };
}

function updateToRequest(deck, update) {
  if (!Number.isInteger(update.slideIndex)) {
    throw new Error("Template update requires integer slideIndex.");
  }
  if (update.shapeId === undefined || update.shapeId === null) {
    throw new Error("Template update requires shapeId.");
  }

  const slide = deck.slides[update.slideIndex - 1];
  if (!slide) {
    throw new Error(`No parsed slide found for slideIndex ${update.slideIndex}.`);
  }

  return {
    slideId: String(slide.id),
    elementId: String(update.shapeId),
    text: String(update.newText ?? ""),
    source: {
      slideIndex: update.slideIndex,
      shapeId: String(update.shapeId),
      field: update.field || null,
    },
  };
}

function updateKey(slideId, elementId) {
  return `${slideId}:${elementId}`;
}

