from __future__ import annotations

from datetime import date
import json
import os
from urllib import error, request


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_MAX_OUTPUT_TOKENS = 2600
DEFAULT_RETRIES = 2
DEFAULT_TIMEOUT = 60


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
        "You are the writing engine for ShadyPPT. Convert source material into concise, "
        "presentation-ready slide content. Return only valid JSON. Do not use Markdown. "
        "Do not invent facts beyond reasonable synthesis of the source."
    )


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
            "outputContract": {
                "deckTitle": "string",
                "subtitle": "string",
                "byline": "string",
                "year": "string",
                "unusedFacts": ["string"],
                "slides": {
                    "1": {"title": "string", "subtitle": "string", "byline": "string", "year": "string"},
                    "2": {"section": "string", "headline": "string", "body": "string"},
                    "3": {"section": "string", "heading1": "string", "body1": "string", "heading2": "string", "body2": "string"},
                    "4": {"section": "string", "heading1": "string", "body1": "string", "heading2": "string", "body2": "string"},
                    "5": {"section": "string", "heading1": "string", "body1": "string", "heading2": "string", "body2": "string"},
                    "6": {"section": "string", "body": "string"},
                    "7": {"section": "string", "body": "string", "caption": "string"},
                    "8": {"section": "string", "body": "string", "caption": "string"},
                    "9": {"section": "string"},
                    "10": {"section": "string", "line1": "string", "line2": "string", "line3": "string", "line4": "string"},
                },
            },
            "rules": [
                "Use the provided topic as the main title.",
                "Keep headings under 42 characters.",
                "Keep body fields under 180 characters unless the fallback example is longer.",
                "Keep closing lines under 90 characters.",
                "Make every slide specific to the source text.",
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
            "fallbackExample": fallback_curated,
            "sourceText": source_text,
        },
        ensure_ascii=True,
    )


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
