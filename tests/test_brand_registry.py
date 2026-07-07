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

    def test_registry_initializes_with_unitystitches_and_degen(self) -> None:
        def scenario(root: Path) -> None:
            result = brand_registry.list_brands()
            ids = {brand["brand_id"] for brand in result["brands"]}

            self.assertIn("unitystitches", ids)
            self.assertIn("degen_market_chaos", ids)
            self.assertEqual(result["brand_count"], 2)

        self.run_with_registry(scenario)

    def test_default_brand_is_unitystitches(self) -> None:
        def scenario(root: Path) -> None:
            brand = brand_registry.get_default_brand()

            self.assertEqual(brand["brand_id"], "unitystitches")
            self.assertTrue(brand["default"])

        self.run_with_registry(scenario)

    def test_teacher_womens_underwear_blocked_for_unitystitches(self) -> None:
        def scenario(root: Path) -> None:
            result = brand_registry.validate_brand_product_niche(
                "unitystitches",
                "womens_underwear",
                "teacher classroom gift",
            )

            self.assertEqual(result["brand_compatibility_status"], "blocked")
            self.assertFalse(result["compatible"])

        self.run_with_registry(scenario)

    def test_pride_womens_underwear_allowed_for_unitystitches(self) -> None:
        def scenario(root: Path) -> None:
            result = brand_registry.validate_brand_product_niche(
                "unitystitches",
                "womens_underwear",
                "LGBTQ+ pride",
            )

            self.assertEqual(result["brand_compatibility_status"], "allowed")
            self.assertTrue(result["compatible"])

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
                self.assertEqual(api.brands_default_route()["brand"]["brand_id"], "unitystitches")
                self.assertEqual(api.brands_route()["brand_count"], 2)
                self.assertEqual(api.brand_detail_route("unitystitches")["brand"]["brand_id"], "unitystitches")
                request = api.BrandValidateRequest(product_type="womens_underwear", niche="teacher gift")
                self.assertEqual(
                    api.brand_validate_route("unitystitches", request)["brand_compatibility_status"],
                    "blocked",
                )

        self.run_with_registry(scenario)


if __name__ == "__main__":
    unittest.main()
