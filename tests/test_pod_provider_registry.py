from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import pod_provider_registry


class PodProviderRegistryTests(unittest.TestCase):
    def run_with_registry(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "JamesOSData" / "JamesOS" / "POD" / "pod_provider_registry.yaml"
            report_path = root / "JamesOSData" / "JamesOS" / "Reports" / "POD Provider Registry.md"
            patches = [
                patch.object(pod_provider_registry, "REGISTRY_PATH", registry_path),
                patch.object(pod_provider_registry, "REPORT_PATH", report_path),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_inkedjoy_provider_exists_and_is_readonly(self) -> None:
        def scenario(root: Path) -> None:
            provider = pod_provider_registry.get_provider("inkedjoy")

            self.assertEqual(provider["provider_id"], "inkedjoy")
            self.assertTrue(provider["enabled"])
            self.assertTrue(provider["readonly"])
            self.assertFalse(provider["writes_enabled"])
            self.assertFalse(provider["draft_creation_enabled"])
            self.assertFalse(provider["order_enabled"])
            self.assertIn("womens_underwear", provider["supported_product_types"])

        self.run_with_registry(scenario)

    def test_external_writes_remain_false_for_all_providers(self) -> None:
        def scenario(root: Path) -> None:
            result = pod_provider_registry.list_providers()
            for provider in result["providers"]:
                self.assertTrue(provider["readonly"])
                self.assertFalse(provider["writes_enabled"])
                self.assertFalse(provider["draft_creation_enabled"])
                self.assertFalse(provider["order_enabled"])

        self.run_with_registry(scenario)

    def test_provider_routes_exist(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise

        paths = {route.path for route in api.app.routes}
        self.assertIn("/pod-providers", paths)
        self.assertIn("/pod-providers/health", paths)
        self.assertIn("/pod-providers/{provider_id}", paths)


if __name__ == "__main__":
    unittest.main()
