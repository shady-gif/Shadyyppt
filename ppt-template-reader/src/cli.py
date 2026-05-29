from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract inventory from a PPTX file.")
    parser.add_argument("pptx", help="Path to the PPTX file")
    parser.add_argument(
        "--out",
        default="outputs/template-1.json",
        help="Path where the JSON output should be written",
    )
    args = parser.parse_args()

    output_path = Path(args.out).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    theme = ThemeParser(args.pptx).parse()
    output = {
        "inventory": PptxPackageReader(args.pptx).inventory(),
        "presentation": PresentationParser(args.pptx).parse(),
        "relationships": RelationshipsParser(args.pptx).parse(),
        "theme": theme,
        "masters": MasterParser(args.pptx).parse(),
        "layouts": LayoutParser(args.pptx).parse(),
        "slides": SlideParser(args.pptx).parse(),
        "assets": MediaExtractor(args.pptx).extract(),
    }

    output = StyleResolver(theme).resolve(output)
    output["validation"] = OutputValidator(output).summary()

    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "jsonOutput": str(output_path),
                "validation": output["validation"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
