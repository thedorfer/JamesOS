from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import server_config


class ServerConfigTests(unittest.TestCase):
    def test_initializes_config_and_reports_safe_integrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_root = root / "JamesOS" / "Config"
            report_path = root / "JamesOS" / "Reports" / "Server Configuration.md"
            with patch.object(server_config, "VAULT", root):
                with patch.object(server_config, "CONFIG_ROOT", config_root):
                    with patch.object(server_config, "REPORT_PATH", report_path):
                        initialized = server_config.initialize_server_config()
                        health = server_config.service_health()
                        report = server_config.write_server_config_report()

            self.assertEqual(initialized["status"], "ok")
            self.assertTrue((config_root / "server.yaml").exists())
            self.assertTrue((config_root / "integrations.yaml").exists())
            self.assertEqual(health["status"], "degraded")
            self.assertTrue(report_path.exists())
            self.assertEqual(report["status"], "ok")
            integrations = report["health"]["integrations"]["integrations"]
            printify = next(item for item in integrations if item["name"] == "printify")
            etsy = next(item for item in integrations if item["name"] == "etsy")
            comfyui = next(item for item in integrations if item["name"] == "comfyui")
            self.assertFalse(printify["execution_enabled"])
            self.assertFalse(etsy["publish_enabled"])
            self.assertFalse(comfyui["execution_enabled"])


if __name__ == "__main__":
    unittest.main()
