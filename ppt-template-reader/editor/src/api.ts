import type { AnimationMetadata, EditorDeck, EditorOperation, TemplateOption } from "./types";

declare global {
  interface Window {
    PPT_API_BASE?: string;
  }
}

const apiBase = (window.PPT_API_BASE || "").replace(/\/$/, "");

export async function fetchTemplates(): Promise<{ defaultTemplateId: string; templates: TemplateOption[] }> {
  return fetchJson("/api/templates");
}

export async function fetchEditorDeck(templateId: string, generatedDeckPath?: string | null): Promise<EditorDeck> {
  const params = new URLSearchParams({ templateId });
  if (generatedDeckPath) {
    params.set("generatedDeck", generatedDeckPath);
  }
  return fetchJson(`/api/editor-template?${params.toString()}`);
}

export async function exportEditedDeck(payload: {
  templateId: string;
  generatedDeckPath?: string | null;
  operations: EditorOperation[];
  userContent?: {
    topic?: string;
    text?: string;
  };
}): Promise<{
  pptxDownloadPath: string;
  operationsPath: string;
  animationMetadata: AnimationMetadata;
  pptxPreviewPath?: string;
  warnings?: string[];
}> {
  return fetchJson("/api/editor/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function assetUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${apiBase}/${path.replace(/^\//, "")}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}
