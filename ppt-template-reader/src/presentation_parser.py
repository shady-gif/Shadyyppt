from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


EMU_PER_INCH = 914400


class PresentationParser:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def parse(self) -> dict:
        with ZipFile(self.pptx_path) as package:
            xml_bytes = package.read("ppt/presentation.xml")

        root = ET.fromstring(xml_bytes)

        size_el = root.find("p:sldSz", NS)
        width_emu = int(size_el.attrib["cx"]) if size_el is not None else None
        height_emu = int(size_el.attrib["cy"]) if size_el is not None else None

        slides = []
        for index, slide_el in enumerate(root.findall(".//p:sldId", NS), start=1):
            slides.append(
                {
                    "index": index,
                    "slideId": slide_el.attrib.get("id"),
                    "relationshipId": slide_el.attrib.get(f"{{{NS['r']}}}id"),
                }
            )

        return {
            "size": {
                "widthEmu": width_emu,
                "heightEmu": height_emu,
                "widthInches": round(width_emu / EMU_PER_INCH, 4) if width_emu else None,
                "heightInches": round(height_emu / EMU_PER_INCH, 4) if height_emu else None,
            },
            "slides": slides,
        }