from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pptx_exporter import NS, _replace_slide_text  # noqa: E402


SLIDE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="10" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr/>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="4400"/><a:t>Old title</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="11" name="Cleanup"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr/>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="2400"/><a:t>Remove me</a:t></a:r></a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""


class PptxExporterTests(unittest.TestCase):
    def test_replace_slide_text_can_add_staggered_text_animations(self) -> None:
        xml = _replace_slide_text(
            SLIDE_XML,
            {
                "10": {"newText": "New title", "geometry": {}, "originalText": "Old title"},
                "11": {"newText": "", "geometry": {}, "originalText": "Remove me"},
            },
            animate_text=True,
        )

        root = ET.fromstring(xml)
        timing = root.find("p:timing", NS)
        self.assertIsNotNone(timing)

        targets = [node.attrib["spid"] for node in root.findall(".//p:spTgt", NS)]
        self.assertEqual(targets, ["10", "10", "10", "10"])

        effect = root.find(".//p:cTn[@presetClass='entr']", NS)
        self.assertIsNotNone(effect)
        self.assertEqual(effect.attrib["nodeType"], "withEffect")
        self.assertIsNotNone(root.find(".//p:cond[@evt='onBegin']", NS))

    def test_replace_slide_text_leaves_timing_out_when_animation_disabled(self) -> None:
        xml = _replace_slide_text(
            SLIDE_XML,
            {"10": {"newText": "New title", "geometry": {}, "originalText": "Old title"}},
            animate_text=False,
        )

        root = ET.fromstring(xml)
        self.assertIsNone(root.find("p:timing", NS))


if __name__ == "__main__":
    unittest.main()
