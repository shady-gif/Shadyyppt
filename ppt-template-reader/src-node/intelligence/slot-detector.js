export function detectLayoutSlots(layout) {
  return layout.elements
    .filter((element) => element.placeholder || element.type === "text" || element.type === "image")
    .map((element, index) => {
      const role = inferSlotRole(element);
      return {
        id: `${layout.id}-slot-${index + 1}`,
        sourceElementId: element.id,
        role,
        x: element.x,
        y: element.y,
        w: element.w,
        h: element.h,
        maxChars: estimateMaxChars(element, role),
        fontSizeRange: estimateFontSizeRange(element),
      };
    });
}

function inferSlotRole(element) {
  if (element.placeholder?.type) {
    return element.placeholder.type;
  }

  const name = String(element.name || "").toLowerCase();
  if (name.includes("title")) return "title";
  if (name.includes("subtitle")) return "subtitle";
  if (name.includes("caption")) return "caption";
  if (name.includes("quote")) return "quote";
  if (element.type === "image") return "image";
  return "body";
}

function estimateMaxChars(element, role) {
  if (["image", "chart", "table"].includes(role)) {
    return undefined;
  }

  const width = element.w || 1;
  const height = element.h || 1;
  const fontSize = element.style?.fontSize || fallbackFontSize(role);
  const averageCharWidthInches = (fontSize / 72) * 0.48;
  const lineHeightInches = (fontSize / 72) * 1.18;
  const charsPerLine = Math.max(8, Math.floor(width / averageCharWidthInches));
  const lines = Math.max(1, Math.floor(height / lineHeightInches));

  return Math.max(12, Math.floor(charsPerLine * lines * 0.88));
}

function estimateFontSizeRange(element) {
  const fontSize = element.style?.fontSize;
  if (!fontSize) {
    return undefined;
  }
  return [Math.max(8, Math.round(fontSize * 0.72)), Math.round(fontSize)];
}

function fallbackFontSize(role) {
  if (role === "title") return 34;
  if (role === "subtitle") return 22;
  if (role === "caption") return 12;
  return 18;
}

