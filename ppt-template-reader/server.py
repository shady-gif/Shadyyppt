from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).parent.resolve()
WEB_DIR = ROOT / "web"
GENERATED_DIR = ROOT / "outputs" / "generated"
GENERATED_PREVIEW_DIR = WEB_DIR / "generated-previews"
TEMPLATE_DIR = ROOT / "templates"
TEMPLATE_PREVIEW_DIR = WEB_DIR / "template-previews"
TEMPLATE_REGISTRY_PATH = ROOT / "outputs" / "template-registry.json"
BUILTIN_TEMPLATES = {
    "profile": {
        "name": "Profile",
        "jsonPath": ROOT / "outputs" / "profile.json",
        "pptxPath": ROOT / "templates" / "profile.pptx",
        "previewPath": "template-previews/profile.pptx.png",
    },
    "pitch": {
        "name": "Pitch",
        "jsonPath": ROOT / "outputs" / "pitch.json",
        "pptxPath": ROOT / "templates" / "pitch.pptx",
        "previewPath": "template-previews/pitch.pptx.png",
    },
    "marketing": {
        "name": "Marketing",
        "jsonPath": ROOT / "outputs" / "marketing.json",
        "pptxPath": ROOT / "templates" / "marketing.pptx",
        "previewPath": "template-previews/marketing.pptx.png",
    },
    "journey": {
        "name": "Journey",
        "jsonPath": ROOT / "outputs" / "journey.json",
        "pptxPath": ROOT / "templates" / "journey.pptx",
        "previewPath": "template-previews/journey.pptx.png",
    },
    "technology": {
        "name": "Technology",
        "jsonPath": ROOT / "outputs" / "technology.json",
        "pptxPath": ROOT / "templates" / "technology.pptx",
        "previewPath": "template-previews/technology.pptx.png",
    },
    "brand": {
        "name": "Brand",
        "jsonPath": ROOT / "outputs" / "brand.json",
        "pptxPath": ROOT / "templates" / "brand.pptx",
        "previewPath": "template-previews/brand.pptx.png",
    },
    "portfolio": {
        "name": "Portfolio",
        "jsonPath": ROOT / "outputs" / "portfolio.json",
        "pptxPath": ROOT / "templates" / "portfolio.pptx",
        "previewPath": "template-previews/portfolio.pptx.png",
    },
    "creative": {
        "name": "Creative",
        "jsonPath": ROOT / "outputs" / "creative.json",
        "pptxPath": ROOT / "templates" / "creative.pptx",
        "previewPath": "template-previews/creative.pptx.png",
    },
    "time": {
        "name": "Time",
        "jsonPath": ROOT / "outputs" / "time.json",
        "pptxPath": ROOT / "templates" / "time.pptx",
        "previewPath": "template-previews/time.pptx.png",
    },
    "iot": {
        "name": "IoT",
        "jsonPath": ROOT / "outputs" / "iot.json",
        "pptxPath": ROOT / "templates" / "iot.pptx",
        "previewPath": "template-previews/iot.pptx.png",
    },
    "roadmap": {
        "name": "Roadmap",
        "jsonPath": ROOT / "outputs" / "roadmap.json",
        "pptxPath": ROOT / "templates" / "roadmap.pptx",
        "previewPath": "template-previews/roadmap.pptx.png",
    },
    "startup": {
        "name": "Startup",
        "jsonPath": ROOT / "outputs" / "startup.json",
        "pptxPath": ROOT / "templates" / "startup.pptx",
        "previewPath": "template-previews/startup.pptx.png",
    },
    "interior": {
        "name": "Interior",
        "jsonPath": ROOT / "outputs" / "interior.json",
        "pptxPath": ROOT / "templates" / "interior.pptx",
        "previewPath": "template-previews/interior.pptx.png",
    },
    "architecture": {
        "name": "Architecture",
        "jsonPath": ROOT / "outputs" / "architecture.json",
        "pptxPath": ROOT / "templates" / "architecture.pptx",
        "previewPath": "template-previews/architecture.pptx.png",
    },
    "product": {
        "name": "Product",
        "jsonPath": ROOT / "outputs" / "product.json",
        "pptxPath": ROOT / "templates" / "product.pptx",
        "previewPath": "template-previews/product.pptx.png",
    },
}
DEFAULT_TEMPLATE_ID = "profile"
EDITOR_FONTS = {"Inter", "Poppins", "Montserrat", "Roboto", "Playfair Display"}
EDITOR_ANIMATIONS = {"none", "fade", "zoom", "wipe", "fly"}
EDITOR_OPERATION_TYPES = {
    "updateText",
    "moveObject",
    "resizeObject",
    "changeFont",
    "changeTextColor",
    "changeBackgroundColor",
    "replaceImage",
    "setEnterAnimation",
    "setExitAnimation",
}

sys.path.insert(0, str(ROOT / "src"))

from content_generator import ContentGenerator  # noqa: E402
from editor_template import build_editor_deck, read_template_asset  # noqa: E402
from pptx_exporter import PptxExporter  # noqa: E402
from template_converter import convert_pptx_to_json  # noqa: E402


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", os.environ.get("CORS_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/app", "/app/"}:
            self.path = "/app.html"
            super().do_GET()
            return

        if parsed.path in {"/editor", "/editor/"}:
            self.path = "/editor.html"
            super().do_GET()
            return

        if parsed.path == "/health":
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/editor-template":
            template_id = _query_value(parsed.query, "templateId", DEFAULT_TEMPLATE_ID)
            template_config = _template_config(template_id)
            generated_deck_path = _query_value(parsed.query, "generatedDeck", "")
            if generated_deck_path:
                template_path = _resolve_generated_deck_path(generated_deck_path)
                template = json.loads(template_path.read_text(encoding="utf-8"))
                source_json_path = f"outputs/generated/{template_path.name}"
            else:
                template = json.loads(template_config["jsonPath"].read_text(encoding="utf-8"))
                source_json_path = None
            self._send_json(build_editor_deck(template_id, template_config, template, source_json_path))
            return

        if parsed.path == "/api/template-asset":
            self._handle_template_asset(parsed.query)
            return

        if parsed.path == "/api/template-summary":
            template_id = _template_id_from_query(parsed.query)
            self._send_json(_template_summary(template_id))
            return

        if parsed.path == "/api/templates":
            self._send_json(_templates_payload())
            return

        if parsed.path.startswith("/outputs/"):
            file_path = ROOT / parsed.path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                self.send_header("Content-Type", _content_type(file_path))
                self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
                return
            self.send_error(404, "File not found")
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload-template":
            self._handle_template_upload()
            return

        if parsed.path == "/api/editor/export":
            self._handle_editor_export()
            return

        if parsed.path != "/api/generate":
            self.send_error(404, "Not found")
            return

        try:
            body = self._read_json_body()
            raw_text = body.get("text", "")
            topic = body.get("topic") or None
            template_id = body.get("templateId") or DEFAULT_TEMPLATE_ID
            template_config = _template_config(template_id)
            template = json.loads(template_config["jsonPath"].read_text(encoding="utf-8"))
            result = ContentGenerator(template, template_id=template_id).generate(raw_text, topic)
            result = _fit_generation_text(template_config, result)

            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            output_stem = _safe_output_stem(result["topic"])
            output_path = GENERATED_DIR / f"{output_stem}-filled-template.json"
            output_path.write_text(
                json.dumps(result["filledTemplateJson"], indent=2),
                encoding="utf-8",
            )
            pptx_path = GENERATED_DIR / f"{output_stem}-filled-deck.pptx"
            PptxExporter(template_config["pptxPath"]).export(result["filledTemplateJson"], pptx_path)
            pptx_preview_path = _render_pptx_preview(pptx_path)

            self._send_json(
                {
                    "topic": result["topic"],
                    "templateId": template_id,
                    "templateName": template_config["name"],
                    "mapperSource": result["mapperSource"],
                    "curatedContent": result["curatedContent"],
                    "updates": result["updates"],
                    "textFit": result.get("textFit"),
                    "templateMap": result["filledTemplateJson"]["generation"]["templateMap"],
                    "slidePreview": _slide_preview(result["filledTemplateJson"]),
                    "downloadPath": f"outputs/generated/{output_path.name}",
                    "pptxDownloadPath": f"outputs/generated/{pptx_path.name}",
                    "pptxPreviewPath": pptx_preview_path,
                    "editorPath": f"/editor?templateId={template_id}&generatedDeck=outputs/generated/{output_path.name}",
                }
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": f"Generation failed: {exc}"}, status=500)

    def _handle_template_upload(self) -> None:
        try:
            filename = self.headers.get("X-Filename", "uploaded-template.pptx")
            if not filename.lower().endswith(".pptx"):
                raise ValueError("Please upload a .pptx file.")

            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("Uploaded file is empty.")

            template_name = Path(filename).stem
            template_id = _unique_template_id(_safe_output_stem(template_name))
            pptx_path = TEMPLATE_DIR / f"{template_id}.pptx"
            json_path = ROOT / "outputs" / f"{template_id}.json"

            TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
            pptx_path.write_bytes(self.rfile.read(length))
            converted = convert_pptx_to_json(pptx_path, json_path)
            preview_path = _render_template_preview(pptx_path)

            registry = _uploaded_templates()
            registry[template_id] = {
                "name": _display_name(template_name),
                "jsonPath": str(json_path),
                "pptxPath": str(pptx_path),
                "previewPath": preview_path,
            }
            _save_uploaded_templates(registry)

            self._send_json(
                {
                    "template": _template_payload(template_id, _template_config(template_id)),
                    "summary": {
                        "slides": len(converted.get("slides", [])),
                        "layouts": len(converted.get("layouts", [])),
                        "assets": len(converted.get("assets", [])),
                        "validation": converted.get("validation", {}),
                    },
                }
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": f"Upload failed: {exc}"}, status=500)

    def _handle_template_asset(self, query: str) -> None:
        try:
            template_id = _query_value(query, "templateId", DEFAULT_TEMPLATE_ID)
            asset_path = _query_value(query, "assetPath", "")
            if not asset_path:
                raise ValueError("assetPath is required.")

            template_config = _template_config(template_id)
            data, content_type = read_template_asset(template_config["pptxPath"], asset_path)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404, "Asset not found")
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": f"Asset failed: {exc}"}, status=500)

    def _handle_editor_export(self) -> None:
        try:
            body = self._read_json_body()
            template_id = body.get("templateId") or DEFAULT_TEMPLATE_ID
            operations = _validate_editor_operations(body.get("operations") or [])
            user_content = body.get("userContent") or {}
            raw_text = user_content.get("text") or body.get("text") or ""
            topic = user_content.get("topic") or body.get("topic") or None
            generated_deck_path = body.get("generatedDeckPath") or ""

            template_config = _template_config(template_id)
            template = json.loads(template_config["jsonPath"].read_text(encoding="utf-8"))

            result = None
            filled_template = template
            output_stem = _safe_output_stem(topic or f"{template_id}-edited")
            if generated_deck_path:
                generated_path = _resolve_generated_deck_path(str(generated_deck_path))
                filled_template = json.loads(generated_path.read_text(encoding="utf-8"))
                output_stem = _safe_output_stem(generated_path.stem.replace("-filled-template", "-edited"))
            elif str(raw_text).strip():
                result = ContentGenerator(template, template_id=template_id).generate(str(raw_text), topic)
                result = _fit_generation_text(template_config, result)
                filled_template = result["filledTemplateJson"]
                output_stem = _safe_output_stem(f"{result['topic']}-edited")

            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            operations_path = GENERATED_DIR / f"{output_stem}-operations.json"
            animation_metadata = _editor_animation_metadata(operations)
            operations_path.write_text(
                json.dumps(
                    {
                        "templateId": template_id,
                        "operations": operations,
                        "animationMetadata": animation_metadata,
                        "capabilities": {
                            "pptAnimationExport": False,
                        },
                        "sourceJsonPath": generated_deck_path or None,
                        "userContent": {
                            "topic": topic,
                            "hasText": bool(str(raw_text).strip()),
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            filled_template = _attach_editor_metadata(filled_template, operations, animation_metadata)
            output_json_path = GENERATED_DIR / f"{output_stem}-template.json"
            output_json_path.write_text(json.dumps(filled_template, indent=2), encoding="utf-8")

            pptx_path = GENERATED_DIR / f"{output_stem}-deck.pptx"
            PptxExporter(template_config["pptxPath"]).export(
                filled_template,
                pptx_path,
                editor_operations_path=operations_path,
            )
            pptx_preview_path = _render_pptx_preview(pptx_path)

            warnings = _editor_operation_warnings(operations)
            self._send_json(
                {
                    "templateId": template_id,
                    "templateName": template_config["name"],
                    "operationsPath": f"outputs/generated/{operations_path.name}",
                    "downloadPath": f"outputs/generated/{output_json_path.name}",
                    "pptxDownloadPath": f"outputs/generated/{pptx_path.name}",
                    "pptxPreviewPath": pptx_preview_path,
                    "animationMetadata": animation_metadata,
                    "warnings": warnings,
                    "updates": result.get("updates") if result else [],
                    "textFit": result.get("textFit") if result else None,
                }
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": f"Editor export failed: {exc}"}, status=500)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _template_summary(template_id: str = DEFAULT_TEMPLATE_ID) -> dict:
    template_config = _template_config(template_id)
    template = json.loads(template_config["jsonPath"].read_text(encoding="utf-8"))
    return {
        "templateId": template_id,
        "templateName": template_config["name"],
        "templatePath": str(template_config["jsonPath"]),
        "pptxPath": str(template_config["pptxPath"]),
        "previewPath": template_config.get("previewPath"),
        "slides": len(template.get("slides", [])),
        "layouts": len(template.get("layouts", [])),
        "assets": len(template.get("assets", [])),
    }


def _templates_payload() -> dict:
    return {
        "defaultTemplateId": DEFAULT_TEMPLATE_ID,
        "templates": [
            _template_payload(template_id, config)
            for template_id, config in _visible_templates().items()
        ],
    }


def _fit_generation_text(template_config: dict, result: dict) -> dict:
    if os.environ.get("DISABLE_TEXT_FITTER", "").lower() in {"1", "true", "yes"}:
        result["textFit"] = {"source": "disabled", "enabled": False}
        return result

    updates = result.get("updates") or []
    if not updates:
        result["textFit"] = {"source": "none", "enabled": True, "summary": {"total": 0}}
        return result

    try:
        fitted = _run_text_fitter(template_config["pptxPath"], updates)
    except Exception as exc:
        result["textFit"] = {
            "source": "unavailable",
            "enabled": True,
            "error": str(exc),
        }
        return result

    fitted_updates = fitted.get("updates") or updates
    result["updates"] = fitted_updates
    result["filledTemplateJson"] = _apply_fitted_updates(result["filledTemplateJson"], fitted_updates)
    result["textFit"] = {
        "source": "node",
        "enabled": True,
        "summary": fitted.get("fitSummary", {}),
        "report": fitted.get("fitReport", []),
    }
    return result


def _run_text_fitter(pptx_path: Path, updates: list[dict]) -> dict:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="text-fit-", dir=GENERATED_DIR) as tmp_dir:
        tmp_path = Path(tmp_dir)
        updates_path = tmp_path / "updates.json"
        output_path = tmp_path / "fitted-updates.json"
        updates_path.write_text(json.dumps(updates), encoding="utf-8")

        command = [
            "node",
            str(ROOT / "src-node" / "cli" / "fit-template-updates.js"),
            str(pptx_path),
            str(updates_path),
            str(output_path),
        ]
        if os.environ.get("ENABLE_FIT_REWRITE", "").lower() in {"1", "true", "yes"}:
            command.append("--rewrite")

        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("TEXT_FITTER_TIMEOUT", "45")),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(detail or "text fitter failed")
        if not output_path.exists():
            raise RuntimeError("text fitter did not write output")
        return json.loads(output_path.read_text(encoding="utf-8"))


def _apply_fitted_updates(filled_template: dict, updates: list[dict]) -> dict:
    update_lookup = {
        (int(update["slideIndex"]), str(update["shapeId"])): str(update["newText"])
        for update in updates
        if update.get("slideIndex") is not None and update.get("shapeId") is not None
    }

    for slide in filled_template.get("slides", []):
        slide_index = int(slide.get("index"))
        for text_box in slide.get("texts", []):
            key = (slide_index, str(text_box.get("shapeId")))
            if key not in update_lookup:
                continue
            _replace_text_box_text(text_box, update_lookup[key])

        for shape in slide.get("shapes", []):
            key = (slide_index, str(shape.get("shapeId")))
            if key in update_lookup and shape.get("hasText"):
                shape["text"] = update_lookup[key]

    if "generation" in filled_template:
        filled_template["generation"]["updates"] = updates
    return filled_template


def _replace_text_box_text(text_box: dict, new_text: str) -> None:
    text_box["text"] = new_text
    paragraphs = text_box.get("paragraphs") or []
    if not paragraphs:
        return

    paragraphs[0]["text"] = new_text
    runs = paragraphs[0].get("runs") or []
    if runs:
        runs[0]["text"] = new_text
        for run in runs[1:]:
            run["text"] = ""


def _template_config(template_id: str) -> dict:
    templates = _visible_templates()
    if template_id not in templates:
        raise ValueError(f"Unknown template: {template_id}")
    return templates[template_id]


def _all_templates() -> dict:
    return {**BUILTIN_TEMPLATES, **_uploaded_templates()}


def _visible_templates() -> dict:
    return _all_templates()


def _uploaded_templates() -> dict:
    if not TEMPLATE_REGISTRY_PATH.exists():
        return {}
    raw_templates = json.loads(TEMPLATE_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {
        template_id: {
            "name": config["name"],
            "jsonPath": Path(config["jsonPath"]),
            "pptxPath": Path(config["pptxPath"]),
            "previewPath": config.get("previewPath"),
        }
        for template_id, config in raw_templates.items()
    }


def _save_uploaded_templates(registry: dict) -> None:
    TEMPLATE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        template_id: {
            "name": config["name"],
            "jsonPath": str(config["jsonPath"]),
            "pptxPath": str(config["pptxPath"]),
            "previewPath": config.get("previewPath"),
        }
        for template_id, config in registry.items()
    }
    TEMPLATE_REGISTRY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _template_payload(template_id: str, config: dict) -> dict:
    return {
        "id": template_id,
        "name": config["name"],
        "jsonPath": str(config["jsonPath"]),
        "pptxPath": str(config["pptxPath"]),
        "previewPath": config.get("previewPath"),
    }


def _template_id_from_query(query: str) -> str:
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        if key == "templateId" and value:
            return value
    return DEFAULT_TEMPLATE_ID


def _query_value(query: str, key: str, default: str = "") -> str:
    values = parse_qs(query).get(key)
    if not values:
        return default
    return values[0]


def _resolve_generated_deck_path(value: str) -> Path:
    if not value:
        raise ValueError("generatedDeck is required.")

    filename = Path(value).name
    if not filename.endswith(".json"):
        raise ValueError("generatedDeck must point to a generated JSON deck.")

    path = GENERATED_DIR / filename
    if not path.exists() or not path.is_file():
        raise ValueError(f"Generated deck not found: {filename}")
    return path


def _validate_editor_operations(operations: list[dict]) -> list[dict]:
    if not isinstance(operations, list):
        raise ValueError("operations must be an array.")

    return [_validate_editor_operation(operation, index) for index, operation in enumerate(operations)]


def _validate_editor_operation(operation: dict, index: int) -> dict:
    if not isinstance(operation, dict):
        raise ValueError(f"Operation {index + 1} must be an object.")

    operation_type = operation.get("type")
    if operation_type not in EDITOR_OPERATION_TYPES:
        raise ValueError(f"Unsupported editor operation: {operation_type}")

    slide_id = operation.get("slideId")
    if not isinstance(slide_id, str) or not slide_id.startswith("slide_"):
        raise ValueError(f"{operation_type} requires a slideId like slide_1.")

    if operation_type == "changeBackgroundColor":
        _require_hex_color(operation, "color", operation_type)
        return operation

    object_id = operation.get("objectId")
    if not isinstance(object_id, str) or "_" not in object_id:
        raise ValueError(f"{operation_type} requires an objectId like text_3.")

    if operation_type == "updateText":
        if not isinstance(operation.get("text"), str):
            raise ValueError("updateText requires text.")
    elif operation_type == "moveObject":
        _require_number(operation, "x", operation_type)
        _require_number(operation, "y", operation_type)
    elif operation_type == "resizeObject":
        _require_number(operation, "width", operation_type)
        _require_number(operation, "height", operation_type)
    elif operation_type == "changeFont":
        if operation.get("font") not in EDITOR_FONTS:
            raise ValueError("changeFont font is not allowed.")
    elif operation_type == "changeTextColor":
        _require_hex_color(operation, "color", operation_type)
    elif operation_type == "replaceImage":
        if not isinstance(operation.get("assetPath"), str):
            raise ValueError("replaceImage requires assetPath.")
    elif operation_type in {"setEnterAnimation", "setExitAnimation"}:
        if operation.get("animation") not in EDITOR_ANIMATIONS:
            raise ValueError(f"{operation_type} animation is not allowed.")

    return operation


def _require_number(operation: dict, key: str, operation_type: str) -> None:
    value = operation.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{operation_type} requires numeric {key}.")


def _require_hex_color(operation: dict, key: str, operation_type: str) -> None:
    value = operation.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{operation_type} requires {key}.")
    raw = value.lstrip("#")
    if len(raw) != 6 or any(char not in "0123456789abcdefABCDEF" for char in raw):
        raise ValueError(f"{operation_type} requires a 6-digit hex {key}.")


def _editor_operation_warnings(operations: list[dict]) -> list[str]:
    warnings = []
    if any(operation.get("type") in {"setEnterAnimation", "setExitAnimation"} for operation in operations):
        warnings.append("Animation settings were saved in JSON for preview; PPT animation export is not enabled yet.")
    if any(operation.get("type") == "replaceImage" for operation in operations):
        warnings.append("Image replacement operations were saved; binary image replacement is not enabled yet.")
    return warnings


def _editor_animation_metadata(operations: list[dict]) -> dict:
    objects = {}
    for operation in operations:
        operation_type = operation.get("type")
        if operation_type not in {"setEnterAnimation", "setExitAnimation"}:
            continue

        key = (str(operation.get("slideId")), str(operation.get("objectId")))
        objects.setdefault(
            key,
            {
                "slideId": key[0],
                "objectId": key[1],
                "enterAnimation": "none",
                "exitAnimation": "none",
            },
        )
        if operation_type == "setEnterAnimation":
            objects[key]["enterAnimation"] = operation.get("animation") or "none"
        else:
            objects[key]["exitAnimation"] = operation.get("animation") or "none"

    return {
        "schemaVersion": 1,
        "pptAnimationExport": False,
        "objects": list(objects.values()),
    }


def _attach_editor_metadata(filled_template: dict, operations: list[dict], animation_metadata: dict) -> dict:
    filled_template["editor"] = {
        "operationSchemaVersion": 1,
        "operations": operations,
        "animationMetadata": animation_metadata,
        "capabilities": {
            "pptAnimationExport": False,
        },
    }
    return filled_template


def _slide_preview(filled_template: dict) -> list[dict]:
    size = filled_template.get("presentation", {}).get("size", {})
    width = size.get("widthInches") or 20
    height = size.get("heightInches") or 11.25
    field_lookup = _field_lookup(filled_template.get("generation", {}).get("templateMap", {}))

    previews = []
    for slide in filled_template.get("slides", []):
        slide_index = slide.get("index")
        elements = []
        for shape in slide.get("shapes", []):
            text = shape.get("text")
            geometry = shape.get("geometry") or {}
            if not text or not geometry:
                continue

            elements.append(
                {
                    "shapeId": shape.get("shapeId"),
                    "field": field_lookup.get((str(slide_index), str(shape.get("shapeId")))),
                    "text": text,
                    "x": _percent(geometry.get("xInches"), width),
                    "y": _percent(geometry.get("yInches"), height),
                    "w": _percent(geometry.get("widthInches"), width),
                    "h": _percent(geometry.get("heightInches"), height),
                    "rotation": geometry.get("rotationDegrees") or 0,
                }
            )

        previews.append(
            {
                "index": slide_index,
                "purpose": filled_template.get("generation", {}).get("templateMap", {}).get(str(slide_index), {}).get("purpose"),
                "elements": elements,
            }
        )

    return previews


def _field_lookup(template_map: dict) -> dict[tuple[str, str], str]:
    lookup = {}
    for slide_index, slide_map in template_map.items():
        for field, shape_id in slide_map.get("fields", {}).items():
            lookup[(str(slide_index), str(shape_id))] = field
    return lookup


def _percent(value: float | None, total: float) -> float:
    if value is None:
        return 0
    return round((value / total) * 100, 4)


def _render_pptx_preview(pptx_path: Path) -> str | None:
    GENERATED_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    expected_name = f"{pptx_path.name}.png"
    expected_path = GENERATED_PREVIEW_DIR / expected_name

    try:
        subprocess.run(
            ["qlmanage", "-t", "-s", "900", "-o", str(GENERATED_PREVIEW_DIR), str(pptx_path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
        )
    except Exception:
        return None

    if expected_path.exists():
        return f"generated-previews/{expected_name}"
    return None


def _render_template_preview(pptx_path: Path) -> str | None:
    TEMPLATE_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    expected_name = f"{pptx_path.name}.png"
    expected_path = TEMPLATE_PREVIEW_DIR / expected_name

    try:
        subprocess.run(
            ["qlmanage", "-t", "-s", "900", "-o", str(TEMPLATE_PREVIEW_DIR), str(pptx_path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
        )
    except Exception:
        return None

    if expected_path.exists():
        return f"template-previews/{expected_name}"
    return None


def _content_type(path: Path) -> str:
    if path.suffix == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if path.suffix == ".json":
        return "application/json"
    return "application/octet-stream"


def _safe_output_stem(topic: str) -> str:
    stem = topic.strip().lower()
    stem = "".join(char if char.isalnum() else "-" for char in stem)
    stem = "-".join(part for part in stem.split("-") if part)
    return stem or "generated"


def _unique_template_id(stem: str) -> str:
    base = stem or "uploaded-template"
    existing = _all_templates()
    if base not in existing:
        return base

    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


def _display_name(value: str) -> str:
    words = [word for word in re_split_slug(value) if word]
    return " ".join(word.capitalize() for word in words) or "Uploaded Template"


def re_split_slug(value: str) -> list[str]:
    normalized = "".join(char if char.isalnum() else " " for char in value)
    return normalized.split()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Open http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
