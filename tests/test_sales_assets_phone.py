from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from creative_intelligence.services import etsy_sales_intelligence_service as sales
from creative_intelligence.services.scoring_service import score_candidate
from jamesos.services import asset_pack_importer, phone_ingestion
from jamesos.services.print_readiness_scorer import score_variation


class SalesAssetsPhoneTests(unittest.TestCase):
    def test_etsy_sales_intelligence_accepts_provider_agnostic_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = sales.import_sales_rows(
                [
                    {
                        "pod_provider": "inkedjoy",
                        "fulfillment_source": "manual",
                        "production_partner": "Local Partner",
                        "product_type": "womens_underwear",
                        "design_family": "underwear_pride_pattern",
                        "recipe_id": "underwear/pride_pattern",
                        "revenue": "42.50",
                        "quantity_sold": "2",
                        "conversion_rate": "4%",
                        "favorite_rate": "10%",
                        "repeat_buyer_signal": "yes",
                        "seasonality_signal": "pride",
                    }
                ],
                root=root,
            )
            rows = sales.list_sales_history(root=root)

            self.assertEqual(result["imported"], 1)
            self.assertEqual(rows[0]["pod_provider"], "inkedjoy")
            self.assertEqual(rows[0]["fulfillment_source"], "manual")
            self.assertEqual(rows[0]["quantity_sold"], 2)
            self.assertAlmostEqual(rows[0]["conversion_rate"], 0.04)
            self.assertFalse(result["safety"]["provider_writes_enabled"])

    def test_inkedjoy_and_manual_sales_influence_scoring_without_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sales.import_sales_rows(
                [
                    {
                        "pod_provider": "inkedjoy",
                        "fulfillment_source": "manual_fulfillment",
                        "title": "Pride hearts underwear",
                        "product_type": "womens_underwear",
                        "design_family": "underwear_pride_pattern",
                        "motifs": ["hearts"],
                        "color_palette": ["rainbow"],
                        "seasonality_signal": "pride",
                        "revenue": 160,
                        "quantity_sold": 8,
                        "conversion_rate": 0.05,
                    }
                ],
                root=root,
            )
            candidate = {
                "name": "pride hearts underwear pattern",
                "audience": "pride shoppers",
                "keywords": ["pride", "hearts", "underwear"],
                "product_type": "womens_underwear",
                "design_family": "underwear_pride_pattern",
                "motifs": ["hearts"],
                "color_palette": ["rainbow"],
                "niche": "pride",
            }
            with patch.object(sales, "SALES_ROOT", root):
                boosted = score_candidate(candidate)

            self.assertGreater(boosted, 0.75)
            self.assertFalse(sales.SAFETY["inkedjoy_enabled"])

            variation = {
                "variation_id": "v1",
                "product_type": "womens_underwear",
                "niche": "pride",
                "design_recipe": {
                    "recipe_id": "underwear/pride_pattern",
                    "product_type": "womens_underwear",
                    "design_family": "underwear_pride_pattern",
                    "product_fit": ["womens_underwear"],
                    "design_type": "repeat_pattern",
                    "pattern_strategy": "seamless-style repeat",
                    "text_strategy": "no_text",
                    "quality_rules": ["high contrast"],
                    "composition_rules": ["safe margins"],
                    "trademark_safety_notes": "safe",
                    "commercial_goal": "wearable pride pattern",
                    "motifs": ["hearts"],
                    "palette": ["rainbow"],
                    "negative_rules": ["large text"],
                },
            }
            with patch.object(sales, "SALES_ROOT", root):
                score = score_variation(variation)
            self.assertGreater(score["etsy_sales_signal"]["boost"], 0)
            self.assertIn("inkedjoy", score["etsy_sales_signal"]["providers_seen"])

    def test_asset_importer_records_license_metadata_and_font_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "heart.svg").write_text("<svg></svg>", encoding="utf-8")
            (source / "display.otf").write_bytes(b"font")
            root = Path(tmp) / "packs"
            result = asset_pack_importer.import_asset_pack(
                source,
                pack_name="Test Pack",
                license_metadata={
                    "source": "local test",
                    "license": "commercial test",
                    "commercial_allowed": True,
                    "attribution_required": False,
                    "notes": "unit test",
                },
                root=root,
            )

            self.assertEqual(result["asset_count"], 2)
            self.assertEqual(result["license"]["source"], "local test")
            font = next(asset for asset in result["assets"] if asset["asset_type"] == "font")
            self.assertTrue(font["metadata_only"])
            self.assertEqual(font["storage_path"], "")
            manifest = json.loads((root / "test_pack" / "asset_pack_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["binary_contents_exposed"])

    def test_readme_does_not_mention_unitystitches(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertNotIn("UnityStitches", readme)
        self.assertNotIn("unitystitches", readme)

    def test_phone_ingestion_methods_include_linux_alternatives(self) -> None:
        result = phone_ingestion.methods()
        text = " ".join(f"{item['id']} {item['name']}" for item in result["methods"]).lower()
        for token in ["mtp", "syncthing", "kde connect", "adb", "tasker"]:
            self.assertIn(token, text)
        self.assertFalse(result["safety"]["deletes_phone_data"])
        self.assertFalse(result["safety"]["sends_messages"])
        self.assertFalse(result["safety"]["cloud_upload_default"])


if __name__ == "__main__":
    unittest.main()
