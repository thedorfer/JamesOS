from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs,urlsplit

from jamesos.agents import CommerceAgent,EtsyAgent,PrintifyAgent
from jamesos.core.agents.approvals import ApprovalPolicy
from jamesos.core.agents.capabilities import ToolBroker
from jamesos.core.agents.ledger import RunLedger
from jamesos.core.agents.models import *
from jamesos.core.agents.protocol import AgentDefaults
from jamesos.core.agents.registry import AgentRegistry
from jamesos.core.agents.runner import AgentRunner
from jamesos.core.profiles.bindings import ProfileBindingResolver
from jamesos.core.profiles.models import AgentBinding,Profile
from jamesos.core.profiles.store import ProfileStore
from jamesos.integrations.etsy_client import EtsyClient
from jamesos.integrations import etsy_oauth

class DummyAgent(AgentDefaults):
    manifest=AgentManifest("dummy","Dummy","1","test",("test.read","test.write"),supported_side_effects=("test.write",),maximum_automatic_attempts=1)
    def __init__(self):self.calls=0
    def plan(self,request):return AgentPlan(request.task_id,"dummy",[AgentStep("one",request.requested_capability,"test",request.risk_level)])
    def execute(self,plan,context):self.calls+=1;return AgentExecutionResult("completed",{"ok":True},side_effects_completed=["test.write"])
    def verify(self,execution,context):return AgentVerificationResult("verified",True)

class CycleAgent(AgentDefaults):
    manifest=AgentManifest("cycle","Cycle","1","test",("test.cycle",))
    def plan(self,request):return AgentPlan(request.task_id,"cycle")
    def execute(self,plan,context):return AgentExecutionResult("planned",{},follow_up_task_requests=[AgentTaskRequest("test.cycle",idempotency_key="cycle-child")])
    def verify(self,execution,context):return AgentVerificationResult("verified",True)

class AgentCoreTests(unittest.TestCase):
    def request(self,**changes):
        value=dict(task_id="task",run_id="run",workflow_id="flow",requested_capability="test.read",requesting_agent_id="test",idempotency_key="stable")
        value.update(changes);return AgentRequest(**value)
    def test_registry_discovery_runner_idempotency_approval_and_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            agent=DummyAgent();registry=AgentRegistry();registry.register(agent);self.assertEqual(registry.find_capability("test.read")[0].agent_id,"dummy")
            ledger=RunLedger(Path(temporary)/"ledger.jsonl");runner=AgentRunner(registry,ledger)
            first=runner.run(self.request());second=runner.run(self.request());self.assertIs(first,second);self.assertEqual(agent.calls,1)
            self.assertTrue(all("secret" not in json.dumps(item).lower() for item in ledger.read()));before=len(ledger.read());runner.run(self.request(task_id="two",idempotency_key="second"));self.assertGreater(len(ledger.read()),before)
            remote=self.request(task_id="remote",idempotency_key="remote",risk_level=RiskLevel.REMOTE_WRITE,approval_requirement=ApprovalRequirement(True,"scope"),requested_capability="test.write")
            with self.assertRaises(PermissionError):runner.run(remote)
            runner.run(remote,"approved:scope");self.assertEqual(agent.calls,3)
            with self.assertRaises(RuntimeError):runner.run(self.request(task_id="deep",idempotency_key="deep",trace_depth=9))
            with self.assertRaises(RuntimeError):runner.run(self.request(task_id="attempts",idempotency_key="attempts",attempt_limit=2))
            self.assertFalse(ApprovalPolicy().evaluate(self.request(risk_level=RiskLevel.ORDER),"approved"));self.assertFalse(ApprovalPolicy().evaluate(self.request(risk_level=RiskLevel.FINANCIAL),"approved"))
            cycle_registry=AgentRegistry();cycle_registry.register(CycleAgent())
            with self.assertRaisesRegex(RuntimeError,"cycle"):AgentRunner(cycle_registry,RunLedger(Path(temporary)/"cycles.jsonl")).run(self.request(requested_capability="test.cycle",idempotency_key="cycle"))
    def test_manifests_capabilities_and_commerce_only_requests_child_work(self):
        registry=AgentRegistry()
        for agent in (CommerceAgent(),PrintifyAgent(),EtsyAgent()):registry.register(agent)
        self.assertEqual(registry.find_capability("marketplace.listing.deactivate")[0].agent_id,"etsy")
        request=AgentRequest("task","run","flow","commerce.workflow.publish_to_inactive_review","cli",input_payload={"job_id":"job","dry_run":True},idempotency_key="key")
        plan=registry.get("commerce").plan(request);self.assertEqual([item.requested_capability for item in plan.follow_up_tasks],["marketplace.listing.read","commerce.product.publish","marketplace.listing.deactivate"])
        source=Path(__file__).parents[1]/"jamesos/agents/commerce_agent.py";text=source.read_text();self.assertNotIn("PrintifyClient",text);self.assertNotIn("EtsyClient",text)
        proposal=registry.get("commerce").learn(None,None);self.assertFalse(proposal.persist)
    def test_active_final_workflow_publishes_once_then_only_verifies_active(self):
        agent=CommerceAgent();request=AgentRequest("task","run","flow","commerce.workflow.publish_active_after_approval","cli",input_payload={"job_id":"job","dry_run":False,"proposal_sha256":"abc"},idempotency_key="final")
        plan=agent.plan(request);self.assertEqual([item.requested_capability for item in plan.follow_up_tasks],["commerce.product.publish","marketplace.listing.verify_state"])
        self.assertEqual(plan.follow_up_tasks[0].approval_requirement.scope,"final-proposal");self.assertEqual(plan.follow_up_tasks[1].risk_level,RiskLevel.READ)
        self.assertEqual(plan.follow_up_tasks[0].approval_requirement.reference,"abc")
        self.assertFalse(plan.follow_up_tasks[1].approval_requirement.required);self.assertNotIn("marketplace.listing.deactivate",[item.requested_capability for item in plan.follow_up_tasks])

class EtsyTests(unittest.TestCase):
    def test_client_headers_get_and_single_form_patch(self):
        session=Mock();response=Mock(status_code=200);response.json.return_value={"listing_id":1,"shop_id":2,"state":"active"};session.request.return_value=response
        client=EtsyClient({"keystring":"key","shared_secret":"shared","access_token":"token"},session=session)
        client.get_listing(1);get=session.request.call_args;self.assertEqual(get.args[0],"GET");self.assertEqual(get.kwargs["headers"]["x-api-key"],"key:shared")
        client.update_listing_state(2,1,"inactive");patch=session.request.call_args;self.assertEqual(patch.args[0],"PATCH");self.assertEqual(patch.kwargs["data"],{"state":"inactive"})
        self.assertEqual(patch.kwargs["headers"]["Content-Type"],"application/x-www-form-urlencoded")
        with self.assertRaises(ValueError):client.update_listing_state(2,1,"draft")
    def test_etsy_agent_active_patches_once_inactive_does_not_patch(self):
        for state,calls in (("active",1),("inactive",0)):
            client=Mock();client.get_listing.side_effect=[{"listing_id":1,"shop_id":77,"title":"Title","state":state},{"listing_id":1,"shop_id":77,"state":"inactive"}]
            broker=ToolBroker();broker.register("etsy.client",lambda _secret:client);agent=EtsyAgent();request=AgentRequest("task","run","flow","marketplace.listing.deactivate","cli",target_resources={"listing_id":1},input_payload={"dry_run":False,"expected_title":"Title"})
            plan=agent.plan(request);execution=agent.execute(plan,AgentContext(tool_broker=broker));agent.verify(execution,AgentContext(tool_broker=broker))
            self.assertEqual(client.update_listing_state.call_count,calls)
            if calls:client.update_listing_state.assert_called_once_with(77,1,"inactive")
    def test_oauth_pkce_state_scope_single_use_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);app=root/"app.json";pending=root/"pending.json";token=root/"token.json"
            app.write_text(json.dumps({"keystring":"key","shared_secret":"shared","redirect_uri":"https://example.test/oauth"}));app.chmod(0o600)
            started=etsy_oauth.start(app,pending,now=100);query=parse_qs(urlsplit(started["authorization_url"]).query)
            self.assertEqual(query["code_challenge_method"],["S256"]);self.assertEqual(query["scope"],["listings_r listings_w"]);self.assertNotIn("verifier",json.dumps(started).lower())
            stored=json.loads(pending.read_text());self.assertGreaterEqual(len(stored["verifier"]),43);self.assertEqual(stored["scopes"],["listings_r","listings_w"]);self.assertEqual(pending.stat().st_mode&0o777,0o600)
            session=Mock();response=Mock();response.json.return_value={"access_token":"private","token_type":"Bearer","refresh_token":"refresh","expires_in":3600};response.raise_for_status.return_value=None;session.post.return_value=response
            callback=f'https://example.test/oauth?code=abc&state={stored["state"]}';result=etsy_oauth.complete(callback,app,pending,token,session,now=101)
            self.assertTrue(result["ready_for_etsy_write"]);self.assertNotIn("private",json.dumps(result));self.assertFalse(pending.exists());self.assertEqual(token.stat().st_mode&0o777,0o600)
            saved=json.loads(token.read_text());self.assertEqual(saved["scopes"],["listings_r","listings_w"]);self.assertEqual(saved["expires_at"],3701);self.assertEqual(saved["refresh_expires_at"],101+90*86400)
            status=etsy_oauth.status(app,token,now=102);self.assertTrue(status["ready_for_etsy_read"]);self.assertTrue(status["ready_for_etsy_write"]);self.assertTrue(status["required_scopes_present"])
            with self.assertRaises(PermissionError):etsy_oauth.complete(callback,app,pending,token,session,now=103)
            pending.write_text(json.dumps({**stored,"created_at":0,"used":False}));pending.chmod(0o600)
            with self.assertRaises(ValueError):etsy_oauth.complete(callback,app,pending,token,session,now=1000)
    def test_oauth_rejects_missing_requested_scope_and_state_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);app=root/"app.json";pending=root/"pending.json";token=root/"token.json"
            app.write_text(json.dumps({"keystring":"key","shared_secret":"shared","redirect_uri":"https://example.test/oauth"}));app.chmod(0o600);etsy_oauth.start(app,pending,now=100);stored=json.loads(pending.read_text())
            callback="https://example.test/oauth?code=hidden-code&state=wrong"
            with self.assertRaisesRegex(ValueError,"state mismatch"):etsy_oauth.complete(callback,app,pending,token,Mock(),now=101)
            self.assertFalse(json.loads(pending.read_text())["used"]);stored["scopes"]=["listings_r"];pending.write_text(json.dumps(stored));pending.chmod(0o600)
            callback=f'https://example.test/oauth?code=hidden-code&state={stored["state"]}'
            with self.assertRaisesRegex(ValueError,"did not request required"):etsy_oauth.complete(callback,app,pending,token,Mock(),now=101)
            self.assertFalse(token.exists())
    def test_oauth_failed_exchange_consumes_pending_without_partial_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);app=root/"app.json";pending=root/"pending.json";token=root/"token.json"
            app.write_text(json.dumps({"keystring":"key","shared_secret":"shared","redirect_uri":"https://example.test/oauth"}));app.chmod(0o600);etsy_oauth.start(app,pending,now=100);stored=json.loads(pending.read_text());callback=f'https://example.test/oauth?code=hidden-code&state={stored["state"]}'
            session=Mock();session.post.side_effect=RuntimeError("response with private-token")
            with self.assertRaisesRegex(RuntimeError,"run start again"):etsy_oauth.complete(callback,app,pending,token,session,now=101)
            self.assertTrue(json.loads(pending.read_text())["used"]);self.assertFalse(token.exists())
            with self.assertRaisesRegex(ValueError,"already consumed"):etsy_oauth.complete(callback,app,pending,token,session,now=102)
    def test_oauth_refresh_preserves_effective_scopes_and_updates_expirations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);app=root/"app.json";token=root/"token.json";app.write_text(json.dumps({"keystring":"key","shared_secret":"shared","redirect_uri":"https://example.test/oauth"}));app.chmod(0o600)
            token.write_text(json.dumps({"access_token":"old","refresh_token":"old-refresh","expires_at":100,"refresh_expires_at":10000,"scopes":["listings_r","listings_w"]}));token.chmod(0o600)
            session=Mock();response=Mock();response.json.return_value={"access_token":"new-private","refresh_token":"new-refresh","expires_in":3600};response.raise_for_status.return_value=None;session.post.return_value=response
            result=etsy_oauth.refresh(app,token,session,now=200);self.assertTrue(result["ready_for_etsy_write"]);self.assertNotIn("new-private",json.dumps(result));saved=json.loads(token.read_text())
            self.assertEqual(saved["scopes"],["listings_r","listings_w"]);self.assertEqual(saved["expires_at"],3800);self.assertEqual(saved["refresh_expires_at"],200+90*86400);self.assertEqual(token.stat().st_mode&0o777,0o600);self.assertEqual(session.post.call_count,1)

class CombinedWorkflowTests(unittest.TestCase):
    def runtime(self,temporary,etsy_factory,printify_factory):
        registry=AgentRegistry()
        for agent in (CommerceAgent(),PrintifyAgent(),EtsyAgent()):registry.register(agent)
        broker=ToolBroker();broker.register("etsy.client",lambda _secret:etsy_factory());broker.register("printify.orchestrator",lambda _secret:printify_factory())
        return AgentRunner(registry,RunLedger(Path(temporary)/"ledger.jsonl"),tool_broker=broker)
    def request(self,product_id="safe",dry=False):
        return AgentRequest("root","run","flow","commerce.workflow.publish_to_inactive_review","cli",{"job_id":"job","listing_id":1,"product_id":product_id},
            {"job_id":"job","dry_run":dry,"expected_title":"Title"},RiskLevel.PUBLICATION if not dry else RiskLevel.READ,
            ApprovalRequirement(not dry,"publish-and-deactivate"),"workflow-key")
    def test_ordering_external_id_single_writes_and_exposure_timestamps(self):
        with tempfile.TemporaryDirectory() as temporary:
            events=[];etsy=Mock()
            def get_listing(listing_id):events.append(f"etsy-get-{listing_id}");return {"listing_id":listing_id,"shop_id":77,"title":"Title","state":"active" if events.count(f"etsy-get-{listing_id}")==1 else "inactive"}
            etsy.get_listing.side_effect=get_listing;etsy.update_listing_state.side_effect=lambda shop,listing,state:events.append(f"etsy-patch-{listing}")
            printify=Mock();printify.send_to_etsy_review.side_effect=lambda job,confirmed:(events.append("printify-publish") or {"publish_performed":True,"etsy_listing_id":9})
            result=self.runtime(temporary,lambda:etsy,lambda:printify).run(self.request(),"approved:publish-and-deactivate")
            self.assertEqual(events[:2],["etsy-get-1","printify-publish"]);self.assertIn("etsy-patch-9",events);self.assertEqual(etsy.update_listing_state.call_count,1);self.assertEqual(printify.send_to_etsy_review.call_count,1)
            output=result["execution"].public_output;self.assertEqual(output["etsy_listing_id"],9);self.assertGreater(output["public_exposure_window_seconds"],0)
            self.assertTrue(output["printify_publication_timestamp"]);self.assertTrue(output["external_id_discovery_timestamp"]);self.assertTrue(output["etsy_deactivation_request_timestamp"]);self.assertTrue(output["etsy_inactive_verification_timestamp"])
    def test_missing_oauth_blocks_printify_and_dry_run_calls_no_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            printify=Mock();blocked=self.runtime(temporary,lambda:(_ for _ in ()).throw(PermissionError("OAuth unavailable")),lambda:printify)
            with self.assertRaises(PermissionError):blocked.run(self.request(),"approved:publish-and-deactivate")
            printify.send_to_etsy_review.assert_not_called()
            etsy_factory=Mock();printify_factory=Mock();dry=self.runtime(temporary,etsy_factory,printify_factory).run(self.request(dry=True))
            self.assertEqual(dry["execution"].public_output["task_graph"],["marketplace.listing.read","commerce.product.publish","marketplace.listing.deactivate"]);etsy_factory.assert_not_called();printify_factory.assert_not_called()
    def test_failed_deactivation_is_urgent_without_retry_delete_unpublish_or_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            etsy=Mock();etsy.get_listing.return_value={"listing_id":1,"shop_id":77,"title":"Title","state":"active"};etsy.update_listing_state.side_effect=RuntimeError("PATCH failed")
            printify=Mock();printify.send_to_etsy_review.return_value={"publish_performed":True,"etsy_listing_id":1}
            result=self.runtime(temporary,lambda:etsy,lambda:printify).run(self.request(),"approved:publish-and-deactivate");output=result["execution"].public_output
            self.assertEqual(result["execution"].status,"urgent_manual_review");self.assertTrue(output["possible_public_exposure"]);self.assertEqual(output["etsy_listing_id"],1)
            self.assertFalse(output["automatic_delete"]);self.assertFalse(output["automatic_unpublish"]);self.assertFalse(output["order_created"]);self.assertEqual(etsy.update_listing_state.call_count,1)
    def test_public_agent_manifest_embeds_no_deployment_product_ids(self):
        self.assertEqual(PrintifyAgent.manifest.protected_resources,())

    def test_private_profile_protection_is_runtime_only_and_blocks_product(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=ProfileStore(Path(temporary)/"profiles");store.save(Profile("private-shop","commerce_shop","Private","owner",
                agent_bindings={"fulfillment":AgentBinding("printify","printify.private")},
                protected_resources=["printify:product:protected-product"]))
            registry=AgentRegistry(ProfileBindingResolver(store));registry.register(PrintifyAgent())
            self.assertEqual(PrintifyAgent.manifest.protected_resources,())
            runner=AgentRunner(registry,RunLedger(Path(temporary)/"ledger.jsonl"))
            request=AgentRequest("protected","run","flow","commerce.product.publish","test",target_resources={"product_id":"protected-product"},
                input_payload={"profile_id":"private-shop","job_id":"job","dry_run":True},idempotency_key="protected")
            with self.assertRaisesRegex(PermissionError,"protected resource"):runner.run(request)

if __name__=="__main__":unittest.main()
