from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openai_content import (  # noqa: E402
    _response_format,
    generate_curated_content_with_openai,
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

    def test_response_format_requires_fallback_slide_fields(self) -> None:
        schema = _response_format(FALLBACK_CURATED)["schema"]
        slides = schema["properties"]["slides"]

        self.assertEqual(slides["required"], ["1", "2"])
        self.assertEqual(
            slides["properties"]["2"]["required"],
            ["body", "headline", "section"],
        )


if __name__ == "__main__":
    unittest.main()
