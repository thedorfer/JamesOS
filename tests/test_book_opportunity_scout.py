from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from jamesos.agents.book_opportunity_scout import BookOpportunityScoutAgent
from jamesos.core import api
from jamesos.core.agency.manifest import AgencyManifest
from jamesos.core.agency.registry import DirectoryCatalogProvider
from jamesos.core.agency.service import AgencyService
from jamesos.core.agency.storage import AgencyStore
from jamesos.core.agents.models import AgentContext,AgentRequest
from jamesos.core.agents.ledger import RunLedger
from jamesos.services.book_opportunity_scout import BookConcept,BookOpportunityResearchRequest,BookOpportunityScoutService,DEFAULT_WEIGHTS,ManualResearchSource,METRICS,ScoringProfile,rank_candidates,score_candidate
from jamesos.services.book_research_adapters import AmazonPublicSearchAdapter,BrowserResponse,CachedThrottledBrowser,LiveResearchAdapters,PublicReviewInsightAdapter,PublicTrendAdapter,PublicWebSearchAdapter


DEFAULT={"market":"US","audience":"children ages 4-8","book_type":"coloring book","candidate_count":20,"result_count":5}


class BookOpportunityScoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();root=Path(self.temporary.name);self.ledger=RunLedger(root/"ledger.jsonl");self.service=BookOpportunityScoutService(root/"runs",ledger=self.ledger)
    def tearDown(self):self.temporary.cleanup()

    def test_manifest_catalog_identity_and_agent_discovery(self):
        manifest=AgencyManifest.from_dict(json.loads((Path(__file__).parents[1]/"agency/manifests/book-opportunity-scout.json").read_text()))
        self.assertEqual(manifest.package.agent_id,"jamesos.book-opportunity-scout");self.assertEqual(manifest.category,"Publishing");self.assertEqual(manifest.package.maximum_automatic_attempts,1);self.assertEqual(manifest.package.required_secret_handles,())
        agent=BookOpportunityScoutAgent(self.service);request=AgentRequest("task","run","flow","books.opportunity.research","test",input_payload=DEFAULT,idempotency_key="book")
        self.assertTrue(agent.discover(request)["accepted"]);self.assertFalse(agent.discover(AgentRequest("bad","run","flow","books.publish","test"))["accepted"]);self.assertEqual(len(agent.plan(request).steps),10)

    def test_existing_agency_lifecycle_hires_configures_and_places_scout_on_duty(self):
        class NoSecrets:
            def status(self,handle):return {"configured":False}
        agency=AgencyService(DirectoryCatalogProvider(Path(__file__).parents[1]/"agency/manifests"),AgencyStore(Path(self.temporary.name)/"agency-state.json"),NoSecrets());agent_id="jamesos.book-opportunity-scout"
        self.assertTrue(next(item for item in agency.catalog_items() if item["agent"]["agent_id"]==agent_id)["installed"] is False);self.assertTrue(agency.hire(agent_id)["confirmation_required"]);agency.hire(agent_id,confirmed=True)
        configuration=agency.configuration(agent_id);self.assertEqual(configuration["values"]["model"],"qwen3:14b");self.assertEqual(configuration["values"]["source_mode"],"demo")
        grants={"side_effects":["local_research_artifacts","local_candidate_decision"]};self.assertTrue(agency.update_permissions(agent_id,grants)["confirmation_required"]);agency.update_permissions(agent_id,grants,confirmed=True);self.assertTrue(agency.set_enabled(agent_id,True)["confirmation_required"]);agency.set_enabled(agent_id,True,confirmed=True);self.assertEqual(agency.details(agent_id)["status"],"active")

    def test_request_validation_boundaries(self):
        valid=BookOpportunityResearchRequest.from_dict(DEFAULT);self.assertEqual((valid.candidate_count,valid.result_count),(20,5))
        for update in ({"market":""},{"audience":""},{"book_type":""},{"candidate_count":4},{"candidate_count":101},{"result_count":0},{"result_count":21}):
            with self.subTest(update=update),self.assertRaises(ValueError):BookOpportunityResearchRequest.from_dict({**DEFAULT,**update})

    def test_scoring_weights_missing_evidence_boundaries_and_ties(self):
        self.assertEqual(sum(ScoringProfile().weights.values()),100)
        with self.assertRaises(ValueError):ScoringProfile(weights={**DEFAULT_WEIGHTS,"demand_signal":24})
        concept=BookConcept("concept-001","Fixture","audience","coloring book","angle","theme","evergreen","low","high");request=BookOpportunityResearchRequest.from_dict(DEFAULT)
        missing=score_candidate(concept,ManualResearchSource({}).collect(concept,request),ScoringProfile());self.assertEqual(missing["total_score"],0);self.assertEqual(missing["confidence"],0);self.assertEqual(set(missing["missing_evidence"]),set(METRICS))
        full=score_candidate(concept,ManualResearchSource({"concept-001":{metric:1 for metric in METRICS}}).collect(concept,request),ScoringProfile());self.assertEqual(full["total_score"],100);self.assertLessEqual(full["confidence"],1)
        tied=rank_candidates([{"candidate_id":"concept-002","total_score":50,"manual_review_required":False},{"candidate_id":"concept-001","total_score":50,"manual_review_required":False}]);self.assertEqual([item["candidate_id"] for item in tied],["concept-001","concept-002"])
        result=self.service.run(DEFAULT);scores={item["total_score"] for item in result["ranked_candidates"]};self.assertTrue(scores);self.assertEqual(result["ranked_candidates"],sorted(result["ranked_candidates"],key=lambda item:(item["manual_review_required"],-item["total_score"],item["candidate_id"])))

    def test_demo_processes_twenty_persists_evidence_and_returns_stable_safe_top_five(self):
        result=self.service.run(DEFAULT);root=self.service.root/result["run_id"]
        self.assertEqual(result["candidate_count"],20);self.assertEqual(len(result["ranked_candidates"]),20);self.assertEqual(len(result["top_candidates"]),5);self.assertTrue(result["fixture_evidence"]);self.assertTrue(BookOpportunityScoutService.verify(result)["verified"])
        self.assertTrue(all(set(item["score_breakdown"])==set(METRICS) and item["evidence_references"] for item in result["top_candidates"]));self.assertFalse(any(item["manual_review_required"] for item in result["top_candidates"]));self.assertEqual(result["side_effects"],{"provider_calls":0,"marketplace_writes":0,"publications":0,"purchases":0,"images_generated":0})
        for name in ("request.json","candidates.json","evidence.json","scoring-profile.json","results.json","report.html"):self.assertTrue((root/name).is_file())
        evidence=json.loads((root/"evidence.json").read_text());self.assertEqual(len(evidence),20*len(METRICS));self.assertTrue(all(row["source_type"]=="deterministic_fixture" for row in evidence));self.assertNotIn("api_key",json.dumps(result).casefold())

    def test_high_risk_concepts_are_excluded_and_verification_detects_corruption(self):
        result=self.service.run(DEFAULT);risky={item["concept"] for item in result["ranked_candidates"] if item["manual_review_required"]};self.assertTrue(any("Celebrity" in item for item in risky));self.assertTrue(any("Superhero" in item for item in risky));self.assertFalse(risky&{item["concept"] for item in result["top_candidates"]})
        broken=json.loads(json.dumps(result));broken["top_candidates"][0]["score_breakdown"].pop("demand_signal");self.assertFalse(BookOpportunityScoutService.verify(broken)["verified"])

    def test_demo_is_labeled_and_never_falls_back_to_hosted_ai(self):
        result=self.service.run(DEFAULT);self.assertEqual(result["research_label"],"DEMO");self.assertFalse(result["model"]["used"]);self.assertEqual(result["model"]["provider"],"ollama_local");self.assertEqual(result["side_effects"]["provider_calls"],0)

    def test_live_adapters_parse_saved_html_without_internet_and_persist_source_metadata(self):
        fixtures=Path(__file__).parent/"fixtures/book_scout"
        class FixtureBrowser:
            calls=[]
            def fetch(self,url,*,timeout):
                self.calls.append((url,timeout));name="amazon_search.html" if "amazon.com" in url else "trends.html" if "trends.google" in url else "web_search.html"
                return BrowserResponse(url,200,(fixtures/name).read_text(),"2026-07-19T12:00:00+00:00")
        browser=CachedThrottledBrowser(FixtureBrowser(),Path(self.temporary.name)/"cache",min_interval_seconds=0,sleep=lambda _:None)
        adapters=LiveResearchAdapters([AmazonPublicSearchAdapter(browser),PublicWebSearchAdapter(browser),PublicTrendAdapter(browser),PublicReviewInsightAdapter(browser)])
        service=BookOpportunityScoutService(Path(self.temporary.name)/"live-runs",ledger=self.ledger,live_adapters=adapters)
        result=service.run({**DEFAULT,"candidate_count":5,"source_mode":"live"});summary=result["research_summary"]
        self.assertEqual(result["research_label"],"LIVE");self.assertEqual(len(summary["sources_attempted"]),4);self.assertEqual(summary["sources_blocked"],[]);self.assertGreater(summary["evidence_collected"],0);self.assertIn("estimated_profitability",summary["missing_metrics"]);self.assertLess(summary["overall_confidence"],1)
        evidence=json.loads((service.root/result["run_id"] / "evidence.json").read_text());available=[row for row in evidence if row["collection_status"]=="available"]
        self.assertTrue(available);self.assertTrue(all(row["source_reference"].startswith("https://") and row["collection_timestamp"] and row["raw_value"] is not None for row in available));self.assertTrue(all("sales volume" in row["summary"] for row in available if row["source_id"].startswith("amazon")))
        amazon=next(row["raw_value"] for row in available if row["source_id"].startswith("amazon"));self.assertEqual(amazon["titles"][0],"Forest Friends Coloring Book");self.assertEqual(amazon["prices"][0],7.0);self.assertEqual(amazon["ratings"][0],4.7);self.assertEqual(amazon["review_counts"][0],1234);self.assertIn("Paperback",amazon["formats"]);self.assertTrue(amazon["publication_information"]);self.assertEqual(amazon["visible_bestseller_ranks"],[12345])
        self.assertEqual(result["side_effects"],{"provider_calls":0,"marketplace_writes":0,"publications":0,"purchases":0,"images_generated":0})

    def test_amazon_challenge_is_blocked_without_retry_or_bypass(self):
        fixtures=Path(__file__).parent/"fixtures/book_scout"
        class BlockedBrowser:
            calls=0
            def fetch(self,url,*,timeout):self.calls+=1;return BrowserResponse(url,200,(fixtures/"amazon_blocked.html").read_text(),"2026-07-19T12:00:00+00:00")
        raw=BlockedBrowser();browser=CachedThrottledBrowser(raw,Path(self.temporary.name)/"blocked-cache",min_interval_seconds=0,sleep=lambda _:None);rows=AmazonPublicSearchAdapter(browser).collect("test")
        self.assertEqual(rows[0].status,"blocked");self.assertEqual(rows[0].error,"challenge_detected");self.assertEqual(raw.calls,1)

    def test_public_browser_cache_timeout_and_bounded_retry(self):
        class Flaky:
            calls=0;timeouts=[]
            def fetch(self,url,*,timeout):
                self.calls+=1;self.timeouts.append(timeout)
                if self.calls==1:raise TimeoutError("fixture timeout")
                return BrowserResponse(url,200,"ok","2026-07-19T12:00:00+00:00")
        raw=Flaky();browser=CachedThrottledBrowser(raw,Path(self.temporary.name)/"retry-cache",min_interval_seconds=0,timeout=3,max_attempts=2,sleep=lambda _:None)
        first=browser.fetch("https://example.com/public");second=browser.fetch("https://example.com/public")
        self.assertEqual(raw.calls,2);self.assertEqual(raw.timeouts,[3,3]);self.assertEqual(first.body,"ok");self.assertGreaterEqual(second.cache_age_seconds,0)

    def test_decisions_preview_confirm_reject_save_and_idempotency_use_ledger(self):
        result=self.service.run(DEFAULT);candidate=result["top_candidates"][0]["candidate_id"]
        self.assertTrue(self.service.decide(result["run_id"],candidate,"approve")["confirmation_required"]);self.assertFalse((self.service.root/result["run_id"]/"decisions.json").exists())
        first=self.service.decide(result["run_id"],candidate,"approve",confirmed=True,reason="strong evidence");self.assertTrue(first["changed"]);repeat=self.service.decide(result["run_id"],candidate,"approve",confirmed=True,reason="strong evidence");self.assertTrue(repeat["idempotent"])
        self.assertEqual(self.service.decide(result["run_id"],candidate,"reject",confirmed=True)["action"],"reject");self.assertEqual(self.service.decide(result["run_id"],candidate,"save_for_later",confirmed=True)["action"],"save_for_later");self.assertTrue(any(row["capability"]=="books.opportunity.decide" for row in self.ledger.read()))

    def test_loaded_run_and_report_restore_each_saved_decision_without_downstream_work(self):
        for action,label in (("approve","Approved"),("reject","Rejected"),("save_for_later","Saved for Later")):
            result=self.service.run(DEFAULT);candidate=result["top_candidates"][0]["candidate_id"]
            saved=self.service.decide(result["run_id"],candidate,action,confirmed=True,reason=f"reason for {label}")
            loaded=self.service.load(result["run_id"]);restored=loaded["decisions"][candidate]
            self.assertEqual((restored["action"],restored["timestamp"],restored["reason"]),(action,saved["timestamp"],f"reason for {label}"))
            self.assertEqual(loaded["top_candidates"][0]["decision"],restored)
            report=(self.service.root/result["run_id"]/"report.html").read_text(encoding="utf-8")
            self.assertIn(label,report);self.assertIn(saved["timestamp"],report);self.assertIn(f"reason for {label}",report)
            if action=="approve":
                for expected in ("Approved for production planning","Coloring Book Producer is not installed yet. No book has been generated.","Create Book Project","Available after the Coloring Book Producer agent is installed."):self.assertIn(expected,report)
            self.assertNotIn("uploaded",report.casefold());self.assertNotIn("marketplace action",report.casefold())
            before=len(self.ledger.read());repeat=self.service.decide(result["run_id"],candidate,action,confirmed=True,reason=f"reason for {label}")
            self.assertTrue(repeat["idempotent"]);self.assertEqual(len(self.ledger.read()),before);self.assertEqual(loaded["side_effects"],{"provider_calls":0,"marketplace_writes":0,"publications":0,"purchases":0,"images_generated":0})

    def test_agent_execute_verify_and_nonpersistent_learning_proposal(self):
        agent=BookOpportunityScoutAgent(self.service);request=AgentRequest("task","run","flow","books.opportunity.research","test",input_payload=DEFAULT,idempotency_key="book");plan=agent.plan(request);execution=agent.execute(plan,AgentContext());verification=agent.verify(execution,AgentContext());proposal=agent.learn(None,AgentContext())
        self.assertEqual(execution.status,"completed");self.assertTrue(verification.verified);self.assertFalse(proposal.persist);self.assertEqual(execution.side_effects_completed,["local_research_artifacts"])

    def test_shell_api_csrf_validation_results_and_confirmation(self):
        client=TestClient(api.app,base_url="http://127.0.0.1:8787");headers={"Origin":"http://127.0.0.1:8787"}
        with patch.object(api,"BookOpportunityScoutService",return_value=self.service),patch.object(api,"_require_local"):
            self.assertEqual(client.post("/app/agency/book-scout/runs",json=DEFAULT,headers=headers).status_code,403)
            created=client.post("/app/agency/book-scout/runs",json={**DEFAULT,"csrf_token":api._COMMERCE_CREATE_CSRF},headers=headers);self.assertEqual(created.status_code,200);run=created.json();self.assertEqual(len(run["top_candidates"]),5)
            loaded=client.get(f"/app/agency/book-scout/runs/{run['run_id']}");self.assertEqual(loaded.status_code,200);self.assertEqual(client.get("/app/agency/book-scout/runs").json()["runs"][0]["run_id"],run["run_id"])
            path=f"/app/agency/book-scout/runs/{run['run_id']}/candidates/{run['top_candidates'][0]['candidate_id']}/decision";self.assertEqual(client.post(path,json={"action":"approve"},headers=headers).status_code,403)
            preview=client.post(path,json={"csrf_token":api._COMMERCE_CREATE_CSRF,"action":"approve"},headers=headers);self.assertTrue(preview.json()["confirmation_required"]);confirmed=client.post(path,json={"csrf_token":api._COMMERCE_CREATE_CSRF,"action":"approve","confirmed":True},headers=headers);self.assertTrue(confirmed.json()["changed"])

    def test_agency_ui_contains_scout_form_results_contract_and_no_publish_action(self):
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}}
        with patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=agency.book-scout").text
        for expected in ("Book Opportunity Scout","children ages 4–8","Candidate count","Result count","Research mode","Sources attempted","Run history","Save for Later","Installed"):
            self.assertIn(expected,text)
        self.assertNotIn("Publish book",text);self.assertNotIn("Amazon login",text)

    def test_chromium_runs_actual_scout_widget_and_displays_ranked_result(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required")
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}};result=self.service.run(DEFAULT)
        with patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=agency.book-scout");document=response.text.replace("</body>","<script>document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>document.querySelector('#book-scout-form button[type=submit]').click(),50))</script></body>")
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/app/agency/book-scout/runs"):body=json.dumps({"runs":[]}).encode();content="application/json"
                else:body=document.encode();content="text/html"
                self.send_response(200);self.send_header("Content-Type",content);self.end_headers();self.wfile.write(body)
            def do_POST(self):
                body=json.dumps(result).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=1500","--dump-dom",f"http://127.0.0.1:{server.server_port}/app?view=agency.book-scout"],check=True,capture_output=True,text=True).stdout
        finally:server.shutdown();server.server_close()
        self.assertIn("Rank: 1",rendered);self.assertIn("Total score:",rendered);self.assertIn("Confidence:",rendered);self.assertIn("Research label: DEMO",rendered);self.assertIn("Sources attempted: fixture.book-market.v1",rendered);self.assertIn("no publication or marketplace write",rendered);self.assertNotIn("Publish book",rendered)

    def test_chromium_decision_badge_is_immediate_and_restored_after_refresh(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required")
        result=self.service.run(DEFAULT);run_id=result["run_id"]
        profile={"profile_id":"bagholder-supply","display_name":"Bagholder","configuration":{"printify_shop_id":1,"etsy_shop_slug":"shop"}}
        with patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            document=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=agency.book-scout").text
        script="""<script>window.confirm=()=>true;document.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{const wait=()=>new Promise(r=>setTimeout(r,250));await wait();if(!sessionStorage.getItem('decision-refresh')){document.querySelector('#book-scout-results .agent-card button').click();await wait();sessionStorage.setItem('immediate',document.querySelector('#book-scout-results .agent-card').textContent);sessionStorage.setItem('decision-refresh','yes');location.reload()}else{await wait();const out=document.createElement('pre');out.id='decision-result';out.textContent=JSON.stringify({immediate:sessionStorage.getItem('immediate'),restored:document.querySelector('#book-scout-results .agent-card').textContent,disabled:document.querySelector('#book-scout-results .agent-card button[disabled]')?.textContent});document.body.append(out)}},200))</script>"""
        document=document.replace("</body>",script+"</body>")
        service=self.service
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path=="/app/agency/book-scout/runs":body=json.dumps({"runs":[{"run_id":run_id,"status":"completed","candidate_count":20}]}).encode();content="application/json"
                elif self.path==f"/app/agency/book-scout/runs/{run_id}":body=json.dumps(service.load(run_id)).encode();content="application/json"
                else:body=document.encode();content="text/html"
                self.send_response(200);self.send_header("Content-Type",content);self.end_headers();self.wfile.write(body)
            def do_POST(self):
                length=int(self.headers.get("Content-Length","0"));value=json.loads(self.rfile.read(length) or b"{}")
                candidate=self.path.split("/candidates/",1)[1].split("/",1)[0];record=service.decide(run_id,candidate,value["action"],confirmed=value.get("confirmed") is True,reason="browser reason")
                body=json.dumps(record).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=3500","--dump-dom",f"http://127.0.0.1:{server.server_port}/app?view=agency.book-scout"],check=True,capture_output=True,text=True).stdout
        finally:server.shutdown();server.server_close()
        for expected in ('"immediate":"Approved','"restored":"Approved',"browser reason","Approved for production planning","Coloring Book Producer is not installed yet. No book has been generated.","Create Book Project"):self.assertIn(expected,rendered)
        self.assertEqual(service.load(run_id)["side_effects"],{"provider_calls":0,"marketplace_writes":0,"publications":0,"purchases":0,"images_generated":0})


if __name__=="__main__":unittest.main()
