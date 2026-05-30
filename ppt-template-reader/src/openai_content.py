from __future__ import annotations

from datetime import date
import json
import os
from urllib import error, request


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_MAX_OUTPUT_TOKENS = 12000
DEFAULT_RETRIES = 2
DEFAULT_TIMEOUT = 60


def generate_text_box_updates_with_openai(
    *,
    topic: str,
    source_text: str,
    profile: dict,
    template_id: str | None,
    template_text_boxes: list[dict],
    fallback_curated: dict,
) -> tuple[list[dict] | None, dict]:
    if _disabled():
        return None, {
            "enabled": False,
            "source": "disabled",
            "model": _model(),
            "userMessage": "OpenAI generation is disabled, so this deck used local rules.",
        }

    api_key = _api_key()
    if not api_key:
        return None, {
            "enabled": False,
            "source": "missing_api_key",
            "model": _model(),
            "userMessage": "OpenAI API key is not configured, so this deck used local rules.",
        }

    if not template_text_boxes:
        return None, {
            "enabled": True,
            "source": "fallback",
            "model": _model(),
            "error": "Template did not include editable text boxes.",
            "userMessage": "AI content was unavailable, so this deck used local rules.",
        }

    model = _model()
    payload = {
        "model": model,
        "instructions": _text_box_instructions(),
        "input": _text_box_prompt(
            topic,
            source_text,
            profile,
            template_id,
            template_text_boxes,
            fallback_curated,
        ),
        "max_output_tokens": _env_int("OPENAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, min_value=256),
        "text": {"format": _text_box_response_format()},
    }

    attempts = _env_int("OPENAI_RETRIES", DEFAULT_RETRIES, min_value=1, max_value=5)
    last_error = None
    for _ in range(attempts):
        try:
            body = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
            output_text = _output_text(body)
            generated = _parse_json_output(output_text)
            updates = _validated_text_box_updates(generated, template_text_boxes)
            return updates, {
                "enabled": True,
                "source": "openai",
                "mode": "text_boxes",
                "model": model,
                "responseId": body.get("id"),
                "userMessage": f"Generated with {model}.",
            }
        except (OSError, RuntimeError, TimeoutError, error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    return None, {
        "enabled": True,
        "source": "fallback",
        "model": model,
        "error": _safe_error(last_error),
        "userMessage": "AI content was unavailable, so this deck used local rules.",
    }


def generate_curated_content_with_openai(
    *,
    topic: str,
    source_text: str,
    profile: dict,
    template_id: str | None,
    template_map: dict,
    fallback_curated: dict,
) -> tuple[dict | None, dict]:
    if _disabled():
        return None, {
            "enabled": False,
            "source": "disabled",
            "model": _model(),
            "userMessage": "OpenAI generation is disabled, so this deck used local rules.",
        }

    api_key = _api_key()
    if not api_key:
        return None, {
            "enabled": False,
            "source": "missing_api_key",
            "model": _model(),
            "userMessage": "OpenAI API key is not configured, so this deck used local rules.",
        }

    model = _model()
    payload = {
        "model": model,
        "instructions": _instructions(),
        "input": _prompt(topic, source_text, profile, template_id, template_map, fallback_curated),
        "max_output_tokens": _env_int("OPENAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, min_value=256),
        "text": {"format": _response_format(fallback_curated)},
    }

    attempts = _env_int("OPENAI_RETRIES", DEFAULT_RETRIES, min_value=1, max_value=5)
    last_error = None
    for _ in range(attempts):
        try:
            body = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
            output_text = _output_text(body)
            generated = _parse_json_output(output_text)
            curated = _validated_curated(generated, fallback_curated, profile)
            return curated, {
                "enabled": True,
                "source": "openai",
                "model": model,
                "responseId": body.get("id"),
                "userMessage": f"Generated with {model}.",
            }
        except (OSError, RuntimeError, TimeoutError, error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    return None, {
        "enabled": True,
        "source": "fallback",
        "model": model,
        "error": _safe_error(last_error),
        "userMessage": "AI content was unavailable, so this deck used local rules.",
    }


def openai_runtime_status() -> dict:
    return {
        "enabled": not _disabled(),
        "configured": bool(_api_key()),
        "model": _model(),
    }


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _disabled() -> bool:
    return os.environ.get("DISABLE_OPENAI_GENERATOR", "").lower() in {"1", "true", "yes"}


def _api_key() -> str:
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    placeholders = {
        "sk-your-key-here",
        "sk-proj-your-key-here",
        "your-openai-api-key",
        "replace-me",
    }
    if not value or value.lower() in placeholders:
        return ""
    return value


def _post_json(url: str, payload: dict, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = _env_int("OPENAI_TIMEOUT", DEFAULT_TIMEOUT, min_value=1, max_value=180)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}: {_openai_error_detail(detail)}") from exc


def _output_text(response: dict) -> str:
    value = response.get("output_text")
    if isinstance(value, str) and value.strip():
        return value

    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])

    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("OpenAI response did not include output text.")
    return text


def _parse_json_output(value: str) -> dict:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    return json.loads(cleaned)


def _instructions() -> str:
    return (
        "You are the senior presentation editor for ShadyPPT. Convert source material "
        "into concise, template-aware slide writing. Return only valid JSON. Do not use "
        "Markdown. Do not invent facts beyond careful synthesis of the source."
    )


def _text_box_instructions() -> str:
    return (
        "You are the strict PowerPoint text-box writer for ShadyPPT. You receive the "
        "actual editable text boxes from a PPT template. Decide what each text box is "
        "for, then return concise replacement text for those exact slideIndex and "
        "shapeId pairs. Return only valid JSON. Do not use Markdown. Do not invent "
        "facts beyond careful synthesis of the source."
    )


def _text_box_prompt(
    topic: str,
    source_text: str,
    profile: dict,
    template_id: str | None,
    template_text_boxes: list[dict],
    fallback_curated: dict,
) -> str:
    return json.dumps(
        {
            "task": "Fill the exact PowerPoint text boxes with summarized presentation text.",
            "hardRules": [
                "Return one update for every text box in templateTextBoxes.",
                "Use slideIndex and shapeId exactly as provided.",
                "Do not create new shape IDs or slide numbers.",
                "Use fontSize, x, y, width, height, and maxChars to infer hierarchy.",
                "Very large text is usually a title, section, or short label.",
                "Long lorem ipsum or paragraph text is usually body copy.",
                "Small repeated brand text should usually become the topic or a short subject label.",
                "Page markers like 01, 02, 03 should usually be preserved exactly with role page_number.",
                "Contact details, fake names, team labels, lorem ipsum, and template instructions must be replaced or cleared.",
                "Every non-page-marker text box should be specific to the source.",
                "Keep newText within maxChars for that box.",
                "Use short, punchy headings and compact body sentences.",
                "Avoid repeating the same fact across boxes unless the repeated box is a brand/topic label.",
                "Remove citation markers, pronunciation guides, wiki markup, and bracket notes.",
                "For sensitive or controversial claims, use neutral editorial wording.",
                "If a box should intentionally be blank, return newText as an empty string and role clear.",
            ],
            "roleOptions": [
                "topic",
                "title",
                "subtitle",
                "section",
                "heading",
                "body",
                "label",
                "takeaway",
                "page_number",
                "clear",
            ],
            "topic": topic,
            "templateId": template_id,
            "profile": {
                "name": profile.get("name"),
                "subtitle": profile.get("subtitle"),
                "sections": profile.get("sections"),
                "closing": profile.get("closing"),
            },
            "localFallbackDraft": fallback_curated,
            "templateTextBoxes": template_text_boxes,
            "sourceText": source_text,
        },
        ensure_ascii=True,
    )


def _text_box_response_format() -> dict:
    return {
        "type": "json_schema",
        "name": "shadyppt_text_box_updates",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["updates"],
            "properties": {
                "updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["slideIndex", "shapeId", "role", "newText"],
                        "properties": {
                            "slideIndex": {"type": "integer"},
                            "shapeId": {"type": "string"},
                            "role": {
                                "type": "string",
                                "enum": [
                                    "topic",
                                    "title",
                                    "subtitle",
                                    "section",
                                    "heading",
                                    "body",
                                    "label",
                                    "takeaway",
                                    "page_number",
                                    "clear",
                                ],
                            },
                            "newText": {"type": "string"},
                        },
                    },
                }
            },
        },
    }


def _validated_text_box_updates(generated: dict, template_text_boxes: list[dict]) -> list[dict]:
    if not isinstance(generated, dict):
        raise ValueError("OpenAI text-box output must be a JSON object.")

    raw_updates = generated.get("updates")
    if not isinstance(raw_updates, list):
        raise ValueError("OpenAI text-box output missing updates array.")

    box_lookup = _text_box_lookup(template_text_boxes)
    required_keys = set(box_lookup.keys())
    seen = set()
    updates = []

    for item in raw_updates:
        if not isinstance(item, dict):
            continue
        try:
            slide_index = int(item.get("slideIndex"))
        except (TypeError, ValueError):
            continue
        shape_id = str(item.get("shapeId") or "")
        key = (slide_index, shape_id)
        if key not in box_lookup or key in seen:
            continue

        box = box_lookup[key]
        role = str(item.get("role") or "body")
        new_text = str(item.get("newText") or "")
        if role == "page_number" and not new_text:
            new_text = str(box.get("originalText") or "")
        new_text = _clip(new_text, _text_box_limit(box))

        updates.append(
            {
                "slideIndex": slide_index,
                "shapeId": shape_id,
                "field": role,
                "role": role,
                "newText": new_text,
            }
        )
        seen.add(key)

    missing = required_keys - seen
    if missing:
        raise ValueError(f"OpenAI text-box output missed {len(missing)} template text boxes.")
    if not updates:
        raise ValueError("OpenAI text-box output did not include valid updates.")
    return updates


def _text_box_lookup(template_text_boxes: list[dict]) -> dict[tuple[int, str], dict]:
    lookup = {}
    for slide in template_text_boxes:
        try:
            slide_index = int(slide.get("index"))
        except (TypeError, ValueError):
            continue
        for text_box in slide.get("textBoxes") or []:
            shape_id = str(text_box.get("shapeId") or "")
            if shape_id:
                lookup[(slide_index, shape_id)] = text_box
    return lookup


def _text_box_limit(text_box: dict) -> int:
    try:
        limit = int(text_box.get("maxChars") or 0)
    except (TypeError, ValueError):
        limit = 0
    return max(1, min(limit or 190, 420))


def _prompt(
    topic: str,
    source_text: str,
    profile: dict,
    template_id: str | None,
    template_map: dict,
    fallback_curated: dict,
) -> str:
    required_fields = {
        str(slide_index): sorted((slide_map.get("fields") or {}).keys())
        for slide_index, slide_map in template_map.items()
    }
    return json.dumps(
        {
            "task": "Generate concise slide content for a PowerPoint deck.",
            "outputContract": _output_contract(fallback_curated),
            "rules": [
                "Use the provided topic as the main title, preserving the person's or subject's name.",
                "Write a claim spine: origin, major moves, evidence, impact, risks or controversy, takeaway.",
                "Give each slide one distinct job; do not repeat the same fact in different wording.",
                "Use exact named entities, dates, companies, and numbers from the source when available.",
                "Keep a neutral editorial tone for controversial or political claims.",
                "Remove citation markers, pronunciation guides, bracket notes, and wiki artifacts.",
                "Keep headings under 42 characters and make them specific, not generic.",
                "Keep body fields under 180 characters unless the field clearly supports longer copy.",
                "Keep closing and line fields under 90 characters.",
                "For fields named headline, heading, or section, write a short label or claim.",
                "For fields named body, write one compact evidence sentence.",
                "For fields that look like template people, team, phone, email, or contact placeholders, replace them with source-based labels or concise takeaways.",
                "Never output fake names, phone numbers, emails, lorem ipsum, template filler, or instructions to the user.",
                "Avoid repeated wording across slides.",
                "Use a tone that matches the template profile.",
                "Return every key shown in outputContract.",
            ],
            "topic": topic,
            "templateId": template_id,
            "profile": {
                "name": profile.get("name"),
                "subtitle": profile.get("subtitle"),
                "sections": profile.get("sections"),
                "closing": profile.get("closing"),
            },
            "requiredFieldsBySlide": required_fields,
            "fieldGuidance": _field_guidance(fallback_curated),
            "fallbackExample": fallback_curated,
            "sourceText": source_text,
        },
        ensure_ascii=True,
    )


def _output_contract(fallback_curated: dict) -> dict:
    return {
        "deckTitle": "string",
        "subtitle": "string",
        "byline": "string",
        "year": "string",
        "unusedFacts": ["string"],
        "slides": {
            str(slide_index): {
                str(field_name): "string"
                for field_name in slide.keys()
            }
            for slide_index, slide in (fallback_curated.get("slides") or {}).items()
            if isinstance(slide, dict)
        },
    }


def _field_guidance(fallback_curated: dict) -> dict:
    guidance = {}
    for slide_index, slide in (fallback_curated.get("slides") or {}).items():
        if not isinstance(slide, dict):
            continue
        guidance[str(slide_index)] = {
            str(field): _field_role(str(field))
            for field in slide.keys()
        }
    return guidance


def _field_role(field: str) -> str:
    if field in {"title", "deckTitle"}:
        return "main subject title"
    if field in {"subtitle", "byline", "year", "caption"}:
        return "short supporting label"
    if field in {"section", "headline"} or field.startswith("heading"):
        return "short source-specific claim or label"
    if field.startswith("line"):
        return "short takeaway line"
    if field.startswith("body"):
        return "compact evidence sentence"
    return "source-based template text"


def _response_format(fallback_curated: dict) -> dict:
    return {
        "type": "json_schema",
        "name": "shadyppt_slide_content",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["deckTitle", "subtitle", "byline", "year", "unusedFacts", "slides"],
            "properties": {
                "deckTitle": {"type": "string"},
                "subtitle": {"type": "string"},
                "byline": {"type": "string"},
                "year": {"type": "string"},
                "unusedFacts": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "slides": _slides_schema(fallback_curated),
            },
        },
    }


def _slides_schema(fallback_curated: dict) -> dict:
    slides = fallback_curated.get("slides") or {}
    slide_properties = {
        str(index): _slide_schema(slide)
        for index, slide in slides.items()
        if isinstance(slide, dict)
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(slide_properties.keys(), key=_slide_sort_key),
        "properties": slide_properties,
    }


def _slide_sort_key(value: str) -> tuple[int, int | str]:
    if value.isdigit():
        return (0, int(value))
    return (1, value)


def _slide_schema(slide: dict) -> dict:
    field_names = sorted(str(field) for field in slide.keys())
    return {
        "type": "object",
        "additionalProperties": False,
        "required": field_names,
        "properties": {
            field: {"type": "string"}
            for field in field_names
        },
    }


def _validated_curated(generated: dict, fallback: dict, profile: dict) -> dict:
    if not isinstance(generated, dict):
        raise ValueError("OpenAI output must be a JSON object.")

    slides = generated.get("slides")
    if not isinstance(slides, dict):
        raise ValueError("OpenAI output missing slides object.")

    curated = {
        "deckTitle": _string(generated.get("deckTitle"), fallback.get("deckTitle")),
        "subtitle": _string(generated.get("subtitle"), fallback.get("subtitle")),
        "byline": _string(generated.get("byline"), fallback.get("byline", "")),
        "year": _string(generated.get("year"), fallback.get("year", str(date.today().year))),
        "unusedFacts": _string_list(generated.get("unusedFacts"), fallback.get("unusedFacts", [])),
        "slides": {},
    }

    for index, fallback_slide in fallback.get("slides", {}).items():
        generated_slide = slides.get(index) if isinstance(slides.get(index), dict) else {}
        merged = {}
        for key, fallback_value in fallback_slide.items():
            limit = _limit_for_field(key)
            merged[key] = _clip(_string(generated_slide.get(key), fallback_value), limit)
        curated["slides"][index] = merged

    if not curated["slides"].get("10", {}).get("section"):
        curated["slides"].setdefault("10", {})["section"] = profile.get("closing", "Takeaways")

    return curated


def _string(value: object, fallback: object = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return str(fallback or "").strip()


def _string_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [_string(item) for item in value]
        items = [item for item in items if item]
        if items:
            return items[:40]
    return fallback[:40]


def _limit_for_field(field: str) -> int:
    if field.startswith("heading") or field in {"section", "caption"}:
        return 48
    if field.startswith("line"):
        return 90
    if field in {"title", "subtitle", "headline"}:
        return 90
    return 190


def _clip(value: str, max_chars: int) -> str:
    value = " ".join(str(value).split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "."


def _env_int(name: str, default: int, *, min_value: int = 0, max_value: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default

    value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _openai_error_detail(detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        payload = {}

    message = ""
    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            message = str(error_payload.get("message") or "")
        elif isinstance(error_payload, str):
            message = error_payload

    return _safe_error(message or detail)


def _safe_error(exc: object) -> str:
    value = " ".join(str(exc or "unknown error").split())
    return value[:300]
