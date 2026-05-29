from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


class PptxExporter:
    def __init__(self, source_pptx: str | Path) -> None:
        self.source_pptx = Path(source_pptx).expanduser().resolve()

    def export(self, filled_template: dict, output_path: str | Path) -> Path:
        if not self.source_pptx.exists():
            raise FileNotFoundError(f"Source PPTX not found: {self.source_pptx}")

        output_path = Path(output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        shape_metadata = _extract_shape_metadata(filled_template)
        updates_by_slide = _group_updates_by_slide(filled_template, shape_metadata)
        slide_paths = {
            slide["index"]: slide["path"]
            for slide in filled_template.get("slides", [])
            if slide.get("index") and slide.get("path")
        }
        replacements = {
            slide_paths[slide_index]: updates
            for slide_index, updates in updates_by_slide.items()
            if slide_index in slide_paths
        }

        with ZipFile(self.source_pptx, "r") as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename in replacements:
                    data = _replace_slide_text(data, replacements[item.filename])
                target.writestr(item, data)

        return output_path


def _extract_shape_metadata(filled_template: dict) -> dict[int, dict[str, dict]]:
    metadata = {}
    for slide in filled_template.get("slides", []):
        slide_index = int(slide["index"])
        metadata[slide_index] = {
            str(shape["shapeId"]): {
                "geometry": shape.get("geometry") or {},
                "originalText": shape.get("originalText") or shape.get("text") or "",
            }
            for shape in slide.get("shapes", [])
            if shape.get("shapeId")
        }
    return metadata


def _group_updates_by_slide(filled_template: dict, shape_metadata: dict[int, dict[str, dict]]) -> dict[int, dict[str, dict]]:
    grouped = defaultdict(dict)
    for update in filled_template.get("generation", {}).get("updates", []):
        slide_index = int(update["slideIndex"])
        shape_id = str(update["shapeId"])
        grouped[slide_index][shape_id] = {
            "newText": str(update["newText"]),
            "geometry": shape_metadata.get(slide_index, {}).get(shape_id, {}).get("geometry", {}),
            "originalText": shape_metadata.get(slide_index, {}).get(shape_id, {}).get("originalText", ""),
        }
    return grouped


def _replace_slide_text(xml_bytes: bytes, updates: dict[str, dict]) -> bytes:
    root = ET.fromstring(xml_bytes)

    for shape in root.findall(".//p:cSld/p:spTree/p:sp", NS):
        non_visual_props = shape.find("p:nvSpPr/p:cNvPr", NS)
        if non_visual_props is None:
            continue

        shape_id = non_visual_props.attrib.get("id")
        if shape_id not in updates:
            continue

        update = updates[shape_id]
        _replace_shape_text(
            shape,
            update["newText"],
            update.get("geometry", {}),
            update.get("originalText", ""),
        )

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _replace_shape_text(shape: ET.Element, new_text: str, geometry: dict, original_text: str) -> None:
    text_body = shape.find("p:txBody", NS)
    if text_body is None:
        return

    paragraphs = text_body.findall("a:p", NS)
    if not paragraphs:
        return

    lines = new_text.splitlines() or [new_text]
    first_paragraph = paragraphs[0]

    for paragraph in paragraphs[1:]:
        text_body.remove(paragraph)

    _set_paragraph_text(first_paragraph, lines[0])

    for line in lines[1:]:
        paragraph = deepcopy(first_paragraph)
        _set_paragraph_text(paragraph, line)
        text_body.append(paragraph)

    fitted_size = _fit_font_size(shape, new_text, geometry, original_text)
    if fitted_size is not None:
        _set_font_size(shape, fitted_size)


def _set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    text_nodes = paragraph.findall(".//a:t", NS)
    if not text_nodes:
        return

    text_nodes[0].text = text
    for node in text_nodes[1:]:
        node.text = ""


def _fit_font_size(shape: ET.Element, text: str, geometry: dict, original_text: str) -> int | None:
    current_size = _current_font_size(shape)
    width_inches = geometry.get("widthInches")
    height_inches = geometry.get("heightInches")
    if current_size is None or not width_inches or not height_inches:
        return None

    new_score = _text_fit_score(text)
    original_score = _text_fit_score(original_text)
    if original_score and new_score <= original_score * 1.15:
        return None

    ratio_fit = current_size
    if original_score:
        ratio_fit = current_size * (original_score / new_score) * 1.08

    line_count = max(len(text.splitlines() or [text]), 1)
    original_line_count = max(len(original_text.splitlines() or [original_text]), 1)
    height_fit = current_size
    if line_count > original_line_count:
        height_fit = current_size * (original_line_count / line_count)

    fitted_size = min(current_size, ratio_fit, height_fit)
    fitted_size = max(fitted_size, min(current_size, 11))
    if fitted_size >= current_size:
        return None
    return int(round(fitted_size * 100))


def _text_fit_score(text: str) -> float:
    lines = text.splitlines() or [text]
    longest_line = max((_weighted_text_length(line) for line in lines), default=1)
    return max(longest_line, 1) * max(len(lines), 1)


def _weighted_text_length(text: str) -> float:
    score = 0.0
    for char in text:
        if char.isspace():
            score += 0.35
        elif char in "il.,'":
            score += 0.45
        elif char in "mwMW":
            score += 1.25
        else:
            score += 1.0
    return score


def _current_font_size(shape: ET.Element) -> float | None:
    sizes = []
    for run_props in shape.findall(".//a:rPr", NS):
        size = run_props.attrib.get("sz")
        if size and size.isdigit():
            sizes.append(int(size) / 100)

    default_props = shape.find(".//a:defRPr", NS)
    if default_props is not None:
        size = default_props.attrib.get("sz")
        if size and size.isdigit():
            sizes.append(int(size) / 100)

    return max(sizes) if sizes else None


def _set_font_size(shape: ET.Element, size: int) -> None:
    for run_props in shape.findall(".//a:rPr", NS):
        run_props.set("sz", str(size))

    default_props = shape.find(".//a:defRPr", NS)
    if default_props is not None:
        default_props.set("sz", str(size))
