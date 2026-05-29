import {
  detectTextSlots,
  logicalTrimToFit,
  textStats,
  validateTextFit,
} from "./text-slots.js";

export function buildFitAwareTextOperations(deck, requests, options = {}) {
  if (!Array.isArray(requests)) {
    throw new Error("Text replacement requests must be an array.");
  }

  const slots = detectTextSlots(deck, options);
  const slotByKey = new Map(slots.map((slot) => [slotKey(slot.slideId, slot.elementId), slot]));
  const operations = [];
  const report = [];

  for (const request of requests) {
    validateRequestShape(request);
    const key = slotKey(request.slideId, request.elementId);
    const slot = slotByKey.get(key);
    if (!slot) {
      throw new Error(`No text slot found for slide ${request.slideId}, element ${request.elementId}.`);
    }
    if (!slot.editable && !options.includeProtected) {
      throw new Error(`Text slot ${key} is protected: ${slot.protectionReason || "protected"}.`);
    }

    const fitted = fitTextForSlot(request.text, slot, options);
    report.push(buildReportItem(slot, request, fitted));

    if (fitted.validation.status !== "fit") {
      throw new Error(`Could not fit text for slide ${slot.slideId}, element ${slot.elementId}.`);
    }

    operations.push({
      type: "REPLACE_TEXT",
      slideId: slot.slideId,
      elementId: slot.elementId,
      text: fitted.text,
      fit: {
        role: slot.role,
        strategy: fitted.strategy,
        capacity: slot.capacity,
      },
    });
  }

  return {
    operations,
    report,
    summary: summarizeFitReport(report),
  };
}

export async function buildFitAwareTextOperationsWithRewrite(deck, requests, options = {}) {
  if (!Array.isArray(requests)) {
    throw new Error("Text replacement requests must be an array.");
  }

  const slots = detectTextSlots(deck, options);
  const slotByKey = new Map(slots.map((slot) => [slotKey(slot.slideId, slot.elementId), slot]));
  const operations = [];
  const report = [];

  for (const request of requests) {
    validateRequestShape(request);
    const key = slotKey(request.slideId, request.elementId);
    const slot = slotByKey.get(key);
    if (!slot) {
      throw new Error(`No text slot found for slide ${request.slideId}, element ${request.elementId}.`);
    }
    if (!slot.editable && !options.includeProtected) {
      throw new Error(`Text slot ${key} is protected: ${slot.protectionReason || "protected"}.`);
    }

    const fitted = await fitTextForSlotWithRewrite(request.text, slot, options);
    report.push(buildReportItem(slot, request, fitted));

    if (fitted.validation.status !== "fit") {
      throw new Error(`Could not fit text for slide ${slot.slideId}, element ${slot.elementId}.`);
    }

    operations.push({
      type: "REPLACE_TEXT",
      slideId: slot.slideId,
      elementId: slot.elementId,
      text: fitted.text,
      fit: {
        role: slot.role,
        strategy: fitted.strategy,
        capacity: slot.capacity,
        rewrite: fitted.rewrite || undefined,
      },
    });
  }

  return {
    operations,
    report,
    summary: summarizeFitReport(report),
  };
}

export function fitTextForSlot(text, slot, options = {}) {
  const normalized = normalizeText(text);
  const directValidation = validateTextFit(normalized, slot);
  if (directValidation.status === "fit") {
    return {
      text: normalized,
      strategy: "unchanged",
      validation: directValidation,
    };
  }

  if (isShortSlot(slot.role)) {
    const compressed = compressShortSlotText(normalized, slot);
    const compressedValidation = validateTextFit(compressed, slot);
    if (compressed && compressedValidation.status === "fit") {
      return {
        text: compressed,
        strategy: "keyword-compressed",
        validation: compressedValidation,
      };
    }
  }

  const roleNormalized = normalizeForRole(normalized, slot.role);
  const roleValidation = validateTextFit(roleNormalized, slot);
  if (roleValidation.status === "fit") {
    return {
      text: roleNormalized,
      strategy: "role-normalized",
      validation: roleValidation,
    };
  }

  const sentenceTrimmed = trimCompleteSentencesToFit(roleNormalized, slot);
  const sentenceValidation = validateTextFit(sentenceTrimmed, slot);
  if (sentenceTrimmed && sentenceValidation.status === "fit") {
    return {
      text: sentenceTrimmed,
      strategy: "sentence-trimmed",
      validation: sentenceValidation,
    };
  }

  const hardTrimmed = hardTrimToFit(roleNormalized, slot);
  const hardValidation = validateTextFit(hardTrimmed, slot);
  if (hardTrimmed && hardValidation.status === "fit") {
    return {
      text: hardTrimmed,
      strategy: "hard-trimmed",
      validation: hardValidation,
    };
  }

  const fallback = fallbackTextForSlot(slot, options);
  const fallbackValidation = validateTextFit(fallback, slot);
  if (fallbackValidation.status === "fit") {
    return {
      text: fallback,
      strategy: "fallback",
      validation: fallbackValidation,
    };
  }

  const preserved = normalizeText(slot.originalText || "");
  const preservedValidation = validateTextFit(preserved, slot);
  if (preserved && preservedValidation.status === "fit") {
    return {
      text: preserved,
      strategy: "preserved-original",
      validation: preservedValidation,
    };
  }

  return {
    text: fallback,
    strategy: "failed",
    validation: fallbackValidation,
  };
}

export async function fitTextForSlotWithRewrite(text, slot, options = {}) {
  const normalized = normalizeText(text);
  const directValidation = validateTextFit(normalized, slot);
  const shouldRewrite = typeof options.rewriter === "function"
    && (options.rewriteFittingText || directValidation.status !== "fit");

  if (shouldRewrite) {
    const rewritten = sanitizeRewriteCandidate(await options.rewriter({ text: normalized, slot }));
    if (rewritten) {
      const rewrittenValidation = validateTextFit(rewritten, slot);
      if (rewrittenValidation.status === "fit") {
        return {
          text: rewritten,
          strategy: "llm-rewritten",
          validation: rewrittenValidation,
          rewrite: {
            attempted: true,
            accepted: true,
          },
        };
      }

      const fittedRewrite = fitTextForSlot(rewritten, slot, options);
      if (fittedRewrite.validation.status === "fit") {
        return {
          ...fittedRewrite,
          strategy: `llm-${fittedRewrite.strategy}`,
          rewrite: {
            attempted: true,
            accepted: false,
            reason: "rewrite-needed-trimming",
            candidate: rewritten,
          },
        };
      }
    }

    if (directValidation.status === "fit") {
      return {
        text: normalized,
        strategy: "unchanged",
        validation: directValidation,
        rewrite: {
          attempted: true,
          accepted: false,
          reason: "no-valid-rewrite",
        },
      };
    }
  }

  return fitTextForSlot(normalized, slot, options);
}

function hardTrimToFit(text, slot) {
  const words = normalizeText(text).split(/\s+/).filter(Boolean);
  let result = "";

  for (const word of words) {
    const cleanWord = stripTrailingPunctuation(word);
    const candidate = result ? `${result} ${cleanWord}` : cleanWord;
    if (validateTextFit(candidate, slot).status !== "fit") {
      break;
    }
    result = candidate;
  }

  return tidyEnding(result, slot.role);
}

function normalizeForRole(text, role) {
  const normalized = normalizeText(text);
  if (["title", "section", "heading", "metadata"].includes(role)) {
    return normalized
      .replace(/[.!?]+$/g, "")
      .replace(/\s+[-–—]\s+/g, ": ")
      .trim();
  }
  if (role === "body") {
    return normalized.replace(/\s*[\r\n]+\s*/g, " ");
  }
  return normalized;
}

function trimCompleteSentencesToFit(text, slot) {
  const sentences = splitSentences(text);
  let result = "";
  for (const sentence of sentences) {
    const candidate = result ? `${result} ${sentence}` : sentence;
    if (validateTextFit(candidate, slot).status !== "fit") {
      break;
    }
    result = candidate;
  }
  return tidyEnding(result, slot.role);
}

function compressShortSlotText(text, slot) {
  const words = normalizeText(text)
    .replace(/[^\w\s'-]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  const significant = words.filter((word) => !SHORT_SLOT_STOPWORDS.has(word.toLowerCase()));
  const candidates = [
    significant.slice(-2).join(" "),
    significant.slice(-1).join(" "),
    significant.slice(0, 2).join(" "),
    words.slice(-2).join(" "),
    words.slice(-1).join(" "),
  ].filter(Boolean);

  for (const candidate of candidates.map(toTitleishCase)) {
    if (validateTextFit(candidate, slot).status === "fit") {
      return tidyEnding(candidate, slot.role);
    }
  }

  return "";
}

function tidyEnding(text, role) {
  let result = normalizeText(text).replace(/[\s,;:.-]+$/g, "");
  if (!result) {
    return "";
  }

  const words = result.split(/\s+/);
  while (words.length > 1 && DANGLING_END_WORDS.has(words.at(-1).toLowerCase())) {
    words.pop();
  }
  result = words.join(" ");

  if (["body", "quote"].includes(role) && result && !/[.!?]$/.test(result)) {
    result = `${result}.`;
  }
  return result;
}

function toTitleishCase(text) {
  return text
    .split(/\s+/)
    .map((word) => {
      if (/[A-Z]{2,}/.test(word) || word.includes("-")) {
        return word;
      }
      return `${word.slice(0, 1).toUpperCase()}${word.slice(1)}`;
    })
    .join(" ");
}

function splitSentences(text) {
  return String(text || "")
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function isShortSlot(role) {
  return ["title", "section", "heading", "subtitle", "caption"].includes(role);
}

function fallbackTextForSlot(slot, options) {
  if (options.fallbackTextByRole?.[slot.role]) {
    return options.fallbackTextByRole[slot.role];
  }

  const fallbackByRole = {
    title: "Overview",
    section: "Overview",
    heading: "Key Point",
    subtitle: "A concise summary",
    byline: "Generated Summary",
    metadata: "2026",
    caption: "Supporting detail",
    quote: "Focused insight",
    body: "A concise summary of the most relevant point.",
  };
  return fallbackByRole[slot.role] || "Summary";
}

function buildReportItem(slot, request, fitted) {
  return {
    slideId: slot.slideId,
    slideIndex: slot.slideIndex,
    elementId: slot.elementId,
    role: slot.role,
    name: slot.name,
    status: fitted.validation.status,
    strategy: fitted.strategy,
    changed: normalizeText(request.text) !== fitted.text,
    input: {
      text: normalizeText(request.text),
      stats: textStats(request.text),
    },
    output: {
      text: fitted.text,
      stats: textStats(fitted.text),
    },
    capacity: slot.capacity,
    validation: fitted.validation,
    rewrite: fitted.rewrite || undefined,
  };
}

function summarizeFitReport(report) {
  return {
    total: report.length,
    fit: report.filter((item) => item.status === "fit").length,
    overflow: report.filter((item) => item.status !== "fit").length,
    changed: report.filter((item) => item.changed).length,
    byStrategy: report.reduce((acc, item) => {
      acc[item.strategy] = (acc[item.strategy] || 0) + 1;
      return acc;
    }, {}),
  };
}

function validateRequestShape(request) {
  if (!request || typeof request !== "object") {
    throw new Error("Text replacement request must be an object.");
  }
  if (request.slideId === undefined || request.elementId === undefined) {
    throw new Error("Text replacement request requires slideId and elementId.");
  }
  if (typeof request.text !== "string") {
    throw new Error("Text replacement request requires text as a string.");
  }
}

function stripTrailingPunctuation(word) {
  return word.replace(/[,:;.!?]+$/g, "");
}

function normalizeText(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function sanitizeRewriteCandidate(value) {
  if (value === undefined || value === null) {
    return "";
  }
  return String(value)
    .replace(/^```(?:text|json)?/i, "")
    .replace(/```$/i, "")
    .replace(/^["']|["']$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function slotKey(slideId, elementId) {
  return `${slideId}:${elementId}`;
}

const SHORT_SLOT_STOPWORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "built",
  "complete",
  "for",
  "from",
  "in",
  "into",
  "is",
  "of",
  "on",
  "the",
  "to",
  "with",
]);

const DANGLING_END_WORDS = new Set([
  "a",
  "an",
  "and",
  "as",
  "at",
  "by",
  "for",
  "from",
  "in",
  "into",
  "of",
  "on",
  "or",
  "the",
  "to",
  "with",
  "feeling",
]);
