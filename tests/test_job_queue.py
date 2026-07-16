from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import job_queue


class JobQueueTests(unittest.TestCase):
    def queue_paths(self, root: Path) -> dict:
        queue_root = root / "JamesOS" / "Queue"
        return {
            "QUEUE_ROOT": queue_root,
            "PENDING": queue_root / "pending",
            "IN_PROGRESS": queue_root / "in_progress",
            "PROCESSED": queue_root / "processed",
            "FAILED": queue_root / "failed",
            "REPORT_PATH": root / "JamesOS" / "Reports" / "Job Queue.md",
        }

    def patch_queue_paths(self, root: Path):
        patches = [
            patch.object(job_queue, name, value)
            for name, value in self.queue_paths(root).items()
        ]
        return patches

    def run_with_queue(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self.patch_queue_paths(root)
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_create_list_and_get_job(self) -> None:
        def scenario(root: Path) -> None:
            created = job_queue.create_job(
                "commerce_shop.draft",
                {"niche": "Pride Month"},
                priority=2,
                steps=["draft", "review"],
            )

            listed = job_queue.list_jobs("pending")
            loaded = job_queue.get_job(created["job_id"])

            self.assertEqual(len(listed), 1)
            self.assertEqual(loaded["job_id"], created["job_id"])
            self.assertEqual(loaded["type"], "commerce_shop.draft")
            self.assertEqual(loaded["status"], "pending")
            self.assertTrue(loaded["requires_approval"])
            self.assertFalse(loaded["approved"])
            self.assertEqual([step["name"] for step in loaded["steps"]], ["draft", "review"])
            self.assertTrue((root / "JamesOS" / "Reports" / "Job Queue.md").exists())

        self.run_with_queue(scenario)

    def test_approve_and_process_job(self) -> None:
        def scenario(root: Path) -> None:
            created = job_queue.create_job("safe.action", {})
            approved = job_queue.approve_job(created["job_id"], approved_by="James")
            processed = job_queue.update_job_status(created["job_id"], "processed")

            self.assertTrue(approved["approved"])
            self.assertEqual(processed["status"], "processed")
            self.assertEqual(len(job_queue.list_jobs("pending")), 0)
            self.assertEqual(len(job_queue.list_jobs("processed")), 1)

        self.run_with_queue(scenario)

    def test_fail_job_moves_to_failed(self) -> None:
        def scenario(root: Path) -> None:
            created = job_queue.create_job("broken.action", {})
            failed = job_queue.fail_job(created["job_id"], "bad input")

            self.assertEqual(failed["status"], "failed")
            self.assertEqual(len(job_queue.list_jobs("failed")), 1)
            self.assertIn("Failure reason: bad input", str(failed["logs"]))

        self.run_with_queue(scenario)

    def test_approval_gated_job_cannot_complete_unapproved(self) -> None:
        def scenario(root: Path) -> None:
            created = job_queue.create_job("publish.something", {}, requires_approval=True)

            with self.assertRaises(job_queue.JobQueueError):
                job_queue.update_job_status(created["job_id"], "processed")

            loaded = job_queue.get_job(created["job_id"])
            self.assertEqual(loaded["status"], "pending")
            self.assertFalse(loaded["approved"])

        self.run_with_queue(scenario)

    def test_non_approval_job_can_complete(self) -> None:
        def scenario(root: Path) -> None:
            created = job_queue.create_job("refresh.report", {}, requires_approval=False)
            processed = job_queue.update_job_status(created["job_id"], "processed")

            self.assertEqual(processed["status"], "processed")
            self.assertFalse(processed["requires_approval"])

        self.run_with_queue(scenario)

    def test_mark_step_and_append_log(self) -> None:
        def scenario(root: Path) -> None:
            created = job_queue.create_job("multi.step", {}, steps=["prepare"])
            job_queue.mark_step(created["job_id"], "prepare", "done", "ready")
            logged = job_queue.append_job_log(created["job_id"], "review requested")

            self.assertEqual(logged["steps"][0]["status"], "done")
            self.assertIn("review requested", str(logged["logs"]))

        self.run_with_queue(scenario)

    def test_legacy_queue_jobs_can_be_listed(self) -> None:
        def scenario(root: Path) -> None:
            job_queue.ensure_job_queue_dirs()
            legacy_path = root / "JamesOS" / "Queue" / "pending" / "legacy-1.json"
            legacy_path.write_text(
                '{"id": "legacy-1", "type": "intake", "created_at": "2026-01-01 00:00:00", "status": "pending", "payload": {}}',
                encoding="utf-8",
            )

            listed = job_queue.list_jobs("pending")

            self.assertEqual(listed[0]["job_id"], "legacy-1")
            self.assertFalse(listed[0]["requires_approval"])

        self.run_with_queue(scenario)


if __name__ == "__main__":
    unittest.main()
