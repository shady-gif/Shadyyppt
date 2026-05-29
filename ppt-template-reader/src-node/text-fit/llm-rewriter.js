export function buildSlotRewritePrompt({ text, slot }) {
  return [
    "Rewrite this text so it fits a PowerPoint template text box.",
    "",
    "Rules:",
    `- Role: ${slot.role}`,
    `- Max characters: ${slot.capacity.maxChars}`,
    `- Max words: ${slot.capacity.maxWords}`,
    `- Max lines: ${slot.capacity.maxLines}`,
    "- Preserve the original meaning.",
    "- Do not add new facts, names, dates, or claims.",
    "- Use professional presentation tone.",
    "- Do not include quotation marks, markdown, bullets, labels, or explanations.",
    "- Output only the rewritten text.",
    "",
    "Text:",
    text,
  ].join("\n");
}

export function createOllamaSlotRewriter(options = {}) {
  const endpoint = options.endpoint || process.env.OLLAMA_URL || "http://127.0.0.1:11434/api/chat";
  const model = options.model || process.env.OLLAMA_MODEL || "llama3.2";
  const timeoutMs = Number(options.timeoutMs || process.env.OLLAMA_TIMEOUT_MS || 3500);

  return async ({ text, slot }) => {
    const payload = {
      model,
      stream: false,
      messages: [
        {
          role: "system",
          content: "You rewrite text for PowerPoint placeholders. Return only the rewritten text.",
        },
        {
          role: "user",
          content: buildSlotRewritePrompt({ text, slot }),
        },
      ],
    };

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!response.ok) {
        return null;
      }

      const body = await response.json();
      return sanitizeRewriteResponse(body?.message?.content || body?.response || "");
    } catch {
      return null;
    }
  };
}

export function sanitizeRewriteResponse(value) {
  let text = String(value || "").trim();
  if (!text) {
    return "";
  }

  text = text
    .replace(/^```(?:text|json)?/i, "")
    .replace(/```$/i, "")
    .trim();

  if (text.startsWith("{")) {
    try {
      const parsed = JSON.parse(text);
      text = parsed.text || parsed.rewrite || parsed.output || text;
    } catch {
      // Keep raw text when the model did not return valid JSON.
    }
  }

  return String(text)
    .replace(/^["']|["']$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

