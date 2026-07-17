from datetime import datetime,timezone
import unittest

from jamesos.core.scheduling.recurrence import next_occurrences,utc_text


class SchedulerRecurrenceTests(unittest.TestCase):
    def test_once_and_hourly_are_anchored_without_drift(self):
        once=next_occurrences({"type":"once","at":"2026-07-18T09:00:00-05:00"},"America/Chicago",datetime(2026,7,18,13,tzinfo=timezone.utc),1)
        self.assertEqual(utc_text(once[0]),"2026-07-18T14:00:00Z")
        hourly=next_occurrences({"type":"hourly","every_hours":4,"anchor_at":"2026-07-17T08:00:00-05:00"},"America/Chicago",datetime(2026,7,17,14,37,tzinfo=timezone.utc),3)
        self.assertEqual([utc_text(item) for item in hourly],["2026-07-17T17:00:00Z","2026-07-17T21:00:00Z","2026-07-18T01:00:00Z"])

    def test_daily_and_weekly_local_times(self):
        daily=next_occurrences({"type":"daily","local_time":"08:00"},"America/Chicago",datetime(2026,7,17,14,tzinfo=timezone.utc),2)
        self.assertEqual([utc_text(item) for item in daily],["2026-07-18T13:00:00Z","2026-07-19T13:00:00Z"])
        weekly=next_occurrences({"type":"weekly","weekdays":["MO","WE","FR"],"local_time":"08:00"},"America/Chicago",datetime(2026,7,17,14,tzinfo=timezone.utc),3)
        self.assertEqual([item.weekday() for item in weekly],[0,2,4])

    def test_dst_nonexistent_advances_to_first_valid_and_ambiguous_uses_fold_zero(self):
        spring=next_occurrences({"type":"daily","local_time":"02:30"},"America/New_York",datetime(2026,3,8,5,tzinfo=timezone.utc),1)
        self.assertEqual(utc_text(spring[0]),"2026-03-08T07:00:00Z")
        fall=next_occurrences({"type":"daily","local_time":"01:30"},"America/New_York",datetime(2026,11,1,4,tzinfo=timezone.utc),1)
        self.assertEqual(utc_text(fall[0]),"2026-11-01T05:30:00Z")

    def test_preview_is_deterministic(self):
        trigger={"type":"daily","local_time":"08:00"};after=datetime(2026,1,1,tzinfo=timezone.utc)
        self.assertEqual(next_occurrences(trigger,"UTC",after,5),next_occurrences(trigger,"UTC",after,5))


if __name__=="__main__":unittest.main()
