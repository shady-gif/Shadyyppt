from __future__ import annotations

import os
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openai_content import (  # noqa: E402
    _prompt,
    _response_format,
    _text_box_prompt,
    _text_box_response_format,
    _validated_text_box_updates,
    generate_curated_content_with_openai,
    generate_text_box_updates_with_openai,
    openai_runtime_status,
)


FALLBACK_CURATED = {
    "deckTitle": "Energy Transition",
    "subtitle": "technology profile",
    "byline": "",
    "year": "2026",
    "unusedFacts": ["Storage improves grid flexibility."],
    "slides": {
        "1": {
            "title": "Energy Transition",
            "subtitle": "technology profile",
            "byline": "",
            "year": "2026",
        },
        "2": {
            "section": "Overview",
            "headline": "Cleaner power systems",
            "body": "Renewable energy changes planning, markets, and infrastructure.",
        },
    },
}


def generate(**env):
    with mock.patch.dict(os.environ, env, clear=True):
        return generate_curated_content_with_openai(
            topic="Energy Transition",
            source_text="Renewable energy source text.",
            profile={"name": "Profile", "closing": "Takeaways"},
            template_id="profile",
            template_map={},
            fallback_curated=FALLBACK_CURATED,
        )


def generate_text_boxes(**env):
    with mock.patch.dict(os.environ, env, clear=True):
        return generate_text_box_updates_with_openai(
            topic="Energy Transition",
            source_text="Renewable energy source text.",
            profile={"name": "Profile", "closing": "Takeaways"},
            template_id="profile",
            template_text_boxes=[
                {
                    "index": 1,
                    "textBoxes": [
                        {"shapeId": "26", "originalText": "COMPANY", "maxChars": 28},
                        {"shapeId": "27", "originalText": "PROFILE", "maxChars": 28},
                    ],
                }
            ],
            fallback_curated=FALLBACK_CURATED,
        )


class OpenAIContentTests(unittest.TestCase):
    def test_placeholder_api_key_uses_missing_key_fallback(self) -> None:
        curated, metadata = generate(OPENAI_API_KEY="sk-your-key-here")

        self.assertIsNone(curated)
        self.assertEqual(metadata["source"], "missing_api_key")
        self.assertFalse(metadata["enabled"])

    def test_status_does_not_expose_key(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-secret"}, clear=True):
            status = openai_runtime_status()

        self.assertEqual(status, {"enabled": True, "configured": True, "model": "gpt-5-nano"})

    def test_invalid_env_numbers_still_fall_back(self) -> None:
        with mock.patch("openai_content._post_json", side_effect=RuntimeError("network down")):
            curated, metadata = generate(
                OPENAI_API_KEY="sk-test-secret",
                OPENAI_RETRIES="not-a-number",
                OPENAI_MAX_OUTPUT_TOKENS="also-bad",
            )

        self.assertIsNone(curated)
        self.assertEqual(metadata["source"], "fallback")
        self.assertEqual(metadata["error"], "network down")

    def test_text_box_generation_uses_missing_key_fallback(self) -> None:
        updates, metadata = generate_text_boxes(OPENAI_API_KEY="sk-your-key-here")

        self.assertIsNone(updates)
        self.assertEqual(metadata["source"], "missing_api_key")

    def test_text_box_generation_success_returns_shape_updates(self) -> None:
        with mock.patch(
            "openai_content._post_json",
            return_value={
                "id": "resp_test",
                "output_text": json.dumps(
                    {
                        "updates": [
                            {
                                "slideIndex": 1,
                                "shapeId": "26",
                                "role": "title",
                                "newText": "Energy Transition",
                            },
                            {
                                "slideIndex": 1,
                                "shapeId": "27",
                                "role": "subtitle",
                                "newText": "Technology profile",
                            },
                        ]
                    }
                ),
            },
        ):
            updates, metadata = generate_text_boxes(OPENAI_API_KEY="sk-test-secret")

        self.assertEqual(metadata["source"], "openai")
        self.assertEqual(metadata["mode"], "text_boxes")
        self.assertEqual(updates[0]["shapeId"], "26")
        self.assertEqual(updates[0]["newText"], "Energy Transition")

    def test_response_format_requires_fallback_slide_fields(self) -> None:
        schema = _response_format(FALLBACK_CURATED)["schema"]
        slides = schema["properties"]["slides"]

        self.assertEqual(slides["required"], ["1", "2"])
        self.assertEqual(
            slides["properties"]["2"]["required"],
            ["body", "headline", "section"],
        )

    def test_prompt_contract_uses_actual_fallback_fields(self) -> None:
        prompt = _prompt(
            topic="Energy Transition",
            source_text="Source text",
            profile={"name": "Profile", "closing": "Takeaways"},
            template_id="profile",
            template_map={"2": {"fields": {"headline": "12", "body": "14"}}},
            fallback_curated={
                **FALLBACK_CURATED,
                "slides": {
                    **FALLBACK_CURATED["slides"],
                    "6": {
                        "section": "Milestones",
                        "headline": "Grid flexibility",
                        "heading1": "Storage",
                        "heading2": "Transmission",
                    },
                },
            },
        )

        payload = json.loads(prompt)

        self.assertEqual(
            sorted(payload["outputContract"]["slides"]["6"].keys()),
            ["heading1", "heading2", "headline", "section"],
        )
        self.assertEqual(
            payload["fieldGuidance"]["6"]["heading1"],
            "short source-specific claim or label",
        )

    def test_text_box_prompt_contains_exact_shape_contract(self) -> None:
        prompt = _text_box_prompt(
            topic="Energy Transition",
            source_text="Source text",
            profile={"name": "Profile", "closing": "Takeaways"},
            template_id="profile",
            template_text_boxes=[
                {
                    "index": 2,
                    "textBoxes": [
                        {
                            "shapeId": "12",
                            "originalText": "ABOUT",
                            "fontSize": 110.84,
                            "maxChars": 28,
                        }
                    ],
                }
            ],
            fallback_curated=FALLBACK_CURATED,
        )

        payload = json.loads(prompt)

        self.assertEqual(payload["templateTextBoxes"][0]["textBoxes"][0]["shapeId"], "12")
        self.assertTrue(
            any("Return one update for every text box" in rule for rule in payload["hardRules"])
        )

    def test_text_box_response_format_requires_exact_update_fields(self) -> None:
        schema = _text_box_response_format()["schema"]
        update_schema = schema["properties"]["updates"]["items"]

        self.assertEqual(update_schema["required"], ["slideIndex", "shapeId", "role", "newText"])
        self.assertIn("page_number", update_schema["properties"]["role"]["enum"])

    def test_validated_text_box_updates_rejects_missing_boxes(self) -> None:
        with self.assertRaises(ValueError):
            _validated_text_box_updates(
                {"updates": [{"slideIndex": 1, "shapeId": "26", "role": "title", "newText": "Energy"}]},
                [
                    {
                        "index": 1,
                        "textBoxes": [
                            {"shapeId": "26", "originalText": "COMPANY", "maxChars": 28},
                            {"shapeId": "27", "originalText": "PROFILE", "maxChars": 28},
                        ],
                    }
                ],
            )

    def test_validated_text_box_updates_clips_and_keeps_keys(self) -> None:
        updates = _validated_text_box_updates(
            {
                "updates": [
                    {
                        "slideIndex": 1,
                        "shapeId": "26",
                        "role": "title",
                        "newText": "Renewable Energy Transition Strategy",
                    },
                    {"slideIndex": 1, "shapeId": "27", "role": "subtitle", "newText": "2026 outlook"},
                ]
            },
            [
                {
                    "index": 1,
                    "textBoxes": [
                        {"shapeId": "26", "originalText": "COMPANY", "maxChars": 18},
                        {"shapeId": "27", "originalText": "PROFILE", "maxChars": 28},
                    ],
                }
            ],
        )

        self.assertEqual(updates[0]["slideIndex"], 1)
        self.assertEqual(updates[0]["shapeId"], "26")
        self.assertLessEqual(len(updates[0]["newText"]), 18)


if __name__ == "__main__":
    unittest.main()
