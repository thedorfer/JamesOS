import json
import tempfile
import unittest
from pathlib import Path

from jamesos.services.coloring_book_producer import ColoringBookProducer
from jamesos.services.structured_planning import DeterministicPlanProvider


class FakeScout:
    def __init__(self, root):
        self.root = root
        run = root / "run-1"
        run.mkdir(parents=True)
        self.value = {
            "run_id": "run-1", "research_label": "DEMO",
            "request": {"market": "US", "audience": "ages 4-8", "book_type": "coloring book", "source_mode": "demo"},
            "ranked_candidates": [{"candidate_id": "concept-011", "concept": "Camping With Critters", "total_score": 91, "confidence": .9, "score_breakdown": {}, "differentiation_recommendation": "Friendly outdoor skills", "risks": [], "missing_evidence": [], "evidence_references": []}],
            "decisions": {"concept-011": {"action": "approve", "timestamp": "2026-07-19T18:03:03-05:00"}},
        }
        for name in ("request.json", "results.json", "evidence.json", "decisions.json"):
            (run / name).write_text("{}")

    def load(self, run_id):
        if run_id != "run-1": raise ValueError("missing")
        return self.value


class ColoringBookProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.service = ColoringBookProducer(root / "projects", FakeScout(root / "runs"))

    def tearDown(self): self.temp.cleanup()

    def test_preview_is_non_writing_and_confirmation_is_explicit(self):
        value = self.service.create("run-1", "concept-011")
        self.assertTrue(value["confirmation_required"])
        self.assertIn("No coloring pages", value["confirmation"])
        self.assertEqual([], list(self.service.root.glob("*")))

    def test_confirm_writes_exact_local_contract_and_is_idempotent(self):
        value = self.service.create("run-1", "concept-011", confirmed=True)
        root = self.service.root / value["project_id"]
        self.assertEqual({"project.json","opportunity-source.json","opportunity-source.sha256","book-brief.json","book-brief.md","production-spec.json","page-plan.json","page-prompts.json","cover-brief.md","approvals.json","events.jsonl"}, {p.name for p in root.iterdir()})
        again = self.service.create("run-1", "concept-011", confirmed=True)
        self.assertEqual(value["project_id"], again["project_id"])
        self.assertTrue(again["idempotent"])
        project = json.loads((root / "project.json").read_text())
        self.assertFalse(project["images_generated"])
        self.assertFalse(project["external_provider_contacted"])
        self.assertEqual("not_published", project["publication_status"])
        self.assertEqual("not_created", project["order_status"])

    def test_rejects_unapproved_and_unknown_candidates(self):
        self.service.scout.value["decisions"] = {}
        with self.assertRaisesRegex(ValueError, "not approved"):
            self.service.create("run-1", "concept-011")
        with self.assertRaisesRegex(ValueError, "candidate not found"):
            self.service.create("run-1", "unknown")

    def test_load_validates_identifier_and_preserves_source(self):
        value = self.service.create("run-1", "concept-011", confirmed=True)
        loaded = self.service.load(value["project_id"])
        self.assertEqual("draft_brief", loaded["project"]["status"])
        with self.assertRaises(ValueError): self.service.load("../../etc")

    def test_list_labels_include_source_and_canonical_duplicate_state(self):
        first = self.service.create("run-1", "concept-011", confirmed=True)
        duplicate = dict(first);duplicate["project_id"]="book-project-20260719T235959-aaaaaaaa";duplicate["created_at"]="9999-12-31T23:59:59-05:00"
        target=self.service.root/duplicate["project_id"];target.mkdir()
        source=self.service.root/first["project_id"]
        for item in source.iterdir(): (target/item.name).write_bytes(item.read_bytes())
        (target/"project.json").write_text(json.dumps(duplicate))
        rows=self.service.list();new=next(x for x in rows if x["project_id"]==duplicate["project_id"])
        self.assertEqual(first["project_id"],new["duplicate_of"])
        self.assertEqual("superseded_duplicate",new["status"])
        self.assertEqual("Camping With Critters",new["working_title"])
        self.assertEqual("concept-011",new["candidate_id"])

    def test_edit_approve_stale_and_refresh_persistence(self):
        created=self.service.create("run-1","concept-011",confirmed=True);pid=created["project_id"]
        preview=self.service.approve_brief(pid);self.assertTrue(preview["confirmation_required"]);self.assertEqual(0,preview["external_actions"])
        approved=self.service.approve_brief(pid,confirmed=True);self.assertFalse(approved["idempotent"])
        self.assertEqual("approved",self.service.load(pid)["book_brief_approval"]["state"])
        edited=self.service.update(pid,{"working_title":"Camping With Critters — Revised"},{"coloring_page_count":44})
        self.assertEqual(2,edited["project"]["revision"]);self.assertTrue(edited["book_brief_approval"]["stale"])
        refreshed=ColoringBookProducer(self.service.root,self.service.scout).load(pid)
        self.assertEqual("Camping With Critters — Revised",refreshed["book_brief"]["working_title"])
        self.assertEqual(44,refreshed["production_spec"]["coloring_page_count"])
        self.assertFalse(refreshed["project"]["external_provider_contacted"])
        self.assertEqual("not_published",refreshed["project"]["publication_status"])
        self.assertEqual("not_created",refreshed["project"]["order_status"])

    def test_page_plan_preview_generation_idempotency_prompts_and_approval(self):
        created=self.service.create("run-1","concept-011",confirmed=True);pid=created["project_id"]
        with self.assertRaisesRegex(ValueError,"approved current book brief"):
            self.service.generate_page_plan(pid,confirmed=True)
        self.service.approve_brief(pid,confirmed=True);root=self.service.root/pid
        before_plan=(root/"page-plan.json").read_bytes();before_prompts=(root/"page-prompts.json").read_bytes()
        preview=self.service.generate_page_plan(pid)
        self.assertEqual(40,preview["requested_page_count"]);self.assertEqual(0,preview["local_only_safety"]["external_provider_calls"])
        self.assertEqual(before_plan,(root/"page-plan.json").read_bytes());self.assertEqual(before_prompts,(root/"page-prompts.json").read_bytes())
        plan=self.service.generate_page_plan(pid,confirmed=True);loaded=self.service.load(pid)
        self.assertEqual(40,len(plan["pages"]));self.assertEqual(40,len(loaded["page_prompts"]["prompts"]))
        self.assertEqual(40,len({x["title"] for x in plan["pages"]}));self.assertEqual(40,len({x["scene_summary"] for x in plan["pages"]}))
        self.assertTrue(plan["validation"]["valid"]);self.assertEqual("deterministic-plan-v1",plan["planner_provider_id"])
        self.assertTrue(all(not x["image_generated"] and x["status"]=="draft" for x in loaded["page_prompts"]["prompts"]))
        again=self.service.generate_page_plan(pid,confirmed=True);self.assertTrue(again["idempotent"]);self.assertEqual(plan["page_plan_sha256"],again["page_plan_sha256"])
        approval_preview=self.service.approve_page_plan(pid);self.assertEqual(40,approval_preview["page_count"]);self.assertEqual(0,approval_preview["external_actions"])
        approved=self.service.approve_page_plan(pid,confirmed=True);self.assertIn("No external provider",approved["message"]);self.assertEqual("page_plan_approved",self.service.load(pid)["project"]["status"])

    def test_page_plan_edit_order_and_brief_change_staleness(self):
        created=self.service.create("run-1","concept-011",confirmed=True);pid=created["project_id"];self.service.approve_brief(pid,confirmed=True);self.service.generate_page_plan(pid,confirmed=True);self.service.approve_page_plan(pid,confirmed=True)
        pages=self.service.load(pid)["page_plan"]["pages"];pages[0],pages[1]=pages[1],pages[0];pages[0]["title"]="A Revised Opening"
        edited=self.service.edit_page_plan(pid,pages);self.assertEqual("page_plan_draft",edited["project"]["status"]);self.assertTrue(edited["page_plan_approval"]["stale"]);self.assertEqual("A Revised Opening",ColoringBookProducer(self.service.root,self.service.scout).load(pid)["page_plan"]["pages"][0]["title"])
        self.service.approve_page_plan(pid,confirmed=True);changed=self.service.update(pid,{"notes":"Brief changed"})
        self.assertEqual("stale",changed["page_plan"]["status"]);self.assertTrue(changed["page_plan_approval"]["stale"])

    def test_shared_structured_provider_is_called(self):
        class TrackingProvider(DeterministicPlanProvider):
            def __init__(self):object.__setattr__(self,"called",0)
            def propose(self,request):object.__setattr__(self,"called",self.called+1);return super().propose(request)
        provider=TrackingProvider();service=ColoringBookProducer(self.service.root,self.service.scout,provider);pid=service.create("run-1","concept-011",confirmed=True)["project_id"];service.approve_brief(pid,confirmed=True);service.generate_page_plan(pid,confirmed=True);self.assertEqual(1,provider.called)


if __name__ == "__main__": unittest.main()
