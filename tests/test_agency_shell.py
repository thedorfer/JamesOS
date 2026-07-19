import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.core.agency.shell_registry import ADMIN_OPERATIONS,ShellAgencyRegistry


class AgencyShellTests(unittest.TestCase):
    def test_installed_idle_and_real_running_states_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"state.json";idle=ShellAgencyRegistry(path).snapshot();merchant=next(x for x in idle["agents"] if x["agent_id"]=="merchant")
            self.assertEqual((merchant["installation_state"],merchant["enabled_state"],merchant["runtime_state"]),("installed","enabled","idle"));self.assertEqual(idle["running_now"],[])
            run={"run_id":"run-1","agent_id":"merchant","state":"running","operation":"commerce.prepare","job_id":"job-1","stage":"artwork","provider_contacted":False}
            active=ShellAgencyRegistry(path,runs=lambda:[run]).snapshot();self.assertEqual(next(x for x in active["agents"] if x["agent_id"]=="merchant")["runtime_state"],"running");self.assertEqual(active["running_now"][0]["run_id"],"run-1")
            completed=ShellAgencyRegistry(path,runs=lambda:[{**run,"state":"completed"}]).snapshot();self.assertEqual(next(x for x in completed["agents"] if x["agent_id"]=="merchant")["runtime_state"],"idle");self.assertEqual(completed["running_now"],[])

    def test_core_protection_optional_mutations_revision_and_retention(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"state.json";service=ShellAgencyRegistry(path);revision=service.snapshot()["revision"]
            with self.assertRaises(PermissionError):service.mutate("jade","remove",confirmed=True,revision=revision)
            preview=service.mutate("merchant","remove",confirmed=False,revision=revision);self.assertIn("commerce jobs",preview["retained"]);self.assertFalse(preview["changed"])
            disabled=service.mutate("merchant","disable",confirmed=True,revision=revision);self.assertTrue(disabled["changed"]);self.assertEqual(os.stat(path).st_mode&0o777,0o600)
            with self.assertRaisesRegex(ValueError,"refresh"):service.mutate("merchant","remove",confirmed=True,revision=revision)
            serialized=path.read_text();self.assertNotIn("api_key",serialized.casefold());self.assertNotIn("bearer ",serialized.casefold());self.assertNotIn("secret_value",serialized.casefold())

    def test_administrator_is_allowlisted_and_marketplace_is_planned_only(self):
        value=ShellAgencyRegistry(Path("/nonexistent/agency-state")).snapshot();admin=next(x for x in value["agents"] if x["agent_id"]=="administrator")
        self.assertEqual(set(admin["capabilities"]),set(ADMIN_OPERATIONS));self.assertNotIn("file.write",admin["capabilities"]);self.assertFalse(any("shell" in x for x in admin["capabilities"]))
        self.assertTrue(all(item["implementation_state"]=="planned" for item in value["catalog"]));self.assertEqual({x["name"] for x in value["catalog"]},{"The Mechanic","The Archivist","The Scribe"})

    def test_shell_api_requires_csrf_and_unknown_ids_fail_closed(self):
        client=TestClient(api.app,base_url="http://127.0.0.1:8787")
        with tempfile.TemporaryDirectory() as temporary,patch.object(api,"ShellAgencyRegistry",side_effect=lambda:ShellAgencyRegistry(Path(temporary)/"state.json")),patch.object(api,"_require_local"):
            state=client.get("/app/agency",headers={"Origin":"http://127.0.0.1:8787"}).json();revision=state["revision"]
            bad=client.post("/app/agency/agents/merchant/disable",json={"revision":revision,"confirmed":True},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(bad.status_code,403)
            unknown=client.post("/app/agency/agents/unknown/remove",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"revision":revision,"confirmed":True},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(unknown.status_code,422)
            core=client.post("/app/agency/agents/jade/remove",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"revision":revision,"confirmed":True},headers={"Origin":"http://127.0.0.1:8787"});self.assertEqual(core.status_code,403)

    def test_shell_renders_default_registry_marketplace_and_safe_actions(self):
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}}
        with tempfile.TemporaryDirectory() as temporary,patch.object(api,"ShellAgencyRegistry",side_effect=lambda:ShellAgencyRegistry(Path(temporary)/"state.json")),patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=client=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=agency.home").text
        for expected in ("My Agents","Marketplace","Runs","Approvals","Updates","Jade","The Merchant","The Administrator","Installed · Enabled · Idle","No agents are currently running.","Open Product Studio","Open Admin","Permission review","Planned"):
            self.assertIn(expected,text)
        self.assertIn("minmax(300px,1fr)",text);self.assertNotIn("file.write",text);self.assertNotIn("Registered tools appear here",text);self.assertNotIn("Active agents",text)


if __name__=="__main__":unittest.main()
