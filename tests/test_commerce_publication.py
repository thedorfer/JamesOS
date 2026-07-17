from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jamesos.services import product_orchestrator
from jamesos.services.commerce_publication import CommercePublicationExecutor,EtsyMarketplaceAdapter,PrintifyProviderDraftAdapter
from tests import test_commerce_workflow


class FakeProvider:
    def __init__(self,remote,*,ambiguous=False):self.remote=deepcopy(remote);self.ambiguous=ambiguous;self.get_calls=0;self.update_calls=0;self.publish_calls=0
    def get_product(self,shop,product):self.get_calls+=1;return deepcopy(self.remote)
    def update_product(self,shop,product,payload):
        self.update_calls+=1;self.remote.update(title=payload["title"],description=payload["description"],tags=payload["tags"],variants=deepcopy(payload["variants"]),print_areas=deepcopy(payload["print_areas"]));return {"ok":True}
    def publish_product(self,shop,product,payload):
        self.publish_calls+=1;self.remote["is_published"]=True;self.remote["external"]={"id":"private-listing","state":"inactive","handle":"https://example.test/listing"}
        if self.ambiguous:raise TimeoutError("ambiguous timeout")
        return {"external":{"id":"private-listing"}}


class FakeMarketplace:
    def __init__(self,state="inactive",resolve=True):self.state=state;self.resolve=resolve;self.resolve_calls=0;self.read_calls=0
    def resolve_listing(self,*,product_binding,publication_evidence):self.resolve_calls+=1;return {"id":"private-listing"} if self.resolve else None
    def get_listing_state(self,listing_binding):self.read_calls+=1;return {"state":self.state,"public_url":"https://example.test/listing"}


class CommercePublicationTests(unittest.TestCase):
    def test_visibility_alone_never_proves_publication(self):
        state={"publish_status":"not_published","transitions":[],"evidence":{"draft":{"publish_status":"not_published"}}}
        result=product_orchestrator.assess_draft_publication_state(state,{"visible":True,"is_locked":False,"external":{}})
        self.assertEqual(result["publication_classification"],"UNPUBLISHED_DRAFT");self.assertFalse(any(x["field"]=="remote.visible" for x in result["explicit_blockers"]))
    def fixture(self,root:Path,*,matching=True,ambiguous=False,market_state="inactive"):
        workflow,orchestrator,state,client=test_commerce_workflow.CommerceWorkflowTests().fixture(root);prepared=workflow.prepare("reconcile-job");sha=prepared["proposal_sha256"]
        workflow.approve("reconcile-job",sha,confirmed=True);proposal=json.loads(Path(prepared["proposal_path"]).read_text());private=json.loads((Path(prepared["proposal_path"]).parent/"current-private.json").read_text())
        remote={"id":private["provider_binding"]["product_id"],"is_published":False,"title":proposal["title"] if matching else "old title",
            "description":proposal["description"],"tags":proposal["tags"],"variants":[{"id":item,"price":proposal["price_cents"],"is_enabled":True} for item in proposal["enabled_variants"]],
            "print_areas":[{"placeholders":[{"position":"front","images":[{"id":private["provider_binding"]["upload_id"],**proposal["placement"]}]}]}]}
        provider=FakeProvider(remote,ambiguous=ambiguous);market=FakeMarketplace(market_state);executor=CommercePublicationExecutor(workflow,provider=provider,marketplace=market)
        return workflow,orchestrator,executor,provider,market,sha,proposal

    def test_dry_run_then_publish_once_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
            journal=orchestrator._path("reconcile-job").parent/"commerce-proposal"/"publication-execution.json"
            dry=executor.execute(job_id="reconcile-job",proposal_sha256=sha);self.assertTrue(dry["dry_run"]);self.assertEqual(provider.get_calls,0);self.assertEqual(provider.update_calls,0);self.assertEqual(provider.publish_calls,0);self.assertFalse(journal.exists())
            result=executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(result["result"],"commerce_publication_completed");self.assertEqual(provider.update_calls,0);self.assertEqual(provider.publish_calls,1)
            self.assertFalse(result["order_created"]);self.assertEqual(orchestrator.load("reconcile-job")["stage"],"completed")
            repeated=executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True);self.assertEqual(repeated["completed_at"],result["completed_at"]);self.assertEqual(provider.publish_calls,1)
            self.assertEqual(journal.stat().st_mode&0o777,0o600);self.assertEqual(json.loads(journal.read_text())["external_write_count"],1)

    def test_metadata_update_once_and_verification_precedes_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary),matching=False)
            executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.update_calls,1);self.assertEqual(provider.publish_calls,1)
            journal=json.loads((orchestrator._path("reconcile-job").parent/"commerce-proposal"/"publication-execution.json").read_text())
            self.assertEqual(journal["steps"]["provider_update_verification"]["outcome"],"completed");self.assertEqual(journal["external_write_count"],2)

    def test_ambiguous_publish_never_retries_and_read_only_reconciliation_can_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary),ambiguous=True)
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.publish_calls,1);self.assertEqual(orchestrator.load("reconcile-job")["stage"],"publication_uncertain")
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.publish_calls,1)
            result=executor.reconcile(job_id="reconcile-job",proposal_sha256=sha);self.assertEqual(result["stage"],"completed");self.assertEqual(provider.publish_calls,1)

    def test_final_state_mismatch_and_protected_product_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary),market_state="active")
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.publish_calls,1);self.assertEqual(orchestrator.load("reconcile-job")["stage"],"publication_failed")
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";private=json.loads((root/"current-private.json").read_text())
            with unittest.mock.patch.object(product_orchestrator,"PROTECTED_PRODUCT_ID",private["provider_binding"]["product_id"]):
                with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.publish_calls,0);self.assertEqual(provider.update_calls,0)

    def test_etsy_adapter_uses_exact_durable_id_and_authoritative_state(self):
        class Etsy:
            def __init__(self):self.calls=[]
            def get_listing(self,listing_id):
                self.calls.append(listing_id);return {"listing_id":listing_id,"shop_id":44,"state":"inactive","url":"https://www.etsy.com/listing/901/example"}
        etsy=Etsy();adapter=EtsyMarketplaceAdapter(etsy,44)
        listing=adapter.resolve_listing(provider_product={"external":{"id":"901","title":"never match this"}},publication_evidence={})
        self.assertEqual(listing,{"id":901});self.assertEqual(etsy.calls,[901])
        self.assertEqual(adapter.get_listing_state(901),{"state":"inactive","public_url":"https://www.etsy.com/listing/901/example"})
        self.assertIsNone(adapter.resolve_listing(provider_product={"title":"same title"},publication_evidence={}))

    def test_etsy_adapter_rejects_wrong_shop_and_unsafe_url(self):
        class Etsy:
            def get_listing(self,listing_id):return {"shop_id":99,"state":"inactive","url":"https://private.example/listing/1"}
        with self.assertRaises(Exception):EtsyMarketplaceAdapter(Etsy(),44).resolve_listing(provider_product={"external":{"listing_id":1}},publication_evidence={})
        adapter=EtsyMarketplaceAdapter(Etsy(),99);listing=adapter.resolve_listing(provider_product={"external":{"listing_id":1}},publication_evidence={})
        self.assertIsNone(adapter.get_listing_state(listing["id"])["public_url"])

    def test_realistic_variant_update_preserves_every_row_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary),matching=False)
            approved=list(proposal["enabled_variants"]);all_ids=approved+list(range(10000,10000+318-len(approved)))
            provider.remote["variants"]=[{"id":variant_id,"price":1999,"is_enabled":False,"sku":f"sku-{variant_id}","is_default":index==0,"provider_meta":{"index":index}} for index,variant_id in enumerate(all_ids)]
            provider.remote["print_areas"]=[{"variant_ids":all_ids,"placeholders":[{"position":"front","images":[]}],"provider_area":"kept"}]
            executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(len(provider.remote["variants"]),318)
            self.assertEqual([row["id"] for row in provider.remote["variants"]],all_ids)
            self.assertTrue(all(row["sku"]==f"sku-{row['id']}" and "is_default" in row and "provider_meta" in row for row in provider.remote["variants"]))
            self.assertEqual({row["id"] for row in provider.remote["variants"] if row["is_enabled"]},set(approved))
            self.assertEqual(provider.remote["print_areas"][0]["variant_ids"],all_ids)

    def test_unexpected_back_or_neck_artwork_blocks_publication(self):
        for position in ("back","neck"):
            with self.subTest(position=position),tempfile.TemporaryDirectory() as temporary:
                workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
                provider.remote["print_areas"][0]["placeholders"].append({"position":position,"images":[{"id":"unexpected"}]})
                # Force the verification path without allowing the updater to sanitize the unexpected artwork.
                executor._payload=lambda remote,proposal,private: {"title":proposal["title"],"description":proposal["description"],"tags":proposal["tags"],"variants":remote["variants"],"print_areas":remote["print_areas"]}
                with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
                self.assertEqual(provider.publish_calls,0)

    def test_provider_update_timeout_is_uncertain_and_never_retried(self):
        class TimeoutProvider(FakeProvider):
            def update_product(self,shop,product,payload):self.update_calls+=1;raise TimeoutError("unknown outcome")
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,old,market,sha,proposal=self.fixture(Path(temporary),matching=False)
            provider=TimeoutProvider(old.remote);executor.provider=provider
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(orchestrator.load("reconcile-job")["stage"],"provider_update_uncertain")
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.update_calls,1);self.assertEqual(provider.publish_calls,0)

    def test_provider_declared_rejection_is_definite_failure(self):
        class Rejected(RuntimeError):status=422
        class RejectingProvider(FakeProvider):
            def update_product(self,shop,product,payload):self.update_calls+=1;raise Rejected("invalid payload")
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,old,market,sha,proposal=self.fixture(Path(temporary),matching=False)
            provider=RejectingProvider(old.remote);executor.provider=provider
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(orchestrator.load("reconcile-job")["stage"],"publication_failed")
            self.assertEqual(provider.update_calls,1);self.assertEqual(provider.publish_calls,0)

    def test_conclusively_not_published_reconciliation_fails_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";journal=executor._new_journal("reconcile-job",sha,{})
            journal["status"]="publication_uncertain";journal["steps"]["provider_metadata_update"].update(outcome="completed")
            journal["steps"]["marketplace_publish"].update(outcome="uncertain",attempt_count=1)
            product_orchestrator._atomic_json(root/"publication-execution.json",journal);state=orchestrator.load("reconcile-job");state["stage"]="publication_uncertain";product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            result=executor.reconcile(job_id="reconcile-job",proposal_sha256=sha)
            self.assertEqual(result["stage"],"publication_failed");self.assertEqual(provider.publish_calls,0);self.assertEqual(provider.update_calls,0)

    def test_listing_delay_is_pending_and_reconciliation_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary));market.resolve=False
            result=executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(result["stage"],"marketplace_listing_pending");self.assertEqual(provider.publish_calls,1)
            first_reads=market.resolve_calls;again=executor.reconcile(job_id="reconcile-job",proposal_sha256=sha)
            self.assertEqual(again["stage"],"marketplace_listing_pending");self.assertGreater(market.resolve_calls,first_reads)
            self.assertEqual(provider.publish_calls,1);self.assertEqual(provider.update_calls,0)
            market.resolve=True;done=executor.reconcile(job_id="reconcile-job",proposal_sha256=sha)
            self.assertEqual(done["stage"],"completed");self.assertEqual(provider.publish_calls,1)

    def test_changed_selected_profile_fails_before_remote_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
            private_path=orchestrator._path("reconcile-job").parent/"commerce-proposal"/"current-private.json";private=json.loads(private_path.read_text())
            expected={"profile_id":private["profile_binding"],"provider":"printify","marketplace":proposal["expected_marketplace"],"shop_id":private["provider_binding"]["shop_id"],"destination":proposal["expected_marketplace"],"expected_final_state":proposal["expected_final_state"]}
            private["execution_profile_binding"]=expected;private_path.write_text(json.dumps(private))
            changed={"profile_id":"another-profile","profile_type":"commerce_shop","configuration":{"provider_type":"printify","expected_marketplace":proposal["expected_marketplace"],"printify_shop_id":expected["shop_id"],"expected_final_state":proposal["expected_final_state"]}}
            executor.profile_loader=lambda required=True:changed
            with self.assertRaises(Exception):executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(provider.update_calls,0);self.assertEqual(provider.publish_calls,0)
            self.assertNotIn(str(expected["shop_id"]),json.dumps(workflow.status("reconcile-job")))

    def test_resume_after_completed_publish_skips_unpublished_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary));market.resolve=False
            executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True);self.assertTrue(provider.remote["is_published"])
            market.resolve=True;done=executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(done["stage"],"completed");self.assertEqual(provider.publish_calls,1)

    def test_interrupted_update_reconciles_applied_state_without_second_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";journal=executor._new_journal("reconcile-job",sha,{})
            journal["steps"]["provider_metadata_update"].update(outcome="started",attempt_count=1,request_digest="persisted-before-request")
            product_orchestrator._atomic_json(root/"publication-execution.json",journal)
            result=executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(result["stage"],"completed");self.assertEqual(provider.update_calls,0);self.assertEqual(provider.publish_calls,1)
            persisted=json.loads((root/"publication-execution.json").read_text());self.assertTrue(persisted["steps"]["provider_metadata_update"]["reconciled"])

    def test_interrupted_publish_response_is_reconciled_without_second_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary));provider.remote["is_published"]=True;provider.remote["external"]={"id":"private-listing"}
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";journal=executor._new_journal("reconcile-job",sha,{})
            journal["status"]="publication_started";journal["steps"]["provider_metadata_update"].update(outcome="completed")
            journal["steps"]["provider_update_verification"].update(outcome="completed")
            journal["steps"]["marketplace_publish"].update(outcome="started",attempt_count=1,request_digest="persisted-before-request")
            product_orchestrator._atomic_json(root/"publication-execution.json",journal);state=orchestrator.load("reconcile-job");state["stage"]="publication_started";product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            result=executor.execute(job_id="reconcile-job",proposal_sha256=sha,confirmed=True)
            self.assertEqual(result["stage"],"completed");self.assertEqual(provider.publish_calls,0);self.assertEqual(provider.update_calls,0)
            persisted=json.loads((root/"publication-execution.json").read_text());self.assertTrue(persisted["steps"]["marketplace_publish"]["reconciled"])

    def test_production_factory_builds_printify_and_etsy_adapters_with_injected_clients(self):
        from jamesos.core import api
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,executor,provider,market,sha,proposal=self.fixture(Path(temporary))
            profile={"profile_id":"p","profile_type":"commerce_shop","configuration":{"etsy_shop_id":44}}
            built=api._commerce_publication_executor(workflow,"reconcile-job",printify_client=object(),etsy_client=object(),profile_loader=lambda required=True:profile)
            self.assertIsInstance(built.provider,PrintifyProviderDraftAdapter);self.assertIsInstance(built.marketplace,EtsyMarketplaceAdapter)
            self.assertFalse(hasattr(built.provider,"create_product"));self.assertFalse(hasattr(built.provider,"upload"));self.assertFalse(hasattr(built.provider,"create_order"))
            self.assertFalse(hasattr(built.marketplace,"update_listing_state"));self.assertFalse(hasattr(built.marketplace,"create_order"))


if __name__=="__main__":unittest.main()
