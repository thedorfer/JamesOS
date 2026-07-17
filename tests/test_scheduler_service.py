from contextlib import redirect_stdout
from datetime import datetime,timezone
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import jamesos as jamesos_cli

from jamesos.core.scheduling.models import ScheduleValidationError
from jamesos.services.scheduler import SchedulerService


class FakeQueue:
    def __init__(self):self.jobs=[];self.fail=False;self.executed=False
    def create(self,template,provenance):
        if self.fail:raise RuntimeError("queue unavailable")
        job={"job_id":f"job-{len(self.jobs)+1}","type":template["job_type"],"requires_approval":template["requires_approval"],"approved":False,
            "payload":{"job_template":template,"scheduling":provenance}};self.jobs.append(job);return job
    def find_occurrence(self,occurrence_id):return next((job for job in self.jobs if job["payload"]["scheduling"]["occurrence_id"]==occurrence_id),None)


class SchedulerServiceTests(unittest.TestCase):
    def template(self,name="Review"):return {"job_type":"career.review","title":name,"payload":{"limit":5},"requires_approval":True}
    def service(self,root,now,queue=None):return SchedulerService(root=root,job_queue_service=queue or FakeQueue(),clock=lambda:now[0])
    def create_once(self,service,at="2026-07-18T09:00:00Z",**kwargs):
        return service.create(name="One time",timezone_name="UTC",trigger={"type":"once","at":at},job_template=self.template(),confirmed=True,**kwargs)

    def test_create_defaults_dry_run_and_confirmed_storage_is_private_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];service=self.service(Path(temporary)/"Scheduler",now)
            plan=service.create(name="Daily",timezone_name="UTC",trigger={"type":"daily","local_time":"08:00"},job_template=self.template())
            self.assertFalse(plan["write_performed"]);self.assertFalse(service.root.exists())
            created=service.create(name="Daily",timezone_name="UTC",trigger={"type":"daily","local_time":"08:00"},job_template=self.template(),confirmed=True)
            path=service.root/"schedules"/f'{created["schedule_id"]}.json';self.assertTrue(path.is_file());self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(service.root.stat().st_mode&0o777,0o700);self.assertFalse(any(item.name.endswith(".tmp") for item in path.parent.iterdir()))
            listed=json.dumps(service.list_schedules());self.assertNotIn('"limit": 5',listed);self.assertNotIn("scheduled_payload",listed)

    def test_preview_tick_is_read_only_and_confirmed_once_enqueues_exactly_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];queue=FakeQueue();service=self.service(Path(temporary)/"Scheduler",now,queue);created=self.create_once(service)
            preview=service.preview_occurrences(created["schedule_id"],5);self.assertEqual(len(preview["occurrences"]),1)
            before=(service.root/"schedules"/f'{created["schedule_id"]}.json').read_bytes();now[0]=datetime(2026,7,18,10,tzinfo=timezone.utc)
            plan=service.tick();self.assertEqual(plan["due_count"],1);self.assertEqual(plan["enqueue_count"],0);self.assertFalse(plan["write_performed"]);self.assertEqual(queue.jobs,[])
            self.assertEqual(before,(service.root/"schedules"/f'{created["schedule_id"]}.json').read_bytes())
            result=service.tick(confirmed=True);self.assertEqual(result["enqueue_count"],1);self.assertEqual(len(queue.jobs),1)
            job=queue.jobs[0];self.assertTrue(job["requires_approval"]);self.assertFalse(job["approved"]);self.assertEqual(job["payload"]["scheduling"]["source"],"jamesos.scheduler")
            self.assertEqual(service.tick(confirmed=True)["enqueue_count"],0);self.assertEqual(len(queue.jobs),1);self.assertTrue(service.show(created["schedule_id"])["schedule"]["completed"])

    def test_hourly_fire_once_uses_latest_without_catchup_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/"Scheduler";now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];queue=FakeQueue();service=self.service(root,now,queue)
            created=service.create(name="Hourly",timezone_name="UTC",trigger={"type":"hourly","every_hours":1,"anchor_at":"2026-07-17T09:00:00Z"},job_template=self.template(),confirmed=True)
            now[0]=datetime(2026,7,17,14,30,tzinfo=timezone.utc);result=service.tick(confirmed=True);self.assertEqual(result["enqueue_count"],1);self.assertEqual(len(queue.jobs),1)
            occurrence=json.loads(next((root/"occurrences"/created["schedule_id"]).glob("*.json")).read_text());self.assertEqual(occurrence["scheduled_for"],"2026-07-17T14:00:00Z");self.assertEqual(occurrence["earlier_missed_occurrences"],5)
            restarted=self.service(root,now,queue);self.assertEqual(restarted.tick(confirmed=True)["enqueue_count"],0);self.assertEqual(len(queue.jobs),1)

    def test_skip_misfire_disabled_and_multiple_schedules(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];queue=FakeQueue();service=self.service(Path(temporary)/"Scheduler",now,queue)
            skipped=self.create_once(service,misfire_policy="skip",misfire_grace_seconds=60)
            disabled=self.create_once(service,at="2026-07-18T09:30:00Z");service.disable(disabled["schedule_id"],confirmed=True)
            active=self.create_once(service,at="2026-07-18T09:45:00Z")
            now[0]=datetime(2026,7,18,10,tzinfo=timezone.utc);result=service.tick(confirmed=True)
            self.assertEqual(result["due_count"],2);self.assertEqual(result["enqueue_count"],1);self.assertEqual(len(queue.jobs),1)
            record=json.loads(next((service.root/"occurrences"/skipped["schedule_id"]).glob("*.json")).read_text());self.assertEqual(record["disposition"],"skipped_misfire")

    def test_queue_failure_does_not_advance_or_record_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];queue=FakeQueue();service=self.service(Path(temporary)/"Scheduler",now,queue);created=self.create_once(service)
            before=service.show(created["schedule_id"])["schedule"]["next_run_at"];now[0]=datetime(2026,7,18,10,tzinfo=timezone.utc);queue.fail=True
            with self.assertRaises(Exception):service.tick(confirmed=True)
            self.assertEqual(service.show(created["schedule_id"])["schedule"]["next_run_at"],before);self.assertFalse((service.root/"occurrences"/created["schedule_id"]).exists());self.assertEqual(queue.jobs,[])

    def test_enable_disable_preview_and_confirmed(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];service=self.service(Path(temporary)/"Scheduler",now);created=self.create_once(service)
            self.assertFalse(service.disable(created["schedule_id"])["write_performed"]);self.assertTrue(service.show(created["schedule_id"])["schedule"]["enabled"])
            service.disable(created["schedule_id"],confirmed=True);self.assertFalse(service.show(created["schedule_id"])["schedule"]["enabled"])
            service.enable(created["schedule_id"],confirmed=True);self.assertTrue(service.show(created["schedule_id"])["schedule"]["enabled"])

    def test_symlink_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/"target";target.mkdir();link=root/"Scheduler";link.symlink_to(target,target_is_directory=True)
            with self.assertRaises(ScheduleValidationError):self.service(link,[datetime(2026,1,1,tzinfo=timezone.utc)])
            service=self.service(root/"safe",[datetime(2026,1,1,tzinfo=timezone.utc)])
            with self.assertRaises(ScheduleValidationError):service.show("../escape")
            (root/"nested-target").mkdir();(root/"safe").mkdir();(root/"safe"/"schedules").symlink_to(root/"nested-target",target_is_directory=True)
            with self.assertRaises(ScheduleValidationError):service.list_schedules()

    def test_schedule_cli_create_list_show_preview_tick_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);now=[datetime(2026,7,17,8,tzinfo=timezone.utc)];queue=FakeQueue();service=self.service(root/"Scheduler",now,queue)
            template=root/"template.json";template.write_text(json.dumps(self.template()))
            def run(*args):
                output=StringIO()
                with patch("sys.argv",["jamesos.py","schedule",*args]),redirect_stdout(output):self.assertEqual(jamesos_cli._main(scheduler=service),0)
                return json.loads(output.getvalue())
            base=("create","--name","CLI schedule","--timezone","UTC","--once-at","2026-07-18T09:00:00Z","--job-template-file",str(template))
            self.assertEqual(run(*base)["result"],"schedule_creation_plan");self.assertFalse(service.root.exists())
            created=run(*base,"--confirm-create");schedule_id=created["schedule_id"]
            self.assertEqual(run("list")["count"],1);self.assertEqual(run("show","--schedule-id",schedule_id)["schedule"]["schedule_id"],schedule_id)
            self.assertEqual(len(run("preview","--schedule-id",schedule_id,"--count","3")["occurrences"]),1)
            self.assertEqual(run("disable","--schedule-id",schedule_id)["result"],"schedule_disable_plan")
            run("disable","--schedule-id",schedule_id,"--confirm");run("enable","--schedule-id",schedule_id,"--confirm")
            now[0]=datetime(2026,7,18,10,tzinfo=timezone.utc);self.assertEqual(run("tick")["enqueue_count"],0)
            self.assertEqual(run("tick","--confirm-enqueue")["enqueue_count"],1);self.assertEqual(len(queue.jobs),1)


if __name__=="__main__":unittest.main()
