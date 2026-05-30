from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from content_generator import _build_cleanup_updates, _expand_curated_for_template  # noqa: E402


BASE_CURATED = {
    "deckTitle": "Elon Musk",
    "subtitle": "technology profile",
    "byline": "",
    "year": "2026",
    "unusedFacts": [
        "SpaceX advanced reusable rockets and commercial spaceflight.",
        "Tesla became a leader in electric vehicles under Musk.",
        "Musk acquired Twitter in 2022 and rebranded it as X in 2023.",
        "His political activity and public statements made him polarizing.",
    ],
    "slides": {
        "1": {"title": "Elon Musk", "subtitle": "technology profile"},
        "2": {"section": "Overview", "body": "Musk leads Tesla and SpaceX."},
    },
}


class ContentGeneratorTests(unittest.TestCase):
    def test_expand_curated_adds_every_template_field(self) -> None:
        expanded = _expand_curated_for_template(
            BASE_CURATED,
            {
                "6": {
                    "fields": {
                        "section": "28",
                        "headline": "29",
                        "heading1": "16",
                        "heading2": "30",
                    }
                }
            },
            {
                "name": "Technology Brief",
                "subtitle": "technology profile",
                "sections": ["Overview", "Context", "Themes", "Evidence", "Milestones"],
                "closing": "Takeaways",
            },
        )

        self.assertEqual(
            sorted(expanded["slides"]["6"].keys()),
            ["heading1", "heading2", "headline", "section"],
        )
        self.assertEqual(expanded["slides"]["6"]["section"], "Milestones")
        self.assertTrue(expanded["slides"]["6"]["heading1"])

    def test_cleanup_removes_profile_template_leftovers(self) -> None:
        updates = _build_cleanup_updates(
            {
                "slides": [
                    {
                        "index": 6,
                        "texts": [
                            {"shapeId": "16", "text": "Adeline Palmerston"},
                            {"shapeId": "28", "text": "OUR"},
                            {"shapeId": "29", "text": "TEAM"},
                            {"shapeId": "30", "text": "Avery Davis"},
                        ],
                    },
                    {
                        "index": 10,
                        "texts": [
                            {"shapeId": "18", "text": "Let's Build Something Great Together"},
                            {"shapeId": "19", "text": "123-456-7890"},
                        ],
                    },
                ]
            },
            BASE_CURATED,
            set(),
        )

        replacements = {update["shapeId"]: update["newText"] for update in updates}

        self.assertEqual(replacements["28"], "")
        self.assertEqual(replacements["18"], "")
        self.assertEqual(replacements["19"], "")
        self.assertNotIn("Adeline", replacements["16"])
        self.assertNotIn("Avery", replacements["30"])
        self.assertNotEqual(replacements["29"], "TEAM")


if __name__ == "__main__":
    unittest.main()
