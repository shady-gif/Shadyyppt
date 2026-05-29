from __future__ import annotations

from pathlib import Path
import re
from zipfile import ZipFile


class PptxPackageReader:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def inventory(self) -> dict:
        if not self.pptx_path.exists():
            raise FileNotFoundError(f"PPTX file not found: {self.pptx_path}")

        with ZipFile(self.pptx_path) as package:
            names = package.namelist()

        slides = self._matching_parts(names, "ppt/slides/slide", ".xml")
        slide_layouts = self._matching_parts(names, "ppt/slideLayouts/slideLayout", ".xml")
        slide_masters = self._matching_parts(names, "ppt/slideMasters/slideMaster", ".xml")
        themes = self._matching_parts(names, "ppt/theme/theme", ".xml")
        media = [name for name in names if name.startswith("ppt/media/") and not name.endswith("/")]
        fonts = [name for name in names if name.startswith("ppt/fonts/") and not name.endswith("/")]
        relationships = [name for name in names if name.endswith(".rels")]

        return {
            "sourceFile": str(self.pptx_path),
            "counts": {
                "slides": len(slides),
                "layouts": len(slide_layouts),
                "masters": len(slide_masters),
                "themes": len(themes),
                "media": len(media),
                "fonts": len(fonts),
                "relationships": len(relationships),
            },
            "parts": {
                "slides": slides,
                "layouts": slide_layouts,
                "masters": slide_masters,
                "themes": themes,
                "media": media,
                "fonts": fonts,
                "relationships": relationships,
            },
        }

    @staticmethod
    def _matching_parts(names: list[str], prefix: str, suffix: str) -> list[str]:
        return sorted(
            [name for name in names if name.startswith(prefix) and name.endswith(suffix)],
            key=_natural_sort_key,
        )


def _natural_sort_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", value)
    ]
