import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jamesos.services.activity_status import ActivityStatusService


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class FakeProducer:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def sample_status(self, project_id):
        self.calls.append(project_id)
        return self.values[project_id]


class ActivityStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.projects, self.commerce, self.runs = root / "projects", root / "commerce", root / "runs"
        self.now = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def service(self, producer=None):
        return ActivityStatusService(projects_root=self.projects, commerce_root=self.commerce,
            agency_runs_root=self.runs, producer_factory=lambda: producer,
            clock=lambda: self.now)

    def producer_record(self, project="book-project-20260723T120000-aaaaaaaa", stage="running"):
        root = self.projects / project / "samples"
        write(root / "operations.json", {"operations": [{"operation": "generate_samples", "state": stage,
            "page_id": "page-001", "timestamp": "2026-07-23T17:59:00+00:00"}]})
        write(root / "manifest.json", {"operation_state": stage, "selected_page_ids": ["page-001"], "artifact_count": 0})
        return project

    def test_idle(self):
        value = self.service().status()
        self.assertEqual("Idle", value["state"])
        self.assertEqual(15000, value["poll_interval_ms"])

    def test_active_generation_is_reconciled_and_restored(self):
        project = self.producer_record()
        fake = FakeProducer({project: {"operation_state": "running", "progress": {
            "operation_type": "generate_samples", "operation_state": "running", "page_ids": ["page-001"],
            "started_at": "2026-07-23T17:59:00+00:00", "last_status_update_at": "2026-07-23T17:59:30+00:00",
            "operation_artifact_count": 0, "expected_artifact_count": 3, "provider_state_confirmed": True}}})
        first = self.service(fake).status()
        second = self.service(fake).status()
        self.assertEqual("Working", first["state"])
        self.assertEqual("Working: Generating page-001", first["display_label"])
        self.assertEqual(3, first["items"][0]["progress_expected"])
        self.assertEqual([project, project], fake.calls)
        self.assertEqual(first["items"][0]["workspace_url"], second["items"][0]["workspace_url"])

    def test_unconfirmed_provider_prompt_is_not_reported_working(self):
        project = self.producer_record(stage="provider_submitted")
        fake = FakeProducer({project: {"operation_state": "provider_submitted", "progress": {
            "operation_type": "generate_samples", "operation_state": "provider_submitted",
            "page_ids": ["page-001"], "provider_state_confirmed": False}}})
        value = self.service(fake).status()
        self.assertEqual("Needs attention", value["state"])
        self.assertEqual("reconciliation_required", value["items"][0]["operation_state"])

    def test_multiple_operations_order_wait_failure_and_canonical_urls(self):
        project = self.producer_record()
        fake = FakeProducer({project: {"progress": {"operation_type": "generate_samples", "operation_state": "running",
            "page_ids": ["page-001"], "provider_state_confirmed": True}}})
        write(self.commerce / "commerce-1" / "orchestrator-state.json",
            {"job_id": "commerce-1", "stage": "awaiting_final_approval", "created_at": "2026-07-23T17:00:00+00:00"})
        write(self.runs / "failed.json", {"run_id": "run-1", "agent_id": "jamesos.book-opportunity-scout",
            "state": "failed", "operation": "research", "safe_failure_message": "Research stopped safely."})
        value = self.service(fake).status()
        self.assertEqual(["Working", "Waiting for approval", "Failed"], [x["state"] for x in value["items"]])
        self.assertEqual("/app?view=commerce.review&job_id=commerce-1", value["items"][1]["workspace_url"])
        self.assertEqual("Research stopped safely.", value["items"][2]["safe_failure_message"])

    def test_terminal_generation_returns_idle_with_recent_completed(self):
        self.producer_record(stage="review_ready")
        value = self.service().status()
        self.assertEqual("Idle", value["state"])
        self.assertEqual("Completed", value["items"][0]["state"])

    def test_shared_service_deduplicates_same_agent_operation(self):
        write(self.runs / "one.json", {"run_id": "run-1", "agent_id": "merchant", "state": "running", "operation": "ingest"})
        write(self.runs / "two.json", {"run_id": "run-1", "agent_id": "merchant", "state": "running", "operation": "ingest"})
        value = self.service().status()
        self.assertEqual(1, len(value["items"]))


if __name__ == "__main__":
    unittest.main()
