import json
import os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import tempfile
import threading
import unittest
from pathlib import Path
import shutil
import subprocess
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

    def test_administrator_is_allowlisted_and_marketplace_contains_installable_scout(self):
        value=ShellAgencyRegistry(Path("/nonexistent/agency-state")).snapshot();admin=next(x for x in value["agents"] if x["agent_id"]=="administrator")
        self.assertEqual(set(admin["capabilities"]),set(ADMIN_OPERATIONS));self.assertNotIn("file.write",admin["capabilities"]);self.assertFalse(any("shell" in x for x in admin["capabilities"]))
        scout=next(x for x in value["catalog"] if x["agent_id"]=="jamesos.book-opportunity-scout");self.assertEqual((scout["name"],scout["category"],scout["version"],scout["implementation_state"],scout["installed"]),("Book Opportunity Scout","Publishing","0.1.0","implemented",False));self.assertNotIn("Planned",scout["description"])

    def test_scout_install_disable_remove_uses_existing_confirmed_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            service=ShellAgencyRegistry(Path(temporary)/"state.json");revision=service.snapshot()["revision"];agent_id="jamesos.book-opportunity-scout"
            preview=service.mutate(agent_id,"install",confirmed=False,revision=revision);self.assertTrue(preview["confirmation_required"]);self.assertIn("public read-only research",preview["permissions"])
            installed=service.mutate(agent_id,"install",confirmed=True,revision=revision);self.assertTrue(installed["changed"]);snapshot=service.snapshot();scout=next(x for x in snapshot["agents"] if x["agent_id"]==agent_id);self.assertEqual((scout["installed_version"],scout["enabled_state"],scout["workspace"]),("0.1.0","enabled","agency.book-scout"))
            disabled=service.mutate(agent_id,"disable",confirmed=True,revision=installed["revision"]);removed=service.mutate(agent_id,"remove",confirmed=True,revision=disabled["revision"]);self.assertTrue(removed["changed"]);self.assertFalse(next(x for x in service.snapshot()["catalog"] if x["agent_id"]==agent_id)["installed"])

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
        for expected in ("My Agents","Marketplace","Runs","Approvals","Updates","Jade","The Merchant","The Administrator","Book Opportunity Scout","Publishing · JamesOS · 0.1.0","Install / Hire","Installed · Enabled · Idle","No agents are currently running.","Open Product Studio","Open Admin","Permission review","Planned"):
            self.assertIn(expected,text)
        self.assertIn("minmax(300px,1fr)",text);self.assertNotIn("file.write",text);self.assertNotIn("Registered tools appear here",text);self.assertNotIn("Active agents",text)

    def test_direct_book_scout_url_layout_history_and_installed_details_are_available(self):
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}}
        with tempfile.TemporaryDirectory() as temporary:
            registry=ShellAgencyRegistry(Path(temporary)/"state.json");revision=registry.snapshot()["revision"];registry.mutate("jamesos.book-opportunity-scout","install",confirmed=True,revision=revision)
            with patch.object(api,"ShellAgencyRegistry",return_value=registry),patch.object(api,"BookOpportunityScoutService",side_effect=lambda:__import__("jamesos.services.book_opportunity_scout",fromlist=["BookOpportunityScoutService"]).BookOpportunityScoutService(Path(temporary)/"runs")),patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"LayoutManager",side_effect=lambda:__import__("jamesos.services.layout_manager",fromlist=["LayoutManager"]).LayoutManager(Path(temporary)/"layouts")),patch.object(api,"_require_local"):
                client=TestClient(api.app,base_url="http://127.0.0.1:8787");page=client.get("/app?view=agency.book-scout");layout=client.get("/app/layouts/agency.book-scout");history=client.get("/app/agency/book-scout/runs");details=client.get("/app/agency/agents/jamesos.book-opportunity-scout")
        self.assertEqual((page.status_code,layout.status_code,history.status_code,details.status_code),(200,200,200,200));self.assertIn('initialView="agency.book-scout"',page.text);self.assertIn("Book Opportunity Scout",page.text);self.assertIn("book-scout-form",page.text);self.assertEqual(layout.json()["view_id"],"agency.book-scout");self.assertEqual(history.json(),{"runs":[]})

    def test_chromium_installs_scout_from_marketplace_and_opens_workspace(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required")
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}}
        with tempfile.TemporaryDirectory() as temporary:
            registry=ShellAgencyRegistry(Path(temporary)/"state.json")
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path.startswith("/app/agency/book-scout/runs"):body=json.dumps({"runs":[]}).encode();content="application/json"
                    elif self.path.startswith("/app?"):
                        response=client.get(self.path);document=response.text.replace("</body>","<script>window.confirm=()=>true;document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{const open=document.querySelector('[data-view=\"agency.book-scout\"]');if(open){open.click();document.body.dataset.scoutOpened='true'}else{document.querySelector('[data-agency-tab=\"marketplace\"]').click();document.querySelector('[data-agent-action=\"install\"]').click()}},100))</script></body>");body=document.encode();content="text/html"
                    elif self.path.startswith("/app/health"):body=b'{"state":"green","label":"Ready","systems":[]}';content="application/json"
                    elif self.path.startswith("/app/access-status"):body=b'{"access_mode":"loopback","warning":""}';content="application/json"
                    else:body=b'{}';content="application/json"
                    self.send_response(200);self.send_header("Content-Type",content);self.end_headers();self.wfile.write(body)
                def do_POST(self):
                    length=int(self.headers.get("Content-Length","0"));values=json.loads(self.rfile.read(length) or b"{}");action=self.path.rsplit("/",1)[-1];result=registry.mutate("jamesos.book-opportunity-scout",action,confirmed=values.get("confirmed") is True,revision=int(values["revision"]));body=json.dumps(result).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(body)
                def log_message(self,*args):pass
            with patch.object(api,"ShellAgencyRegistry",return_value=registry),patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
                client=TestClient(api.app,base_url="http://127.0.0.1:8787");server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
                try:rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=3000","--dump-dom",f"http://127.0.0.1:{server.server_port}/app?view=agency.home"],capture_output=True,text=True,check=True,timeout=30).stdout
                finally:server.shutdown();server.server_close()
            self.assertIn('data-scout-opened="true"',rendered);self.assertIn("Open Scout",rendered);self.assertIn("Run Scout",rendered);self.assertIn("Book Opportunity Scout",rendered);self.assertTrue(next(x for x in registry.snapshot()["catalog"] if x["agent_id"]=="jamesos.book-opportunity-scout")["installed"])

    def test_chromium_open_scout_navigation_refresh_and_layout_request(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required")
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}}
        with tempfile.TemporaryDirectory() as temporary:
            registry=ShellAgencyRegistry(Path(temporary)/"state.json");registry.mutate("jamesos.book-opportunity-scout","install",confirmed=True,revision=registry.snapshot()["revision"]);layout_statuses=[]
            with patch.object(api,"ShellAgencyRegistry",return_value=registry),patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"LayoutManager",side_effect=lambda:__import__("jamesos.services.layout_manager",fromlist=["LayoutManager"]).LayoutManager(Path(temporary)/"layouts")),patch.object(api,"_require_local"):
                client=TestClient(api.app,base_url="http://127.0.0.1:8787")
                script="""<script>document.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{const wait=()=>new Promise(r=>setTimeout(r,150)),visible=n=>n&&getComputedStyle(n).display!=='none'&&!n.hidden,collect=async()=>{const layout=await fetch('/app/layouts/agency.book-scout'),runs=await fetch('/app/agency/book-scout/runs'),scout=document.getElementById('book-scout-workspace'),dashboard=document.getElementById('dashboard-view');return {url:location.search.includes('view=agency.book-scout'),heading:scout?.textContent.includes('Book Opportunity Scout'),form:visible(document.getElementById('book-scout-form')),scout:visible(scout),dashboard:visible(dashboard),layout:layout.status,runs:runs.status}};if(!sessionStorage.getItem('scout-refresh')){document.querySelector('[data-view=\"agency.book-scout\"]').click();await wait();sessionStorage.setItem('scout-before',JSON.stringify(await collect()));sessionStorage.setItem('scout-refresh','yes');location.reload()}else{const refreshed=await collect();history.back();await wait();const backHome=location.search.includes('view=agency.home')&&visible(document.querySelector('[data-agency-section=my-agents]'));history.forward();await wait();const result={before:JSON.parse(sessionStorage.getItem('scout-before')),refreshed,backHome,after:await collect()};const out=document.createElement('pre');out.id='scout-routing-result';out.textContent=JSON.stringify(result);document.body.append(out)}},150))</script>"""
                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        response=client.get(self.path)
                        if self.path.startswith("/app/layouts/agency.book-scout"):layout_statuses.append(response.status_code)
                        body=response.content;content=response.headers.get("content-type","application/json")
                        if self.path.startswith("/app?"):body=response.text.replace("</body>",script+"</body>").encode()
                        self.send_response(response.status_code);self.send_header("Content-Type",content);self.end_headers();self.wfile.write(body)
                    def log_message(self,*args):pass
                server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
                try:rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=6000","--dump-dom",f"http://127.0.0.1:{server.server_port}/app?view=agency.home"],capture_output=True,text=True,check=True,timeout=40).stdout
                finally:server.shutdown();server.server_close()
        self.assertIn('"url":true',rendered);self.assertIn('"heading":true',rendered);self.assertIn('"form":true',rendered);self.assertIn('"scout":true',rendered);self.assertIn('"dashboard":false',rendered);self.assertIn('"layout":200',rendered);self.assertIn('"runs":200',rendered);self.assertIn('"backHome":true',rendered);self.assertTrue(layout_statuses);self.assertNotIn(422,layout_statuses)


if __name__=="__main__":unittest.main()
