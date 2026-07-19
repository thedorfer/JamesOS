import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.shell_dashboard import ShellDashboardService
from jamesos.services.shell_secrets import ShellSecretStore
from jamesos.services.shell_profile_settings import ShellProfileSettings


def profile():
    return {"profile_id":"bagholder-supply","display_name":"Bagholder Supply Co.","configuration":{"printify_shop_id":1,"printify_shop_title":"Bagholder","etsy_shop_slug":"BagholdersSupplyCo"}}


class DashboardAdminTests(unittest.TestCase):
    def test_profile_settings_are_allowlisted_private_and_do_not_touch_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"profiles.json";service=ShellProfileSettings(path);job=Mock(side_effect=AssertionError("job mutated"))
            saved=service.save("bagholder-supply",{"display_name":"Bagholder Supply Co.","printify_shop_id":"123","listing_guidance":"bagholder-supply-listing-v1"})
            self.assertEqual(saved["configuration"]["printify_shop_id"],123);self.assertTrue(path.is_file());job.assert_not_called()
            with self.assertRaises(ValueError):service.save("unknown",{"display_name":"X"})
            with self.assertRaises(ValueError):service.save("bagholder-supply",{"environment":"SECRET"})

    def test_profile_settings_require_current_revision_and_create_rollback_and_sanitized_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"profiles.json";service=ShellProfileSettings(path);first=service.save("bagholder-supply",{"display_name":"First"})
            second=service.save("bagholder-supply",{"display_name":"Second"},revision=first["revision"]);self.assertNotEqual(first["revision"],second["revision"])
            self.assertTrue(path.with_name("profiles.rollback.json").is_file());audit=path.with_name("profiles.audit.json").read_text();self.assertIn("commerce_profile_updated",audit);self.assertNotIn("First",audit);self.assertNotIn("Second",audit)
            with self.assertRaisesRegex(ValueError,"refresh"):service.save("bagholder-supply",{"display_name":"Stale"},revision=first["revision"])
    def test_dashboard_is_sanitized_and_read_only(self):
        provider = unittest.mock.Mock(side_effect=AssertionError("provider call"))
        health = lambda profiles: {"state":"yellow","label":"Usable","systems":[{"id":"ollama","label":"Ollama","status":"unavailable","message":"Optional"}]}
        jobs = lambda: [{"job_id":"job-1","type":"commerce","status":"failed","updated_at":"now","payload":{"destination_name":"Bagholder"},"requires_approval":True,"approved":False}]
        value = ShellDashboardService(health=health,jobs=jobs).status([profile()])
        self.assertEqual(value["work"]["failed"][0]["publication_state"],"not_published")
        self.assertEqual(value["work"]["failed"][0]["order_state"],"not_created")
        self.assertNotIn("payload",str(value)); provider.assert_not_called()

    def test_secret_store_atomic_permissions_blank_preservation_and_delete_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"JamesOS"/"secrets.env"; store=ShellSecretStore(path)
            store.save("printify","private-secret-123")
            self.assertEqual(os.stat(path).st_mode & 0o777,0o600)
            self.assertNotIn("private-secret-123",str(store.status()))
            store.save("printify",""); self.assertIn("private-secret-123",path.read_text())
            status=next(x for x in store.status() if x["provider"]=="printify");self.assertEqual(status["masked"],"********-123");self.assertNotIn("private-secret-123",str(status))
            with self.assertRaises(PermissionError):store.delete("printify",confirmed=False)
            store.delete("printify",confirmed=True); self.assertNotIn("private-secret-123",path.read_text())
            with self.assertRaises(ValueError):store.save("unknown","value")

    def test_shell_contains_dashboard_admin_and_no_activity_or_second_draft_confirmation(self):
        with patch.object(api,"list_commerce_profiles",return_value=[profile()]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app").text
        for value in ("System status","Needs attention","Work in progress","Recent workspaces","Quick actions","Recent results","Provider credentials","Private-network access","Commerce profiles","Layouts and appearance","Diagnostics"):
            self.assertIn(value,text)
        self.assertNotIn("<strong>Activity</strong>",text);self.assertNotIn("id='activity'",text)
        self.assertIn("sessionStorage.setItem('jamesos-commerce-form'",text)
        self.assertNotIn("Confirm destination '+(selected()?.dataset.etsy",text)
        self.assertIn("type='password'",text);self.assertNotIn("11434",text)
        self.assertIn("data-profile-edit",text);self.assertIn("data-profile-cancel",text);self.assertIn("readonly",text);self.assertIn("Listing guidance defines the identifier",text)

    def test_legacy_new_product_route_redirects_to_shell(self):
        with patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/commerce/new",follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertEqual(response.headers["location"],"/app?view=commerce.new")

    def test_credential_routes_require_origin_csrf_and_valid_provider_and_never_return_secret(self):
        client=TestClient(api.app,base_url="http://127.0.0.1:8787")
        with tempfile.TemporaryDirectory() as temporary,patch.object(api,"ShellSecretStore",return_value=ShellSecretStore(Path(temporary)/"secrets.env")),patch.object(api,"_require_local"):
            bad=client.post("/app/admin/credentials/printify",json={"csrf_token":"bad","secret":"hidden"},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(bad.status_code,403)
            origin=client.post("/app/admin/credentials/printify",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"secret":"hidden"},headers={"Origin":"https://evil.invalid"});self.assertEqual(origin.status_code,403)
            unknown=client.post("/app/admin/credentials/unknown",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"secret":"hidden"},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(unknown.status_code,422)
            good=client.post("/app/admin/credentials/printify",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"secret":"hidden"},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(good.status_code,200);self.assertNotIn("hidden",good.text)


if __name__ == "__main__": unittest.main()
