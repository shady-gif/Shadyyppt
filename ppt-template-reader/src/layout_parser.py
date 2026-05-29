from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


class LayoutParser:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def parse(self) -> list[dict]:
        with ZipFile(self.pptx_path) as package:
            layout_paths = sorted(
                name
                for name in package.namelist()
                if name.startswith("ppt/slideLayouts/slideLayout")
                and name.endswith(".xml")
            )

            return [
                self._parse_layout(package.read(layout_path), layout_path)
                for layout_path in layout_paths
            ]

    def _parse_layout(self, xml_bytes: bytes, layout_path: str) -> dict:
        root = ET.fromstring(xml_bytes)
        common_slide = root.find("p:cSld", NS)
        shapes = root.findall(".//p:cSld/p:spTree/p:sp", NS)

        placeholders = []
        for shape in shapes:
            placeholder = shape.find(".//p:ph", NS)
            if placeholder is None:
                continue

            non_visual_props = shape.find("p:nvSpPr/p:cNvPr", NS)

            placeholders.append(
                {
                    "shapeId": non_visual_props.attrib.get("id") if non_visual_props is not None else None,
                    "name": non_visual_props.attrib.get("name") if non_visual_props is not None else None,
                    "type": placeholder.attrib.get("type"),
                    "index": placeholder.attrib.get("idx"),
                    "size": placeholder.attrib.get("sz"),
                }
            )

        return {
            "path": layout_path,
            "name": common_slide.attrib.get("name") if common_slide is not None else None,
            "type": root.attrib.get("type"),
            "preserve": root.attrib.get("preserve"),
            "shapeCount": len(shapes),
            "placeholderCount": len(placeholders),
            "placeholders": placeholders,
        }