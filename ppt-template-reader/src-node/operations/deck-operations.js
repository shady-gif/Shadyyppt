const OPERATION_TYPES = new Set([
  "ADD_SLIDE",
  "CLONE_SLIDE",
  "DELETE_SLIDE",
  "MOVE_SLIDE",
  "UPDATE_ELEMENT",
  "REPLACE_TEXT",
]);

export function applyOperations(deck, operations, options = {}) {
  assertDeck(deck);
  if (!Array.isArray(operations)) {
    throw new Error("Operations payload must be an array.");
  }

  return operations.reduce((currentDeck, operation) => {
    return applyOperation(currentDeck, operation, options);
  }, structuredClone(deck));
}

export function applyOperation(deck, operation, options = {}) {
  assertDeck(deck);
  assertOperation(operation);

  const copy = structuredClone(deck);
  switch (operation.type) {
    case "ADD_SLIDE":
      addSlide(copy, operation);
      break;
    case "CLONE_SLIDE":
      cloneSlide(copy, operation);
      break;
    case "DELETE_SLIDE":
      deleteSlide(copy, operation, options);
      break;
    case "MOVE_SLIDE":
      moveSlide(copy, operation);
      break;
    case "UPDATE_ELEMENT":
      updateElement(copy, operation);
      break;
    case "REPLACE_TEXT":
      replaceText(copy, operation);
      break;
    default:
      throw new Error(`Unsupported operation: ${operation.type}`);
  }

  reindexSlides(copy);
  validateDeck(copy);
  appendOperationLog(copy, operation);
  return copy;
}

export function validateOperation(deck, operation, options = {}) {
  try {
    applyOperation(deck, operation, options);
    return { ok: true, errors: [] };
  } catch (error) {
    return { ok: false, errors: [error.message] };
  }
}

export function validateDeck(deck) {
  assertDeck(deck);
  const slideIds = new Set();
  for (const [index, slide] of deck.slides.entries()) {
    if (!slide?.id) {
      throw new Error(`Slide at index ${index} is missing an id.`);
    }
    if (slideIds.has(String(slide.id))) {
      throw new Error(`Duplicate slide id: ${slide.id}`);
    }
    slideIds.add(String(slide.id));

    if (slide.index !== index) {
      throw new Error(`Slide ${slide.id} has index ${slide.index}; expected ${index}.`);
    }
  }
  return true;
}

function addSlide(deck, operation) {
  if (!operation.slide || typeof operation.slide !== "object") {
    throw new Error("ADD_SLIDE requires a slide object.");
  }

  const slide = structuredClone(operation.slide);
  if (!slide.id) {
    throw new Error("ADD_SLIDE slide must include a unique id.");
  }
  if (findSlide(deck, slide.id)) {
    throw new Error(`ADD_SLIDE id already exists: ${slide.id}`);
  }

  deck.slides.splice(normalizeInsertIndex(deck, operation.index), 0, slide);
}

function cloneSlide(deck, operation) {
  const source = requireSlide(deck, operation.sourceSlideId, "CLONE_SLIDE");
  const clone = structuredClone(source);
  clone.id = operation.newSlideId || nextCloneId(deck, source.id);
  clone.relationshipId = operation.newRelationshipId || null;
  clone.path = operation.newPath || null;
  clone.cloneOf = source.id;

  if (findSlide(deck, clone.id)) {
    throw new Error(`CLONE_SLIDE new id already exists: ${clone.id}`);
  }

  deck.slides.splice(normalizeInsertIndex(deck, operation.index ?? source.index + 1), 0, clone);
}

function deleteSlide(deck, operation, options) {
  const index = findSlideIndex(deck, operation.slideId);
  if (index === -1) {
    throw new Error(`DELETE_SLIDE could not find slide: ${operation.slideId}`);
  }
  if (!options.allowEmptyDeck && deck.slides.length <= 1) {
    throw new Error("DELETE_SLIDE would remove the final slide.");
  }
  deck.slides.splice(index, 1);
}

function moveSlide(deck, operation) {
  const from = findSlideIndex(deck, operation.slideId);
  if (from === -1) {
    throw new Error(`MOVE_SLIDE could not find slide: ${operation.slideId}`);
  }
  if (!Number.isInteger(operation.toIndex)) {
    throw new Error("MOVE_SLIDE requires an integer toIndex.");
  }
  if (operation.toIndex < 0 || operation.toIndex >= deck.slides.length) {
    throw new Error(`MOVE_SLIDE toIndex out of range: ${operation.toIndex}`);
  }

  const [slide] = deck.slides.splice(from, 1);
  deck.slides.splice(operation.toIndex, 0, slide);
}

function updateElement(deck, operation) {
  const slide = requireSlide(deck, operation.slideId, "UPDATE_ELEMENT");
  const element = requireElement(slide, operation.elementId, "UPDATE_ELEMENT");
  if (!operation.patch || typeof operation.patch !== "object") {
    throw new Error("UPDATE_ELEMENT requires a patch object.");
  }
  if ("id" in operation.patch && String(operation.patch.id) !== String(element.id)) {
    throw new Error("UPDATE_ELEMENT cannot change element id.");
  }

  Object.assign(element, deepMerge(element, operation.patch));
}

function replaceText(deck, operation) {
  const slide = requireSlide(deck, operation.slideId, "REPLACE_TEXT");
  const element = requireElement(slide, operation.elementId, "REPLACE_TEXT");
  if (typeof operation.text !== "string") {
    throw new Error("REPLACE_TEXT requires text as a string.");
  }
  if (!element.text) {
    throw new Error(`REPLACE_TEXT target is not a text element: ${operation.elementId}`);
  }

  replaceElementText(element, operation.text);
}

function replaceElementText(element, text) {
  element.type = "text";
  element.text = structuredClone(element.text || {});
  element.text.originalRaw ??= element.text.raw || "";
  element.text.raw = text;

  const lines = text.split(/\r?\n/);
  const existingParagraphs = element.text.paragraphs?.length
    ? structuredClone(element.text.paragraphs)
    : [{ raw: "", align: element.style?.align ?? null, level: null, bullet: undefined, runs: [{ text: "", style: {} }] }];
  const templateParagraph = existingParagraphs[0];

  element.text.paragraphs = lines.map((line, index) => {
    const paragraph = index === 0 ? templateParagraph : structuredClone(templateParagraph);
    const runs = paragraph.runs?.length ? paragraph.runs : [{ text: "", style: {} }];
    return {
      ...paragraph,
      raw: line,
      runs: runs.map((run, runIndex) => ({
        ...run,
        text: runIndex === 0 ? line : "",
      })),
    };
  });
  element.text.runs = element.text.paragraphs.flatMap((paragraph) => paragraph.runs || []);
}

function deepMerge(target, patch) {
  if (!isPlainObject(target) || !isPlainObject(patch)) {
    return structuredClone(patch);
  }

  const merged = structuredClone(target);
  for (const [key, value] of Object.entries(patch)) {
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = deepMerge(merged[key], value);
    } else {
      merged[key] = structuredClone(value);
    }
  }
  return merged;
}

function appendOperationLog(deck, operation) {
  deck.operationLog = deck.operationLog || [];
  deck.operationLog.push({
    sequence: deck.operationLog.length + 1,
    type: operation.type,
    operation: structuredClone(operation),
  });
}

function reindexSlides(deck) {
  deck.slides.forEach((slide, index) => {
    slide.index = index;
  });
  if (deck.meta) {
    deck.meta.slideCount = deck.slides.length;
  }
}

function assertDeck(deck) {
  if (!deck || !Array.isArray(deck.slides)) {
    throw new Error("DeckJSON must include a slides array.");
  }
}

function assertOperation(operation) {
  if (!operation || typeof operation !== "object") {
    throw new Error("Operation must be an object.");
  }
  if (!OPERATION_TYPES.has(operation.type)) {
    throw new Error(`Unknown operation type: ${operation.type}`);
  }
}

function requireSlide(deck, slideId, operationType) {
  const slide = findSlide(deck, slideId);
  if (!slide) {
    throw new Error(`${operationType} could not find slide: ${slideId}`);
  }
  return slide;
}

function requireElement(slide, elementId, operationType) {
  const element = findElement(slide.elements || [], elementId);
  if (!element) {
    throw new Error(`${operationType} could not find element ${elementId} on slide ${slide.id}.`);
  }
  return element;
}

function findSlide(deck, slideId) {
  return deck.slides.find((slide) => String(slide.id) === String(slideId)) || null;
}

function findSlideIndex(deck, slideId) {
  return deck.slides.findIndex((slide) => String(slide.id) === String(slideId));
}

function findElement(elements, elementId) {
  for (const element of elements) {
    if (String(element.id) === String(elementId)) {
      return element;
    }
    const nested = findElement(element.elements || [], elementId);
    if (nested) {
      return nested;
    }
  }
  return null;
}

function normalizeInsertIndex(deck, index) {
  const insertIndex = index ?? deck.slides.length;
  if (!Number.isInteger(insertIndex)) {
    throw new Error("Slide insert index must be an integer.");
  }
  if (insertIndex < 0 || insertIndex > deck.slides.length) {
    throw new Error(`Slide insert index out of range: ${insertIndex}`);
  }
  return insertIndex;
}

function nextCloneId(deck, sourceId) {
  const base = `${sourceId}-clone`;
  let candidate = base;
  let suffix = 1;
  while (findSlide(deck, candidate)) {
    suffix += 1;
    candidate = `${base}-${suffix}`;
  }
  return candidate;
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

