from __future__ import annotations

import json
from pathlib import Path

from package_reader import PptxPackageReader
from presentation_parser import PresentationParser
from relationships_parser import RelationshipsParser
from theme_parser import ThemeParser
from master_parser import MasterParser
from layout_parser import LayoutParser
from slide_parser import SlideParser
from media_extractor import MediaExtractor
from style_resolver import StyleResolver
from validator import OutputValidator


def convert_pptx_to_json(pptx_path: str | Path, output_path: str | Path) -> dict:
    pptx_path = Path(pptx_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    theme = ThemeParser(pptx_path).parse()
    output = {
        "inventory": PptxPackageReader(pptx_path).inventory(),
        "presentation": PresentationParser(pptx_path).parse(),
        "relationships": RelationshipsParser(pptx_path).parse(),
        "theme": theme,
        "masters": MasterParser(pptx_path).parse(),
        "layouts": LayoutParser(pptx_path).parse(),
        "slides": SlideParser(pptx_path).parse(),
        "assets": MediaExtractor(pptx_path).extract(),
    }

    output = StyleResolver(theme).resolve(output)
    output["validation"] = OutputValidator(output).summary()
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output
