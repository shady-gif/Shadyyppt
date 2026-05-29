from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


class ThemeParser:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def parse(self) -> dict:
        with ZipFile(self.pptx_path) as package:
            xml_bytes = package.read("ppt/theme/theme1.xml")

        root = ET.fromstring(xml_bytes)
        theme_elements = root.find("a:themeElements", NS)

        return {
            "name": root.attrib.get("name"),
            "colors": self._parse_colors(theme_elements),
            "fonts": self._parse_fonts(theme_elements),
        }

    def _parse_colors(self, theme_elements: ET.Element | None) -> dict:
        if theme_elements is None:
            return {}

        color_scheme = theme_elements.find("a:clrScheme", NS)
        if color_scheme is None:
            return {}

        colors = {}
        for color_el in list(color_scheme):
            color_name = self._local_name(color_el.tag)
            srgb = color_el.find("a:srgbClr", NS)
            system = color_el.find("a:sysClr", NS)

            if srgb is not None:
                colors[color_name] = {
                    "type": "srgb",
                    "hex": f"#{srgb.attrib.get('val')}",
                }
            elif system is not None:
                colors[color_name] = {
                    "type": "system",
                    "systemColor": system.attrib.get("val"),
                    "lastColor": f"#{system.attrib.get('lastClr')}",
                }

        return colors

    def _parse_fonts(self, theme_elements: ET.Element | None) -> dict:
        if theme_elements is None:
            return {}

        font_scheme = theme_elements.find("a:fontScheme", NS)
        if font_scheme is None:
            return {}

        return {
            "schemeName": font_scheme.attrib.get("name"),
            "major": self._parse_font_group(font_scheme.find("a:majorFont", NS)),
            "minor": self._parse_font_group(font_scheme.find("a:minorFont", NS)),
        }

    def _parse_font_group(self, font_group: ET.Element | None) -> dict:
        if font_group is None:
            return {}

        latin = font_group.find("a:latin", NS)
        east_asian = font_group.find("a:ea", NS)
        complex_script = font_group.find("a:cs", NS)

        return {
            "latin": latin.attrib.get("typeface") if latin is not None else None,
            "eastAsian": east_asian.attrib.get("typeface") if east_asian is not None else None,
            "complexScript": complex_script.attrib.get("typeface") if complex_script is not None else None,
        }

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
