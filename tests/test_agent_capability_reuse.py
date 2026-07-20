import tempfile
import unittest
from pathlib import Path

from jamesos.core.artifacts import AtomicDocumentStore,ApprovalService,AuditEventStore,ProjectArtifactStore,VersionedDocument,local_safety_declaration
from jamesos.services import book_opportunity_scout
from jamesos.services.coloring_book_producer import ColoringBookProducer
from jamesos.services.local_creative_studio import LocalAssetRequest,LocalAssetResult
from jamesos.services.structured_planning import DeterministicPlanProvider


class CapabilityReuseTests(unittest.TestCase):
    def test_shared_documents_approval_audit_and_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);documents=AtomicDocumentStore();artifacts=ProjectArtifactStore(root,documents)
            artifacts.write("project-1","brief.json",{"title":"Safe"})
            self.assertEqual("Safe",artifacts.read("project-1","brief.json")["title"])
            document=VersionedDocument.bind(1,{"title":"Safe"},names=("book_brief",))
            approvals=ApprovalService();record=approvals.record(document,timestamp="2026-01-01T00:00:00Z")
            self.assertEqual({"state":"approved","stale":False},approvals.state(record,document))
            self.assertTrue(approvals.state(record,VersionedDocument.bind(2,{"title":"Changed"},names=("book_brief",)))["stale"])
            events=AuditEventStore(root/"events.jsonl");events.append({"event":"saved"});self.assertIn('"event": "saved"',(root/"events.jsonl").read_text())

    def test_scout_and_producer_use_shared_document_store(self):
        self.assertIsInstance(book_opportunity_scout._DOCUMENTS,AtomicDocumentStore)
        with tempfile.TemporaryDirectory() as directory:
            producer=ColoringBookProducer(Path(directory))
            self.assertIsInstance(producer.artifacts,ProjectArtifactStore)

    def test_deterministic_planning_and_creative_contract_are_provider_free(self):
        result=DeterministicPlanProvider().propose({"topics":["forest","ocean"],"count":2})
        self.assertEqual(["forest","ocean"],[item["topic"] for item in result["items"]])
        self.assertEqual(0,result["external_provider_calls"])
        request=LocalAssetRequest("request-1","image.compose","producer","project-1",{},"abc")
        response=LocalAssetResult(request.request_id,"not_executed")
        self.assertEqual("none",response.provider_id);self.assertEqual(0,response.external_provider_calls)
        self.assertEqual({"external_provider_calls":0,"images_generated":False,"pdf_generated":False,"publication_status":"not_published","purchase_status":"not_created","order_status":"not_created"},local_safety_declaration())


if __name__=="__main__":unittest.main()
