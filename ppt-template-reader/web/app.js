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

loadTemplates();

function loadTemplates(selectedTemplateId = null) {
  return fetch(apiUrl("/api/templates"))
    .then((response) => response.json())
    .then((payload) => {
      templates = payload.templates;
      templateSelect.innerHTML = payload.templates
        .map((template) => `
          <option value="${escapeHtml(template.id)}">${escapeHtml(template.name)}</option>
        `)
        .join("");
      templateSelect.value = selectedTemplateId || payload.defaultTemplateId;
      loadTemplateSummary();
    })
    .catch(() => {
      templateMeta.textContent = "Templates unavailable";
    });
}

function loadTemplateSummary() {
  updateTemplatePreview();
  const templateId = encodeURIComponent(templateSelect.value);
  fetch(apiUrl(`/api/template-summary?templateId=${templateId}`))
  .then((response) => response.json())
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
  statusEl.textContent = "Generating...";
  slidesEl.innerHTML = "";
  downloadPptxLink.hidden = true;
  generatedPreview.hidden = true;
  generatedPreviewImage.removeAttribute("src");

  const response = await fetch(apiUrl("/api/generate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      templateId: templateSelect.value,
      topic: topic.value,
      text: sourceText.value,
    }),
  });

  const payload = await response.json();
  if (!response.ok) {
    statusEl.textContent = payload.error || "Generation failed.";
    return;
  }

  statusEl.textContent = `Generated ${Object.keys(payload.curatedContent.slides).length} slides. Opening editor...`;
  window.location.href = editorUrl(payload.editorPath || `/editor?templateId=${encodeURIComponent(payload.templateId)}&generatedDeck=${encodeURIComponent(payload.downloadPath)}`);
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

function apiUrl(path) {
  return `${apiBase}${path}`;
}

function assetUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${apiBase}/${String(path).replace(/^\//, "")}`;
}

function editorUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
