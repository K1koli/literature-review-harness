from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.utils.config import Config


class ConfigTest(unittest.TestCase):
    def test_openai_image_size_and_quality_aliases_match_documentation(self) -> None:
        with patch("src.utils.config._load_toml", return_value={}), patch.dict(
            os.environ,
            {
                "INTERN_API_KEY": "intern-key",
                "SCIVERSE_API_TOKEN": "sciverse-key",
                "IMAGE_GENERATION_ENABLED": "true",
                "OPENAI_API_KEY": "openai-key",
                "OPENAI_IMAGE_SIZE": "1024x1024",
                "OPENAI_IMAGE_QUALITY": "medium",
            },
            clear=True,
        ):
            config = Config.from_env()

        self.assertTrue(config.image_generation_enabled)
        self.assertEqual(config.image_generation_size, "1024x1024")
        self.assertEqual(config.image_generation_quality, "medium")
        self.assertEqual(config.validate(), [])

    def test_image_generation_specific_env_names_take_precedence(self) -> None:
        with patch("src.utils.config._load_toml", return_value={}), patch.dict(
            os.environ,
            {
                "INTERN_API_KEY": "intern-key",
                "SCIVERSE_API_TOKEN": "sciverse-key",
                "OPENAI_API_KEY": "openai-key",
                "OPENAI_IMAGE_SIZE": "1024x1024",
                "IMAGE_GENERATION_SIZE": "1536x1024",
                "OPENAI_IMAGE_QUALITY": "medium",
                "IMAGE_GENERATION_QUALITY": "low",
            },
            clear=True,
        ):
            config = Config.from_env()

        self.assertEqual(config.image_generation_size, "1536x1024")
        self.assertEqual(config.image_generation_quality, "low")


if __name__ == "__main__":
    unittest.main()
