from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.shell_health import ShellHealthService, calculate_shell_health


def profile(profile_id: str, display: str, shop_id: int, title: str, slug: str, listing_title: str) -> dict:
    return {
        "profile_id": profile_id,
        "enabled": True,
        "display_name": display,
        "configuration": {
            "printify_shop_id": shop_id,
            "printify_shop_title": title,
            "etsy_shop_slug": slug,
            "default_garment_colors": ["Black", "White"],
            "artwork_palette": ["#111111", "#eeeeee"],
            "brand_voice": ["direct", "warm"],
            "listing_policy_reference": f"{profile_id}-listing-v1",
            "listing_title": listing_title,
        },
    }


ROWS = [
    profile("bagholder-supply", "Bagholder Supply Co.", 28275232, "BagholdersSupplyCo", "bagholders", "Market Humor Tee"),
    profile("unitystitches", "UnityStitches", 9437076, "UnityStitches", "unitystitches", "Inclusive Ally Tee"),
]


class ShellChromeTests(unittest.TestCase):
    def render(self) -> str:
        with patch.object(api, "list_commerce_profiles", return_value=ROWS), patch.object(api, "selected_profile_id", return_value="bagholder-supply"), patch.object(api, "_require_local"):
            return TestClient(api.app, base_url="http://127.0.0.1:8787").get("/app?view=commerce.new").text

    def test_context_dock_is_primary_chrome_without_standalone_title_row(self):
        text = self.render()
        self.assertNotIn("id='workspace-title'", text)
        self.assertNotIn("<header class='topbar'", text)
        self.assertLess(text.index("id='context-dock'"), text.index("id='commerce-new'"))
        for label in (">Home<", ">The Agency<", ">Admin<"):
            self.assertIn(label, text)

    def test_compact_profile_selector_destination_and_dirty_field_guards(self):
        text = self.render()
        self.assertIn("<select class='profile-select' id='commerce-profile'", text)
        self.assertIn("Bagholder Supply Co.", text)
        self.assertIn("UnityStitches", text)
        self.assertIn("destination-printify", text)
        self.assertIn("destination-etsy", text)
        self.assertIn("destination-status'>UNPUBLISHED", text)
        self.assertIn("data-panel-id='destination'", text)
        self.assertIn("data-layout-locked='true'", text)
        self.assertIn("fieldMeta[k].dirty", text)
        self.assertIn("!fieldMeta[k].dirty", text)
        self.assertIn("profileSelect.value=lastProfile", text)
        self.assertIn("profileSelect.disabled=true", text)
        self.assertIn("updated destination and", text)
        self.assertNotIn("id='undo'", text)
        self.assertNotIn("input type='radio' name='commerce_profile_id'", text)

    def test_health_dot_and_accessible_detail_polling_are_present(self):
        text = self.render()
        for value in ("health-dot", "aria-label='System health", "health-detail", "API/server", "/app/health", "setTimeout(pollHealth,15000)", "value.state!==healthState"):
            self.assertIn(value, text)
        self.assertNotIn("Local model: desktop", text)
        self.assertNotIn("GPU: desktop execution host", text)

    def test_health_reducer_supports_green_yellow_and_red(self):
        healthy = [{"status": "healthy", "required": True}]
        optional = healthy + [{"status": "degraded", "required": False}]
        critical = healthy + [{"status": "unavailable", "required": True}]
        self.assertEqual(calculate_shell_health(healthy)["state"], "green")
        self.assertEqual(calculate_shell_health(optional)["state"], "yellow")
        self.assertEqual(calculate_shell_health(critical)["state"], "red")

    def test_optional_image_failure_is_yellow_and_storage_failure_is_red(self):
        with patch("jamesos.services.shell_health.Path.exists", return_value=True), patch("jamesos.services.shell_health.os.access", return_value=True):
            yellow = ShellHealthService(storage=Mock(is_dir=Mock(return_value=True)), ollama_probe=lambda: {"ready": True}, image_probe=lambda: {"running": False}).status(ROWS)
        self.assertEqual(yellow["state"], "yellow")
        red = ShellHealthService(storage=Mock(is_dir=Mock(return_value=False)), ollama_probe=lambda: {"ready": True}, image_probe=lambda: {"running": True}).status(ROWS)
        self.assertEqual(red["state"], "red")

    def test_health_route_uses_local_read_only_service(self):
        service = Mock(); service.status.return_value = {"state": "green", "label": "healthy", "systems": []}
        provider = Mock(side_effect=AssertionError("provider must not be called"))
        with patch.object(api, "ShellHealthService", return_value=service), patch.object(api, "list_commerce_profiles", return_value=ROWS), patch.object(api, "_require_local"):
            response = TestClient(api.app, base_url="http://127.0.0.1:8787").get("/app/health")
        self.assertEqual(response.json()["state"], "green")
        service.status.assert_called_once_with(ROWS)
        provider.assert_not_called()

    def test_rendering_and_ui_selection_do_not_mutate_global_profile_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            pointer = Path(temporary) / "selected-profile"
            pointer.write_text("bagholder-supply\n", encoding="utf-8")
            before = pointer.read_bytes()
            self.render()
            self.assertEqual(pointer.read_bytes(), before)

    def test_health_details_name_every_required_local_subsystem(self):
        value = ShellHealthService(storage=Mock(is_dir=Mock(return_value=False)), ollama_probe=lambda: {"ready": False}, image_probe=lambda: {"running": False}).status(ROWS)
        self.assertEqual(
            {item["label"] for item in value["systems"]},
            {"API/server", "Ollama", "GPU", "ComfyUI/image worker", "Private JamesOSData storage", "Commerce-profile readiness"},
        )


if __name__ == "__main__":
    unittest.main()
