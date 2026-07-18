from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from jamesos.core.commerce.proposal import canonical_proposal_sha256
from jamesos.core.errors import StateConflictError
from jamesos.services import product_orchestrator
from jamesos.services.commerce_workflow import CommerceWorkflow
from jamesos.services.commerce_workflow import format_currency
from scripts import jamesos as jamesos_cli
from tests import test_product_orchestrator as product_tests


class CommerceWorkflowTests(unittest.TestCase):
    def test_inspect_draft_cli_is_read_only(self):
        workflow=SimpleNamespace(orchestrator=SimpleNamespace(inspect_draft=lambda job_id:{"result":"draft_ownership_inspection","job_id":job_id,"write_performed":False,"provider_write_performed":False}))
        output=StringIO()
        with patch.object(sys,"argv",["jamesos.py","commerce","inspect-draft","--job-id","job-1"]),redirect_stdout(output):self.assertEqual(jamesos_cli._main(workflow=workflow),0)
        result=json.loads(output.getvalue());self.assertEqual(result["job_id"],"job-1");self.assertFalse(result["provider_write_performed"])

    def test_currency_formatting(self):
        self.assertEqual(format_currency(2499,"USD"),"$24.99")
        self.assertEqual(format_currency(2500,"USD"),"$25.00")
        self.assertEqual(format_currency(5,"USD"),"$0.05")
    def fixture(self, root: Path):
        orchestrator,state,remote,replacement,client=product_tests.ProductOrchestratorTests().listing_fixture(root,product_id="private-product-fixture")
        artwork=root/"artwork.png";artwork.write_bytes(b"proposal-artwork")
        artwork_sha=product_orchestrator.sha256(artwork.read_bytes()).hexdigest()
        state["profile_id"]="private-profile-fixture";state["brief"].update(exact_text="PUBLIC PHRASE",garment_colors=product_orchestrator.DEFAULT_COLORS,
            sizes=product_orchestrator.DEFAULT_SIZES,currency="USD",blank="Public Model",print_provider="Public Provider")
        state["evidence"]["selection"]={"selected":{"png_path":str(artwork),"png_sha256":artwork_sha}}
        state["evidence"]["upload"]["selected_design_sha256"]=artwork_sha
        state["evidence"]["destination"]={"marketplace":"Etsy","expected_final_state":"inactive"}
        review_path=orchestrator._path("reconcile-job").parent/"visual-review"/"visual-review.json";review=json.loads(review_path.read_text())
        review["checks"].update(artwork_image_id=state["evidence"]["upload"]["printify_image_id"],artwork_image_id_matches=True,
            placement={"x":.5,"y":.46,"scale":.85,"angle":0})
        for item in review["checks"]["mockups"]:
            image=review_path.parent/{"Black":"black-front.png","Dark Grey Heather":"dark-grey-heather-front.png","White":"white-front.png"}[item["color"]]
            image.write_bytes(item["color"].encode())
        product_orchestrator._atomic_json(review_path,review);product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        return CommerceWorkflow(orchestrator),orchestrator,state,client

    def test_valid_job_creates_private_and_public_proposal_without_provider_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));result=workflow.prepare("reconcile-job")
            self.assertEqual(result["result"],"commerce_proposal_ready");self.assertEqual(result["stage"],"awaiting_final_approval")
            self.assertTrue(result["write_performed"]);self.assertFalse(result["external_write_performed"]);self.assertFalse(result["publish_performed"]);self.assertFalse(result["order_created"])
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";public=json.loads((root/"current.json").read_text());private=(root/"current-private.json")
            serialized=json.dumps(public).lower();self.assertNotIn("private-product-fixture",serialized);self.assertNotIn("upload-fixture",serialized);self.assertNotIn("1001",serialized)
            self.assertNotIn("secret:",serialized);self.assertNotIn("/home/",serialized);self.assertEqual(private.stat().st_mode&0o777,0o600)
            self.assertEqual(json.loads(private.read_text())["provider_binding"]["product_id"],"private-product-fixture")
            html=(root/"review.html").read_text();self.assertIn("NOT PUBLISHED",html);self.assertIn("NO ORDER CREATED",html);self.assertIn("AWAITING FINAL APPROVAL",html)
            self.assertIn("$24.99",html);self.assertNotIn("<h2>Warnings</h2>",html);self.assertNotIn("Required confirmations",html)
            self.assertNotIn("Final marketplace attributes require human review",html);self.assertNotIn("temporary public exposure",html)
            self.assertNotIn("method='post'",html);self.assertIn("Open through the JamesOS localhost review URL",html)
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called();client.create_product.assert_not_called()

    def test_prepare_is_deterministic_and_supersedes_differing_proposal(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));first=workflow.prepare("reconcile-job");second=workflow.prepare("reconcile-job")
            self.assertEqual(first["proposal_sha256"],second["proposal_sha256"]);self.assertFalse(second["write_performed"])
            with patch.object(product_orchestrator,"ETSY_TITLE","Changed Public Title"):
                third=workflow.prepare("reconcile-job")
            self.assertNotEqual(first["proposal_sha256"],third["proposal_sha256"])
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";archived=json.loads((root/"archive"/first["proposal_sha256"]/"proposal.json").read_text())
            self.assertTrue(archived["superseded"]);self.assertFalse(archived["approval_eligible"]);self.assertEqual(archived["superseded_by"],third["proposal_sha256"])
            self.assertTrue(json.loads((root/"current.json").read_text())["approval_eligible"])

    def test_invalid_metadata_ownership_and_visual_review_create_no_artifacts(self):
        cases=("metadata","ownership","visual","mockup","published","ordered","protected","unexpected_area","variants")
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temporary:
                workflow,orchestrator,state,client=self.fixture(Path(temporary));remote=client.get_product.return_value
                if case=="ownership":remote["id"]="other"
                elif case=="visual":json.loads((orchestrator._path("reconcile-job").parent/"visual-review"/"visual-review.json").read_text())
                elif case=="published":remote["is_published"]=True
                elif case=="ordered":remote["orders"]=[{"id":"order"}]
                elif case=="protected":
                    state["evidence"]["draft"]["printify_product_id"]=product_orchestrator.PROTECTED_PRODUCT_ID;product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
                elif case=="unexpected_area":remote["print_areas"][0]["placeholders"].append({"position":"sleeve","images":[{"id":"other"}]})
                elif case=="variants":next(item for item in remote["variants"] if item.get("is_enabled"))["is_enabled"]=False
                review_path=orchestrator._path("reconcile-job").parent/"visual-review"/"visual-review.json"
                if case in {"visual","mockup"}:
                    review=json.loads(review_path.read_text());review["checks"]["artwork_image_id_matches"]=False if case=="visual" else True
                    if case=="mockup":review["checks"]["mockups"][0]["downloaded_sha256"]=None
                    product_orchestrator._atomic_json(review_path,review)
                context=patch.object(product_orchestrator,"ETSY_TITLE","") if case=="metadata" else patch.object(product_orchestrator,"ETSY_TITLE",product_orchestrator.ETSY_TITLE)
                with context,self.assertRaises(Exception):workflow.prepare("reconcile-job")
                self.assertFalse((orchestrator._path("reconcile-job").parent/"commerce-proposal").exists())
                client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

    def test_status_review_and_cli_are_read_only_and_html_escapes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary))
            with patch.object(product_orchestrator,"ETSY_TITLE","Public <Title>"):
                prepared=workflow.prepare("reconcile-job")
            before=orchestrator._path("reconcile-job").read_bytes();status=workflow.status("reconcile-job");review=workflow.review("reconcile-job")
            self.assertTrue(status["proposal_current"]);self.assertEqual(status["next_allowed_action"],"review_or_approve");self.assertEqual(review["proposal_sha256"],prepared["proposal_sha256"])
            self.assertEqual(before,orchestrator._path("reconcile-job").read_bytes());self.assertIn("Public &lt;Title&gt;",Path(review["review_path"]).read_text())
            for command in ("prepare","status","review"):
                output=StringIO()
                with patch.object(sys,"argv",["jamesos.py","commerce",command,"--job-id","reconcile-job"]),redirect_stdout(output):
                    self.assertEqual(jamesos_cli._main(workflow),0)
                self.assertIn("reconcile-job",output.getvalue())
            with patch.object(sys,"argv",["jamesos.py","commerce","review","--job-id","reconcile-job","--open"]),patch.object(jamesos_cli.webbrowser,"open") as opened,redirect_stdout(StringIO()):
                self.assertEqual(jamesos_cli._main(workflow),0);opened.assert_called_once()
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

    def test_evidence_warning_is_hash_bound_and_rendered(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));state["evidence"]["commerce_warnings"]=["Actual <warning>"]
            product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state);result=workflow.prepare("reconcile-job")
            page=Path(result["review_path"]).read_text();self.assertIn("<h2>Warnings</h2>",page);self.assertIn("Actual &lt;warning&gt;",page)
            proposal=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current.json").read_text())
            changed=dict(proposal);changed["warnings"]=[]
            self.assertNotEqual(proposal["proposal_sha256"],canonical_proposal_sha256(changed))

    def test_malformed_job_ids_fail_without_path_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary))
            for job_id in ("", "../job", "/tmp/job", "a/b"):
                with self.subTest(job_id=job_id),self.assertRaises(Exception):workflow.status(job_id)

    def test_local_approval_and_revision_are_sha_bound_and_dry_run_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));prepared=workflow.prepare("reconcile-job");sha=prepared["proposal_sha256"]
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal"
            self.assertTrue(workflow.approve("reconcile-job",sha)["dry_run"]);self.assertFalse((root/"approval.json").exists())
            with self.assertRaises(Exception):workflow.approve("reconcile-job","0"*64,confirmed=True)
            result=workflow.approve("reconcile-job",sha,confirmed=True);self.assertFalse(result["dry_run"])
            self.assertEqual(json.loads((root/"approval.json").read_text())["proposal_sha256"],sha)
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

    def test_superseded_and_changed_evidence_refuse_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));sha=workflow.prepare("reconcile-job")["proposal_sha256"]
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";proposal=json.loads((root/"current.json").read_text())
            proposal["superseded"]=True;product_orchestrator._atomic_json(root/"current.json",proposal)
            with self.assertRaises(Exception):workflow.approve("reconcile-job",sha,confirmed=True)
            self.assertFalse((root/"approval.json").exists())
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));sha=workflow.prepare("reconcile-job")["proposal_sha256"]
            state=orchestrator.load("reconcile-job");state["evidence"]["listing"]["title"]="Evidence changed"
            product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            with self.assertRaises(Exception):workflow.approve("reconcile-job",sha,confirmed=True)
            self.assertFalse((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"approval.json").exists())
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));prepared=workflow.prepare("reconcile-job");sha=prepared["proposal_sha256"]
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";before=(root/"current.json").read_text()
            self.assertTrue(workflow.request_changes("reconcile-job",sha,note="Shorter title")["dry_run"]);self.assertEqual(before,(root/"current.json").read_text())
            workflow.request_changes("reconcile-job",sha,note="Use <shorter> title",confirmed=True)
            self.assertTrue((root/"revision-request.json").is_file());self.assertIn("Use <shorter> title",(root/"revision-request.json").read_text())
            self.assertFalse(json.loads((root/"current.json").read_text())["approval_eligible"])
            with self.assertRaises(Exception):workflow.request_changes("reconcile-job",sha,note="x"*1001)
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

    def test_real_browser_review_session_and_approval(self):
        from fastapi.testclient import TestClient
        from jamesos.core import api
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));prepared=workflow.prepare("reconcile-job");sha=prepared["proposal_sha256"]
            class BrowserExecutor:
                def execute(inner,**kwargs):
                    root=orchestrator._path("reconcile-job").parent/"commerce-proposal";approval=json.loads((root/"approval.json").read_text())
                    product_orchestrator._atomic_json(root/"publication-execution.json",{"proposal_sha256":sha,"status":"completed","approved_at":approval["approved_at"],
                        "publication_started_at":"now","completed_at":"now","marketplace":"Etsy","verified_final_state":"inactive","provider_update_verified":True,"order_created":False})
                    current=orchestrator.load("reconcile-job");current.update(stage="completed",publish_status="published");product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),current)
                    return {"result":"commerce_publication_completed"}
            launched=workflow.review("reconcile-job");parts=urlsplit(launched["review_url"]);bootstrap=parts.query.removeprefix("session=")
            session_path=orchestrator._path("reconcile-job").parent/"commerce-proposal"/"review-session.json"
            self.assertTrue(launched["write_performed"]);self.assertEqual(session_path.stat().st_mode&0o777,0o600)
            self.assertNotIn(bootstrap,session_path.read_text());self.assertNotIn("test-key",launched["review_url"]+session_path.read_text())
            with patch.object(api,"CommerceWorkflow",return_value=workflow),patch.object(api,"_require_local"),patch.object(api,"_commerce_publication_executor",return_value=BrowserExecutor()):
                client=TestClient(api.app,base_url="http://127.0.0.1:9999")
                initial=client.get(parts.path+"?"+parts.query,follow_redirects=False)
                self.assertEqual(initial.status_code,303);self.assertEqual(initial.headers["location"],parts.path)
                self.assertEqual(initial.headers["referrer-policy"],"no-referrer")
                cookie=initial.headers["set-cookie"];self.assertIn("HttpOnly",cookie);self.assertIn("SameSite=strict",cookie);self.assertIn("Max-Age=",cookie)
                self.assertIn("Path=/commerce/proposals/reconcile-job",cookie);self.assertNotIn("test-key",cookie)
                self.assertNotIn(bootstrap,initial.headers["location"])
                self.assertNotEqual(client.get(parts.path+"?"+parts.query,follow_redirects=False).status_code,303)
                page=client.get(parts.path);self.assertEqual(page.status_code,200);self.assertEqual(page.headers["referrer-policy"],"origin");self.assertIn("method='post'",page.text)
                self.assertIn("Approve &amp; Publish",page.text);self.assertIn("Request changes",page.text);self.assertNotIn("private-product-fixture",page.text)
                empty=TestClient(api.app,base_url="http://127.0.0.1:8787")
                self.assertNotEqual(empty.get(parts.path).status_code,200)
                self.assertNotEqual(empty.get(parts.path+"?session=wrong",follow_redirects=False).status_code,303)
                csrf=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current-private.json").read_text())["csrf_token"]
                origin={"Origin":"http://127.0.0.1:8787","Host":"127.0.0.1:8787"}
                self.assertEqual(client.post(parts.path.removesuffix("/review")+"/approve",headers=origin,data={"proposal_sha256":sha}).status_code,403)
                self.assertEqual(client.post(parts.path.removesuffix("/review")+"/approve",data={"proposal_sha256":sha,"csrf_token":csrf}).status_code,403)
                response=client.post(parts.path.removesuffix("/review")+"/approve",headers=origin,data={"proposal_sha256":sha,"csrf_token":csrf})
                self.assertEqual(response.status_code,200);self.assertIn("PUBLISHED SUCCESSFULLY",response.text);self.assertIn("Description",response.text)
                self.assertIn("Approved at:",response.text);self.assertIn(sha,response.text);self.assertIn("id='publication-result'",response.text);self.assertIn("NO ORDER CREATED",response.text)
                self.assertEqual(response.headers["referrer-policy"],"origin")
                self.assertNotIn("method='post'",response.text);self.assertNotEqual(client.get(parts.path).status_code,200)
                self.assertEqual(workflow.status("reconcile-job")["next_allowed_action"],"completed")
            provider.update_product.assert_not_called();provider.publish_product.assert_not_called();provider.create_order.assert_not_called()

    def test_browser_revokes_session_and_renders_safe_terminal_receipts(self):
        from fastapi.testclient import TestClient
        from jamesos.core import api
        outcomes={
            "marketplace_listing_pending":("MARKETPLACE LISTING PENDING","RUN READ-ONLY RECONCILIATION"),
            "provider_update_uncertain":("PROVIDER UPDATE RESULT UNCERTAIN","DO NOT RETRY"),
            "publication_uncertain":("PUBLICATION RESULT UNCERTAIN","DO NOT CLICK PUBLISH AGAIN"),
            "publication_failed":("PUBLICATION NOT SUBMITTED","NO ORDER CREATED"),
        }
        for stage,phrases in outcomes.items():
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as temporary:
                workflow,orchestrator,state,provider=self.fixture(Path(temporary));prepared=workflow.prepare("reconcile-job");sha=prepared["proposal_sha256"]
                launch=workflow.review("reconcile-job");parts=urlsplit(launch["review_url"])
                class TerminalExecutor:
                    def execute(inner,**kwargs):
                        current=orchestrator.load("reconcile-job");current["stage"]=stage;product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),current)
                        raise StateConflictError("PUBLICATION_STATE_CONFLICT",diagnostic_message="safe test failure",operation="test",stage=stage,retryable=False)
                with patch.object(api,"CommerceWorkflow",return_value=workflow),patch.object(api,"_require_local"),patch.object(api,"_commerce_publication_executor",return_value=TerminalExecutor()):
                    client=TestClient(api.app,base_url="http://127.0.0.1:8787");client.get(parts.path+"?"+parts.query,follow_redirects=False)
                    private=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current-private.json").read_text())
                    response=client.post(parts.path.removesuffix("/review")+"/approve",headers={"Origin":"http://127.0.0.1:8787","Host":"127.0.0.1:8787"},
                        data={"proposal_sha256":sha,"csrf_token":private["csrf_token"]})
                    self.assertEqual(response.status_code,200)
                    for phrase in phrases:self.assertIn(phrase,response.text)
                    self.assertNotIn("private-product-fixture",response.text);self.assertNotEqual(client.get(parts.path).status_code,200)
                provider.update_product.assert_not_called();provider.publish_product.assert_not_called();provider.create_order.assert_not_called()

    def test_browser_request_changes_expiration_and_evidence_invalidation(self):
        from fastapi.testclient import TestClient
        from jamesos.core import api
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));sha=workflow.prepare("reconcile-job")["proposal_sha256"]
            launch=workflow.review("reconcile-job");parts=urlsplit(launch["review_url"])
            with patch.object(api,"CommerceWorkflow",return_value=workflow),patch.object(api,"_require_local"):
                client=TestClient(api.app,base_url="http://127.0.0.1:8787");client.get(parts.path+"?"+parts.query,follow_redirects=False)
                csrf=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current-private.json").read_text())["csrf_token"]
                response=client.post(parts.path.removesuffix("/review")+"/request-changes",headers={"Origin":"http://localhost:8787","Host":"localhost:8787"},
                    data={"proposal_sha256":sha,"csrf_token":csrf,"note":"Shorter title"})
                self.assertEqual(response.status_code,202);self.assertIn("REGENERATION PENDING",response.text);self.assertIn("Description",response.text)
                self.assertIn("OLD PROPOSAL CANNOT BE APPROVED",response.text);self.assertIn("Shorter title",response.text);self.assertIn("id='revision-result'",response.text)
                self.assertEqual(response.headers["referrer-policy"],"origin")
                self.assertNotEqual(client.get(parts.path).status_code,200)
                self.assertEqual(workflow.status("reconcile-job")["next_allowed_action"],"revise_proposal")
            provider.update_product.assert_not_called();provider.publish_product.assert_not_called();provider.create_order.assert_not_called()

    def test_browser_request_changes_accepts_crlf_and_failures_render_safe_receipt(self):
        from fastapi.testclient import TestClient
        from jamesos.core import api
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));sha=workflow.prepare("reconcile-job")["proposal_sha256"]
            launch=workflow.review("reconcile-job");parts=urlsplit(launch["review_url"])
            with patch.object(api,"CommerceWorkflow",return_value=workflow),patch.object(api,"_require_local"):
                client=TestClient(api.app,base_url="http://127.0.0.1:8787");client.get(parts.path+"?"+parts.query,follow_redirects=False)
                private=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current-private.json").read_text())
                response=client.post(parts.path.removesuffix("/review")+"/request-changes",headers={"Origin":"http://127.0.0.1:8787","Host":"127.0.0.1:8787"},
                    data={"proposal_sha256":sha,"csrf_token":private["csrf_token"],"note":"New composition\r\nNo heart"})
                revision=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"revision-request.json").read_text())
                self.assertEqual(response.status_code,202);self.assertEqual(revision["note"],"New composition\nNo heart");self.assertTrue(revision["force_new_composition"])
            provider.update_product.assert_not_called();provider.publish_product.assert_not_called();provider.create_order.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));sha=workflow.prepare("reconcile-job")["proposal_sha256"]
            launch=workflow.review("reconcile-job");parts=urlsplit(launch["review_url"])
            with patch.object(api,"CommerceWorkflow",return_value=workflow),patch.object(api,"_require_local"):
                client=TestClient(api.app,base_url="http://127.0.0.1:8787");client.get(parts.path+"?"+parts.query,follow_redirects=False)
                private=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current-private.json").read_text())
                response=client.post(parts.path.removesuffix("/review")+"/request-changes",headers={"Origin":"http://127.0.0.1:8787","Host":"127.0.0.1:8787"},
                    data={"proposal_sha256":sha,"csrf_token":private["csrf_token"],"note":""})
                self.assertEqual(response.status_code,422);self.assertIn("Revision request failed",response.text);self.assertIn("Anything changed:</strong> no",response.text)
                self.assertFalse((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"revision-request.json").exists())
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));workflow.prepare("reconcile-job");launch=workflow.review("reconcile-job")
            session_path=orchestrator._path("reconcile-job").parent/"commerce-proposal"/"review-session.json";session=json.loads(session_path.read_text())
            session["expires_at"]="2000-01-01T00:00:00+00:00";product_orchestrator._atomic_json(session_path,session)
            with self.assertRaises(Exception):workflow.establish_browser_session("reconcile-job",urlsplit(launch["review_url"]).query.removeprefix("session="))

    def test_browser_cookie_and_loopback_are_proposal_scoped(self):
        from fastapi import HTTPException
        from jamesos.core import api
        with self.assertRaises(HTTPException):api._require_local(SimpleNamespace(client=SimpleNamespace(host="192.0.2.10")))
        api._require_local(SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")))
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));workflow.prepare("reconcile-job");launch=workflow.review("reconcile-job")
            token=urlsplit(launch["review_url"]).query.removeprefix("session=");cookie,_=workflow.establish_browser_session("reconcile-job",token)
            workflow.authenticate_browser_session("reconcile-job",cookie)
            with self.assertRaises(Exception):workflow.authenticate_browser_session("reconcile-job","another-proposal-cookie")

    def test_legacy_proposal_without_generation_summary_remains_reviewable(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));workflow.prepare("reconcile-job")
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";proposal=json.loads((root/"current.json").read_text());private=json.loads((root/"current-private.json").read_text())
            proposal.pop("design_generation_summary",None);legacy_sha=canonical_proposal_sha256(proposal);proposal["proposal_sha256"]=legacy_sha;private["proposal_sha256"]=legacy_sha
            product_orchestrator._atomic_json(root/"current.json",proposal);product_orchestrator._atomic_json(root/"current-private.json",private)
            state=orchestrator.load("reconcile-job");state["evidence"]["commerce_proposal"]["proposal_sha256"]=legacy_sha;product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            result=workflow.review("reconcile-job");self.assertEqual(result["proposal_sha256"],legacy_sha);self.assertTrue((root/"review-session.json").is_file())
            self.assertFalse((root/"approval.json").exists());self.assertFalse((root/"revision-request.json").exists());self.assertFalse((root/"publication-execution.json").exists())
            provider.update_product.assert_not_called();provider.publish_product.assert_not_called();provider.create_order.assert_not_called()

    def test_review_conflict_has_actionable_safe_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));workflow.prepare("reconcile-job")
            state=orchestrator.load("reconcile-job");state["stage"]="completed";state["publish_status"]="published";product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            with self.assertRaises(Exception) as raised:workflow.review("reconcile-job")
            self.assertEqual(raised.exception.stage,"review_eligibility");self.assertIn("failing_validation",raised.exception.context);self.assertIn("safe_state",raised.exception.context)
            self.assertFalse((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"review-session.json").exists())
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,provider=self.fixture(Path(temporary));workflow.prepare("reconcile-job");launch=workflow.review("reconcile-job")
            state=orchestrator.load("reconcile-job");state["evidence"]["listing"]["title"]="changed";product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            with self.assertRaises(Exception):workflow.establish_browser_session("reconcile-job",urlsplit(launch["review_url"]).query.removeprefix("session="))

    def test_browser_mutation_origin_validation(self):
        from fastapi import HTTPException
        from jamesos.core import api
        def request(origin,host="127.0.0.1:8787"):
            headers={}
            if origin is not None:headers["origin"]=origin
            if host is not None:headers["host"]=host
            return SimpleNamespace(headers=headers,scope={"server":("0.0.0.0",43210)})
        valid=(("http://127.0.0.1:8787","127.0.0.1:8787"),("http://localhost:8787","localhost:8787"),("http://[::1]:8787","[::1]:8787"))
        for origin,host in valid:
            with self.subTest(origin=origin,host=host):api._validate_commerce_origin(request(origin,host))
        invalid=(None,"null","not an origin","http://127.0.0.1:9999","https://127.0.0.1:8787","http://example.com:8787",
            "http://user@127.0.0.1:8787","http://127.0.0.1:8787/path","http://127.0.0.1:8787?query","http://127.0.0.1:8787#fragment",
            "http://127.0.0.1:not-a-port","http://[::1")
        for origin in invalid:
            with self.subTest(origin=origin),self.assertRaises(HTTPException):api._validate_commerce_origin(request(origin))
        invalid_pairs=(("http://localhost:8787","127.0.0.1:8787"),("http://127.0.0.1:8787","127.0.0.1:9999"),
            ("http://127.0.0.1:8787",None),("http://127.0.0.1:8787","example.com:8787"),
            ("http://127.0.0.1:8787","127.0.0.1:8787, example.com"),("http://127.0.0.1:8787","user@127.0.0.1:8787"))
        for origin,host in invalid_pairs:
            with self.subTest(origin=origin,host=host),self.assertRaises(HTTPException):api._validate_commerce_origin(request(origin,host))
        duplicate_headers=SimpleNamespace(getlist=lambda name:["http://127.0.0.1:8787","http://localhost:8787"] if name=="origin" else ["127.0.0.1:8787"],get=lambda name:None)
        with self.assertRaises(HTTPException):api._validate_commerce_origin(SimpleNamespace(headers=duplicate_headers,scope={"server":("0.0.0.0",43210)}))

if __name__=="__main__":unittest.main()
