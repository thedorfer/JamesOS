from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jamesos.services import product_orchestrator
from jamesos.services.commerce_binding_migration import LegacyCommerceBindingMigration, _canonical_digest
from tests import test_commerce_workflow


class CommerceBindingMigrationTests(unittest.TestCase):
    def fixture(self, root: Path, *, selected="private-profile-fixture", etsy_shop=456):
        workflow,orchestrator,state,client=test_commerce_workflow.CommerceWorkflowTests().fixture(root);prepared=workflow.prepare("reconcile-job");sha=prepared["proposal_sha256"]
        workflow.approve("reconcile-job",sha,confirmed=True)
        client.reset_mock()
        profiles=root/"profiles";profiles.mkdir();profile={"profile_id":"private-profile-fixture","profile_type":"commerce_shop",
            "configuration":{"provider_type":"printify","marketplace_type":"etsy","expected_marketplace":"etsy","expected_final_state":"inactive",
                "printify_shop_id":state["shop_id"],"etsy_shop_id":etsy_shop},"secret_handle_bindings":{"marketplace":"etsy.test","fulfillment":"printify.test"}}
        (profiles/"private-profile-fixture.json").write_text(json.dumps(profile));(profiles/"selected_commerce_profile").write_text(selected+"\n")
        service=LegacyCommerceBindingMigration(workflow,profiles_root=profiles,selected_profile_resolver=lambda:(profiles/"selected_commerce_profile").read_text().strip())
        return workflow,orchestrator,client,service,profiles,sha

    def test_dry_run_is_read_only_and_creates_no_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary));root=orchestrator._path("reconcile-job").parent/"commerce-proposal"
            before={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()};result=service.migrate(job_id="reconcile-job")
            after={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertTrue(result["dry_run"]);self.assertTrue(result["migration_can_proceed"]);self.assertEqual(before,after);self.assertFalse((root/"publication-execution.json").exists())
            client.get_product.assert_not_called();client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_product.assert_not_called();client.create_order.assert_not_called()

    def test_selected_mismatch_requires_explicit_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary),selected="different")
            other=json.loads((profiles/"private-profile-fixture.json").read_text());other["profile_id"]="different";(profiles/"different.json").write_text(json.dumps(other))
            blocked=service.migrate(job_id="reconcile-job");self.assertEqual(blocked["blocking_reason"],"BLOCKED_PROFILE_IDENTITY_MISMATCH")
            plan=service.migrate(job_id="reconcile-job",profile_id="private-profile-fixture")
            self.assertTrue(plan["migration_can_proceed"]);self.assertNotEqual(plan["legacy_profile"],plan["selected_profile"])
            self.assertEqual((profiles/"selected_commerce_profile").read_text().strip(),"different")

    def test_missing_or_ambiguous_legacy_identity_fails_closed(self):
        for ambiguous in (False,True):
            with self.subTest(ambiguous=ambiguous),tempfile.TemporaryDirectory() as temporary:
                workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary));root=orchestrator._path("reconcile-job").parent
                private_path=root/"commerce-proposal/current-private.json";private=json.loads(private_path.read_text());private.pop("profile_binding",None);private_path.write_text(json.dumps(private))
                state=orchestrator.load("reconcile-job")
                if ambiguous:state["profile_id"]="one";state["selected_profile_id"]="two"
                else:state.pop("profile_id",None);state.pop("selected_profile_id",None)
                product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
                with self.assertRaises(Exception):service.migrate(job_id="reconcile-job",profile_id="private-profile-fixture")

    def test_missing_etsy_binding_blocks_and_never_infers_text_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary),etsy_shop=None)
            profile_path=profiles/"private-profile-fixture.json";profile=json.loads(profile_path.read_text());profile["configuration"].update(shop_name="12345",listing_url="https://etsy.example/999",email="777@example.test",username="888")
            profile_path.write_text(json.dumps(profile));plan=service.migrate(job_id="reconcile-job")
            self.assertEqual(plan["blocking_reason"],"BLOCKED_ETSY_SHOP_BINDING_REQUIRED");self.assertFalse(plan["etsy_shop_binding_available"])
            with self.assertRaises(Exception):service.migrate(job_id="reconcile-job",confirmed=True)

    def test_confirmed_migration_is_private_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary));root=orchestrator._path("reconcile-job").parent;proposal=(root/"commerce-proposal/current.json").read_bytes();approval=(root/"commerce-proposal/approval.json").read_bytes()
            result=service.migrate(job_id="reconcile-job",confirmed=True);self.assertTrue(result["write_performed"])
            private_path=root/"commerce-proposal/current-private.json";private=json.loads(private_path.read_text());binding=private["execution_profile_binding"]
            self.assertEqual(private_path.stat().st_mode&0o777,0o600);self.assertEqual(_canonical_digest(binding),private["execution_profile_binding_sha256"])
            receipt=root/"commerce-proposal/execution-binding-migration.json";self.assertTrue(receipt.is_file());self.assertEqual(receipt.stat().st_mode&0o777,0o600)
            self.assertEqual((root/"commerce-proposal/current.json").read_bytes(),proposal);self.assertEqual((root/"commerce-proposal/approval.json").read_bytes(),approval)
            self.assertFalse((root/"commerce-proposal/publication-execution.json").exists());before=private_path.read_bytes();again=service.migrate(job_id="reconcile-job",confirmed=True)
            self.assertTrue(again["already_migrated"]);self.assertFalse(again["write_performed"]);self.assertEqual(private_path.read_bytes(),before)
            dry_again=service.migrate(job_id="reconcile-job");self.assertTrue(dry_again["already_migrated"]);self.assertTrue(dry_again["dry_run"]);self.assertEqual(dry_again["files_would_change"],[])
            self.assertTrue(any((root/"commerce-proposal/migration-backups").rglob("current-private.json")))

    def test_conflicting_existing_binding_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary));private_path=orchestrator._path("reconcile-job").parent/"commerce-proposal/current-private.json"
            private=json.loads(private_path.read_text());private["execution_profile_binding"]={"conflict":True};private["execution_profile_binding_sha256"]=_canonical_digest(private["execution_profile_binding"]);private_path.write_text(json.dumps(private));before=private_path.read_bytes()
            with self.assertRaises(Exception):service.migrate(job_id="reconcile-job",confirmed=True)
            self.assertEqual(private_path.read_bytes(),before)

    def test_explicit_profile_repair_and_selection_create_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary),selected="different",etsy_shop=None)
            profile_path=profiles/"private-profile-fixture.json";profile=json.loads(profile_path.read_text());profile["configuration"]["legacy_etsy_shop_id"]=456;profile_path.write_text(json.dumps(profile));mode=profile_path.stat().st_mode&0o777
            with self.assertRaises(Exception):service.migrate(job_id="reconcile-job",profile_id="private-profile-fixture",repair_profile_binding=True)
            with self.assertRaises(Exception):service.migrate(job_id="reconcile-job",profile_id="private-profile-fixture",set_selected_profile=True)
            result=service.migrate(job_id="reconcile-job",profile_id="private-profile-fixture",confirmed=True,repair_profile_binding=True,set_selected_profile=True)
            self.assertTrue(result["write_performed"]);repaired=json.loads(profile_path.read_text());self.assertEqual(repaired["configuration"]["etsy_shop_id"],456)
            self.assertEqual(profile_path.stat().st_mode&0o777,0o600);self.assertEqual((profiles/"selected_commerce_profile").read_text().strip(),"private-profile-fixture")
            backups=orchestrator._path("reconcile-job").parent/"commerce-proposal/migration-backups";self.assertTrue(any(backups.rglob("profile.json")))
            self.assertTrue(any(backups.rglob("selected_commerce_profile")))

    def test_public_plan_contains_no_private_identifiers(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary));plan=service.migrate(job_id="reconcile-job");text=json.dumps(plan)
            self.assertNotIn("private-profile-fixture",text);self.assertNotIn(str(orchestrator.load("reconcile-job")["shop_id"]),text)
            self.assertNotIn("etsy_shop_id",text);self.assertFalse(hasattr(service,"provider"));self.assertFalse(hasattr(service,"marketplace"))

    def test_all_blocking_reasons_are_reported_safely(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,client,service,profiles,sha=self.fixture(Path(temporary),selected="different",etsy_shop=None)
            other=json.loads((profiles/"private-profile-fixture.json").read_text());other["profile_id"]="different";(profiles/"different.json").write_text(json.dumps(other))
            plan=service.migrate(job_id="reconcile-job")
            self.assertEqual(plan["blocking_reasons"],["BLOCKED_PROFILE_IDENTITY_MISMATCH","BLOCKED_ETSY_SHOP_BINDING_REQUIRED"])


if __name__ == "__main__": unittest.main()
