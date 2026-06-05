const templateMeta = document.querySelector("#templateMeta");
const templateSelect = document.querySelector("#templateSelect");
const templatePreviewImage = document.querySelector("#templatePreviewImage");
const sourceText = document.querySelector("#sourceText");
const topic = document.querySelector("#topic");
const generateBtn = document.querySelector("#generateBtn");
const statusEl = document.querySelector("#status");
const generatedPreview = document.querySelector("#generatedPreview");
const generatedPreviewImage = document.querySelector("#generatedPreviewImage");
const slidesEl = document.querySelector("#slides");
const downloadPptxLink = document.querySelector("#downloadPptxLink");
const applyLayoutBtn = document.querySelector("#applyLayoutBtn");
const slideEditor = document.querySelector("#slideEditor");
const editorSlideSelect = document.querySelector("#editorSlideSelect");
const editorStage = document.querySelector("#editorStage");
const apiBase = (window.PPT_API_BASE || "").replace(/\/$/, "");
let templates = [];
let templatesReady = false;
let currentDeck = null;
let layoutUpdates = new Map();

loadTemplates();

function loadTemplates(selectedTemplateId = null) {
  generateBtn.disabled = true;
  return fetch(apiUrl("/api/templates"))
    .then((response) => {
      if (!response.ok) {
        throw new Error("Template API unavailable");
      }
      return response.json();
    })
    .then((payload) => {
      if (!Array.isArray(payload.templates) || payload.templates.length === 0) {
        throw new Error("No templates returned");
      }

      templates = payload.templates;
      templateSelect.innerHTML = payload.templates
        .map((template) => `
          <option value="${escapeHtml(template.id)}">${escapeHtml(template.name)}</option>
        `)
        .join("");
      templateSelect.value = selectedTemplateId || payload.defaultTemplateId;
      templatesReady = true;
      generateBtn.disabled = false;
      setStatus("Paste text and generate.");
      return loadTemplateSummary();
    })
    .catch(() => {
      templates = [];
      templatesReady = false;
      templateSelect.innerHTML = "";
      templatePreviewImage.removeAttribute("src");
      templateMeta.textContent = "Templates unavailable";
      setStatus("Generator API unavailable. Check that PPT_API_BASE_URL points to your backend.", "error");
    });
}

function loadTemplateSummary() {
  updateTemplatePreview();
  if (!templateSelect.value) {
    templateMeta.textContent = "Template unavailable";
    return Promise.resolve();
  }

  const templateId = encodeURIComponent(templateSelect.value);
  return fetch(apiUrl(`/api/template-summary?templateId=${templateId}`))
  .then((response) => {
    if (!response.ok) {
      throw new Error("Template summary unavailable");
    }
    return response.json();
  })
  .then((summary) => {
    templateMeta.textContent = `${summary.templateName} · ${summary.slides} slides · ${summary.layouts} layouts · ${summary.assets} assets`;
  })
  .catch(() => {
    templateMeta.textContent = "Template unavailable";
  });
}

templateSelect.addEventListener("change", loadTemplateSummary);

function updateTemplatePreview() {
  const template = templates.find((item) => item.id === templateSelect.value);
  if (!template?.previewPath) {
    templatePreviewImage.removeAttribute("src");
    return;
  }

  templatePreviewImage.src = assetUrl(template.previewPath);
}

generateBtn.addEventListener("click", async () => {
  if (!templatesReady || !templateSelect.value) {
    setStatus("Templates are not loaded yet. Check the generator API connection.", "error");
    return;
  }

  setStatus("Generating...");
  slidesEl.innerHTML = "";
  currentDeck = null;
  layoutUpdates = new Map();
  downloadPptxLink.hidden = true;
  applyLayoutBtn.hidden = true;
  slideEditor.hidden = true;
  generatedPreview.hidden = true;
  generatedPreviewImage.removeAttribute("src");
  generateBtn.disabled = true;
  generateBtn.dataset.busy = "true";

  try {
    const topicValue = topic.value.trim();
    const topicWordCount = topicValue ? topicValue.split(/\s+/).length : 0;
    if (topicWordCount < 1 || topicWordCount > 10) {
      setStatus("Topic must be between 1 and 10 words and match the pasted source text.", "error");
      return;
    }

    const response = await fetch(apiUrl("/api/generate"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        templateId: templateSelect.value,
        topic: topicValue,
        text: sourceText.value,
      }),
    });

    const payload = await readJson(response);
    if (!response.ok) {
      setStatus(payload.error || "Generation failed.", "error");
      return;
    }

    const slideCount = Object.keys(payload.curatedContent.slides).length;
    setStatus(generationStatus(slideCount, payload.contentSource), generationTone(payload.contentSource));
    currentDeck = {
      templateId: payload.templateId,
      filledTemplatePath: payload.downloadPath,
      pptxDownloadPath: payload.pptxDownloadPath,
      pptxPreviewPath: payload.pptxPreviewPath,
      slidePreview: payload.slidePreview || [],
    };
    renderSlides(payload.curatedContent.slides, payload.templateMap, payload.slidePreview);
    renderSlideEditor(currentDeck.slidePreview);

    if (payload.pptxPreviewPath) {
      generatedPreviewImage.src = assetUrl(payload.pptxPreviewPath);
      generatedPreview.hidden = false;
    }

    if (payload.pptxDownloadPath) {
      downloadPptxLink.href = assetUrl(payload.pptxDownloadPath);
      downloadPptxLink.textContent = "Download PPTX";
      downloadPptxLink.hidden = false;
    }
  } catch (error) {
    setStatus("Generation API unavailable. Check that the backend is running and PPT_API_BASE_URL is set.", "error");
  } finally {
    delete generateBtn.dataset.busy;
    generateBtn.disabled = !templatesReady;
  }
});

editorSlideSelect.addEventListener("change", () => {
  renderEditorStage(Number(editorSlideSelect.value));
});

applyLayoutBtn.addEventListener("click", async () => {
  if (!currentDeck || layoutUpdates.size === 0) {
    setStatus("Drag a text box before applying layout.", "warning");
    return;
  }

  applyLayoutBtn.disabled = true;
  applyLayoutBtn.dataset.busy = "true";
  setStatus("Applying layout changes...");

  try {
    const response = await fetch(apiUrl("/api/apply-layout"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        templateId: currentDeck.templateId,
        filledTemplatePath: currentDeck.filledTemplatePath,
        layoutUpdates: Array.from(layoutUpdates.values()),
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) {
      setStatus(payload.error || "Layout update failed.", "error");
      return;
    }

    currentDeck.filledTemplatePath = payload.downloadPath;
    currentDeck.pptxDownloadPath = payload.pptxDownloadPath;
    currentDeck.pptxPreviewPath = payload.pptxPreviewPath || currentDeck.pptxPreviewPath;
    currentDeck.slidePreview = payload.slidePreview || currentDeck.slidePreview;
    layoutUpdates = new Map();
    applyLayoutBtn.hidden = true;

    if (payload.pptxPreviewPath) {
      generatedPreviewImage.src = assetUrl(payload.pptxPreviewPath);
      generatedPreview.hidden = false;
    }
    if (payload.pptxDownloadPath) {
      downloadPptxLink.href = assetUrl(payload.pptxDownloadPath);
      downloadPptxLink.textContent = "Download Edited PPTX";
      downloadPptxLink.hidden = false;
    }

    renderSlideEditor(currentDeck.slidePreview, Number(editorSlideSelect.value));
    setStatus("Layout applied. Download the edited PPTX when ready.", "success");
  } catch (error) {
    setStatus("Layout API unavailable. Check that the backend is running.", "error");
  } finally {
    delete applyLayoutBtn.dataset.busy;
    applyLayoutBtn.disabled = false;
  }
});

function renderSlides(slides, templateMap = {}, slidePreview = []) {
  const previewLookup = Object.fromEntries(
    slidePreview.map((slide) => [String(slide.index), slide])
  );

  slidesEl.innerHTML = Object.entries(slides)
    .map(([index, fields]) => {
      const purpose = templateMap[index]?.purpose || "content";
      const preview = previewLookup[index];
      const rows = Object.entries(fields)
        .map(([key, value]) => `
          <div class="field">
            <div class="key">${escapeHtml(key)}</div>
            <div>${escapeHtml(value)}</div>
          </div>
        `)
        .join("");

      return `
        <article class="slide">
          <div class="slideHeader">
            <strong>Slide ${index}</strong>
            <span>${escapeHtml(formatPurpose(purpose))}</span>
          </div>
          ${rows}
        </article>
      `;
    })
    .join("");
}

function renderSlideEditor(slidePreview = [], selectedIndex = null) {
  const editableSlides = slidePreview.filter((slide) => Array.isArray(slide.elements) && slide.elements.length);
  if (!editableSlides.length) {
    slideEditor.hidden = true;
    applyLayoutBtn.hidden = true;
    return;
  }

  slideEditor.hidden = false;
  editorSlideSelect.innerHTML = editableSlides
    .map((slide) => `<option value="${escapeHtml(slide.index)}">Slide ${escapeHtml(slide.index)}</option>`)
    .join("");
  const nextIndex = selectedIndex && editableSlides.some((slide) => Number(slide.index) === Number(selectedIndex))
    ? selectedIndex
    : editableSlides[0].index;
  editorSlideSelect.value = String(nextIndex);
  renderEditorStage(Number(nextIndex));
}

function renderEditorStage(slideIndex) {
  if (!currentDeck) {
    return;
  }

  const slide = currentDeck.slidePreview.find((item) => Number(item.index) === Number(slideIndex));
  if (!slide) {
    editorStage.innerHTML = "";
    return;
  }

  const previewImage = currentDeck.pptxPreviewPath && Number(slideIndex) === 1
    ? assetUrl(currentDeck.pptxPreviewPath)
    : "";
  editorStage.classList.toggle("hasSlideImage", Boolean(previewImage));
  editorStage.style.backgroundImage = previewImage ? `url("${previewImage}")` : "";
  editorStage.dataset.previewState = previewImage ? "Slide preview" : "Layout guide";

  editorStage.innerHTML = slide.elements
    .map((element) => {
      const key = layoutKey(slide.index, element.shapeId);
      const moved = layoutUpdates.get(key);
      const box = moved || element;
      return `
        <button
          type="button"
          class="editorBox"
          data-slide-index="${escapeHtml(slide.index)}"
          data-shape-id="${escapeHtml(element.shapeId)}"
          style="left:${box.x}%; top:${box.y}%; width:${box.w}%; height:${box.h}%;"
          title="${escapeHtml(element.field || element.shapeId)}"
        >
          <span>${escapeHtml(element.field || "text")}</span>
          ${escapeHtml(element.text)}
        </button>
      `;
    })
    .join("");

  editorStage.querySelectorAll(".editorBox").forEach((box) => {
    box.addEventListener("pointerdown", startDrag);
  });
}

function startDrag(event) {
  const box = event.currentTarget;
  const stageRect = editorStage.getBoundingClientRect();
  const startRect = box.getBoundingClientRect();
  const slideIndex = Number(box.dataset.slideIndex);
  const shapeId = box.dataset.shapeId;
  const startX = event.clientX;
  const startY = event.clientY;
  const originalLeft = ((startRect.left - stageRect.left) / stageRect.width) * 100;
  const originalTop = ((startRect.top - stageRect.top) / stageRect.height) * 100;
  const width = (startRect.width / stageRect.width) * 100;
  const height = (startRect.height / stageRect.height) * 100;

  box.setPointerCapture(event.pointerId);
  box.classList.add("isDragging");

  function move(pointerEvent) {
    const dx = ((pointerEvent.clientX - startX) / stageRect.width) * 100;
    const dy = ((pointerEvent.clientY - startY) / stageRect.height) * 100;
    const x = clamp(originalLeft + dx, 0, 100 - width);
    const y = clamp(originalTop + dy, 0, 100 - height);
    box.style.left = `${x}%`;
    box.style.top = `${y}%`;
    layoutUpdates.set(layoutKey(slideIndex, shapeId), { slideIndex, shapeId, x, y, w: width, h: height });
    applyLayoutBtn.hidden = false;
  }

  function stop(pointerEvent) {
    box.releasePointerCapture(pointerEvent.pointerId);
    box.classList.remove("isDragging");
    box.removeEventListener("pointermove", move);
    box.removeEventListener("pointerup", stop);
    box.removeEventListener("pointercancel", stop);
  }

  box.addEventListener("pointermove", move);
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
}

function layoutKey(slideIndex, shapeId) {
  return `${slideIndex}:${shapeId}`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatPurpose(value) {
  return String(value).replaceAll("_", " ");
}

function formatContentSource(contentSource = {}) {
  if (contentSource.source === "openai") {
    return contentSource.model || "OpenAI";
  }
  if (contentSource.source === "fallback") {
    return "local fallback";
  }
  if (contentSource.source === "missing_api_key") {
    return "local rules";
  }
  if (contentSource.source === "disabled") {
    return "local rules";
  }
  return "the generator";
}

function generationStatus() {
  return "Generated using the most advanced LLM, your PPT is ready to download.";
}

function generationTone(contentSource = {}) {
  if (["fallback", "missing_api_key", "disabled"].includes(contentSource.source)) {
    return "warning";
  }
  return "success";
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (error) {
    return {};
  }
}

function setStatus(message, tone = "") {
  statusEl.textContent = message;
  if (tone) {
    statusEl.dataset.tone = tone;
  } else {
    delete statusEl.dataset.tone;
  }
}

function apiUrl(path) {
  return `${apiBase}${path}`;
}

function assetUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${apiBase}/${String(path).replace(/^\//, "")}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
