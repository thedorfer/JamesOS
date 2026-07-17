from __future__ import annotations

from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo

from .models import WEEKDAYS,aware,validate_timezone,validate_trigger


UTC=timezone.utc


def utc_text(value:datetime)->str:
    return value.astimezone(UTC).isoformat().replace("+00:00","Z")


def _resolve_local(day:date,local_time:str,zone:ZoneInfo)->datetime:
    hour,minute=(int(item) for item in local_time.split(":"));naive=datetime.combine(day,time(hour,minute))
    for offset in range(181):
        candidate_naive=naive+timedelta(minutes=offset);candidate=candidate_naive.replace(tzinfo=zone,fold=0)
        if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)==candidate_naive:return candidate
    raise ValueError("local time could not be resolved")


def next_occurrences(trigger:dict,timezone_name:str,after:datetime,count:int,*,inclusive:bool=False)->list[datetime]:
    validate_timezone(timezone_name);trigger=validate_trigger(trigger)
    if after.tzinfo is None:raise ValueError("after must be aware")
    if type(count) is not int or not 1<=count<=10000:raise ValueError("count must be 1..10000")
    zone=ZoneInfo(timezone_name);boundary=after.astimezone(UTC);result=[];kind=trigger["type"]
    def accepted(value):return value>boundary or inclusive and value==boundary
    if kind=="once":
        value=aware(trigger["at"],"at").astimezone(UTC)
        return [value] if accepted(value) else []
    if kind=="hourly":
        anchor=aware(trigger["anchor_at"],"anchor_at").astimezone(UTC);step=timedelta(hours=trigger["every_hours"])
        if boundary<anchor:index=0
        else:
            index=int((boundary-anchor)//step)
            if not inclusive or anchor+index*step<boundary:index+=1
        return [anchor+(index+i)*step for i in range(count)]
    local_day=boundary.astimezone(zone).date()-timedelta(days=1)
    allowed=set(range(7)) if kind=="daily" else {WEEKDAYS.index(item) for item in trigger["weekdays"]}
    for offset in range(0,3700):
        day=local_day+timedelta(days=offset)
        if day.weekday() not in allowed:continue
        value=_resolve_local(day,trigger["local_time"],zone).astimezone(UTC)
        if accepted(value):result.append(value)
        if len(result)==count:return result
    raise ValueError("recurrence search exceeded bounded horizon")
