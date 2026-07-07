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
            brand_assets_root = root / "Brands"
            style_root = root / "Styles"
            patches = [
                patch.object(prompt_library, "PROMPT_ROOT", prompt_root),
                patch.object(asset_library, "ASSET_ROOT", asset_root),
                patch.object(asset_library, "BRAND_ASSETS_ROOT", brand_assets_root),
                patch.object(style_registry, "STYLE_ROOT", style_root),
                patch.object(image_worker.prompt_library, "PROMPT_ROOT", prompt_root),
                patch.object(image_worker.asset_library, "ASSET_ROOT", asset_root),
                patch.object(image_worker.asset_library, "BRAND_ASSETS_ROOT", brand_assets_root),
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
            self.assertIn("print_design_basic", result["templates"])
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
            "product_type": "design_art",
            "stage": "design_art",
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
        self.assertIn("flat centered print artwork", package["positive_prompt"])
        self.assertTrue(package["negative_prompt"])
        self.assertEqual(package["recommended_workflow_type"], "print_design_basic")
        self.assertFalse(package["execution_enabled"])

    def test_prompt_does_not_start_with_punctuation_or_empty_asset_sentence(self) -> None:
        package = prompt_library.creative_spec_to_prompt_package({
            "stage": "design_art",
            "product_type": "design_art",
            "niche": "Pride Month",
            "assets": [],
        })

        self.assertFalse(package["positive_prompt"].startswith("."))
        self.assertNotIn("Assets/reference motifs: .", package["positive_prompt"])

    def test_design_recipe_renders_into_prompt_package(self) -> None:
        package = prompt_library.creative_spec_to_prompt_package({
            "brand_id": "unitystitches",
            "stage": "design_art",
            "design_recipe": {
                "product_type": "design_art",
                "niche": "LGBTQ+ pride",
                "artwork_type": "flat print design",
                "background": "white or transparent-background-friendly",
                "layout": "centered",
                "palette": ["rainbow", "white", "black accent"],
                "text": "Love Is Love",
                "typography": "bold readable rounded sans",
                "motifs": ["hearts", "sparkles", "pride rainbow"],
                "effects": "clean vector-like print art",
                "provider": "printify",
                "print_notes": "high contrast, readable at thumbnail size, no person, no mockup",
            },
        })

        self.assertIn("Love Is Love", package["positive_prompt"])
        self.assertIn("clean vector-like print art", package["positive_prompt"])
        self.assertIn("Print notes", package["positive_prompt"])
        self.assertEqual(package["recommended_workflow_type"], "print_design_basic")
        self.assertEqual(package["design_recipe"]["provider"], "printify")

    def test_design_art_prompt_rejects_person_model_and_mockup(self) -> None:
        package = prompt_library.creative_spec_to_prompt_package({
            "stage": "design_art",
            "product_type": "design_art",
            "niche": "Pride Month",
            "text": "Be You",
        })

        self.assertIn("Standalone print design", package["positive_prompt"])
        self.assertIn("flat centered print artwork", package["positive_prompt"])
        self.assertIn("no human model", package["positive_prompt"].lower())
        self.assertIn("person", package["negative_prompt"])
        self.assertIn("model", package["negative_prompt"])
        self.assertIn("mockup", package["negative_prompt"])

    def test_mockup_terms_only_allowed_in_mockup_stage(self) -> None:
        design = prompt_library.creative_spec_to_prompt_package({"stage": "design_art", "product_type": "design_art"})
        mockup = prompt_library.creative_spec_to_prompt_package({"stage": "mockup", "product_type": "shirt"})

        self.assertIn("mockup", design["negative_prompt"].lower())
        self.assertNotIn("no mockup", mockup["negative_prompt"].lower())
        self.assertEqual(mockup["recommended_workflow_type"], "mockup")

    def test_selected_assets_include_pride_assets_and_hide_fonts(self) -> None:
        def scenario(root: Path) -> None:
            brand_assets = root / "Brands" / "UnityStitches" / "Assets"
            brand_assets.mkdir(parents=True)
            (brand_assets / "pride_rainbow_flag.svg").write_text("<svg></svg>", encoding="utf-8")
            (brand_assets / "unitystitches_logo.png").write_bytes(b"png")
            (brand_assets / "brand_font.ttf").write_bytes(b"font")

            result = image_worker.plan({
                "brand_id": "unitystitches",
                "creative_spec": {
                    "brand_id": "unitystitches",
                    "stage": "design_art",
                    "product_type": "design_art",
                    "niche": "LGBTQ+ pride",
                    "text": "Love Is Love",
                },
            })

            names = {asset["name"] for asset in result["selected_assets"]}
            self.assertIn("pride_rainbow_flag", names)
            self.assertIn("unitystitches_logo", names)
            font = next(asset for asset in result["selected_assets"] if asset["extension"] == ".ttf")
            self.assertEqual(font["path"], "")
            self.assertTrue(font["metadata_only"])
            self.assertFalse(font["content_included"])

        self.run_with_foundations(scenario)


if __name__ == "__main__":
    unittest.main()
