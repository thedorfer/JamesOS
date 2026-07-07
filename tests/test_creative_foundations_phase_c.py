from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import asset_library, image_worker, prompt_library, style_registry


class CreativeFoundationsPhaseCTests(unittest.TestCase):
    def run_with_foundations(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt_root = root / "PromptLibrary"
            asset_root = root / "Assets"
            style_root = root / "Styles"
            patches = [
                patch.object(prompt_library, "PROMPT_ROOT", prompt_root),
                patch.object(asset_library, "ASSET_ROOT", asset_root),
                patch.object(style_registry, "STYLE_ROOT", style_root),
                patch.object(image_worker.prompt_library, "PROMPT_ROOT", prompt_root),
                patch.object(image_worker.asset_library, "ASSET_ROOT", asset_root),
                patch.object(image_worker.style_registry, "STYLE_ROOT", style_root),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_prompt_library_loads(self) -> None:
        def scenario(root: Path) -> None:
            result = prompt_library.load_prompt_templates()

            self.assertEqual(result["status"], "ok")
            self.assertIn("product_art", result["templates"])
            self.assertIn("negative_marketplace_safe", result["templates"])
            self.assertFalse(result["execution_enabled"])

        self.run_with_foundations(scenario)

    def test_style_registry_loads(self) -> None:
        def scenario(root: Path) -> None:
            result = style_registry.list_styles()

            self.assertEqual(result["status"], "ok")
            self.assertIn("typography", result["styles"])
            self.assertIn("pride", result["styles"])
            self.assertFalse(result["execution_enabled"])

        self.run_with_foundations(scenario)

    def test_asset_library_scans_metadata_only(self) -> None:
        def scenario(root: Path) -> None:
            asset_root = root / "Assets"
            asset_root.mkdir(parents=True)
            (asset_root / "pride.svg").write_text("<svg></svg>", encoding="utf-8")
            (asset_root / "brand_font.ttf").write_bytes(b"font-bytes")

            result = asset_library.scan_assets()

            self.assertEqual(result["asset_count"], 2)
            font = next(asset for asset in result["assets"] if asset["extension"] == ".ttf")
            self.assertTrue(font["metadata_only"])
            self.assertEqual(font["path"], "")
            self.assertFalse(font["content_included"])

        self.run_with_foundations(scenario)

    def test_image_plan_includes_prompt_style_brand_and_assets(self) -> None:
        def scenario(root: Path) -> None:
            asset_root = root / "Assets"
            asset_root.mkdir(parents=True)
            (asset_root / "pride_rainbow.svg").write_text("<svg></svg>", encoding="utf-8")

            result = image_worker.plan(
                {
                    "brand_id": "unitystitches",
                    "product_type": "shirt",
                    "niche": "Pride Month",
                    "design_prompt": "bold typography pride shirt",
                }
            )

            self.assertEqual(result["brand_id"], "unitystitches")
            self.assertIn("brand_voice", result)
            self.assertIn("selected_prompt_template", result)
            self.assertIn("selected_style", result)
            self.assertIn("asset_suggestions", result)
            self.assertFalse(result["execution_enabled"])
            self.assertFalse(result["safety"]["comfyui_execution_enabled"])

        self.run_with_foundations(scenario)

    def test_creative_spec_converts_to_prompt_package(self) -> None:
        spec = {
            "brand_id": "unitystitches",
            "brand_voice": "warm and inclusive",
            "product_type": "shirt",
            "niche": "Pride Month",
            "audience": "gift shoppers",
            "emotional_hook": "joyful pride",
            "style": "bold typography",
            "colors": ["rainbow", "white"],
            "text": "Love Is Love",
            "typography": "bold readable sans",
            "layout": "centered",
        }
        package = prompt_library.creative_spec_to_prompt_package(spec)
        self.assertIn("Love Is Love", package["positive_prompt"])
        self.assertIn("Pride Month", package["positive_prompt"])
        self.assertTrue(package["negative_prompt"])
        self.assertEqual(package["recommended_workflow_type"], "typography")
        self.assertFalse(package["execution_enabled"])


if __name__ == "__main__":
    unittest.main()
