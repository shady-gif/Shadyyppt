const PROTECTED_PLACEHOLDER_TYPES = new Set(["date", "footer", "slideNumber"]);
const MASTER_INSTRUCTION_RE = /^click to edit\b/i;

export function buildTextSlotReport(deck, options = {}) {
  const slots = detectTextSlots(deck, options);
  return {
    deck: {
      sourcePath: deck.meta?.sourcePath || null,
      slideCount: deck.slides?.length || 0,
    },
    summary: summarizeSlots(slots),
    slots,
  };
}

export function detectTextSlots(deck, options = {}) {
  const slots = [];
  for (const slide of deck.slides || []) {
    const textElements = collectTextElements(slide.elements || []);
    const largestFontSize = Math.max(...textElements.map((element) => element.style?.fontSize || 0), 0);

    for (const element of textElements) {
      const role = classifyTextRole(element, { slide, largestFontSize });
      const editable = isEditableTextSlot(element, role, options);
      const capacity = estimateTextCapacity(element, role, options);
      const currentFit = validateTextFit(element.text?.raw || "", { role, capacity });

      slots.push({
        id: `${slide.id}:${element.id}`,
        slideId: String(slide.id),
        slideIndex: slide.index,
        elementId: String(element.id),
        name: element.name || null,
        role,
        editable,
        protectionReason: editable ? null : protectionReason(element, role),
        box: {
          x: element.x ?? null,
          y: element.y ?? null,
          w: element.w ?? null,
          h: element.h ?? null,
        },
        style: {
          fontSize: element.style?.fontSize ?? null,
          fontFamily: element.style?.fontFamily ?? null,
          align: element.style?.align ?? null,
        },
        originalText: element.text?.raw || "",
        originalStats: textStats(element.text?.raw || ""),
        capacity,
        currentFit,
      });
    }
  }

  return slots;
}

export function classifyTextRole(element, context = {}) {
  const placeholderType = element.placeholder?.type;
  if (PROTECTED_PLACEHOLDER_TYPES.has(placeholderType)) {
    return placeholderType;
  }
  if (placeholderType === "title" || placeholderType === "subtitle" || placeholderType === "body") {
    return placeholderType;
  }

  const text = (element.text?.raw || "").trim();
  const lowerName = String(element.name || "").toLowerCase();
  const stats = textStats(text);
  const fontSize = element.style?.fontSize || 0;
  const h = element.h || 0;
  const y = element.y || 0;
  const largestFontSize = context.largestFontSize || fontSize;

  if (/footer/.test(lowerName)) return "footer";
  if (/date/.test(lowerName)) return "date";
  if (/slide number|page/.test(lowerName)) return "slideNumber";
  if (/caption/.test(lowerName)) return "caption";
  if (/quote/.test(lowerName)) return "quote";
  if (/subtitle|sub title/.test(lowerName)) return "subtitle";
  if (/title|headline/.test(lowerName)) return "title";

  if (/^\d{4}$/.test(text)) {
    return "metadata";
  }
  if (/^created by\b/i.test(text) || /^by\b/i.test(text)) {
    return "byline";
  }
  if (stats.words >= 18 || stats.chars >= 100) {
    return "body";
  }
  if (fontSize >= Math.max(72, largestFontSize * 0.72) && stats.words <= 5) {
    return y < 2.2 ? "title" : "section";
  }
  if (fontSize >= 42 && stats.words <= 8) {
    return "heading";
  }
  if (h <= 0.85 && stats.words <= 10) {
    return "heading";
  }
  if (stats.words <= 12 && fontSize <= 18) {
    return "caption";
  }

  return "body";
}

export function estimateTextCapacity(element, role, options = {}) {
  const fontSize = element.style?.fontSize || fallbackFontSize(role);
  const box = {
    w: positiveOrDefault(element.w, 1),
    h: positiveOrDefault(element.h, fontSize / 72),
  };
  const original = element.text?.raw || "";
  const originalStats = textStats(original);
  const maxLines = estimateMaxLines(box, fontSize, role);
  const geometricChars = estimateGeometricChars(box, fontSize, maxLines, role);
  const originalCharsLimit = originalStats.chars > 0
    ? Math.ceil(originalStats.chars * originalExpansionRatio(role))
    : null;
  const maxChars = originalCharsLimit
    ? Math.ceil(Math.min(
        Math.max(originalCharsLimit, geometricChars * geometryInfluenceRatio(role)),
        originalStats.chars * originalExpansionCeiling(role),
      ))
    : geometricChars;
  const maxWeightedChars = originalStats.weightedChars > 0
    ? Number(Math.min(
        Math.max(originalStats.weightedChars * originalExpansionRatio(role), maxChars * 0.82),
        originalStats.weightedChars * originalExpansionCeiling(role),
      ).toFixed(2))
    : Number((maxChars * 0.92).toFixed(2));

  return {
    maxChars: clampInt(maxChars, roleMinChars(role), roleMaxChars(role, options)),
    maxWords: estimateMaxWords(maxChars, originalStats.words, role, options),
    maxLines,
    maxWeightedChars,
    safetyMargin: options.safetyMargin ?? 0.9,
    basis: originalStats.chars > 0 ? "original-plus-geometry" : "geometry",
  };
}

function estimateMaxWords(maxChars, originalWords, role, options) {
  const geometricWords = Math.floor(maxChars / averageCharsPerWord(role));
  if (originalWords > 0) {
    return clampInt(
      Math.min(
        Math.max(Math.ceil(originalWords * originalExpansionRatio(role)), geometricWords),
        Math.ceil(originalWords * originalExpansionCeiling(role)),
      ),
      roleMinWords(role),
      roleMaxWords(role, options),
    );
  }

  return clampInt(
    geometricWords,
    roleMinWords(role),
    roleMaxWords(role, options),
  );
}

export function validateTextFit(text, slotOrCapacity) {
  const capacity = slotOrCapacity.capacity || slotOrCapacity;
  const role = slotOrCapacity.role || "body";
  const stats = textStats(text);
  const estimatedLines = estimateRenderedLines(text, capacity, role);
  const checks = {
    chars: stats.chars <= capacity.maxChars,
    words: stats.words <= capacity.maxWords,
    lines: stats.lines <= capacity.maxLines && estimatedLines <= capacity.maxLines,
    weightedChars: stats.weightedChars <= capacity.maxWeightedChars,
  };
  const status = Object.values(checks).every(Boolean) ? "fit" : "overflow";

  return {
    status,
    checks,
    actual: {
      chars: stats.chars,
      words: stats.words,
      lines: stats.lines,
      weightedChars: stats.weightedChars,
      estimatedLines,
    },
    capacity,
  };
}

export function logicalTrimToFit(text, slotOrCapacity) {
  const capacity = slotOrCapacity.capacity || slotOrCapacity;
  const role = slotOrCapacity.role || "body";
  const sentences = splitSentences(text);
  let result = "";

  for (const sentence of sentences) {
    const candidate = result ? `${result} ${sentence}` : sentence;
    if (validateTextFit(candidate, { role, capacity }).status !== "fit") {
      break;
    }
    result = candidate;
  }

  if (result) {
    return result;
  }

  const words = text.split(/\s+/).filter(Boolean);
  let wordResult = "";
  for (const word of words) {
    const candidate = wordResult ? `${wordResult} ${word}` : word;
    if (validateTextFit(candidate, { role, capacity }).status !== "fit") {
      break;
    }
    wordResult = candidate;
  }
  return wordResult;
}

export function textStats(text) {
  const normalized = String(text || "").trim();
  const words = normalized ? normalized.match(/\b[\w'-]+\b/g) || [] : [];
  const lines = normalized ? normalized.split(/\r?\n/).length : 0;
  return {
    chars: normalized.length,
    words: words.length,
    lines,
    weightedChars: Number(weightedTextLength(normalized).toFixed(2)),
  };
}

export function weightedTextLength(text) {
  let score = 0;
  for (const char of String(text || "")) {
    if (/\s/.test(char)) {
      score += 0.34;
    } else if ("il.,'|!;:".includes(char)) {
      score += 0.45;
    } else if ("mwMW@#%&".includes(char)) {
      score += 1.3;
    } else if (/[A-Z]/.test(char)) {
      score += 1.08;
    } else {
      score += 1;
    }
  }
  return score;
}

function isTextElement(element) {
  return element?.type === "text" && element.text && typeof element.text.raw === "string";
}

function collectTextElements(elements) {
  const textElements = [];
  for (const element of elements || []) {
    if (isTextElement(element)) {
      textElements.push(element);
    }
    if (element?.type === "group" && Array.isArray(element.elements)) {
      textElements.push(...collectTextElements(element.elements));
    }
  }
  return textElements;
}

function isEditableTextSlot(element, role, options) {
  if (options.includeProtected) {
    return true;
  }
  if (PROTECTED_PLACEHOLDER_TYPES.has(role)) {
    return false;
  }
  if (MASTER_INSTRUCTION_RE.test(element.text?.raw || "")) {
    return false;
  }
  return true;
}

function protectionReason(element, role) {
  if (PROTECTED_PLACEHOLDER_TYPES.has(role)) {
    return "protected-placeholder";
  }
  if (MASTER_INSTRUCTION_RE.test(element.text?.raw || "")) {
    return "master-instruction";
  }
  return "protected";
}

function estimateMaxLines(box, fontSize, role) {
  const lineHeightInches = (fontSize / 72) * lineHeightRatio(role);
  return clampInt(Math.floor(box.h / Math.max(lineHeightInches, 0.12)), 1, roleMaxLines(role));
}

function estimateGeometricChars(box, fontSize, maxLines, role) {
  const averageCharWidth = (fontSize / 72) * averageGlyphWidthRatio(role);
  const charsPerLine = Math.max(4, Math.floor(box.w / Math.max(averageCharWidth, 0.04)));
  return Math.max(roleMinChars(role), Math.floor(charsPerLine * maxLines * 0.92));
}

function estimateRenderedLines(text, capacity, role) {
  const safeWeightedPerLine = Math.max(4, capacity.maxWeightedChars / Math.max(1, capacity.maxLines));
  const lines = String(text || "").split(/\r?\n/);
  return lines.reduce((total, line) => {
    return total + Math.max(1, Math.ceil(weightedTextLength(line) / safeWeightedPerLine));
  }, 0);
}

function summarizeSlots(slots) {
  const byRole = {};
  for (const slot of slots) {
    byRole[slot.role] = (byRole[slot.role] || 0) + 1;
  }
  return {
    total: slots.length,
    editable: slots.filter((slot) => slot.editable).length,
    protected: slots.filter((slot) => !slot.editable).length,
    byRole,
  };
}

function splitSentences(text) {
  return String(text || "")
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function positiveOrDefault(value, fallback) {
  return Number(value) > 0 ? Number(value) : fallback;
}

function fallbackFontSize(role) {
  if (role === "title") return 64;
  if (role === "section") return 56;
  if (role === "subtitle") return 34;
  if (role === "heading") return 30;
  if (role === "caption") return 14;
  return 22;
}

function originalExpansionRatio(role) {
  const ratios = {
    title: 1.08,
    section: 1.06,
    subtitle: 1.08,
    heading: 1.1,
    byline: 1.05,
    metadata: 1,
    caption: 1,
    quote: 0.95,
    body: 0.96,
  };
  return ratios[role] || 0.96;
}

function originalExpansionCeiling(role) {
  const ratios = {
    title: 1.25,
    section: 1.2,
    subtitle: 1.16,
    heading: 1.24,
    byline: 1.12,
    metadata: 1.05,
    caption: 1.08,
    quote: 1.08,
    body: 1.08,
  };
  return ratios[role] || 1.08;
}

function geometryInfluenceRatio(role) {
  if (role === "body") return 0.62;
  if (role === "quote") return 0.6;
  if (["title", "section", "heading"].includes(role)) return 0.72;
  return 0.66;
}

function averageCharsPerWord(role) {
  if (["title", "section", "heading"].includes(role)) return 7;
  if (role === "caption") return 6;
  return 6.2;
}

function averageGlyphWidthRatio(role) {
  if (["title", "section"].includes(role)) return 0.5;
  if (role === "heading") return 0.48;
  return 0.46;
}

function lineHeightRatio(role) {
  if (["title", "section"].includes(role)) return 1.08;
  return 1.18;
}

function roleMinChars(role) {
  if (role === "metadata") return 4;
  if (["title", "section", "heading"].includes(role)) return 3;
  return 16;
}

function roleMinWords(role) {
  if (role === "metadata") return 1;
  if (["title", "section", "heading"].includes(role)) return 1;
  return 4;
}

function roleMaxChars(role, options) {
  if (options.maxCharsByRole?.[role]) return options.maxCharsByRole[role];
  const limits = {
    title: 52,
    section: 46,
    subtitle: 90,
    heading: 64,
    byline: 70,
    metadata: 12,
    caption: 80,
    quote: 120,
    body: 220,
  };
  return limits[role] || 180;
}

function roleMaxWords(role, options) {
  if (options.maxWordsByRole?.[role]) return options.maxWordsByRole[role];
  const limits = {
    title: 8,
    section: 7,
    subtitle: 14,
    heading: 9,
    byline: 10,
    metadata: 2,
    caption: 12,
    quote: 22,
    body: 38,
  };
  return limits[role] || 30;
}

function roleMaxLines(role) {
  const limits = {
    title: 1,
    section: 1,
    subtitle: 2,
    heading: 1,
    byline: 1,
    metadata: 1,
    caption: 2,
    quote: 3,
    body: 5,
  };
  return limits[role] || 4;
}

function clampInt(value, min, max) {
  return Math.max(min, Math.min(max, Math.floor(Number(value) || min)));
}
