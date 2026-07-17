from __future__ import annotations
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from jamesos.core.agent_manager.compatibility import compatibility
from jamesos.core.agent_manager.discovery import discover_builtin,discover_entry_points
from jamesos.core.agent_manager.manager import AgentManager
from jamesos.core.agent_manager.manifest import ManifestValidationError,PackageManifest
from jamesos.core.agent_manager.permissions import compare_permissions
from jamesos.core.agent_manager.state import InstalledAgent,InstalledAgentStore
from jamesos.core.agent_manager.store_contract import *
from jamesos.core.agents.ledger import RunLedger
from jamesos.core.agents.models import AgentRequest
from jamesos.core.agents.runner import AgentRunner
from jamesos.core.profiles.bindings import ProfileBindingResolver
from jamesos.core.profiles.migration import commerce_shop_migration_plan
from jamesos.core.profiles.approval import complete_proposal_hash,final_approval,final_approval_matches,publication_workflow
from jamesos.core.profiles.models import AgentBinding,Profile
from jamesos.core.profiles.store import ProfileStore

ROOT=Path(__file__).parents[1]
def manifest(**changes):
    value={"schema_version":"1","protocol_version":"1.0.0","agent_id":"thirdparty","name":"Third Party","version":"1.2.3","publisher":"Publisher","description":"test","capabilities":["example.third.read"],"accepted_task_types":["read"],"emitted_result_types":["result"],"package_name":"third-party","entry_point":"third_party.agent:ThirdPartyAgent","owner":"Publisher","declared_permissions":{}}
    value.update(changes);return PackageManifest.from_dict(value)
class FakeDistribution:
    name="third-party";version="1.2.3"
class FakeEntryPoint:
    name="thirdparty";value="third_party.agent:ThirdPartyAgent";dist=FakeDistribution()
class FakeEntryPoints:
    def select(self,group):return [FakeEntryPoint()] if group=="jamesos.agents" else []

class AgentManagerTests(unittest.TestCase):
    def test_builtin_and_mock_entry_point_discovery_without_loading_code(self):
        self.assertEqual({item.agent_id for item in discover_builtin()},{"career","commerce","etsy","printify"})
        found=discover_entry_points(FakeEntryPoints());self.assertEqual(found[0].entry_point,"third_party.agent:ThirdPartyAgent");self.assertIsNone(found[0].agent)
    def test_manifest_schema_semver_compatibility_and_validation(self):
        self.assertEqual(compatibility(manifest()),"compatible")
        with self.assertRaises(ManifestValidationError):manifest(schema_version="2")
        with self.assertRaises(ManifestValidationError):manifest(version="latest")
        with self.assertRaises(ManifestValidationError):manifest(protocol_version="2.0.0")
        with self.assertRaises(ManifestValidationError):manifest(capabilities=["Bad Capability"])
        with self.assertRaises(ManifestValidationError):manifest(publisher="")
        with self.assertRaises(ManifestValidationError):manifest(entry_point="../bad:Agent")
    def test_install_remove_dry_run_no_pip_and_atomic_secret_free_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/"package";source.mkdir();(source/"jamesos-agent.json").write_text(json.dumps(manifest().to_dict()))
            store=InstalledAgentStore(root/"installed.json");manager=AgentManager(store,RunLedger(root/"ledger.jsonl"))
            plan=manager.install(source);self.assertTrue(plan["dry_run"]);self.assertFalse(plan["details"]["pip_executed"]);self.assertFalse(store.path.exists())
            applied=manager.install(source,True);self.assertTrue(applied["state_change_performed"]);self.assertTrue(store.path.exists());self.assertEqual(store.path.stat().st_mode&0o777,0o600)
            self.assertNotIn("token",store.path.read_text().lower());remove=manager.remove("thirdparty");self.assertTrue(remove["dry_run"]);self.assertFalse(remove["details"]["package_uninstall_performed"]);self.assertIn("thirdparty",store.load())
    def test_disabled_agents_do_not_load_and_bindings_survive_disable(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=InstalledAgentStore(Path(temporary)/"state.json");states={"etsy":InstalledAgent("etsy","jamesos","0.1.0","JamesOS","builtin",enabled=True,configured_profile_bindings=["commerce_shop"])};store.save(states)
            manager=AgentManager(store);self.assertEqual(manager.enabled_registry().find_capability("marketplace.listing.read")[0].agent_id,"etsy")
            manager.set_enabled("etsy",False,True);self.assertEqual(manager.enabled_registry().find_capability("marketplace.listing.read"),[]);self.assertEqual(store.load()["etsy"].configured_profile_bindings,["commerce_shop"])
            states=store.load();states["etsy"].enabled=True;states["etsy"].compatibility_status="incompatible_protocol";store.save(states);self.assertEqual(manager.enabled_registry().find_capability("marketplace.listing.read"),[])
    def test_duplicate_agent_ids_rejected(self):
        registry=AgentManager(InstalledAgentStore(Path(tempfile.mkdtemp())/"state.json")).enabled_registry();agent=discover_builtin()[0].agent
        with self.assertRaises(ValueError):registry.register(agent)
    def test_permissions_declared_granted_denied_are_separate(self):
        report=compare_permissions({"network_domains":["api.example"],"remote_writes":["listing"]},{"network_domains":["api.example"],"remote_writes":[]})
        self.assertEqual(report.granted["network_domains"],("api.example",));self.assertEqual(report.denied["remote_writes"],("listing",));self.assertNotIn("other",report.granted)
        with tempfile.TemporaryDirectory() as temporary:
            store=InstalledAgentStore(Path(temporary)/"state.json")
            with self.assertRaises(ValueError):store.save({"x":InstalledAgent("x","p","1.0.0","o","s",granted_permissions={"access_token":["bad"]})})
    def test_store_contract_pricing_types(self):self.assertEqual({item.value for item in PricingType},{"free","one_time","subscription","private"})

class ProfileTests(unittest.TestCase):
    def test_commerce_shop_is_generic_profile_with_handles_not_values(self):
        profile=commerce_shop_migration_plan();self.assertEqual(profile.profile_type,"commerce_shop");self.assertEqual(profile.agent_bindings["marketplace"].agent_id,"etsy");self.assertEqual(profile.agent_bindings["fulfillment"].agent_id,"printify")
        self.assertEqual(profile.configuration["approval_mode"],"single_final");self.assertEqual(profile.configuration["etsy_final_state"],"active")
        self.assertEqual(profile.configuration["human_review_location"],"jamesos_listing_preview");self.assertTrue(profile.configuration["preapproval_printify_draft_allowed"])
        self.assertEqual(profile.configuration["publish_policy"],"publish_active_after_approval")
        text=json.dumps(profile.to_dict());self.assertIn("etsy.commerce_shop",text);self.assertNotIn("access_token",text);self.assertNotIn("shared_secret",text)
        self.assertFalse((ROOT/"jamesos/agents/commerce_shop_agent.py").exists())
    def test_generic_agents_support_multiple_profiles_and_runner_uses_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=ProfileStore(temporary)
            for profile_id in ("shop-one","shop-two"):store.save(Profile(profile_id,"commerce_shop",profile_id,"owner",agent_bindings={"marketplace":AgentBinding("etsy",f"etsy.{profile_id}"),"fulfillment":AgentBinding("printify",f"printify.{profile_id}"),"orchestrator":AgentBinding("commerce")}))
            resolver=ProfileBindingResolver(store);registry=AgentManager(InstalledAgentStore(Path(temporary)/"agents.json")).enabled_registry(resolver)
            self.assertEqual(registry.resolve("marketplace.listing.read","shop-one").manifest.agent_id,"etsy");self.assertEqual(resolver.connection_handle_for("shop-two","marketplace.listing.read"),"etsy.shop-two")
            request=AgentRequest("task","run","flow","marketplace.listing.read","test",target_resources={"listing_id":1},input_payload={"dry_run":True,"profile_id":"shop-one"},idempotency_key="profile")
            result=AgentRunner(registry,RunLedger(Path(temporary)/"ledger.jsonl")).run(request);self.assertEqual(result["execution"].public_output["etsy_listing_id"],1)
    def test_profile_store_is_atomic_and_rejects_secret_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=ProfileStore(temporary);profile=commerce_shop_migration_plan();path=store.save(profile);self.assertEqual(path.stat().st_mode&0o777,0o600)
            profile.configuration["access_token"]="bad"
            with self.assertRaises(ValueError):store.save(profile)
    def test_approval_and_final_state_are_independent_validated_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=ProfileStore(temporary)
            for mode in ("single_final","staged"):
                for state in ("active","inactive"):
                    profile=Profile(f"p-{mode}-{state}".replace("_","-"),"commerce_shop","Profile","owner",configuration={"approval_mode":mode,"etsy_final_state":state})
                    store.save(profile)
            bad=Profile("bad-mode","commerce_shop","Bad","owner",configuration={"approval_mode":"candidate","etsy_final_state":"active"})
            with self.assertRaisesRegex(ValueError,"approval mode"):store.save(bad)
    def test_single_final_approval_binds_every_complete_proposal_component(self):
        proposal={"artwork":{"sha256":"art"},"product_configuration":{"variants":[1]},"mockups":[{"sha256":"mock"}],
            "listing_metadata":{"title":"Title"},"destination":{"shop_id":1},"expected_final_state":"active"}
        approval=final_approval(proposal,approved=True);self.assertTrue(final_approval_matches(proposal,approval))
        for field in proposal:
            changed=json.loads(json.dumps(proposal));changed[field]={"changed":True}
            self.assertNotEqual(complete_proposal_hash(changed),approval["proposal_sha256"]);self.assertFalse(final_approval_matches(changed,approval))
        workflow=publication_workflow(commerce_shop_migration_plan().configuration)
        self.assertEqual(workflow["capability"],"commerce.workflow.publish_active_after_approval");self.assertEqual(workflow["approval_scope"],"final-proposal")

class HelloAgentTests(unittest.TestCase):
    def test_example_manifest_and_agent_conform(self):
        source=ROOT/"examples/hello_agent";package=__import__("jamesos.core.agent_manager.package",fromlist=["inspect_package"]);inspection=package.inspect_package(source)
        self.assertEqual(inspection.manifest.agent_id,"hello");self.assertEqual(inspection.manifest.capabilities,("example.hello.read",));self.assertFalse(inspection.manifest.required_secret_handles)
        spec=importlib.util.spec_from_file_location("hello_agent_module",source/"hello_agent/agent.py");module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);agent=module.HelloAgent();self.assertEqual(agent.manifest.supported_side_effects,())

if __name__=="__main__":unittest.main()
