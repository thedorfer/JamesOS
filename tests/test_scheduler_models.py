from datetime import datetime,timezone
import json
import unittest

from jamesos.core.scheduling.models import Schedule,ScheduleValidationError,payload_digest,validate_job_template,validate_schedule,validate_timezone,validate_trigger


class SchedulerModelTests(unittest.TestCase):
    def template(self):return {"job_type":"career.review","title":"Morning review","payload":{"limit":5},"requires_approval":True,"priority":3,"profile_binding_reference":"profile:opaque"}
    def test_valid_triggers_and_schedule(self):
        triggers=({"type":"once","at":"2026-07-18T09:00:00-05:00"},{"type":"hourly","every_hours":4,"anchor_at":"2026-07-17T08:00:00-05:00"},
            {"type":"daily","local_time":"08:00"},{"type":"weekly","weekdays":["FR","MO","WE"],"local_time":"08:00"})
        for trigger in triggers:
            with self.subTest(trigger=trigger["type"]):self.assertEqual(validate_trigger(trigger)["type"],trigger["type"])
        template=self.template();schedule=Schedule("1.0","schedule-"+"a"*24,"Test",True,"America/Chicago",triggers[2],template,"fire_once",3600,
            "2026-07-17T12:00:00Z","2026-07-17T12:00:00Z","2026-07-18T13:00:00Z",payload_digest=payload_digest(template))
        self.assertIs(validate_schedule(schedule),schedule)

    def test_invalid_timezone_naive_once_interval_and_weekdays_fail(self):
        bad=(lambda:validate_timezone("Not/AZone"),lambda:validate_trigger({"type":"once","at":"2026-01-01T08:00:00"}),
            lambda:validate_trigger({"type":"hourly","every_hours":0,"anchor_at":"2026-01-01T08:00:00Z"}),
            lambda:validate_trigger({"type":"hourly","every_hours":-1,"anchor_at":"2026-01-01T08:00:00Z"}),
            lambda:validate_trigger({"type":"weekly","weekdays":["MO","XX"],"local_time":"08:00"}),
            lambda:validate_trigger({"type":"weekly","weekdays":["MO","MO"],"local_time":"08:00"}),lambda:validate_trigger({"type":"monthly"}))
        for call in bad:
            with self.assertRaises(ScheduleValidationError):call()

    def test_job_template_rejects_credentials_callables_paths_and_executable_hooks(self):
        self.assertEqual(validate_job_template(self.template())["payload"],{"limit":5})
        invalid=({**self.template(),"payload":{"api_key":"value"}},{**self.template(),"payload":{"callback":lambda:None}},
            {**self.template(),"payload":{"input":"/home/user/file"}},{**self.template(),"payload":{"shell":"echo unsafe"}},
            {**self.template(),"profile_binding_reference":"../../profile"})
        for value in invalid:
            with self.assertRaises(ScheduleValidationError):validate_job_template(value)

    def test_malformed_schedule_id_and_grace_fail(self):
        template=self.template();base=dict(schema_version="1.0",schedule_id="../bad",name="Test",enabled=True,timezone="UTC",trigger={"type":"daily","local_time":"08:00"},
            job_template=template,misfire_policy="fire_once",misfire_grace_seconds=1,created_at="2026-01-01T00:00:00Z",updated_at="2026-01-01T00:00:00Z",next_run_at="2026-01-02T08:00:00Z",payload_digest=payload_digest(template))
        with self.assertRaises(ScheduleValidationError):validate_schedule(Schedule(**base))
        base["schedule_id"]="schedule-"+"a"*24;base["misfire_grace_seconds"]=-1
        with self.assertRaises(ScheduleValidationError):validate_schedule(Schedule(**base))


if __name__=="__main__":unittest.main()
