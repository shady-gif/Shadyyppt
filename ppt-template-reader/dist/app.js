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
const apiBase = (window.PPT_API_BASE || "").replace(/\/$/, "");
let templates = [];
let templatesReady = false;

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
  downloadPptxLink.hidden = true;
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
    renderSlides(payload.curatedContent.slides, payload.templateMap, payload.slidePreview);

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
