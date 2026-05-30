from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pptx_exporter import PptxExporter, _apply_editor_operations_to_slide  # noqa: E402


class EditorOperationPatchTest(unittest.TestCase):
    def test_applies_text_geometry_color_font_and_background(self) -> None:
        xml = """<?xml version="1.0"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="7" name="Title"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:rPr/><a:t>Old title</a:t></a:r></a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>"""

        patched = _apply_editor_operations_to_slide(
            xml.encode("utf-8"),
            [
                {"type": "updateText", "slideId": "slide_1", "objectId": "text_7", "text": "New title"},
                {"type": "moveObject", "slideId": "slide_1", "objectId": "text_7", "x": 1.25, "y": 2.5},
                {"type": "resizeObject", "slideId": "slide_1", "objectId": "text_7", "width": 3, "height": 1},
                {"type": "changeFont", "slideId": "slide_1", "objectId": "text_7", "font": "Inter"},
                {"type": "changeTextColor", "slideId": "slide_1", "objectId": "text_7", "color": "#ff0000"},
                {"type": "changeBackgroundColor", "slideId": "slide_1", "color": "#f8fafc"},
            ],
        ).decode("utf-8")

        self.assertIn("New title", patched)
        self.assertIn('x="1143000"', patched)
        self.assertIn('y="2286000"', patched)
        self.assertIn('cx="2743200"', patched)
        self.assertIn('typeface="Inter"', patched)
        self.assertIn('val="FF0000"', patched)
        self.assertIn('val="F8FAFC"', patched)

    def test_export_applies_saved_editor_operations_file(self) -> None:
        slide_xml = """<?xml version="1.0"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="7" name="Title"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:rPr/><a:t>Old title</a:t></a:r></a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_pptx = tmp_path / "source.pptx"
            output_pptx = tmp_path / "output.pptx"
            operations_path = tmp_path / "operations.json"

            with ZipFile(source_pptx, "w", ZIP_DEFLATED) as package:
                package.writestr("ppt/slides/slide1.xml", slide_xml)

            operations_path.write_text(
                """
{
  "templateId": "unit-test",
  "operations": [
    {"type": "updateText", "slideId": "slide_1", "objectId": "text_7", "text": "Saved JSON title"},
    {"type": "moveObject", "slideId": "slide_1", "objectId": "text_7", "x": 2, "y": 3}
  ]
}
""",
                encoding="utf-8",
            )

            PptxExporter(source_pptx).export(
                {
                    "slides": [
                        {
                            "index": 1,
                            "path": "ppt/slides/slide1.xml",
                            "shapes": [{"shapeId": "7", "geometry": {}, "text": "Old title"}],
                        }
                    ]
                },
                output_pptx,
                editor_operations_path=operations_path,
            )

            with ZipFile(output_pptx) as package:
                patched = package.read("ppt/slides/slide1.xml").decode("utf-8")

            self.assertIn("Saved JSON title", patched)
            self.assertIn('x="1828800"', patched)
            self.assertIn('y="2743200"', patched)

    def test_export_ignores_animation_metadata_operations_until_supported(self) -> None:
        slide_xml = """<?xml version="1.0"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="7" name="Title"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:rPr/><a:t>Old title</a:t></a:r></a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_pptx = tmp_path / "source.pptx"
            output_pptx = tmp_path / "output.pptx"
            operations_path = tmp_path / "operations.json"

            with ZipFile(source_pptx, "w", ZIP_DEFLATED) as package:
                package.writestr("ppt/slides/slide1.xml", slide_xml)

            operations_path.write_text(
                """
{
  "templateId": "unit-test",
  "animationMetadata": {
    "schemaVersion": 1,
    "pptAnimationExport": false,
    "objects": [
      {"slideId": "slide_1", "objectId": "text_7", "enterAnimation": "fade", "exitAnimation": "zoom"}
    ]
  },
  "operations": [
    {"type": "setEnterAnimation", "slideId": "slide_1", "objectId": "text_7", "animation": "fade"},
    {"type": "setExitAnimation", "slideId": "slide_1", "objectId": "text_7", "animation": "zoom"}
  ]
}
""",
                encoding="utf-8",
            )

            PptxExporter(source_pptx).export(
                {
                    "slides": [
                        {
                            "index": 1,
                            "path": "ppt/slides/slide1.xml",
                            "shapes": [{"shapeId": "7", "geometry": {}, "text": "Old title"}],
                        }
                    ]
                },
                output_pptx,
                editor_operations_path=operations_path,
            )

            with ZipFile(output_pptx) as package:
                patched = package.read("ppt/slides/slide1.xml").decode("utf-8")

            self.assertIn("Old title", patched)
            self.assertNotIn("fade", patched)
            self.assertNotIn("zoom", patched)


if __name__ == "__main__":
    unittest.main()
