from __future__ import annotations

from pathlib import Path
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

EMU_PER_INCH = 914400


class SlideParser:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def parse(self) -> list[dict]:
        with ZipFile(self.pptx_path) as package:
            slide_paths = sorted(
                [
                    name
                    for name in package.namelist()
                    if name.startswith("ppt/slides/slide")
                    and name.endswith(".xml")
                ],
                key=_natural_sort_key,
            )

            return [
                self._parse_slide(package, slide_path, index)
                for index, slide_path in enumerate(slide_paths, start=1)
            ]

    def _parse_slide(self, package: ZipFile, slide_path: str, index: int) -> dict:
        root = ET.fromstring(package.read(slide_path))
        rels = self._parse_slide_relationships(package, slide_path)

        shapes = root.findall(".//p:sp", NS)
        pictures = root.findall(".//p:pic", NS)
        groups = root.findall(".//p:grpSp", NS)

        return {
            "index": index,
            "path": slide_path,
            "relationshipPath": self._relationship_path(slide_path),
            "layoutRelationshipId": self._find_relationship_id(rels, "slideLayout"),
            "counts": {
                "shapes": len(shapes),
                "pictures": len(pictures),
                "groups": len(groups),
                "textBoxes": len([shape for shape in shapes if shape.find(".//p:txBody", NS) is not None]),
            },
            "shapes": self._parse_shapes(shapes),
            "texts": self._parse_texts(shapes),
            "pictures": self._parse_pictures(pictures),
        }

    def _parse_shapes(self, shapes: list[ET.Element]) -> list[dict]:
        return [
            self._parse_shape(shape, z_order)
            for z_order, shape in enumerate(shapes, start=1)
        ]

    def _parse_shape(self, shape: ET.Element, z_order: int) -> dict:
        non_visual_props = shape.find("p:nvSpPr/p:cNvPr", NS)
        placeholder = shape.find(".//p:ph", NS)
        preset_geometry = shape.find("p:spPr/a:prstGeom", NS)
        transform = shape.find("p:spPr/a:xfrm", NS)

        text = "".join(text_el.text or "" for text_el in shape.findall(".//a:t", NS)).strip()

        return {
            "shapeId": non_visual_props.attrib.get("id") if non_visual_props is not None else None,
            "name": non_visual_props.attrib.get("name") if non_visual_props is not None else None,
            "zOrder": z_order,
            "type": preset_geometry.attrib.get("prst") if preset_geometry is not None else None,
            "placeholder": self._parse_placeholder(placeholder),
            "geometry": self._parse_transform(transform),
            "fill": self._parse_fill(shape.find("p:spPr", NS)),
            "line": self._parse_line(shape.find("p:spPr/a:ln", NS)),
            "hasText": bool(text),
            "text": text or None,
        }

    def _parse_placeholder(self, placeholder: ET.Element | None) -> dict | None:
        if placeholder is None:
            return None

        return {
            "type": placeholder.attrib.get("type"),
            "index": placeholder.attrib.get("idx"),
            "size": placeholder.attrib.get("sz"),
        }

    def _parse_transform(self, transform: ET.Element | None) -> dict:
        if transform is None:
            return {}

        offset = transform.find("a:off", NS)
        extent = transform.find("a:ext", NS)
        rotation = transform.attrib.get("rot")

        x = self._int_attr(offset, "x")
        y = self._int_attr(offset, "y")
        width = self._int_attr(extent, "cx")
        height = self._int_attr(extent, "cy")

        return {
            "xEmu": x,
            "yEmu": y,
            "widthEmu": width,
            "heightEmu": height,
            "xInches": self._emu_to_inches(x),
            "yInches": self._emu_to_inches(y),
            "widthInches": self._emu_to_inches(width),
            "heightInches": self._emu_to_inches(height),
            "rotationDegrees": round(int(rotation) / 60000, 4) if rotation is not None else 0,
        }

    def _parse_fill(self, shape_props: ET.Element | None) -> dict:
        if shape_props is None:
            return {}

        no_fill = shape_props.find("a:noFill", NS)
        solid_fill = shape_props.find("a:solidFill", NS)
        grad_fill = shape_props.find("a:gradFill", NS)
        blip_fill = shape_props.find("a:blipFill", NS)

        if no_fill is not None:
            return {"type": "none"}
        if solid_fill is not None:
            return {"type": "solid", "color": self._parse_color(solid_fill)}
        if grad_fill is not None:
            return {"type": "gradient"}
        if blip_fill is not None:
            return {"type": "image"}
        return {}

    def _parse_line(self, line: ET.Element | None) -> dict:
        if line is None:
            return {}

        no_fill = line.find("a:noFill", NS)
        solid_fill = line.find("a:solidFill", NS)

        return {
            "widthEmu": self._int_attr(line, "w"),
            "widthPt": round(self._int_attr(line, "w") / 12700, 4)
            if self._int_attr(line, "w") is not None
            else None,
            "fill": {"type": "none"} if no_fill is not None else None,
            "color": self._parse_color(solid_fill) if solid_fill is not None else {},
        }

    def _parse_color(self, parent: ET.Element | None) -> dict:
        if parent is None:
            return {}

        srgb = parent.find("a:srgbClr", NS)
        scheme = parent.find("a:schemeClr", NS)
        prst = parent.find("a:prstClr", NS)

        if srgb is not None:
            return {"type": "srgb", "hex": f"#{srgb.attrib.get('val')}"}
        if scheme is not None:
            return {"type": "scheme", "value": scheme.attrib.get("val")}
        if prst is not None:
            return {"type": "preset", "value": prst.attrib.get("val")}
        return {}

    def _parse_texts(self, shapes: list[ET.Element]) -> list[dict]:
        texts = []
        for shape in shapes:
            paragraphs = self._parse_paragraphs(shape)
            full_text = "\n".join(
                paragraph["text"]
                for paragraph in paragraphs
                if paragraph["text"]
            ).strip()
            if not full_text:
                continue

            non_visual_props = shape.find("p:nvSpPr/p:cNvPr", NS)
            placeholder = shape.find(".//p:ph", NS)

            texts.append(
                {
                    "shapeId": non_visual_props.attrib.get("id") if non_visual_props is not None else None,
                    "name": non_visual_props.attrib.get("name") if non_visual_props is not None else None,
                    "placeholderType": placeholder.attrib.get("type") if placeholder is not None else None,
                    "text": full_text,
                    "paragraphs": paragraphs,
                }
            )

        return texts

    def _parse_paragraphs(self, shape: ET.Element) -> list[dict]:
        paragraphs = []
        for paragraph in shape.findall(".//a:p", NS):
            runs = self._parse_runs(paragraph)
            paragraph_text = "".join(run["text"] for run in runs)
            paragraph_props = paragraph.find("a:pPr", NS)

            paragraphs.append(
                {
                    "text": paragraph_text,
                    "alignment": paragraph_props.attrib.get("algn") if paragraph_props is not None else None,
                    "level": int(paragraph_props.attrib["lvl"]) if paragraph_props is not None and "lvl" in paragraph_props.attrib else None,
                    "bullet": self._parse_bullet(paragraph_props),
                    "runs": runs,
                }
            )

        return paragraphs

    def _parse_runs(self, paragraph: ET.Element) -> list[dict]:
        runs = []
        for run in paragraph.findall("a:r", NS):
            text_el = run.find("a:t", NS)
            run_props = run.find("a:rPr", NS)

            runs.append(
                {
                    "text": text_el.text if text_el is not None and text_el.text is not None else "",
                    "font": self._parse_run_font(run_props),
                    "fontSize": int(run_props.attrib["sz"]) / 100
                    if run_props is not None and "sz" in run_props.attrib
                    else None,
                    "bold": self._bool_attr(run_props.attrib.get("b")) if run_props is not None else None,
                    "italic": self._bool_attr(run_props.attrib.get("i")) if run_props is not None else None,
                    "underline": run_props.attrib.get("u") if run_props is not None else None,
                    "color": self._parse_color(run_props),
                }
            )

        return runs

    def _parse_run_font(self, run_props: ET.Element | None) -> dict:
        if run_props is None:
            return {}

        latin = run_props.find("a:latin", NS)
        east_asian = run_props.find("a:ea", NS)
        complex_script = run_props.find("a:cs", NS)

        return {
            "latin": latin.attrib.get("typeface") if latin is not None else None,
            "eastAsian": east_asian.attrib.get("typeface") if east_asian is not None else None,
            "complexScript": complex_script.attrib.get("typeface") if complex_script is not None else None,
        }

    def _parse_bullet(self, paragraph_props: ET.Element | None) -> dict:
        if paragraph_props is None:
            return {}

        if paragraph_props.find("a:buNone", NS) is not None:
            return {"type": "none"}

        char_bullet = paragraph_props.find("a:buChar", NS)
        auto_number = paragraph_props.find("a:buAutoNum", NS)

        if char_bullet is not None:
            return {"type": "character", "character": char_bullet.attrib.get("char")}
        if auto_number is not None:
            return {"type": "autoNumber", "scheme": auto_number.attrib.get("type")}

        return {}

    def _parse_pictures(self, pictures: list[ET.Element]) -> list[dict]:
        parsed = []
        for picture in pictures:
            non_visual_props = picture.find("p:nvPicPr/p:cNvPr", NS)
            blip = picture.find(".//a:blip", NS)

            parsed.append(
                {
                    "shapeId": non_visual_props.attrib.get("id") if non_visual_props is not None else None,
                    "name": non_visual_props.attrib.get("name") if non_visual_props is not None else None,
                    "relationshipId": blip.attrib.get(f"{{{NS['r']}}}embed") if blip is not None else None,
                }
            )

        return parsed

    def _parse_slide_relationships(self, package: ZipFile, slide_path: str) -> list[dict]:
        rel_path = self._relationship_path(slide_path)
        if rel_path not in package.namelist():
            return []

        root = ET.fromstring(package.read(rel_path))
        rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}

        return [
            {
                "id": rel.attrib.get("Id"),
                "type": rel.attrib.get("Type"),
                "target": rel.attrib.get("Target"),
            }
            for rel in root.findall("rel:Relationship", rel_ns)
        ]

    @staticmethod
    def _find_relationship_id(relationships: list[dict], type_suffix: str) -> str | None:
        for relationship in relationships:
            rel_type = relationship.get("type") or ""
            if rel_type.endswith(f"/{type_suffix}"):
                return relationship.get("id")
        return None

    @staticmethod
    def _relationship_path(slide_path: str) -> str:
        filename = slide_path.rsplit("/", 1)[-1]
        return f"ppt/slides/_rels/{filename}.rels"

    @staticmethod
    def _int_attr(element: ET.Element | None, attr: str) -> int | None:
        if element is None or attr not in element.attrib:
            return None
        return int(element.attrib[attr])

    @staticmethod
    def _emu_to_inches(value: int | None) -> float | None:
        return round(value / EMU_PER_INCH, 4) if value is not None else None

    @staticmethod
    def _bool_attr(value: str | None) -> bool | None:
        if value is None:
            return None
        return value in {"1", "true"}


def _natural_sort_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", value)
    ]
