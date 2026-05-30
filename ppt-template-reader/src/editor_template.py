from __future__ import annotations

import mimetypes
from pathlib import Path
import posixpath
from urllib.parse import quote
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}

FONT_OPTIONS = {"Inter", "Poppins", "Montserrat", "Roboto", "Playfair Display"}
BASIC_SHAPES = {
    "rect",
    "roundRect",
    "ellipse",
    "triangle",
    "diamond",
    "parallelogram",
    "trapezoid",
    "pentagon",
    "hexagon",
    "octagon",
    "line",
    "arc",
}
EMU_PER_INCH = 914400


def build_editor_deck(
    template_id: str,
    template_config: dict,
    template: dict,
    source_json_path: str | None = None,
) -> dict:
    size = template.get("presentation", {}).get("size", {})
    width = float(size.get("widthInches") or 20)
    height = float(size.get("heightInches") or 11.25)

    slides = []
    for slide in template.get("slides", []):
        slide_index = int(slide.get("index") or len(slides) + 1)
        text_lookup = _text_lookup(slide)
        objects = _shape_objects(slide, text_lookup)
        objects.extend(_image_fill_shape_objects(template_id, template_config["pptxPath"], slide))
        objects.extend(_picture_objects(template_id, template_config["pptxPath"], slide))
        objects.sort(key=lambda item: item["zIndex"])

        slides.append(
            {
                "id": f"slide_{slide_index}",
                "index": slide_index,
                "sourceSlideIndex": slide_index,
                "background": "#ffffff",
                "objects": objects,
            }
        )

    return {
        "templateId": template_id,
        "templateName": template_config["name"],
        "sourceJsonPath": source_json_path,
        "sourceKind": "generated" if source_json_path else "template",
        "size": {
            "widthInches": width,
            "heightInches": height,
        },
        "slides": slides,
    }


def read_template_asset(pptx_path: Path, asset_path: str) -> tuple[bytes, str]:
    safe_asset_path = posixpath.normpath(asset_path).lstrip("/")
    if not safe_asset_path.startswith("ppt/media/"):
        raise ValueError("Only template media assets can be served.")

    with ZipFile(pptx_path) as package:
        if safe_asset_path not in package.namelist():
            raise FileNotFoundError(f"Template asset not found: {safe_asset_path}")
        data = package.read(safe_asset_path)

    content_type, _ = mimetypes.guess_type(safe_asset_path)
    return data, content_type or "application/octet-stream"


def _shape_objects(slide: dict, text_lookup: dict[str, dict]) -> list[dict]:
    objects = []
    for shape in slide.get("shapes", []):
        shape_id = shape.get("shapeId")
        geometry = shape.get("geometry") or {}
        if not shape_id or not _has_geometry(geometry):
            continue

        source_id = str(shape_id)
        base = {
            "sourceId": source_id,
            "name": shape.get("name") or f"Shape {source_id}",
            "x": _number(geometry.get("xInches")),
            "y": _number(geometry.get("yInches")),
            "width": _number(geometry.get("widthInches"), 1),
            "height": _number(geometry.get("heightInches"), 1),
            "rotation": _number(geometry.get("rotationDegrees")),
            "zIndex": int(shape.get("zOrder") or 0),
            "enterAnimation": "none",
            "exitAnimation": "none",
        }

        if shape.get("hasText") or source_id in text_lookup:
            text = text_lookup.get(source_id) or {}
            style = _text_style(text)
            objects.append(
                {
                    **base,
                    "id": f"text_{source_id}",
                    "type": "text",
                    "text": text.get("text") or shape.get("text") or "",
                    "font": style["font"],
                    "color": style["color"],
                    "fontSize": style["fontSize"],
                }
            )
            continue

        if _is_basic_shape(shape):
            objects.append(
                {
                    **base,
                    "id": f"shape_{source_id}",
                    "type": "shape",
                    "geometryType": shape.get("type") or "rect",
                    "fillColor": _shape_fill_color(shape),
                    "lineColor": _shape_line_color(shape),
                }
            )

    return objects


def _image_fill_shape_objects(template_id: str, pptx_path: Path, slide: dict) -> list[dict]:
    slide_path = slide.get("path")
    if not slide_path:
        return []

    try:
        with ZipFile(pptx_path) as package:
            if slide_path not in package.namelist():
                return []
            root = ET.fromstring(package.read(slide_path))
            relationships = _relationships_for_slide(package, slide_path)
    except Exception:
        return []

    z_lookup = {
        str(shape.get("shapeId")): int(shape.get("zOrder") or 0)
        for shape in slide.get("shapes", [])
        if shape.get("shapeId") is not None
    }

    objects = []
    for shape in root.findall(".//p:sp", NS):
        non_visual_props = shape.find("p:nvSpPr/p:cNvPr", NS)
        shape_id = non_visual_props.attrib.get("id") if non_visual_props is not None else None
        geometry = _parse_transform(shape.find("p:spPr/a:xfrm", NS))
        if not shape_id or not _has_geometry(geometry):
            continue

        embed = shape.find(".//a:blip", NS)
        relationship_id = embed.attrib.get(f"{{{NS['r']}}}embed") if embed is not None else None
        asset_path = relationships.get(relationship_id)
        if not asset_path:
            continue

        objects.append(
            {
                "id": f"image_{shape_id}",
                "sourceId": str(shape_id),
                "name": non_visual_props.attrib.get("name") if non_visual_props is not None else f"Image {shape_id}",
                "type": "image",
                "x": _number(geometry.get("xInches")),
                "y": _number(geometry.get("yInches")),
                "width": _number(geometry.get("widthInches"), 1),
                "height": _number(geometry.get("heightInches"), 1),
                "rotation": _number(geometry.get("rotationDegrees")),
                "zIndex": z_lookup.get(str(shape_id), 0),
                "enterAnimation": "none",
                "exitAnimation": "none",
                "assetPath": asset_path,
                "imageUrl": f"api/template-asset?templateId={quote(template_id)}&assetPath={quote(asset_path)}",
            }
        )

    return objects


def _picture_objects(template_id: str, pptx_path: Path, slide: dict) -> list[dict]:
    slide_path = slide.get("path")
    if not slide_path:
        return []

    try:
        with ZipFile(pptx_path) as package:
            if slide_path not in package.namelist():
                return []
            root = ET.fromstring(package.read(slide_path))
            relationships = _relationships_for_slide(package, slide_path)
            pictures = root.findall(".//p:pic", NS)
    except Exception:
        return []

    objects = []
    z_start = len(slide.get("shapes", [])) + 1
    for offset, picture in enumerate(pictures):
        non_visual_props = picture.find("p:nvPicPr/p:cNvPr", NS)
        shape_id = non_visual_props.attrib.get("id") if non_visual_props is not None else None
        geometry = _parse_transform(picture.find("p:spPr/a:xfrm", NS))
        if not shape_id or not _has_geometry(geometry):
            continue

        embed = picture.find(".//a:blip", NS)
        relationship_id = embed.attrib.get(f"{{{NS['r']}}}embed") if embed is not None else None
        asset_path = relationships.get(relationship_id)
        image_url = (
            f"api/template-asset?templateId={quote(template_id)}&assetPath={quote(asset_path)}"
            if asset_path
            else None
        )

        objects.append(
            {
                "id": f"image_{shape_id}",
                "sourceId": str(shape_id),
                "name": non_visual_props.attrib.get("name") if non_visual_props is not None else f"Image {shape_id}",
                "type": "image",
                "x": _number(geometry.get("xInches")),
                "y": _number(geometry.get("yInches")),
                "width": _number(geometry.get("widthInches"), 1),
                "height": _number(geometry.get("heightInches"), 1),
                "rotation": _number(geometry.get("rotationDegrees")),
                "zIndex": z_start + offset,
                "enterAnimation": "none",
                "exitAnimation": "none",
                "assetPath": asset_path,
                "imageUrl": image_url,
            }
        )

    return objects


def _relationships_for_slide(package: ZipFile, slide_path: str) -> dict[str | None, str]:
    rel_path = _relationship_path(slide_path)
    if rel_path not in package.namelist():
        return {}

    rels_root = ET.fromstring(package.read(rel_path))
    lookup = {}
    for rel in rels_root.findall("rel:Relationship", REL_NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        rel_type = rel.attrib.get("Type") or ""
        if not rel_id or not target or not rel_type.endswith("/image"):
            continue
        lookup[rel_id] = posixpath.normpath(posixpath.join(posixpath.dirname(slide_path), target))
    return lookup


def _relationship_path(slide_path: str) -> str:
    filename = slide_path.rsplit("/", 1)[-1]
    return f"ppt/slides/_rels/{filename}.rels"


def _parse_transform(transform: ET.Element | None) -> dict:
    if transform is None:
        return {}

    offset = transform.find("a:off", NS)
    extent = transform.find("a:ext", NS)
    rotation = transform.attrib.get("rot")

    x = _int_attr(offset, "x")
    y = _int_attr(offset, "y")
    width = _int_attr(extent, "cx")
    height = _int_attr(extent, "cy")

    return {
        "xInches": _emu_to_inches(x),
        "yInches": _emu_to_inches(y),
        "widthInches": _emu_to_inches(width),
        "heightInches": _emu_to_inches(height),
        "rotationDegrees": round(int(rotation) / 60000, 4) if rotation is not None else 0,
    }


def _text_lookup(slide: dict) -> dict[str, dict]:
    return {
        str(text["shapeId"]): text
        for text in slide.get("texts", [])
        if text.get("shapeId") is not None
    }


def _text_style(text: dict) -> dict:
    first_run = None
    for paragraph in text.get("paragraphs", []):
        for run in paragraph.get("runs", []):
            if run.get("text"):
                first_run = run
                break
        if first_run:
            break

    first_run = first_run or {}
    raw_font = (
        (first_run.get("font") or {}).get("latin")
        or ((first_run.get("resolved") or {}).get("font") or {}).get("latin")
        or "Inter"
    )
    font = raw_font if raw_font in FONT_OPTIONS else "Inter"

    return {
        "font": font,
        "color": _hex_color(first_run.get("color")) or _hex_color((first_run.get("resolved") or {}).get("color")) or "#111111",
        "fontSize": _number(first_run.get("fontSize"), 24),
    }


def _is_basic_shape(shape: dict) -> bool:
    fill = shape.get("fill") or {}
    line = shape.get("line") or {}
    if fill.get("type") == "solid":
        return True
    if _hex_color(line.get("color")) or line.get("widthEmu"):
        return True
    return False


def _shape_fill_color(shape: dict) -> str:
    return (
        _hex_color((shape.get("fill") or {}).get("color"))
        or _hex_color((shape.get("resolved") or {}).get("fillColor"))
        or "#eef0f4"
    )


def _shape_line_color(shape: dict) -> str:
    return (
        _hex_color((shape.get("line") or {}).get("color"))
        or _hex_color((shape.get("resolved") or {}).get("lineColor"))
        or "#9aa3b2"
    )


def _hex_color(value: object) -> str | None:
    if isinstance(value, str) and value.startswith("#") and len(value) in {4, 7}:
        return value
    if isinstance(value, dict):
        raw = value.get("hex")
        if isinstance(raw, str) and raw.startswith("#"):
            return raw
    return None


def _has_geometry(geometry: dict) -> bool:
    return bool(geometry.get("widthInches") and geometry.get("heightInches"))


def _number(value: object, fallback: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int_attr(element: ET.Element | None, attr: str) -> int | None:
    if element is None or attr not in element.attrib:
        return None
    return int(element.attrib[attr])


def _emu_to_inches(value: int | None) -> float | None:
    return round(value / EMU_PER_INCH, 4) if value is not None else None
