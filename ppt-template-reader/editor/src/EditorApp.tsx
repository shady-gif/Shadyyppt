import { useEffect, useMemo, useState } from "react";
import { assetUrl, exportEditedDeck, fetchEditorDeck, fetchTemplates } from "./api";
import { applyEditorOperation, mergeOperation, roundInches } from "./operations";
import { SlideCanvas } from "./SlideCanvas";
import {
  ANIMATION_OPTIONS,
  FONT_OPTIONS,
  type AnimationOption,
  type EditorDeck,
  type EditorOperation,
  type SlideObject,
  type TemplateOption,
} from "./types";

export function EditorApp() {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const initialTemplateId = initialParams.get("templateId") || "";
  const initialGeneratedDeckPath = initialParams.get("generatedDeck");
  const [templates, setTemplates] = useState<TemplateOption[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [generatedDeckPath, setGeneratedDeckPath] = useState<string | null>(initialGeneratedDeckPath);
  const [deck, setDeck] = useState<EditorDeck | null>(null);
  const [selectedSlideId, setSelectedSlideId] = useState<string | null>(null);
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [operations, setOperations] = useState<EditorOperation[]>([]);
  const [topic, setTopic] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [status, setStatus] = useState("Loading templates...");
  const [downloadPath, setDownloadPath] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    fetchTemplates()
      .then((payload) => {
        setTemplates(payload.templates);
        setTemplateId(initialTemplateId || payload.defaultTemplateId);
      })
      .catch((error: Error) => setStatus(error.message));
  }, [initialTemplateId]);

  useEffect(() => {
    if (!templateId) {
      return;
    }

    setStatus("Loading template...");
    setDeck(null);
    setOperations([]);
    setSelectedObjectId(null);
    setDownloadPath(null);
    setPreviewPath(null);

    fetchEditorDeck(templateId, generatedDeckPath)
      .then((payload) => {
        setDeck(payload);
        setSelectedSlideId(payload.slides[0]?.id || null);
        setStatus(payload.sourceKind === "generated" ? `Generated ${payload.templateName} deck loaded` : `${payload.templateName} loaded`);
      })
      .catch((error: Error) => setStatus(error.message));
  }, [generatedDeckPath, templateId]);

  const selectedSlide = useMemo(
    () => deck?.slides.find((slide) => slide.id === selectedSlideId) || deck?.slides[0] || null,
    [deck, selectedSlideId],
  );

  const selectedObject = useMemo(
    () => selectedSlide?.objects.find((object) => object.id === selectedObjectId) || null,
    [selectedObjectId, selectedSlide],
  );

  function commitOperation(operation: EditorOperation) {
    setDeck((current) => (current ? applyEditorOperation(current, operation) : current));
    setOperations((current) => mergeOperation(current, operation));
    setDownloadPath(null);
    setPreviewPath(null);
  }

  async function handleExport() {
    if (!deck) {
      return;
    }

    setIsExporting(true);
    setStatus("Exporting edited PPTX...");
    try {
      const result = await exportEditedDeck({
        templateId: deck.templateId,
        generatedDeckPath: deck.sourceJsonPath || generatedDeckPath,
        operations,
        userContent: {
          topic,
          text: sourceText,
        },
      });
      setDownloadPath(result.pptxDownloadPath);
      setPreviewPath(result.pptxPreviewPath || null);
      setStatus(result.warnings?.length ? result.warnings.join(" ") : "Edited PPTX ready");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Export failed.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <main className="templateEditor">
      <header className="editorTopbar">
        <a className="brandLink" href="/app">
          <span className="brandMark" aria-hidden="true" />
          <span>Prompt on PPT</span>
        </a>
        <div className="topbarControls">
          <select
            value={templateId}
            onChange={(event) => {
              setGeneratedDeckPath(null);
              setTemplateId(event.target.value);
              window.history.replaceState(null, "", `/editor?templateId=${encodeURIComponent(event.target.value)}`);
            }}
            aria-label="Template"
          >
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={handleExport} disabled={!deck || isExporting}>
            {isExporting ? "Exporting" : "Export PPTX"}
          </button>
          {downloadPath && (
            <a className="downloadLink" href={assetUrl(downloadPath)} download>
              Download
            </a>
          )}
        </div>
      </header>

      <section className="editorGrid">
        <aside className="leftRail" aria-label="Slides and content">
          <div className="panelBlock">
            <p className="panelLabel">Slides</p>
            <div className="slideList">
              {deck?.slides.map((slide) => (
                <button
                  type="button"
                  key={slide.id}
                  className={slide.id === selectedSlide?.id ? "slideButton active" : "slideButton"}
                  onClick={() => {
                    setSelectedSlideId(slide.id);
                    setSelectedObjectId(null);
                  }}
                >
                  {slide.index}
                </button>
              ))}
            </div>
          </div>

          <div className="panelBlock">
            <label htmlFor="topic">Topic</label>
            <input id="topic" value={topic} onChange={(event) => setTopic(event.target.value)} />
            <label htmlFor="sourceText">Source Text</label>
            <textarea id="sourceText" value={sourceText} onChange={(event) => setSourceText(event.target.value)} />
          </div>

          <div className="statusBlock">
            <span>{operations.length} ops</span>
            <p>{status}</p>
          </div>
        </aside>

        <section className="canvasPanel" aria-label="Slide canvas">
          {deck && selectedSlide ? (
            <SlideCanvas
              deck={deck}
              slide={selectedSlide}
              selectedObjectId={selectedObjectId}
              onSelectObject={setSelectedObjectId}
              onMoveObject={(object, x, y) =>
                commitOperation({
                  type: "moveObject",
                  slideId: selectedSlide.id,
                  objectId: object.id,
                  x,
                  y,
                })
              }
              onResizeObject={(object, geometry) => {
                commitOperation({
                  type: "moveObject",
                  slideId: selectedSlide.id,
                  objectId: object.id,
                  x: geometry.x,
                  y: geometry.y,
                });
                commitOperation({
                  type: "resizeObject",
                  slideId: selectedSlide.id,
                  objectId: object.id,
                  width: geometry.width,
                  height: geometry.height,
                });
              }}
            />
          ) : (
            <div className="canvasEmpty">Loading</div>
          )}
          {previewPath && (
            <figure className="exportPreview">
              <img src={assetUrl(previewPath)} alt="Edited PPTX preview" />
            </figure>
          )}
        </section>

        <Inspector
          selectedSlide={selectedSlide}
          selectedObject={selectedObject}
          onBackgroundChange={(color) => {
            if (selectedSlide) {
              commitOperation({ type: "changeBackgroundColor", slideId: selectedSlide.id, color });
            }
          }}
          onObjectChange={commitOperation}
        />
      </section>
    </main>
  );
}

interface InspectorProps {
  selectedSlide: EditorDeck["slides"][number] | null;
  selectedObject: SlideObject | null;
  onBackgroundChange: (color: string) => void;
  onObjectChange: (operation: EditorOperation) => void;
}

function Inspector({ selectedSlide, selectedObject, onBackgroundChange, onObjectChange }: InspectorProps) {
  if (!selectedSlide) {
    return <aside className="inspector" aria-label="Inspector" />;
  }

  return (
    <aside className="inspector" aria-label="Inspector">
      <div className="panelBlock">
        <p className="panelLabel">Slide</p>
        <label htmlFor="backgroundColor">Background</label>
        <input
          id="backgroundColor"
          type="color"
          value={selectedSlide.background}
          onChange={(event) => onBackgroundChange(event.target.value)}
        />
      </div>

      {selectedObject ? (
        <div className="panelBlock">
          <p className="panelLabel">{selectedObject.name || selectedObject.id}</p>
          <GeometryFields selectedSlide={selectedSlide} selectedObject={selectedObject} onObjectChange={onObjectChange} />

          {selectedObject.type === "text" && (
            <>
              <label htmlFor="objectText">Text</label>
              <textarea
                id="objectText"
                value={selectedObject.text}
                onChange={(event) =>
                  onObjectChange({
                    type: "updateText",
                    slideId: selectedSlide.id,
                    objectId: selectedObject.id,
                    text: event.target.value,
                  })
                }
              />

              <label htmlFor="font">Font</label>
              <select
                id="font"
                value={selectedObject.font}
                onChange={(event) =>
                  onObjectChange({
                    type: "changeFont",
                    slideId: selectedSlide.id,
                    objectId: selectedObject.id,
                    font: event.target.value as (typeof FONT_OPTIONS)[number],
                  })
                }
              >
                {FONT_OPTIONS.map((font) => (
                  <option key={font} value={font}>
                    {font}
                  </option>
                ))}
              </select>

              <label htmlFor="textColor">Text Color</label>
              <input
                id="textColor"
                type="color"
                value={selectedObject.color}
                onChange={(event) =>
                  onObjectChange({
                    type: "changeTextColor",
                    slideId: selectedSlide.id,
                    objectId: selectedObject.id,
                    color: event.target.value,
                  })
                }
              />
            </>
          )}

          <AnimationSelect
            id="enterAnimation"
            label="Enter"
            value={selectedObject.enterAnimation}
            onChange={(animation) =>
              onObjectChange({
                type: "setEnterAnimation",
                slideId: selectedSlide.id,
                objectId: selectedObject.id,
                animation,
              })
            }
          />
          <AnimationSelect
            id="exitAnimation"
            label="Exit"
            value={selectedObject.exitAnimation}
            onChange={(animation) =>
              onObjectChange({
                type: "setExitAnimation",
                slideId: selectedSlide.id,
                objectId: selectedObject.id,
                animation,
              })
            }
          />
        </div>
      ) : (
        <div className="emptyInspector">Select an object</div>
      )}
    </aside>
  );
}

function GeometryFields({
  selectedSlide,
  selectedObject,
  onObjectChange,
}: {
  selectedSlide: EditorDeck["slides"][number];
  selectedObject: SlideObject;
  onObjectChange: (operation: EditorOperation) => void;
}) {
  return (
    <div className="geometryGrid">
      <NumberField
        label="X"
        value={selectedObject.x}
        onChange={(x) =>
          onObjectChange({ type: "moveObject", slideId: selectedSlide.id, objectId: selectedObject.id, x, y: selectedObject.y })
        }
      />
      <NumberField
        label="Y"
        value={selectedObject.y}
        onChange={(y) =>
          onObjectChange({ type: "moveObject", slideId: selectedSlide.id, objectId: selectedObject.id, x: selectedObject.x, y })
        }
      />
      <NumberField
        label="W"
        value={selectedObject.width}
        onChange={(width) =>
          onObjectChange({
            type: "resizeObject",
            slideId: selectedSlide.id,
            objectId: selectedObject.id,
            width,
            height: selectedObject.height,
          })
        }
      />
      <NumberField
        label="H"
        value={selectedObject.height}
        onChange={(height) =>
          onObjectChange({
            type: "resizeObject",
            slideId: selectedSlide.id,
            objectId: selectedObject.id,
            width: selectedObject.width,
            height,
          })
        }
      />
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="numberField">
      <span>{label}</span>
      <input
        type="number"
        min="0"
        step="0.1"
        value={value}
        onChange={(event) => {
          const nextValue = Number(event.target.value);
          if (Number.isFinite(nextValue)) {
            onChange(roundInches(nextValue));
          }
        }}
      />
    </label>
  );
}

function AnimationSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: AnimationOption;
  onChange: (animation: AnimationOption) => void;
}) {
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value as AnimationOption)}>
        {ANIMATION_OPTIONS.map((animation) => (
          <option key={animation} value={animation}>
            {animation}
          </option>
        ))}
      </select>
    </>
  );
}
