from __future__ import annotations

import json
import os
from urllib import request, error


ALLOWED_FIELDS = {
    "title",
    "subtitle",
    "byline",
    "year",
    "section",
    "headline",
    "body",
    "caption",
    "line1",
    "line2",
    "line3",
    "line4",
}


def improve_template_map_with_ai(template: dict, rule_map: dict) -> tuple[dict, str]:
    if not _ollama_enabled():
        return rule_map, "rule"

    slide_payload = _compact_slide_payload(template)
    if not slide_payload:
        return rule_map, "rule"

    prompt = _build_prompt(slide_payload, rule_map)
    response = _ollama_chat(prompt)
    if not response:
        return rule_map, "rule"

    ai_map = _parse_ai_map(response)
    if not ai_map:
        return rule_map, "rule"

    validated = _validate_ai_map(ai_map, template)
    if not validated:
        return rule_map, "rule"

    return validated, "ollama"


def _ollama_enabled() -> bool:
    return os.environ.get("DISABLE_OLLAMA_MAPPER", "").lower() not in {"1", "true", "yes"}


def _ollama_chat(prompt: str) -> str | None:
    endpoint = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "You map PowerPoint text boxes to semantic content fields. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, error.URLError, json.JSONDecodeError):
        return None

    message = body.get("message", {})
    return message.get("content")


def _build_prompt(slides: list[dict], rule_map: dict) -> str:
    return json.dumps(
        {
            "task": "Improve the semantic map for a PowerPoint template. Use the ruleMap as a starting point, but correct wrong placements. Prefer high-confidence mappings only.",
            "instructions": [
                "Map text boxes to fields that generated deck content can fill.",
                "Use shapeId values exactly as provided.",
                "Do not map decorative, footer, navigation, page number, or repeated instruction text.",
                "For cover slides, prefer title, subtitle, byline, and year when obvious.",
                "For content slides, prefer section, headline, body, heading1..heading8, body1..body8, caption, line1..line4.",
                "For infographic slides, map multiple labels as heading1..heading8 and longer explanatory boxes as body1..body8.",
                "If uncertain, leave the box unmapped.",
                "Return JSON with this shape: {\"slides\":{\"1\":{\"purpose\":\"cover\",\"fields\":{\"title\":\"10\"}}}}.",
            ],
            "allowedFields": sorted(ALLOWED_FIELDS)
            + [f"heading{i}" for i in range(1, 9)]
            + [f"body{i}" for i in range(1, 9)],
            "ruleMap": rule_map,
            "slides": slides,
        },
        indent=2,
    )


def _compact_slide_payload(template: dict) -> list[dict]:
    payload = []
    for slide in template.get("slides", [])[:12]:
        shapes = {
            str(shape.get("shapeId")): shape
            for shape in slide.get("shapes", [])
            if shape.get("shapeId")
        }
        texts = []
        for text_box in slide.get("texts", [])[:30]:
            shape_id = str(text_box.get("shapeId"))
            shape = shapes.get(shape_id, {})
            geometry = shape.get("geometry") or {}
            texts.append(
                {
                    "shapeId": shape_id,
                    "text": _truncate(text_box.get("text", ""), 180),
                    "fontSize": _font_size(text_box),
                    "x": geometry.get("xInches"),
                    "y": geometry.get("yInches"),
                    "width": geometry.get("widthInches"),
                    "height": geometry.get("heightInches"),
                }
            )
        payload.append({"index": slide.get("index"), "texts": texts})
    return payload


def _parse_ai_map(response: str) -> dict | None:
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return None

    slides = payload.get("slides")
    return slides if isinstance(slides, dict) else None


def _validate_ai_map(ai_map: dict, template: dict) -> dict:
    valid_shape_ids = {
        str(slide.get("index")): {
            str(text_box.get("shapeId"))
            for text_box in slide.get("texts", [])
            if text_box.get("shapeId")
        }
        for slide in template.get("slides", [])
    }
    allowed_fields = ALLOWED_FIELDS | {f"heading{i}" for i in range(1, 9)} | {f"body{i}" for i in range(1, 9)}
    validated = {}

    for slide_index, slide_map in ai_map.items():
        slide_index = str(slide_index)
        if slide_index not in valid_shape_ids or not isinstance(slide_map, dict):
            continue

        fields = slide_map.get("fields", {})
        if not isinstance(fields, dict):
            continue

        valid_fields = {}
        for field, shape_id in fields.items():
            shape_id = str(shape_id)
            if field not in allowed_fields:
                continue
            if shape_id not in valid_shape_ids[slide_index]:
                continue
            valid_fields[field] = shape_id

        if valid_fields:
            validated[slide_index] = {
                "purpose": str(slide_map.get("purpose") or "content"),
                "fields": valid_fields,
            }

    return validated


def _font_size(text_box: dict) -> float:
    sizes = []
    for paragraph in text_box.get("paragraphs", []):
        for run in paragraph.get("runs", []):
            size = run.get("fontSize")
            if size:
                sizes.append(float(size))
    return max(sizes) if sizes else 0


def _truncate(value: str, max_chars: int) -> str:
    value = " ".join(str(value).split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rsplit(" ", 1)[0]
