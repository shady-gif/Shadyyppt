from __future__ import annotations

from collections import Counter
import re


NAVIGATION_PATTERNS = [
    "back to agenda",
    "back to",
    "page",
    "click to",
]

PLACEHOLDER_PATTERNS = [
    "lorem ipsum",
    "add ",
    "briefly elaborate",
    "provide data",
]


def build_template_map(template: dict) -> dict:
    slides = template.get("slides", [])
    repeated_text = _repeated_text(slides)
    template_map = {}

    for slide in slides:
        slide_index = str(slide.get("index"))
        candidates = _text_candidates(slide, repeated_text)
        if not candidates:
            continue

        if slide.get("index") == 1:
            template_map[slide_index] = _cover_map(candidates)
            continue

        if _is_infographic_slide(candidates):
            template_map[slide_index] = _infographic_map(candidates)
        else:
            template_map[slide_index] = _standard_slide_map(candidates)

    return template_map


def _cover_map(candidates: list[dict]) -> dict:
    ranked = sorted(candidates, key=lambda item: (item["fontSize"], -item["y"], item["area"]), reverse=True)
    fields = {}

    if ranked:
        fields["title"] = ranked[0]["shapeId"]
    if len(ranked) > 1:
        fields["subtitle"] = ranked[1]["shapeId"]
    if len(ranked) > 2:
        fields["byline"] = ranked[-1]["shapeId"]

    year = _find_year_candidate(candidates)
    if year:
        fields["year"] = year["shapeId"]

    return {"purpose": "cover", "fields": fields}


def _standard_slide_map(candidates: list[dict]) -> dict:
    fields = {}
    title = _title_candidate(candidates)
    if title:
        fields["section"] = title["shapeId"]

    remaining = [item for item in candidates if item is not title]
    bodies = sorted(
        [item for item in remaining if _is_body_candidate(item)],
        key=lambda item: (item["length"], item["area"]),
        reverse=True,
    )
    headings = sorted(
        [item for item in remaining if not _is_body_candidate(item)],
        key=lambda item: (item["fontSize"], -item["y"], item["area"]),
        reverse=True,
    )

    if headings:
        fields["headline"] = headings[0]["shapeId"]
    if bodies:
        fields["body"] = bodies[0]["shapeId"]

    for index, heading in enumerate(headings[1:3], start=1):
        fields[f"heading{index}"] = heading["shapeId"]
    for index, body in enumerate(bodies[1:3], start=1):
        fields[f"body{index}"] = body["shapeId"]

    return {"purpose": "content", "fields": fields}


def _infographic_map(candidates: list[dict]) -> dict:
    fields = {}
    title = _title_candidate(candidates)
    if title:
        fields["section"] = title["shapeId"]

    remaining = [item for item in candidates if item is not title]
    subtitle = _subtitle_candidate(remaining)
    if subtitle:
        fields["headline"] = subtitle["shapeId"]
        remaining = [item for item in remaining if item is not subtitle]

    labels = sorted(
        [item for item in remaining if item["length"] <= 48],
        key=lambda item: (item["y"], item["x"]),
    )
    bodies = sorted(
        [item for item in remaining if item["length"] > 48],
        key=lambda item: (item["y"], item["x"]),
    )

    for index, label in enumerate(labels[:8], start=1):
        fields[f"heading{index}"] = label["shapeId"]
    for index, body in enumerate(bodies[:8], start=1):
        fields[f"body{index}"] = body["shapeId"]

    return {"purpose": "infographic", "fields": fields}


def _text_candidates(slide: dict, repeated_text: set[str]) -> list[dict]:
    shapes = {
        str(shape.get("shapeId")): shape
        for shape in slide.get("shapes", [])
        if shape.get("shapeId")
    }
    candidates = []

    for text_box in slide.get("texts", []):
        text = _normalize_text(text_box.get("text", ""))
        if not text:
            continue

        shape_id = str(text_box.get("shapeId"))
        shape = shapes.get(shape_id, {})
        geometry = shape.get("geometry") or {}
        font_size = _font_size(text_box)
        lowered = text.lower()

        if lowered in repeated_text and len(text) < 40:
            continue
        if any(pattern in lowered for pattern in NAVIGATION_PATTERNS):
            continue
        if font_size <= 8:
            continue

        width = geometry.get("widthInches") or 0
        height = geometry.get("heightInches") or 0
        candidates.append(
            {
                "shapeId": shape_id,
                "text": text,
                "fontSize": font_size,
                "x": geometry.get("xInches") or 0,
                "y": geometry.get("yInches") or 0,
                "width": width,
                "height": height,
                "area": width * height,
                "length": len(text),
                "placeholder": any(pattern in lowered for pattern in PLACEHOLDER_PATTERNS),
            }
        )

    return candidates


def _title_candidate(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    top_half = [item for item in candidates if item["y"] <= 4.5]
    pool = top_half or candidates
    return max(pool, key=lambda item: (item["fontSize"], item["area"], -item["length"]))


def _subtitle_candidate(candidates: list[dict]) -> dict | None:
    short_items = [item for item in candidates if item["length"] <= 90]
    if not short_items:
        return None
    return max(short_items, key=lambda item: (item["fontSize"], item["area"]))


def _find_year_candidate(candidates: list[dict]) -> dict | None:
    for item in candidates:
        if re.fullmatch(r"(19|20)\d{2}", item["text"]):
            return item
    return None


def _is_body_candidate(item: dict) -> bool:
    return item["length"] > 70 or "\n" in item["text"] or item["placeholder"]


def _is_infographic_slide(candidates: list[dict]) -> bool:
    if len(candidates) < 6:
        return False

    rounded_sizes = Counter(round(item["fontSize"] / 5) * 5 for item in candidates)
    repeated_size_count = max(rounded_sizes.values(), default=0)
    short_label_count = len([item for item in candidates if item["length"] <= 48])
    return repeated_size_count >= 4 and short_label_count >= 4


def _repeated_text(slides: list[dict]) -> set[str]:
    counts = Counter()
    for slide in slides:
        for text_box in slide.get("texts", []):
            text = _normalize_text(text_box.get("text", "")).lower()
            if text:
                counts[text] += 1
    return {text for text, count in counts.items() if count >= 3}


def _font_size(text_box: dict) -> float:
    sizes = []
    for paragraph in text_box.get("paragraphs", []):
        for run in paragraph.get("runs", []):
            size = run.get("fontSize")
            if size:
                sizes.append(float(size))
    return max(sizes) if sizes else 0


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
