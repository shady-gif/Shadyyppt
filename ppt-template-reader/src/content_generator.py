from __future__ import annotations

from copy import deepcopy
from datetime import date
import re

from template_map import TEMPLATE_MAP
from semantic_mapper import build_template_map
from ai_semantic_mapper import improve_template_map_with_ai
from openai_content import generate_curated_content_with_openai
from template_profiles import get_template_profile


class ContentGenerator:
    def __init__(self, template: dict, template_id: str | None = None) -> None:
        self.template = template
        self.template_id = template_id
        self.profile = get_template_profile(template_id)
        rule_map = build_template_map(template) or TEMPLATE_MAP
        self.template_map, self.mapper_source = improve_template_map_with_ai(template, rule_map)

    def generate(self, raw_text: str, topic: str | None = None) -> dict:
        structured_slides = _parse_structured_slides(raw_text)
        cleaned = _clean_text(raw_text)
        if not cleaned:
            raise ValueError("Please paste some text before generating.")
        word_count = _word_count(cleaned)
        if word_count < 150 and not structured_slides:
            raise ValueError(f"Please paste at least 150 words. Current source text has {word_count} words.")
        if word_count > 3000:
            raise ValueError(f"Please keep source text under 3000 words. Current source text has {word_count} words.")

        paragraphs = _split_paragraphs(cleaned)
        sentences = _split_sentences(cleaned)
        topic = _format_topic((topic or _topic_from_structured_slides(structured_slides) or _guess_topic(cleaned) or "Generated Profile").strip())

        if structured_slides:
            curated = _curated_from_structured_slides(
                topic,
                structured_slides,
                self.template,
                self.template_map,
                self.profile,
            )
            curated = _expand_curated_for_template(curated, self.template_map, self.profile)
            updates = self._build_updates(curated)
            filled = self._apply_updates(updates)

            return {
                "topic": topic,
                "curatedContent": curated,
                "updates": updates,
                "mapperSource": self.mapper_source,
                "contentSource": {
                    "source": "structured_input",
                    "enabled": True,
                    "mode": "slide_outline",
                    "slides": len(structured_slides),
                },
                "filledTemplateJson": filled,
            }

        fallback_curated = self._curate_content(topic, paragraphs, sentences)
        fallback_curated = _expand_curated_for_template(
            fallback_curated,
            self.template_map,
            self.profile,
        )
        curated, openai_metadata = generate_curated_content_with_openai(
            topic=topic,
            source_text=cleaned,
            profile=self.profile,
            template_id=self.template_id,
            template_map=self.template_map,
            fallback_curated=fallback_curated,
        )
        curated = curated or fallback_curated
        updates = self._build_updates(curated)
        filled = self._apply_updates(updates)

        return {
            "topic": topic,
            "curatedContent": curated,
            "updates": updates,
            "mapperSource": self.mapper_source,
            "contentSource": openai_metadata,
            "filledTemplateJson": filled,
        }

    def _curate_content(self, topic: str, paragraphs: list[str], sentences: list[str]) -> dict:
        facts = _build_fact_pool(topic, paragraphs, sentences)
        outline = _build_outline(topic, facts)
        subtitle = _make_subtitle(topic, facts, self.profile)
        byline = _make_byline(self.profile)
        sections = self.profile["sections"]

        return {
            "deckTitle": topic,
            "subtitle": subtitle,
            "byline": byline,
            "year": str(date.today().year),
            "unusedFacts": outline["unusedFacts"],
            "slides": {
                "1": {
                    "title": topic,
                    "subtitle": subtitle,
                    "byline": byline,
                    "year": str(date.today().year),
                },
                "2": {
                    "section": _section(sections, 0),
                    "headline": f"Who is {topic}?",
                    "body": _shorten(outline["introduction"], 420),
                },
                "3": {
                    "section": _section(sections, 1),
                    "heading1": outline["backgroundHeading1"],
                    "body1": outline["backgroundBody1"],
                    "heading2": outline["backgroundHeading2"],
                    "body2": outline["backgroundBody2"],
                },
                "4": {
                    "section": _section(sections, 2),
                    "heading1": outline["themeHeading1"],
                    "body1": outline["themeBody1"],
                    "heading2": outline["themeHeading2"],
                    "body2": outline["themeBody2"],
                },
                "5": {
                    "section": _section(sections, 3),
                    "heading1": outline["milestoneHeading1"],
                    "body1": outline["milestoneBody1"],
                    "heading2": outline["milestoneHeading2"],
                    "body2": outline["milestoneBody2"],
                },
                "6": {
                    "section": _section(sections, 4),
                    "body": outline["summaryBody"],
                },
                "7": {
                    "section": _section(sections, 5),
                    "body": outline["detailBody1"],
                    "caption": outline["detailCaption1"],
                },
                "8": {
                    "section": _section(sections, 6),
                    "body": outline["detailBody2"],
                    "caption": outline["detailCaption2"],
                },
                "9": {
                    "section": outline["highlight"],
                },
                "10": {
                    "section": self.profile["closing"],
                    "line1": f"{topic}",
                    "line2": outline["takeaway1"],
                    "line3": outline["takeaway2"],
                    "line4": outline["takeaway3"],
                },
            },
        }

    def _build_updates(self, curated: dict) -> list[dict]:
        updates = []
        slide_content = curated["slides"]
        updated_keys = set()

        for slide_index, slide_map in self.template_map.items():
            content = slide_content.get(slide_index, {})
            for field_name, shape_id in slide_map["fields"].items():
                field_value = content.get(field_name)
                if field_value is None:
                    field_value = _fallback_field_value(field_name, curated, int(slide_index), self.profile)
                if field_value is None:
                    continue
                updates.append(
                    {
                        "slideIndex": int(slide_index),
                        "shapeId": shape_id,
                        "field": field_name,
                        "newText": field_value,
                    }
                )
                updated_keys.add((int(slide_index), str(shape_id)))

        updates.extend(_build_cleanup_updates(self.template, curated, updated_keys))
        return updates

    def _apply_updates(self, updates: list[dict]) -> dict:
        filled = deepcopy(self.template)
        update_lookup = {
            (update["slideIndex"], update["shapeId"]): update
            for update in updates
        }

        for slide in filled.get("slides", []):
            slide_index = slide.get("index")
            for text_box in slide.get("texts", []):
                key = (slide_index, text_box.get("shapeId"))
                update = update_lookup.get(key)
                if not update:
                    continue

                text_box["originalText"] = text_box.get("text")
                text_box["text"] = update["newText"]
                self._replace_paragraph_text(text_box, update["newText"])

            for shape in slide.get("shapes", []):
                key = (slide_index, shape.get("shapeId"))
                update = update_lookup.get(key)
                if update and shape.get("hasText"):
                    shape["originalText"] = shape.get("text")
                    shape["text"] = update["newText"]

        filled["generation"] = {
            "templateMap": self.template_map,
            "mapperSource": self.mapper_source,
            "updates": updates,
        }
        return filled

    @staticmethod
    def _replace_paragraph_text(text_box: dict, new_text: str) -> None:
        paragraphs = text_box.get("paragraphs") or []
        if not paragraphs:
            return

        paragraphs[0]["text"] = new_text
        runs = paragraphs[0].get("runs") or []
        if runs:
            runs[0]["text"] = new_text
            for run in runs[1:]:
                run["text"] = ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def _split_paragraphs(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip()]
    return parts or [value]


def _split_sentences(value: str) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]
    return sentences or [value]


def _guess_topic(value: str) -> str | None:
    first_sentence = _split_sentences(value)[0]
    candidates = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", first_sentence)
    skip = {"The", "A", "An", "In", "On", "For", "This"}
    for candidate in candidates:
        if candidate.split()[0] not in skip:
            return candidate
    return None


def _build_fact_pool(topic: str, paragraphs: list[str], sentences: list[str]) -> list[str]:
    candidates = []
    for sentence in sentences:
        sentence = _complete_fragment(topic, sentence)
        if _word_count(sentence) >= 5:
            candidates.append(_polish_sentence(sentence))

    for paragraph in paragraphs:
        if _word_count(paragraph) >= 18:
            candidates.append(_polish_sentence(_shorten(_complete_fragment(topic, paragraph), 170)))

    facts = []
    seen = set()
    for candidate in candidates:
        normalized = _normalize_for_dedupe(candidate)
        if len(candidate) < 8 or normalized in seen:
            continue
        seen.add(normalized)
        facts.append(_shorten(candidate, 145))

    fallback_facts = [
        f"{topic} connects context, evidence, and practical implications.",
        f"The strongest story about {topic} pairs concise claims with concrete proof.",
        f"{topic} matters most when the audience can see what changed and why.",
        f"Each section should turn one important idea about {topic} into a clear takeaway.",
        "The narrative works best when examples, outcomes, and audience context stay linked.",
        "A focused presentation keeps every slide tied to one message and one proof point.",
        "Strong takeaways explain what the audience should remember and why it matters.",
        "The closing should connect the main insight to the next decision or action.",
        "A clean structure helps complex material stay easy to scan.",
        "The most useful points combine evidence, consequence, and a specific implication.",
        "Details should support the central argument without competing with it.",
        "The final message should feel concise, specific, and audience-ready.",
    ]

    for fallback in fallback_facts:
        if len(facts) >= 40:
            break
        facts.append(fallback)

    return facts[:40]


def _template_text_box_inventory(template: dict) -> list[dict]:
    inventory = []
    for slide in template.get("slides", []):
        slide_index = int(slide.get("index", 0))
        shapes = {
            str(shape.get("shapeId")): shape
            for shape in slide.get("shapes", [])
            if shape.get("shapeId")
        }
        text_boxes = []
        for text_box in slide.get("texts", []):
            shape_id = str(text_box.get("shapeId") or "")
            original_text = _clean_text(text_box.get("text") or "")
            if not shape_id or not original_text:
                continue

            shape = shapes.get(shape_id, {})
            geometry = shape.get("geometry") or {}
            font_size = _font_size(text_box)
            text_boxes.append(
                {
                    "shapeId": shape_id,
                    "name": text_box.get("name") or f"TextBox {shape_id}",
                    "originalText": _shorten(original_text, 180),
                    "fontSize": font_size,
                    "x": geometry.get("xInches"),
                    "y": geometry.get("yInches"),
                    "width": geometry.get("widthInches"),
                    "height": geometry.get("heightInches"),
                    "maxChars": _box_text_budget(original_text, font_size, geometry),
                }
            )
        if text_boxes:
            inventory.append({"index": slide_index, "textBoxes": text_boxes})
    return inventory


def _parse_structured_slides(raw_text: str) -> dict[int, dict]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"^\s*[⸻—–-]+\s*$", "", normalized, flags=re.M)
    matches = list(re.finditer(r"^\s*Slide\s+(\d{1,2})\s*:\s*(.*?)\s*$", normalized, flags=re.I | re.M))
    if len(matches) < 2:
        return {}

    slides = {}
    for index, match in enumerate(matches):
        slide_number = int(match.group(1))
        header_title = _clean_text(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        lines = [
            line.strip()
            for line in normalized[start:end].splitlines()
            if line.strip() and not re.fullmatch(r"[⸻—–-]+", line.strip())
        ]
        if not lines and not header_title:
            continue

        title = header_title
        subtitle = ""
        generic_headers = {"title slide", "section slide", "closing slide", "agenda"}
        if (not title or title.lower() in generic_headers) and lines:
            title = _clean_text(_strip_bullet(lines.pop(0)))
        elif lines and not _is_bullet_line(lines[0]):
            subtitle = _clean_text(_strip_bullet(lines.pop(0)))

        bullets = []
        section_labels = []
        groups = {}
        conclusion = ""
        pending_label = ""
        for line in lines:
            stripped = _strip_bullet(line)
            if not stripped:
                continue
            if re.match(r"^conclusion\s*:", stripped, flags=re.I):
                conclusion = _clean_text(re.sub(r"^conclusion\s*:\s*", "", stripped, flags=re.I))
                pending_label = "Conclusion"
                continue
            if pending_label == "Conclusion" and not _is_bullet_line(line):
                conclusion = _clean_text(f"{conclusion} {stripped}".strip())
                continue
            if not _is_bullet_line(line) and len(stripped.split()) <= 4:
                pending_label = stripped.rstrip(":")
                section_labels.append(pending_label)
                groups.setdefault(pending_label, [])
                continue
            if pending_label and pending_label.lower() not in {"conclusion"}:
                bullets.append(f"{pending_label}: {stripped}")
                groups.setdefault(pending_label, []).append(stripped)
            else:
                bullets.append(stripped)

        slides[slide_number] = {
            "title": title or f"Slide {slide_number}",
            "subtitle": subtitle,
            "bullets": bullets,
            "sectionLabels": section_labels,
            "groups": groups,
            "conclusion": conclusion,
        }

    return slides if len(slides) >= 2 else {}


def _is_bullet_line(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[*•\-–]|\d+[.)])\s+", line))


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\s*(?:[*•\-–]|\d+[.)])\s+", "", line).strip()


def _topic_from_structured_slides(slides: dict[int, dict]) -> str | None:
    first = slides.get(1) or {}
    title = first.get("title") or ""
    if ":" in title:
        return title.split(":", 1)[0].strip()
    match = re.match(r"([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,3})", title)
    return match.group(1).strip() if match else None


def _curated_from_structured_slides(
    topic: str,
    structured_slides: dict[int, dict],
    template: dict,
    template_map: dict,
    profile: dict,
) -> dict:
    budgets = _field_budgets(template, template_map)
    curated = {
        "deckTitle": topic,
        "subtitle": _structured_cover_subtitle(topic, structured_slides.get(1, {}), profile),
        "byline": _structured_cover_byline(structured_slides.get(1, {})),
        "year": str(date.today().year),
        "unusedFacts": _structured_fact_sequence(structured_slides),
        "slides": {},
    }

    for slide_number in sorted(structured_slides):
        slide_data = structured_slides[slide_number]
        fields = (template_map.get(str(slide_number)) or {}).get("fields") or {}
        if not fields:
            continue
        curated["slides"][str(slide_number)] = _structured_slide_fields(
            topic,
            slide_number,
            slide_data,
            fields,
            budgets.get(slide_number, {}),
            curated,
        )

    return curated


def _field_budgets(template: dict, template_map: dict) -> dict[int, dict[str, int]]:
    inventory_by_slide = {
        int(slide["index"]): {
            str(text_box["shapeId"]): int(text_box.get("maxChars") or 120)
            for text_box in slide.get("textBoxes", [])
        }
        for slide in _template_text_box_inventory(template)
    }
    budgets = {}
    for slide_index, slide_map in template_map.items():
        slide_number = int(slide_index)
        budgets[slide_number] = {}
        for field_name, shape_id in (slide_map.get("fields") or {}).items():
            raw_budget = inventory_by_slide.get(slide_number, {}).get(str(shape_id), 120)
            budgets[slide_number][field_name] = max(raw_budget, _minimum_field_budget(field_name))
    return budgets


def _minimum_field_budget(field_name: str) -> int:
    if field_name == "title":
        return 24
    if field_name in {"section", "headline", "subtitle"}:
        return 44
    if field_name.startswith("heading") or field_name.startswith("line"):
        return 64
    if field_name.startswith("body"):
        return 145
    return 80


def _structured_cover_subtitle(topic: str, slide: dict, profile: dict) -> str:
    title = slide.get("title") or topic
    if ":" in title:
        return _fit_structured_text(title.split(":", 1)[1].strip(), 48)
    return _fit_structured_text(slide.get("subtitle") or profile.get("subtitle", "profile"), 48)


def _structured_cover_byline(slide: dict) -> str:
    bullets = slide.get("bullets") or []
    return _fit_structured_text(bullets[0] if bullets else slide.get("subtitle", ""), 70, sentence=True)


def _structured_fact_sequence(slides: dict[int, dict]) -> list[str]:
    facts = []
    for slide_number in sorted(slides):
        slide = slides[slide_number]
        for value in [slide.get("title"), slide.get("subtitle"), *(slide.get("bullets") or []), slide.get("conclusion")]:
            value = _clean_text(value or "")
            if value:
                facts.append(_shorten(value, 145))
    return facts


def _structured_slide_fields(
    topic: str,
    slide_number: int,
    slide: dict,
    fields: dict,
    budgets: dict[str, int],
    curated: dict,
) -> dict:
    if slide_number == 1:
        return {
            "title": _fit_structured_text(topic, budgets.get("title", 28)),
            "subtitle": _fit_structured_text(curated.get("subtitle", ""), budgets.get("subtitle", 48)),
            "byline": _fit_structured_text(curated.get("byline", ""), budgets.get("byline", 70), sentence=True),
            "year": curated.get("year", str(date.today().year)),
        }

    title = slide.get("title") or f"Slide {slide_number}"
    subtitle = slide.get("subtitle") or title
    bullets = slide.get("bullets") or []
    conclusion = slide.get("conclusion") or ""
    content = {}

    if "section" in fields and "headline" in fields:
        first, second = _split_structured_heading(subtitle or title)
        content["headline"] = _fit_structured_text(first, budgets.get("headline", 48))
        content["section"] = _fit_structured_text(second, budgets.get("section", 48))
    elif "section" in fields:
        content["section"] = _fit_structured_text(subtitle or title, budgets.get("section", 48))
    elif "headline" in fields:
        content["headline"] = _fit_structured_text(subtitle or title, budgets.get("headline", 48))

    body_fields = [field for field in fields if field.startswith("body")]
    body_fields.sort(key=lambda field: (field != "body", _field_number(field)))
    if body_fields:
        chunks = _bullet_chunks(bullets, len(body_fields), conclusion)
        for field_name, chunk in zip(body_fields, chunks):
            content[field_name] = _fit_structured_text(chunk, budgets.get(field_name, 145), sentence=True)

    heading_fields = sorted([field for field in fields if field.startswith("heading")], key=_field_number)
    if heading_fields:
        if not body_fields:
            heading_values = _structured_group_values(slide, heading_fields, bullets, conclusion)
        else:
            heading_values = _structured_heading_values(slide, heading_fields, bullets, conclusion)
        for field_name, value in zip(heading_fields, heading_values):
            content[field_name] = _fit_structured_text(value, budgets.get(field_name, 70), sentence=not body_fields)

    line_fields = sorted([field for field in fields if field.startswith("line")], key=_field_number)
    if line_fields:
        values = [topic, *bullets, conclusion]
        for field_name, value in zip(line_fields, values):
            content[field_name] = _fit_structured_text(value, budgets.get(field_name, 90), sentence=field_name != "line1")

    return content


def _split_structured_heading(value: str) -> tuple[str, str]:
    value = _clean_text(value)
    if "&" in value:
        left, right = [part.strip() for part in value.split("&", 1)]
        return left or value, right or value
    parts = value.split()
    if len(parts) <= 1:
        return value, ""
    if len(parts) == 2:
        return parts[0], parts[1]
    midpoint = max(1, len(parts) // 2)
    return " ".join(parts[:midpoint]), " ".join(parts[midpoint:])


def _fit_structured_text(value: str, max_chars: int, *, sentence: bool = False) -> str:
    value = _clean_text(value)
    if len(value) > max_chars:
        value = value[: max_chars - 1].rsplit(" ", 1)[0]
    value = re.sub(r"\b(and|or|the|a|an|of|for|to|with|in|on|at|by)$", "", value, flags=re.I)
    value = re.sub(r"\s+[&:;,/-]\s*$", "", value).strip(" ,;:-")
    if not sentence:
        return value
    return _polish_sentence(value)


def _bullet_chunks(bullets: list[str], count: int, conclusion: str = "") -> list[str]:
    values = bullets[:]
    if conclusion:
        values.append(f"Conclusion: {conclusion}")
    if not values:
        values = ["Key point"]
    chunks = [[] for _ in range(count)]
    for index, bullet in enumerate(values):
        chunks[index % count].append(bullet)
    return ["; ".join(chunk) for chunk in chunks]


def _structured_heading_values(slide: dict, heading_fields: list[str], bullets: list[str], conclusion: str) -> list[str]:
    labels = slide.get("sectionLabels") or []
    values = labels[:]
    for bullet in bullets:
        if ":" in bullet:
            values.append(bullet.split(":", 1)[0])
        else:
            values.append(_heading_from_fact(bullet))
    if conclusion:
        values.append("Conclusion")
    while len(values) < len(heading_fields):
        values.append(slide.get("subtitle") or slide.get("title") or "Key Point")
    return values[: len(heading_fields)]


def _structured_group_values(slide: dict, heading_fields: list[str], bullets: list[str], conclusion: str) -> list[str]:
    groups = {
        label: values
        for label, values in (slide.get("groups") or {}).items()
        if values
    }
    if groups:
        values = []
        for label, group_bullets in groups.items():
            values.append(f"{label}: {'; '.join(group_bullets)}")
        if conclusion:
            values.append(f"Conclusion: {conclusion}")
        return values[: len(heading_fields)]

    return _bullet_chunks(bullets, len(heading_fields), conclusion)


def _font_size(text_box: dict) -> float:
    sizes = []
    for paragraph in text_box.get("paragraphs", []):
        for run in paragraph.get("runs", []):
            size = run.get("fontSize")
            if size:
                sizes.append(float(size))
    return max(sizes) if sizes else 0


def _box_text_budget(text: str, font_size: float, geometry: dict) -> int:
    if _is_page_marker(text):
        return len(text)
    height = float(geometry.get("heightInches") or 0)
    if font_size >= 100:
        return 28
    if font_size >= 55:
        return 48
    if font_size >= 35:
        return 70
    if height and height <= 1.2:
        return 110
    return 190


def _curated_from_text_box_updates(topic: str, fallback_curated: dict, updates: list[dict]) -> dict:
    curated = {
        "deckTitle": topic,
        "subtitle": fallback_curated.get("subtitle", ""),
        "byline": fallback_curated.get("byline", ""),
        "year": fallback_curated.get("year", str(date.today().year)),
        "unusedFacts": fallback_curated.get("unusedFacts", []),
        "slides": {},
    }
    role_counts = {}
    for update in updates:
        slide_index = str(update["slideIndex"])
        role = str(update.get("role") or update.get("field") or "text")
        text = str(update.get("newText") or "").strip()
        if not text:
            continue
        count_key = (slide_index, role)
        role_counts[count_key] = role_counts.get(count_key, 0) + 1
        field = role if role_counts[count_key] == 1 else f"{role}{role_counts[count_key]}"
        curated["slides"].setdefault(slide_index, {})[field] = text
    return curated


def _expand_curated_for_template(curated: dict, template_map: dict, profile: dict) -> dict:
    expanded = deepcopy(curated)
    expanded.setdefault("slides", {})

    for slide_index, slide_map in template_map.items():
        slide_number = int(slide_index)
        slide = expanded["slides"].setdefault(str(slide_index), {})
        for field_name in (slide_map.get("fields") or {}).keys():
            if slide.get(field_name):
                continue
            field_value = _fallback_field_value(field_name, expanded, slide_number, profile)
            if field_value is not None:
                slide[field_name] = field_value

    return expanded


def _fallback_field_value(
    field_name: str,
    curated: dict,
    slide_index: int,
    profile: dict | None = None,
) -> str | None:
    facts = curated.get("unusedFacts") or _curated_fact_sequence(curated)
    profile = profile or {}

    if field_name == "title":
        return curated.get("deckTitle")
    if field_name == "subtitle":
        return curated.get("subtitle") or profile.get("subtitle")
    if field_name == "byline":
        return curated.get("byline", "")
    if field_name == "year":
        return curated.get("year", str(date.today().year))
    if field_name == "section":
        if slide_index <= 1:
            return profile.get("name") or "Overview"
        return _section(profile.get("sections") or [], slide_index - 2)
    if field_name == "headline":
        fact_index = max(slide_index - 2, 0)
        fact = _fact_at(facts, fact_index)
        if fact:
            return _heading_from_fact(fact)
        return _section(profile.get("sections") or [], slide_index - 2)
    if field_name.startswith("heading"):
        heading_index = _field_number(field_name)
        fact_index = slide_index + heading_index - 2
        fact = _fact_at(facts, fact_index)
        if fact:
            return _heading_from_fact(fact)
        return None

    if field_name.startswith("body"):
        body_index = _field_number(field_name)
        fact_index = slide_index + body_index - 2
        fact = _fact_at(facts, fact_index)
        if fact:
            return fact
        return None

    if field_name.startswith("line"):
        line_index = _field_number(field_name)
        fact_index = slide_index + line_index - 2
        fact = _fact_at(facts, fact_index)
        if fact:
            return _shorten(fact, 90)
        return curated.get("deckTitle")

    if field_name == "caption":
        return "Key detail"

    return None


def _fact_at(facts: list[str], index: int) -> str | None:
    if not facts:
        return None
    return facts[index % len(facts)]


def _build_cleanup_updates(template: dict, curated: dict, updated_keys: set[tuple[int, str]]) -> list[dict]:
    updates = []
    facts = curated.get("unusedFacts") or _curated_fact_sequence(curated)
    cleanup_index = 0

    for slide in template.get("slides", []):
        slide_index = int(slide.get("index", 0))
        for text_box in slide.get("texts", []):
            shape_id = str(text_box.get("shapeId"))
            if not shape_id or (slide_index, shape_id) in updated_keys:
                continue

            replacement = _cleanup_replacement(
                text_box.get("text") or "",
                curated,
                facts,
                slide_index,
                cleanup_index,
            )
            if replacement is None:
                continue

            cleanup_index += 1
            updates.append(
                {
                    "slideIndex": slide_index,
                    "shapeId": shape_id,
                    "field": "cleanup",
                    "newText": replacement,
                }
            )

    return updates


def _cleanup_replacement(
    text: str,
    curated: dict,
    facts: list[str],
    slide_index: int,
    cleanup_index: int,
) -> str | None:
    normalized = _clean_text(text)
    if not normalized or _is_page_marker(normalized):
        return None

    lowered = normalized.lower()
    topic = curated.get("deckTitle", "Generated Topic")

    if lowered == "our":
        return ""
    if _is_clearable_template_filler(lowered):
        return ""
    if _is_date_filler(normalized):
        return curated.get("year", str(date.today().year))
    if _is_fake_person_filler(lowered):
        return _heading_from_fact(_fact_for_cleanup(facts, slide_index, cleanup_index))
    if _is_brand_or_person_filler(lowered):
        return topic
    if _is_body_template_filler(lowered):
        return _fact_for_cleanup(facts, slide_index, cleanup_index)
    if _is_short_template_filler(lowered):
        return _heading_from_fact(_fact_for_cleanup(facts, slide_index, cleanup_index))

    return None


def _fact_for_cleanup(facts: list[str], slide_index: int, cleanup_index: int) -> str:
    if not facts:
        return "Key point."
    index = (slide_index * 2 + cleanup_index) % len(facts)
    return _shorten(facts[index], 120)


def _is_page_marker(text: str) -> bool:
    normalized = text.strip().lower()
    return bool(
        re.fullmatch(r"(page\s*)?\d{1,2}", normalized)
        or re.fullmatch(r"\d{1,2}\s*/\s*\d{1,2}", normalized)
    )


def _is_date_filler(text: str) -> bool:
    return bool(
        re.search(r"\b(19|20)\d{2}\b", text)
        and re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", text, re.I)
    )


def _is_clearable_template_filler(lowered: str) -> bool:
    patterns = [
        "reallygreatsite",
        "123 anywhere",
        "+123",
        "phone number",
        "email address",
        "website",
        "read more",
        "get started",
        "lets build something great together",
        "let's build something great together",
        "source text",
        "generated from source text",
        "[project portfolio]",
    ]
    return (
        any(pattern in lowered for pattern in patterns)
        or bool(re.search(r"\b[\w.-]+@[\w.-]+\.\w+\b", lowered))
        or bool(re.search(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", lowered))
    )


def _is_fake_person_filler(lowered: str) -> bool:
    patterns = [
        "adeline palmerston",
        "avery davis",
        "chad gibbons",
        "cia rodriguez",
    ]
    return any(pattern in lowered for pattern in patterns)


def _is_brand_or_person_filler(lowered: str) -> bool:
    patterns = [
        "arowwai",
        "alexander aronowitz",
        "borcelle",
        "cahaya dewi",
        "giggling platypus",
        "ingoude",
        "jonathan patter",
        "larana team",
        "liceria",
        "interor designer",
        "interior designer",
        "rimberio",
        "studio shodwe",
        "timmerman",
        "tynk unlimited",
        "wardiere",
        "warner & spencer",
        "fagatr apartment",
        "final archiect concept",
        "final architect concept",
        "cum laude",
        "indonesia",
    ]
    return any(pattern in lowered for pattern in patterns)


def _is_body_template_filler(lowered: str) -> bool:
    patterns = [
        "lorem ipsum",
        "presentation are communication",
        "presentations are communication",
        "thing that wraps around",
        "the percentage of people who did a thing",
        "make an impact with a big, bold statement",
        "this insight is so big",
        "explain why this number is important",
        "review the generated",
        "generated content",
        "export the pptx",
        "add stronger examples",
        "add more source material",
        "source text is thin",
        "source is thin",
        "before presenting",
        "text thin",
        "easy scan",
        "keep each slide focused",
        "use verified details",
        "use visuals to support",
        "template structure",
        "audience takeaways",
        "2025 marketing strategy",
        "creating functional and inspiring spaces",
        "designing harmony",
        "featured project",
        "technical planning",
        "living area",
        "workspace",
        "design notes",
        "concept development",
        "mood exploration",
        "iteration & refinement",
        "final / concept",
        "the challenges of iot",
        "pros and cons of the iot",
        "development of the iot",
        "rise of the iot",
        "what is the iot",
        "future of iot",
        "iot",
        "internet of things",
    ]
    return any(pattern in lowered for pattern in patterns)


def _is_short_template_filler(lowered: str) -> bool:
    patterns = [
        "project portfolio",
        "source text",
        "source highlight",
        "before presenting",
        "easy scan",
        "text thin",
        "so much",
        "thank you",
        "happy client",
        "design context",
        "boost brand visibility",
        "accelerate lead generation",
        "expand recognition",
        "product demos",
        "software",
        "it consulting",
        "data analytics",
        "bachelor",
        "master",
        "project -",
        "team",
        "our team",
        "presence",
    ]
    return any(pattern in lowered for pattern in patterns)


def _curated_fact_sequence(curated: dict) -> list[str]:
    facts = []
    for slide in curated.get("slides", {}).values():
        for key in ["body", "body1", "body2", "line2", "line3"]:
            value = slide.get(key)
            if value and value not in facts:
                facts.append(value)
    return facts


def _field_number(field_name: str) -> int:
    match = re.search(r"(\d+)$", field_name)
    return int(match.group(1)) if match else 1


class FactAllocator:
    def __init__(self, facts: list[str]) -> None:
        self.facts = facts
        self.used = set()

    def take(self, groups: list[list[str]], max_chars: int = 145) -> str:
        for group in groups:
            for fact in group:
                key = _normalize_for_dedupe(fact)
                if key in self.used:
                    continue
                self.used.add(key)
                return _shorten(fact, max_chars)
        return ""

    def take_combined(self, groups: list[list[str]], max_chars: int) -> str:
        selected = []
        for group in groups:
            fact = self.take([group], max_chars)
            if fact:
                selected.append(fact)
            if len(" ".join(selected)) >= max_chars * 0.75:
                break
        return _shorten(" ".join(selected), max_chars)

    def remaining(self) -> list[str]:
        return [
            fact
            for fact in self.facts
            if _normalize_for_dedupe(fact) not in self.used
        ]


def _build_outline(topic: str, facts: list[str]) -> dict:
    allocator = FactAllocator(facts)
    categories = {
        "background": _select_facts(facts, ["born", "early", "family", "education", "studied", "school", "university", "grew"]),
        "milestones": _select_facts(facts, ["founded", "launched", "became", "joined", "acquired", "sold", "created", "led", "year", "in 19", "in 20"]),
        "business": _select_facts(facts, ["company", "business", "tesla", "spacex", "market", "product", "technology", "venture", "industry"]),
        "impact": _select_facts(facts, ["known", "influence", "impact", "world", "public", "wealth", "major", "notable", "important"]),
    }

    outline = {
        "introduction": allocator.take_combined([facts, categories["impact"], categories["business"]], 420),
        "backgroundBody1": allocator.take([categories["background"], facts]),
        "backgroundBody2": allocator.take([categories["background"], facts]),
        "themeBody1": allocator.take([categories["business"], facts]),
        "themeBody2": allocator.take([categories["impact"], facts]),
        "milestoneBody1": allocator.take([categories["milestones"], facts]),
        "milestoneBody2": allocator.take([categories["milestones"], facts]),
        "summarySection": "Impact Summary",
        "summaryBody": allocator.take_combined([categories["impact"], categories["business"], facts], 360),
        "detailSection1": _detail_section(categories["business"], "Key Venture"),
        "detailBody1": allocator.take([categories["business"], facts]),
        "detailCaption1": "Selected example",
        "detailSection2": _detail_section(categories["impact"], "Notable Influence"),
        "detailBody2": allocator.take([categories["impact"], categories["business"], facts]),
        "detailCaption2": "Key detail",
        "highlight": _highlight_phrase(topic, categories, facts),
        "takeaway1": _shorten(allocator.take([facts]), 70),
        "takeaway2": _shorten(allocator.take([categories["impact"], facts]), 70),
        "takeaway3": allocator.take([facts]) or f"{topic} connects context, evidence, and next steps.",
    }
    outline["backgroundHeading1"] = _heading_from_fact(outline["backgroundBody1"])
    outline["backgroundHeading2"] = _heading_from_fact(outline["backgroundBody2"])
    outline["themeHeading1"] = _heading_from_fact(outline["themeBody1"])
    outline["themeHeading2"] = _heading_from_fact(outline["themeBody2"])
    outline["milestoneHeading1"] = _milestone_heading_from_fact(outline["milestoneBody1"], "Milestone 01")
    outline["milestoneHeading2"] = _milestone_heading_from_fact(outline["milestoneBody2"], "Milestone 02")
    outline["unusedFacts"] = allocator.remaining()
    return outline


def _section(sections: list[str], index: int) -> str:
    if not sections:
        return "Overview"
    if index < len(sections):
        return sections[index]
    return sections[-1]


def _select_facts(facts: list[str], keywords: list[str]) -> list[str]:
    selected = []
    for fact in facts:
        lowered = fact.lower()
        if any(keyword in lowered for keyword in keywords):
            selected.append(fact)
    return selected


def _pick(values: list[str], index: int, fallback: str | None = None) -> str:
    if index < len(values):
        return values[index]
    if fallback:
        return fallback
    return values[-1] if values else ""


def _combine_unique(values: list[str], max_chars: int) -> str:
    combined = []
    seen = set()
    for value in values:
        normalized = value.lower()
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        combined.append(value)
    return _shorten(" ".join(combined), max_chars)


def _normalize_for_dedupe(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    words = value.split()
    return " ".join(words[:18])


def _heading_for(values: list[str], fallback: str) -> str:
    first = values[0].lower() if values else ""
    if "education" in first or "university" in first or "school" in first:
        return "Education"
    if "born" in first or "family" in first:
        return "Origins"
    return fallback


def _theme_heading(values: list[str], fallback: str) -> str:
    text = " ".join(values[:2]).lower()
    if "technology" in text:
        return "Technology"
    if "company" in text or "business" in text:
        return "Business"
    if "public" in text or "known" in text:
        return "Public Profile"
    return fallback


def _heading_from_fact(fact: str) -> str:
    lowered = fact.lower()
    keyword_headings = [
        (["founded", "launched", "created", "started"], "Founding Move"),
        (["growth", "expanded", "scale", "global"], "Growth Signal"),
        (["customer", "users", "audience"], "Audience Need"),
        (["market", "industry", "competitive"], "Market Context"),
        (["risk", "critics", "challenge", "pressure"], "Key Risk"),
        (["technology", "software", "ai", "space", "electric"], "Technology Focus"),
        (["result", "impact", "influence", "known"], "Impact"),
        (["revenue", "profit", "cost", "financial"], "Financial Logic"),
        (["team", "culture", "organization"], "Operating Model"),
    ]
    for keywords, heading in keyword_headings:
        if any(keyword in lowered for keyword in keywords):
            return heading

    words = [
        word.capitalize()
        for word in re.findall(r"[A-Za-z][A-Za-z'-]+", fact)
        if word.lower() not in {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "into",
            "also",
            "because",
            "their",
            "there",
        }
    ]
    return " ".join(words[:3]) or "Key Point"


def _milestone_heading(values: list[str], index: int) -> str:
    fact = values[index].lower() if index < len(values) else ""
    year = re.search(r"\b(19|20)\d{2}\b", fact)
    if year:
        return year.group(0)
    return f"Milestone {index + 1:02d}"


def _milestone_heading_from_fact(fact: str, fallback: str) -> str:
    year = re.search(r"\b(19|20)\d{2}\b", fact)
    if year:
        return year.group(0)
    return _heading_from_fact(fact) or fallback


def _detail_section(values: list[str], fallback: str) -> str:
    text = " ".join(values[:2]).lower()
    if "tesla" in text:
        return "Tesla"
    if "spacex" in text:
        return "SpaceX"
    if "company" in text:
        return "Company Focus"
    return fallback


def _highlight_phrase(topic: str, categories: dict[str, list[str]], facts: list[str]) -> str:
    source = " ".join(categories["business"][:1] + categories["impact"][:1] + facts[:1]).lower()
    if "spacex" in source:
        return "SpaceX"
    if "tesla" in source:
        return "Tesla"
    if "technology" in source or "software" in source:
        return "Technology"
    if "business" in source or "company" in source:
        return "Business Impact"
    return "Key Highlight"


def _complete_fragment(topic: str, value: str) -> str:
    value = value.strip()
    if re.match(r"^(is|are|was|were|has|have|had|can|could|will|would|should)\b", value, flags=re.I):
        return f"{topic} {value}"
    return value


def _format_topic(value: str) -> str:
    if not value:
        return value
    if value.islower() or value.isupper():
        small_words = {"a", "an", "and", "as", "for", "in", "of", "on", "the", "to"}
        words = []
        for index, word in enumerate(value.lower().split()):
            words.append(word if index > 0 and word in small_words else word.capitalize())
        return " ".join(words)
    return value


def _make_subtitle(topic: str, facts: list[str], profile: dict) -> str:
    source = " ".join(facts).lower()
    if "marketing" in source:
        return "marketing profile"
    if any(keyword in source for keyword in ["technology", "space", "software", "electric", "ai"]):
        return "technology profile"
    if any(keyword in source for keyword in ["business", "company", "founder", "venture", "market"]):
        return "business profile"
    return profile.get("subtitle", "presentation profile")


def _make_byline(profile: dict) -> str:
    return ""


def _polish_sentence(value: str) -> str:
    value = value.strip(" ,;:-")
    if not value:
        return value

    value = value[0].upper() + value[1:]
    if value[-1] not in ".!?":
        value = f"{value}."
    return value


def _shorten(value: str, max_chars: int) -> str:
    value = value.strip()
    if len(value) <= max_chars:
        return _polish_sentence(value)

    clipped = value[: max_chars - 1].rsplit(" ", 1)[0]
    clipped = re.sub(r"\b(and|or|the|a|an|of|for|to|with|in|on|at|by)$", "", clipped, flags=re.I)
    return _polish_sentence(clipped)
