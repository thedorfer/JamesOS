import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.ehf_admin import EHFAdminService


class EHFAdminTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name);day=self.root/"2026-07-18";day.mkdir()
        self.error_id="err-20260718-120000-abcd1234"
        self.secret="super-secret-token";self.private="/home/james/JamesOSData/private/file.txt"
        self.path=day/f"{self.error_id}.json"
        self.path.write_text(json.dumps({"error_id":self.error_id,"occurred_at":datetime.now().astimezone().isoformat(),"severity":"error","code":"COMFYUI_FAILED","operation":"commerce_creation.background","stage":"artwork","user_message":"Local artwork generation failed safely.","retryable":True,"job_id":"job-123","run_id":"run-123","suggested_action":"Retry local generation.","context":{"authorization":self.secret,"private_path":self.private,"provider_contacted":False},"state":{"printify_draft_exists":False,"publication_status":"not_published","order_status":"not_created","validation_reasons":["No eligible candidates"]},"diagnostic_artifact_path":self.private}))
        self.service=EHFAdminService(self.root)

    def tearDown(self):self.temporary.cleanup()

    def test_projection_filters_summary_detail_and_export_are_sanitized(self):
        value=self.service.records({"severity":"error","operation":"commerce_creation.background","stage":"artwork","job":"job-123","resolved":"false","date_from":"2026-01-01","date_to":"2099-01-01"})
        self.assertEqual(len(value["records"]),1);self.assertEqual(value["summary"]["failed_commerce_jobs"],1)
        detail=self.service.detail(self.error_id);self.assertEqual(detail["publication_state"],"not_published");self.assertEqual(detail["order_state"],"not_created")
        rendered=json.dumps({"list":value,"detail":detail,"export":self.service.export()})
        self.assertNotIn(self.secret,rendered);self.assertNotIn(self.private,rendered);self.assertNotIn("diagnostic_artifact_path",rendered);self.assertNotIn("cause_chain",rendered)

    def test_acknowledge_and_resolve_update_existing_ehf_record_atomically(self):
        self.assertTrue(self.service.update(self.error_id,action="acknowledge")["acknowledged"])
        resolved=self.service.update(self.error_id,action="resolve");self.assertTrue(resolved["resolved"])
        persisted=json.loads(self.path.read_text());self.assertTrue(persisted["admin_state"]["resolved"]);self.assertFalse(list(self.path.parent.glob("*.tmp")))
        with self.assertRaises(ValueError):self.service.update("../../secret",action="resolve")
        with self.assertRaises(ValueError):self.service.update(self.error_id,action="execute")

    def test_routes_require_origin_csrf_and_valid_ids_without_provider_calls(self):
        client=TestClient(api.app,base_url="http://127.0.0.1:8787");provider=Mock(side_effect=AssertionError("provider called"))
        with patch.object(api,"EHFAdminService",return_value=self.service),patch.object(api,"_require_local"):
            listing=client.get("/app/admin/errors",headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(listing.status_code,200)
            self.assertNotIn(self.secret,listing.text);self.assertNotIn(self.private,listing.text)
            bad_origin=client.get("/app/admin/errors",headers={"Origin":"https://evil.invalid"});self.assertEqual(bad_origin.status_code,403)
            bad_csrf=client.post(f"/app/admin/errors/{self.error_id}/resolve",json={"csrf_token":"bad"},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(bad_csrf.status_code,403)
            invalid=client.get("/app/admin/errors/not-valid",headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(invalid.status_code,422)
            ok=client.post(f"/app/admin/errors/{self.error_id}/acknowledge",json={"csrf_token":api._COMMERCE_CREATE_CSRF},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(ok.status_code,200)
        provider.assert_not_called()

    def test_admin_exposes_ehf_controls_but_no_raw_log_access(self):
        profile={"profile_id":"p","display_name":"P","configuration":{"printify_shop_id":1,"printify_shop_title":"P","etsy_shop_slug":"P"}}
        with patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="p"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app").text
        for expected in ("Errors &amp; Diagnostics","Unresolved errors","Critical failures","Open associated job","Acknowledge","Mark resolved","Export sanitized report","textContent"):
            self.assertIn(expected,text)
        for forbidden in ("journalctl","/var/log","diagnostic_artifact_path","cause_chain",self.private,self.secret):self.assertNotIn(forbidden,text)


if __name__=="__main__":unittest.main()
