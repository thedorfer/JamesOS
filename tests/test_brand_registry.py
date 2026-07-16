from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import brand_registry


class BrandRegistryTests(unittest.TestCase):
    def run_with_registry(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "JamesOSData" / "JamesOS" / "Brands" / "brand_registry.yaml"
            report_path = root / "JamesOSData" / "JamesOS" / "Reports" / "Brand Registry.md"
            patches = [
                patch.object(brand_registry, "REGISTRY_PATH", registry_path),
                patch.object(brand_registry, "REPORT_PATH", report_path),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_registry_initializes_with_commerce_shop_and_degen(self) -> None:
        def scenario(root: Path) -> None:
            result = brand_registry.list_brands()
            ids = {brand["brand_id"] for brand in result["brands"]}

            self.assertIn("commerce_shop", ids)
            self.assertIn("bagholder_supply_co", ids)
            self.assertIn("cheeky_peach_prints", ids)
            self.assertIn("degen_market_chaos", ids)
            self.assertGreaterEqual(result["brand_count"], 4)

        self.run_with_registry(scenario)

    def test_default_brand_is_commerce_shop(self) -> None:
        def scenario(root: Path) -> None:
            brand = brand_registry.get_default_brand()

            self.assertEqual(brand["brand_id"], "commerce_shop")
            self.assertTrue(brand["default"])

        self.run_with_registry(scenario)

    def test_teacher_womens_underwear_blocked_for_commerce_shop(self) -> None:
        def scenario(root: Path) -> None:
            result = brand_registry.validate_brand_product_niche(
                "commerce_shop",
                "womens_underwear",
                "teacher classroom gift",
            )

            self.assertEqual(result["brand_compatibility_status"], "blocked")
            self.assertFalse(result["compatible"])

        self.run_with_registry(scenario)

    def test_pride_womens_underwear_allowed_for_commerce_shop(self) -> None:
        def scenario(root: Path) -> None:
            result = brand_registry.validate_brand_product_niche(
                "commerce_shop",
                "womens_underwear",
                "LGBTQ+ pride",
            )

            self.assertEqual(result["brand_compatibility_status"], "allowed")
            self.assertTrue(result["compatible"])

        self.run_with_registry(scenario)

    def test_underwear_product_rules_prefer_printify_for_now(self) -> None:
        def scenario(root: Path) -> None:
            for brand_id in ["commerce_shop", "cheeky_peach_prints"]:
                brand = brand_registry.get_brand(brand_id)

                self.assertEqual(brand["preferred_pod_provider"], "printify")
                self.assertEqual(brand["provider_rules"]["womens_underwear"]["preferred_provider"], "printify")
                self.assertEqual(brand["provider_rules"]["panties"]["preferred_provider"], "printify")
                self.assertEqual(brand["provider_rules"]["thong"]["preferred_provider"], "printify")

        self.run_with_registry(scenario)

    def test_new_shop_profiles_prefer_printify(self) -> None:
        def scenario(root: Path) -> None:
            bagholder = brand_registry.get_brand("bagholder_supply_co")
            cheeky = brand_registry.get_brand("cheeky_peach_prints")

            self.assertEqual(bagholder["display_name"], "Bagholder Supply Co")
            self.assertEqual(bagholder["preferred_pod_provider"], "printify")
            self.assertEqual(bagholder["niche"], "market_chaos_degen_tshirts")
            self.assertEqual(bagholder["product_focus"], ["shirts"])
            self.assertEqual(bagholder["daily_design_target"], {"min": 3, "max": 5})
            self.assertEqual(bagholder["stage_default"], "print_design_basic")
            self.assertEqual(cheeky["display_name"], "Cheeky Peach Prints")
            self.assertEqual(cheeky["preferred_pod_provider"], "printify")
            self.assertEqual(cheeky["fallback_pod_provider"], "inkedjoy_manual_future")
            self.assertEqual(cheeky["niche"], "womens_underwear_playful_seasonal")
            self.assertEqual(cheeky["product_focus"], ["womens_underwear", "panties", "thong"])
            self.assertEqual(cheeky["daily_design_target"], {"min": 3, "max": 5})
            self.assertEqual(cheeky["stage_default"], "print_design_basic")

        self.run_with_registry(scenario)

    def test_degen_shop_disabled_by_default(self) -> None:
        def scenario(root: Path) -> None:
            brand = brand_registry.get_brand("degen_market_chaos")

            self.assertFalse(brand["enabled"])
            self.assertFalse(brand["default"])

        self.run_with_registry(scenario)

    def test_external_writes_remain_false(self) -> None:
        def scenario(root: Path) -> None:
            for brand in brand_registry.list_brands()["brands"]:
                self.assertFalse(brand["approval_rules"]["writes_enabled"])
                self.assertFalse(brand["integrations"]["etsy"]["writes_enabled"])
                self.assertFalse(brand["integrations"]["printify"]["writes_enabled"])
                self.assertFalse(brand["integrations"]["printify"].get("draft_creation_enabled", False))
                self.assertFalse(brand["integrations"]["printify"].get("order_enabled", False))
                self.assertFalse(brand["integrations"]["comfyui"]["execution_enabled"])

        self.run_with_registry(scenario)

    def test_live_brand_route_functions_work(self) -> None:
        def scenario(root: Path) -> None:
            try:
                from jamesos.core import api
            except ModuleNotFoundError as exc:
                if exc.name in {"fastapi", "pydantic"}:
                    self.skipTest("fastapi/pydantic are not installed in this Python environment")
                raise

            with (
                patch.object(api, "require_key", return_value=None),
                patch.object(api, "list_brands", brand_registry.list_brands),
                patch.object(api, "brand_health", brand_registry.brand_health),
                patch.object(api, "get_default_brand", brand_registry.get_default_brand),
                patch.object(api, "get_brand", brand_registry.get_brand),
                patch.object(api, "validate_brand_product_niche", brand_registry.validate_brand_product_niche),
            ):
                self.assertEqual(api.brands_health_route()["status"], "ok")
                self.assertEqual(api.brands_default_route()["brand"]["brand_id"], "commerce_shop")
                self.assertGreaterEqual(api.brands_route()["brand_count"], 4)
                self.assertEqual(api.brand_detail_route("commerce_shop")["brand"]["brand_id"], "commerce_shop")
                request = api.BrandValidateRequest(product_type="womens_underwear", niche="teacher gift")
                self.assertEqual(
                    api.brand_validate_route("commerce_shop", request)["brand_compatibility_status"],
                    "blocked",
                )

        self.run_with_registry(scenario)


if __name__ == "__main__":
    unittest.main()
