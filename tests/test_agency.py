import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jamesos.core.agency.manifest import AgencyManifest, AgencyManifestError
from jamesos.core.agency.registry import DirectoryCatalogProvider
from jamesos.core.agency.service import AgencyError, AgencyService
from jamesos.core.agency.storage import AgencyStore
from jamesos.core.agency.routes import create_router
from jamesos.core.agency.secrets import AgencySecretProvider


ROOT = Path(__file__).resolve().parents[1]


class FakeSecrets:
    def __init__(self): self.handles = set()
    def status(self, handle): return {"configured": handle in self.handles, "permissions_valid": handle in self.handles}
    def create(self, label, value):
        handle = f"secret:{label}:generated"
        self.handles.add(handle)
        return {"handle": handle, "label": label, "configured": True}


class AgencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.catalog_path = root / "catalog"
        self.catalog_path.mkdir()
        for source in (ROOT / "agency" / "manifests").glob("*.json"):
            (self.catalog_path / source.name).write_text(source.read_text())
        self.secrets = FakeSecrets()
        self.service = AgencyService(DirectoryCatalogProvider(self.catalog_path), AgencyStore(root / "state.json"), self.secrets)
        app = FastAPI()
        app.include_router(create_router(self.service, authenticate=False))
        self.client = TestClient(app)

    def tearDown(self): self.temporary.cleanup()

    def test_manifest_validation_and_catalog(self):
        catalog = self.service.catalog_items()
        self.assertEqual(2, len(catalog))
        self.assertTrue(all(not item["installed"] for item in catalog))
        value = json.loads((self.catalog_path / "example-agent.json").read_text())
        value["configuration"][0]["type"] = "plaintext-secret"
        with self.assertRaisesRegex(AgencyManifestError, "unsupported type"):
            AgencyManifest.from_dict(value)

    def test_incompatible_manifest_is_rejected(self):
        path = self.catalog_path / "example-agent.json"
        value = json.loads(path.read_text())
        value["agent"]["minimum_jamesos_version"] = "99.0.0"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(AgencyError, "incompatible"):
            self.service.hire("jamesos.example", confirmed=True)

    def test_hire_duplicate_disable_and_release_are_guarded(self):
        preview = self.service.hire("jamesos.example")
        self.assertTrue(preview["confirmation_required"])
        self.assertEqual([], self.service.team())
        self.service.hire("jamesos.example", confirmed=True)
        with self.assertRaisesRegex(AgencyError, "already hired"):
            self.service.hire("jamesos.example", confirmed=True)
        self.service.set_enabled("jamesos.example", True, confirmed=True)
        self.assertEqual("active", self.service.details("jamesos.example")["status"])
        self.assertFalse(self.service.release("jamesos.example")["changed"])
        self.service.set_enabled("jamesos.example", False, confirmed=True)
        self.service.release("jamesos.example", confirmed=True)
        self.assertEqual([], self.service.team())

    def test_configuration_is_typed_and_required_setup_blocks_enable(self):
        self.service.hire("jamesos.commerce", confirmed=True)
        with self.assertRaisesRegex(AgencyError, "setup is incomplete"):
            self.service.set_enabled("jamesos.commerce", True, confirmed=True)
        with self.assertRaises(AgencyManifestError):
            self.service.update_configuration("jamesos.commerce", {"profile_id": 4}, confirmed=True)
        self.service.update_configuration("jamesos.commerce", {"profile_id": "commerce_shop"}, confirmed=True)
        with self.assertRaisesRegex(AgencyError, "setup is incomplete"):
            self.service.set_enabled("jamesos.commerce", True, confirmed=True)

    def test_permissions_require_confirmation_and_requested_scope(self):
        self.service.hire("jamesos.commerce", confirmed=True)
        preview = self.service.update_permissions("jamesos.commerce", {"side_effects": ["local_state"]})
        self.assertTrue(preview["confirmation_required"])
        self.assertEqual({}, self.service.permissions("jamesos.commerce")["granted"])
        with self.assertRaisesRegex(AgencyError, "not requested"):
            self.service.update_permissions("jamesos.commerce", {"financial_actions": ["purchase"]}, confirmed=True)
        result = self.service.update_permissions("jamesos.commerce", {"side_effects": ["local_state"]}, confirmed=True)
        self.assertEqual(["local_state"], result["granted"]["side_effects"])

    def test_secret_grant_and_revoke_never_expose_value(self):
        self.service.hire("jamesos.commerce", confirmed=True)
        handle = "secret:test:123"
        secret_value = "super-sensitive-value"
        self.secrets.handles.add(handle)
        response = self.service.update_secrets("jamesos.commerce", {"COMMERCE_PROVIDER_TOKEN": handle}, confirmed=True)
        self.assertTrue(response["requirements"][0]["configured"])
        self.assertNotIn(secret_value, json.dumps(response))
        self.assertNotIn(secret_value, self.service.store.path.read_text())
        self.service.update_secrets("jamesos.commerce", {"COMMERCE_PROVIDER_TOKEN": None}, confirmed=True)
        self.assertFalse(self.service.secret_status("jamesos.commerce")["requirements"][0]["configured"])

    def test_secret_creation_returns_handle_not_value(self):
        preview = self.service.create_secret("provider", "do-not-return")
        self.assertTrue(preview["confirmation_required"])
        created = self.service.create_secret("provider", "do-not-return", confirmed=True)
        self.assertNotIn("do-not-return", json.dumps(created))
        self.assertTrue(created["handle"].startswith("secret:"))

    def test_local_secret_provider_uses_existing_resolution_contract(self):
        provider = AgencySecretProvider(Path(self.temporary.name) / "secrets")
        created = provider.create("provider", "resolved-value")
        self.assertEqual("resolved-value", provider.resolve(created["handle"]))
        restarted = AgencySecretProvider(Path(self.temporary.name) / "secrets")
        self.assertEqual("resolved-value", restarted.resolve(created["handle"]))
        self.assertNotIn("resolved-value", json.dumps(created))

    def test_complete_setup_can_enable_and_activity_is_safe(self):
        self.service.hire("jamesos.commerce", confirmed=True)
        self.service.update_configuration("jamesos.commerce", {"profile_id": "commerce_shop"}, confirmed=True)
        self.service.update_permissions("jamesos.commerce", {"side_effects": ["local_state"]}, confirmed=True)
        self.secrets.handles.add("secret:provider:abc")
        self.service.update_secrets("jamesos.commerce", {"COMMERCE_PROVIDER_TOKEN": "secret:provider:abc"}, confirmed=True)
        self.service.set_enabled("jamesos.commerce", True, confirmed=True)
        events = [item["event"] for item in self.service.activity("jamesos.commerce")["activity"]]
        self.assertIn("enabled", events)

    def test_api_vertical_slice_and_confirmation_defaults(self):
        catalog = self.client.get("/agency/catalog")
        self.assertEqual(200, catalog.status_code)
        self.assertEqual(2, len(catalog.json()))
        preview = self.client.post("/agency/agents/jamesos.example/hire", json={})
        self.assertTrue(preview.json()["confirmation_required"])
        hired = self.client.post("/agency/agents/jamesos.example/hire", json={"confirmed": True})
        self.assertEqual(200, hired.status_code)
        self.assertEqual(1, len(self.client.get("/agency/agents").json()))
        enabled = self.client.post("/agency/agents/jamesos.example/enable", json={"confirmed": True})
        self.assertEqual(200, enabled.status_code)
        self.assertEqual("active", self.client.get("/agency/agents/jamesos.example").json()["status"])

    def test_api_never_returns_created_secret_value(self):
        value = "api-secret-must-be-redacted"
        response = self.client.post("/agency/secrets", json={"label": "test", "value": value, "confirmed": True})
        self.assertEqual(200, response.status_code)
        self.assertNotIn(value, response.text)


if __name__ == "__main__": unittest.main()
