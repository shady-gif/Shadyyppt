from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class MasterParser:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def parse(self) -> list[dict]:
        with ZipFile(self.pptx_path) as package:
            master_paths = sorted(
                name
                for name in package.namelist()
                if name.startswith("ppt/slideMasters/slideMaster")
                and name.endswith(".xml")
            )

            return [
                self._parse_master(package.read(master_path), master_path)
                for master_path in master_paths
            ]

    def _parse_master(self, xml_bytes: bytes, master_path: str) -> dict:
        root = ET.fromstring(xml_bytes)
        shapes = root.findall(".//p:cSld/p:spTree/p:sp", NS)
        placeholders = [
            self._parse_placeholder(shape)
            for shape in shapes
            if shape.find(".//p:ph", NS) is not None
        ]

        return {
            "path": master_path,
            "shapeCount": len(shapes),
            "placeholderCount": len(placeholders),
            "placeholders": placeholders,
            "layoutReferences": self._parse_layout_references(root),
            "textStyles": {
                "title": self._parse_text_style(root.find("p:txStyles/p:titleStyle", NS)),
                "body": self._parse_text_style(root.find("p:txStyles/p:bodyStyle", NS)),
                "other": self._parse_text_style(root.find("p:txStyles/p:otherStyle", NS)),
            },
        }

    def _parse_layout_references(self, root: ET.Element) -> list[dict]:
        refs = []
        for layout_id in root.findall("p:sldLayoutIdLst/p:sldLayoutId", NS):
            refs.append(
                {
                    "id": layout_id.attrib.get("id"),
                    "relationshipId": layout_id.attrib.get(f"{{{NS['r']}}}id"),
                }
            )
        return refs

    def _parse_placeholder(self, shape: ET.Element) -> dict:
        non_visual_props = shape.find("p:nvSpPr/p:cNvPr", NS)
        placeholder = shape.find(".//p:ph", NS)

        return {
            "shapeId": non_visual_props.attrib.get("id") if non_visual_props is not None else None,
            "name": non_visual_props.attrib.get("name") if non_visual_props is not None else None,
            "type": placeholder.attrib.get("type") if placeholder is not None else None,
            "index": placeholder.attrib.get("idx") if placeholder is not None else None,
            "size": placeholder.attrib.get("sz") if placeholder is not None else None,
        }

    def _parse_text_style(self, style_el: ET.Element | None) -> dict:
        if style_el is None:
            return {}

        levels = {}
        for child in list(style_el):
            name = self._local_name(child.tag)
            if not name.startswith("lvl") or not name.endswith("pPr"):
                continue

            default_run = child.find("a:defRPr", NS)
            levels[name] = {
                "alignment": child.attrib.get("algn"),
                "fontSize": int(default_run.attrib["sz"]) / 100
                if default_run is not None and "sz" in default_run.attrib
                else None,
                "bold": self._bool_attr(default_run.attrib.get("b"))
                if default_run is not None
                else None,
                "font": self._parse_font(default_run),
                "color": self._parse_color(default_run),
            }

        return levels

    def _parse_font(self, run_props: ET.Element | None) -> dict:
        if run_props is None:
            return {}

        latin = run_props.find("a:latin", NS)
        return {
            "latin": latin.attrib.get("typeface") if latin is not None else None,
        }

    def _parse_color(self, run_props: ET.Element | None) -> dict:
        if run_props is None:
            return {}

        srgb = run_props.find(".//a:srgbClr", NS)
        scheme = run_props.find(".//a:schemeClr", NS)

        if srgb is not None:
            return {"type": "srgb", "hex": f"#{srgb.attrib.get('val')}"}
        if scheme is not None:
            return {"type": "scheme", "value": scheme.attrib.get("val")}
        return {}

    @staticmethod
    def _bool_attr(value: str | None) -> bool | None:
        if value is None:
            return None
        return value in {"1", "true"}

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
