from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
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

PATCHABLE_EDITOR_OPERATION_TYPES = {
    "updateText",
    "moveObject",
    "resizeObject",
    "changeFont",
    "changeTextColor",
    "changeBackgroundColor",
}


class PptxExporter:
    def __init__(self, source_pptx: str | Path) -> None:
        self.source_pptx = Path(source_pptx).expanduser().resolve()

    def export(
        self,
        filled_template: dict,
        output_path: str | Path,
        editor_operations: list[dict] | None = None,
        editor_operations_path: str | Path | None = None,
    ) -> Path:
        if not self.source_pptx.exists():
            raise FileNotFoundError(f"Source PPTX not found: {self.source_pptx}")

        output_path = Path(output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_editor_operations = _resolve_editor_operations(
            editor_operations,
            editor_operations_path,
        )

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
        editor_operations_by_path = _group_editor_operations_by_path(
            resolved_editor_operations,
            slide_paths,
        )

        with ZipFile(self.source_pptx, "r") as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename in replacements:
                    data = _replace_slide_text(data, replacements[item.filename])
                if item.filename in editor_operations_by_path:
                    data = _apply_editor_operations_to_slide(
                        data,
                        editor_operations_by_path[item.filename],
                    )
                target.writestr(item, data)

        return output_path


def _resolve_editor_operations(
    editor_operations: list[dict] | None,
    editor_operations_path: str | Path | None,
) -> list[dict]:
    if editor_operations_path is None:
        return editor_operations or []

    operations_path = Path(editor_operations_path).expanduser().resolve()
    payload = json.loads(operations_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("operations"), list):
        return payload["operations"]
    raise ValueError("Editor operations file must be an array or contain an operations array.")


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

    for shape in root.findall(".//p:sp", NS):
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


def _group_editor_operations_by_path(
    operations: list[dict],
    slide_paths: dict[int, str],
) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for operation in operations:
        if operation.get("type") not in PATCHABLE_EDITOR_OPERATION_TYPES:
            continue

        slide_index = _slide_index_from_id(operation.get("slideId"))
        if slide_index is None or slide_index not in slide_paths:
            continue
        grouped[slide_paths[slide_index]].append(operation)
    return grouped


def _slide_index_from_id(slide_id: object) -> int | None:
    if slide_id is None:
        return None

    raw = str(slide_id)
    if raw.startswith("slide_"):
        raw = raw.split("_", 1)[1]
    try:
        return int(raw)
    except ValueError:
        return None


def _apply_editor_operations_to_slide(xml_bytes: bytes, operations: list[dict]) -> bytes:
    root = ET.fromstring(xml_bytes)

    for operation in operations:
        operation_type = operation.get("type")
        if operation_type == "changeBackgroundColor":
            _set_slide_background(root, str(operation.get("color") or "#ffffff"))
            continue

        shape_id = _shape_id_from_object_id(operation.get("objectId"))
        if not shape_id:
            continue

        visual = _find_visual_by_id(root, shape_id)
        if visual is None:
            continue

        if operation_type == "updateText":
            _replace_shape_text(visual, str(operation.get("text") or ""), {}, "")
        elif operation_type == "moveObject":
            _set_visual_position(visual, operation.get("x"), operation.get("y"))
        elif operation_type == "resizeObject":
            _set_visual_size(visual, operation.get("width"), operation.get("height"))
        elif operation_type == "changeFont":
            _set_visual_font(visual, str(operation.get("font") or "Inter"))
        elif operation_type == "changeTextColor":
            _set_visual_text_color(visual, str(operation.get("color") or "#111111"))

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _shape_id_from_object_id(object_id: object) -> str | None:
    if object_id is None:
        return None

    raw = str(object_id)
    if "_" in raw:
        return raw.rsplit("_", 1)[-1]
    return raw


def _find_visual_by_id(root: ET.Element, shape_id: str) -> ET.Element | None:
    for visual in root.findall(".//p:sp", NS) + root.findall(".//p:pic", NS):
        non_visual_props = visual.find(".//p:cNvPr", NS)
        if non_visual_props is not None and non_visual_props.attrib.get("id") == shape_id:
            return visual
    return None


def _set_visual_position(visual: ET.Element, x_inches: object, y_inches: object) -> None:
    transform = _ensure_transform(visual)
    offset = transform.find("a:off", NS)
    if offset is None:
        offset = ET.SubElement(transform, _qn("a", "off"))

    x = _coerce_float(x_inches)
    y = _coerce_float(y_inches)
    if x is not None:
        offset.set("x", str(_inches_to_emu(x)))
    if y is not None:
        offset.set("y", str(_inches_to_emu(y)))


def _set_visual_size(visual: ET.Element, width_inches: object, height_inches: object) -> None:
    transform = _ensure_transform(visual)
    extent = transform.find("a:ext", NS)
    if extent is None:
        extent = ET.SubElement(transform, _qn("a", "ext"))

    width = _coerce_float(width_inches)
    height = _coerce_float(height_inches)
    if width is not None:
        extent.set("cx", str(_inches_to_emu(max(width, 0.01))))
    if height is not None:
        extent.set("cy", str(_inches_to_emu(max(height, 0.01))))


def _ensure_transform(visual: ET.Element) -> ET.Element:
    shape_props = visual.find("p:spPr", NS)
    if shape_props is None:
        shape_props = visual.find("p:picPr", NS)
    if shape_props is None:
        shape_props = ET.SubElement(visual, _qn("p", "spPr"))

    transform = shape_props.find("a:xfrm", NS)
    if transform is None:
        transform = ET.SubElement(shape_props, _qn("a", "xfrm"))
    return transform


def _set_visual_font(visual: ET.Element, font: str) -> None:
    for run_props in _text_run_properties(visual):
        for tag in ("latin", "ea", "cs"):
            font_node = run_props.find(f"a:{tag}", NS)
            if font_node is None:
                font_node = ET.SubElement(run_props, _qn("a", tag))
            font_node.set("typeface", font)


def _set_visual_text_color(visual: ET.Element, color: str) -> None:
    hex_color = _normalize_hex_color(color, "111111")
    for run_props in _text_run_properties(visual):
        solid_fill = run_props.find("a:solidFill", NS)
        if solid_fill is None:
            solid_fill = ET.SubElement(run_props, _qn("a", "solidFill"))
        for child in list(solid_fill):
            solid_fill.remove(child)
        ET.SubElement(solid_fill, _qn("a", "srgbClr"), {"val": hex_color})


def _text_run_properties(visual: ET.Element) -> list[ET.Element]:
    run_props = list(visual.findall(".//a:rPr", NS))
    for run in visual.findall(".//a:r", NS):
        if run.find("a:rPr", NS) is None:
            run_props_node = ET.Element(_qn("a", "rPr"))
            run.insert(0, run_props_node)
            run_props.append(run_props_node)

    run_props.extend(visual.findall(".//a:endParaRPr", NS))
    return run_props


def _set_slide_background(root: ET.Element, color: str) -> None:
    c_sld = root.find("p:cSld", NS)
    if c_sld is None:
        return

    background = c_sld.find("p:bg", NS)
    if background is None:
        background = ET.Element(_qn("p", "bg"))
        c_sld.insert(0, background)

    for child in list(background):
        background.remove(child)

    background_props = ET.SubElement(background, _qn("p", "bgPr"))
    solid_fill = ET.SubElement(background_props, _qn("a", "solidFill"))
    ET.SubElement(solid_fill, _qn("a", "srgbClr"), {"val": _normalize_hex_color(color, "ffffff")})


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _inches_to_emu(value: float) -> int:
    return int(round(value * 914400))


def _normalize_hex_color(value: str, fallback: str) -> str:
    stripped = value.strip().lstrip("#")
    if len(stripped) == 3 and all(char in "0123456789abcdefABCDEF" for char in stripped):
        stripped = "".join(char * 2 for char in stripped)
    if len(stripped) != 6 or not all(char in "0123456789abcdefABCDEF" for char in stripped):
        return fallback
    return stripped.upper()


def _qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


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
