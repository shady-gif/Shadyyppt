from __future__ import annotations

from copy import deepcopy
from datetime import date
import re

from template_map import TEMPLATE_MAP
from semantic_mapper import build_template_map
from ai_semantic_mapper import improve_template_map_with_ai
from template_profiles import get_template_profile


class ContentGenerator:
    def __init__(self, template: dict, template_id: str | None = None) -> None:
        self.template = template
        self.template_id = template_id
        self.profile = get_template_profile(template_id)
        rule_map = build_template_map(template) or TEMPLATE_MAP
        self.template_map, self.mapper_source = improve_template_map_with_ai(template, rule_map)

    def generate(self, raw_text: str, topic: str | None = None) -> dict:
        cleaned = _clean_text(raw_text)
        if not cleaned:
            raise ValueError("Please paste some text before generating.")
        word_count = _word_count(cleaned)
        if word_count < 500:
            raise ValueError(f"Please paste at least 500 words. Current source text has {word_count} words.")
        if word_count > 2000:
            raise ValueError(f"Please keep source text under 2000 words. Current source text has {word_count} words.")

        paragraphs = _split_paragraphs(cleaned)
        sentences = _split_sentences(cleaned)
        topic = _format_topic((topic or _guess_topic(cleaned) or "Generated Profile").strip())

        curated = self._curate_content(topic, paragraphs, sentences)
        updates = self._build_updates(curated)
        filled = self._apply_updates(updates)

        return {
            "topic": topic,
            "curatedContent": curated,
            "updates": updates,
            "mapperSource": self.mapper_source,
            "filledTemplateJson": filled,
        }

    def _curate_content(self, topic: str, paragraphs: list[str], sentences: list[str]) -> dict:
        facts = _build_fact_pool(topic, paragraphs, sentences)
        outline = _build_outline(topic, facts)
        subtitle = _make_subtitle(topic, facts, self.profile)
        sections = self.profile["sections"]

        return {
            "deckTitle": topic,
            "subtitle": subtitle,
            "byline": "Generated from source text",
            "year": str(date.today().year),
            "unusedFacts": outline["unusedFacts"],
            "slides": {
                "1": {
                    "title": topic,
                    "subtitle": subtitle,
                    "byline": "Generated from source text",
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

        for slide_index, slide_map in self.template_map.items():
            content = slide_content.get(slide_index, {})
            for field_name, shape_id in slide_map["fields"].items():
                field_value = content.get(field_name)
                if field_value is None:
                    field_value = _fallback_field_value(field_name, curated, int(slide_index))
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
        f"{topic} is the central subject of this presentation.",
        f"The source text gives enough context to introduce {topic}.",
        "Add more source material to deepen the background and evidence.",
        "Keep each slide focused on one clear idea.",
        "Use verified details before sharing the final deck.",
        "Pair concise claims with examples, dates, or outcomes.",
        "Use the template structure to keep the story easy to scan.",
        "Add stronger examples where the source text is thin.",
        "Review the generated content before presenting.",
        "Use visuals to support the strongest claims.",
        "Close with the most important audience takeaways.",
        "Export the PPTX after reviewing slide fit and accuracy.",
    ]

    for fallback in fallback_facts:
        if len(facts) >= 40:
            break
        facts.append(fallback)

    return facts[:40]


def _fallback_field_value(field_name: str, curated: dict, slide_index: int) -> str | None:
    facts = curated.get("unusedFacts") or _curated_fact_sequence(curated)
    if not facts:
        return None

    if field_name.startswith("heading"):
        heading_index = _field_number(field_name)
        fact_index = slide_index + heading_index - 2
        if fact_index < len(facts):
            return _heading_from_fact(facts[fact_index])
        return None

    if field_name.startswith("body"):
        body_index = _field_number(field_name)
        fact_index = slide_index + body_index - 2
        if fact_index < len(facts):
            return facts[fact_index]
        return None

    if field_name == "caption":
        return "Source highlight"

    return None


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
        "detailCaption2": "Source highlight",
        "highlight": _highlight_phrase(topic, categories, facts),
        "takeaway1": _shorten(allocator.take([facts]), 70),
        "takeaway2": _shorten(allocator.take([categories["impact"], facts]), 70),
        "takeaway3": "Review facts and refine before presenting.",
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
        return "SpaceX and Innovation"
    if "tesla" in source:
        return "Tesla and Electric Mobility"
    if "technology" in source or "software" in source:
        return "Technology and Influence"
    if "business" in source or "company" in source:
        return "Business and Influence"
    return f"{topic}: Key Highlight"


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
