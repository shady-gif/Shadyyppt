from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import json

from content_generator import ContentGenerator, _build_cleanup_updates, _expand_curated_for_template  # noqa: E402


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

    def test_structured_slide_outline_preserves_slide_specific_content(self) -> None:
        template = json.loads((ROOT / "outputs" / "profile.json").read_text(encoding="utf-8"))
        result = ContentGenerator(template, template_id="profile").generate(
            """
            Slide 1: Title Slide
            Elon Musk: Entrepreneur, Innovator & Business Leader
            * Founder, CEO, Investor, and Technologist

            Slide 2: Early Life & Background
            Early Life
            * Born: June 28, 1971
            * Birthplace: Pretoria, South Africa

            Slide 3: Education & Early Interests
            Education and Passion for Technology
            * Developed interest in computers at age 10
            * Created and sold the video game Blastar at age 12

            Slide 4: First Business Ventures
            Zip2 and PayPal
            * Co-founded Zip2 in 1995
            * PayPal acquired by eBay in 2002

            Slide 5: SpaceX Revolution
            SpaceX and Space Exploration
            * Founded SpaceX in 2002
            * Developed reusable rocket technology

            Slide 6: Tesla and Electric Vehicles
            Tesla Leadership
            * Joined Tesla as an early investor in 2004
            * Became CEO in 2008
            * Led development of electric vehicles

            Slide 7: Artificial Intelligence & Innovation
            AI and Emerging Technologies
            * Co-founded OpenAI in 2015
            * Founded xAI to advance AI research

            Slide 8: Social Media and X
            Twitter Acquisition and Rebranding
            * Acquired Twitter in 2022
            * Rebranded Twitter as X in 2023

            Slide 9: Political Activities & Public Influence
            Politics and Public Role
            * Major donor in the 2024 U.S. Presidential Election
            * Supported Donald Trump

            Slide 10: Legacy, Impact & Controversies
            Achievements and Challenges
            Achievements
            * Revolutionized electric vehicles
            * Advanced commercial spaceflight
            Challenges
            * Political controversies
            * Debates regarding content moderation and social media policies
            Conclusion:
            Elon Musk remains influential and controversial.
            """,
            topic="Elon Musk",
        )

        self.assertEqual(result["contentSource"]["source"], "structured_input")

        slide_six = result["curatedContent"]["slides"]["6"]
        self.assertEqual(slide_six["headline"], "Tesla")
        self.assertEqual(slide_six["section"], "Leadership")
        self.assertIn("Joined Tesla", slide_six["heading1"])
        self.assertIn("Became CEO", slide_six["heading2"])

        slide_ten = result["curatedContent"]["slides"]["10"]
        self.assertTrue(slide_ten["heading1"].startswith("Achievements:"))
        self.assertTrue(slide_ten["heading2"].startswith("Challenges:"))


if __name__ == "__main__":
    unittest.main()
