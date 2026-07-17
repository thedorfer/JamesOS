from __future__ import annotations

from dataclasses import asdict,dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError


SCHEMA_VERSION="1.0"
SCHEDULE_ID=re.compile(r"^schedule-[0-9a-f]{24}$")
WEEKDAYS=("MO","TU","WE","TH","FR","SA","SU")
FORBIDDEN_KEYS=("password","secret","token","api_key","cookie","session","private_key")
MAX_MISFIRE_GRACE_SECONDS=31*24*60*60


class ScheduleValidationError(ValueError):pass


def aware(value:str,field:str)->datetime:
    try:parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (TypeError,ValueError) as exc:raise ScheduleValidationError(f"{field} must be an RFC3339 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:raise ScheduleValidationError(f"{field} must be timezone-aware")
    return parsed


def validate_timezone(value:str)->str:
    try:ZoneInfo(value)
    except (ZoneInfoNotFoundError,ValueError,TypeError) as exc:raise ScheduleValidationError("timezone must be a valid IANA name") from exc
    return value


def _local_time(value:Any)->str:
    if not isinstance(value,str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",value):raise ScheduleValidationError("local_time must use HH:MM")
    return value


def validate_trigger(trigger:dict[str,Any])->dict[str,Any]:
    if not isinstance(trigger,dict):raise ScheduleValidationError("trigger must be an object")
    kind=trigger.get("type")
    if kind=="once":return {"type":"once","at":aware(trigger.get("at"),"at").isoformat()}
    if kind=="hourly":
        every=trigger.get("every_hours")
        if type(every) is not int or every<1 or every>24*31:raise ScheduleValidationError("every_hours must be an integer from 1 to 744")
        return {"type":"hourly","every_hours":every,"anchor_at":aware(trigger.get("anchor_at"),"anchor_at").isoformat()}
    if kind=="daily":return {"type":"daily","local_time":_local_time(trigger.get("local_time"))}
    if kind=="weekly":
        days=trigger.get("weekdays")
        if not isinstance(days,list) or not days or any(item not in WEEKDAYS for item in days) or len(set(days))!=len(days):raise ScheduleValidationError("weekdays must be unique MO..SU codes")
        return {"type":"weekly","weekdays":sorted(days,key=WEEKDAYS.index),"local_time":_local_time(trigger.get("local_time"))}
    raise ScheduleValidationError("unknown trigger type")


def _inspect(value:Any,key:str="payload")->None:
    lowered=key.casefold()
    if any(item in lowered for item in FORBIDDEN_KEYS):raise ScheduleValidationError(f"credential-like key is forbidden: {key}")
    if lowered in {"command","shell","exec","executable","callback","hook"}:raise ScheduleValidationError("executable hooks are forbidden")
    if callable(value):raise ScheduleValidationError("callable job-template values are forbidden")
    if isinstance(value,str):
        if re.search(r"(?:^|\s)(?:/|~/|file://|[a-z]:\\)",value,re.I):raise ScheduleValidationError("absolute filesystem paths are forbidden")
    elif isinstance(value,dict):
        for child,item in value.items():
            if not isinstance(child,str):raise ScheduleValidationError("job-template keys must be strings")
            _inspect(item,child)
    elif isinstance(value,(list,tuple)):
        for item in value:_inspect(item,key)


def validate_job_template(value:dict[str,Any])->dict[str,Any]:
    if not isinstance(value,dict):raise ScheduleValidationError("job_template must be an object")
    required=("job_type","title","payload","requires_approval")
    if any(key not in value for key in required):raise ScheduleValidationError("job_template requires job_type, title, payload, and requires_approval")
    if not isinstance(value["job_type"],str) or not value["job_type"].strip() or len(value["job_type"])>120:raise ScheduleValidationError("job_type is invalid")
    if not isinstance(value["title"],str) or not value["title"].strip() or len(value["title"])>200:raise ScheduleValidationError("title is invalid")
    if not isinstance(value["payload"],dict):raise ScheduleValidationError("payload must be an object")
    if type(value["requires_approval"]) is not bool:raise ScheduleValidationError("requires_approval must be boolean")
    if "priority" in value and (type(value["priority"]) is not int or not 1<=value["priority"]<=10):raise ScheduleValidationError("priority must be 1..10")
    if "profile_binding_reference" in value and (not isinstance(value["profile_binding_reference"],str) or "/" in value["profile_binding_reference"] or "\\" in value["profile_binding_reference"] or len(value["profile_binding_reference"])>160):raise ScheduleValidationError("profile_binding_reference must be opaque")
    if "tags" in value and (not isinstance(value["tags"],list) or len(value["tags"])>20 or any(not isinstance(item,str) or len(item)>60 for item in value["tags"])):raise ScheduleValidationError("tags are invalid")
    _inspect(value)
    try:json.dumps(value,sort_keys=True)
    except (TypeError,ValueError) as exc:raise ScheduleValidationError("job_template must be JSON-serializable") from exc
    return json.loads(json.dumps(value))


def payload_digest(value:dict[str,Any])->str:
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


@dataclass
class Schedule:
    schema_version:str;schedule_id:str;name:str;enabled:bool;timezone:str;trigger:dict[str,Any];job_template:dict[str,Any]
    misfire_policy:str;misfire_grace_seconds:int;created_at:str;updated_at:str;next_run_at:str|None
    last_evaluated_at:str|None=None;last_enqueued_occurrence:str|None=None;payload_digest:str="";completed:bool=False
    def to_dict(self)->dict[str,Any]:return asdict(self)
    @classmethod
    def from_dict(cls,value:dict[str,Any])->"Schedule":
        schedule=cls(**value);validate_schedule(schedule);return schedule


def validate_schedule(schedule:Schedule)->Schedule:
    if schedule.schema_version!=SCHEMA_VERSION:raise ScheduleValidationError("unsupported schedule schema")
    if not SCHEDULE_ID.fullmatch(schedule.schedule_id):raise ScheduleValidationError("malformed schedule ID")
    if not isinstance(schedule.name,str) or not schedule.name.strip() or len(schedule.name)>200:raise ScheduleValidationError("schedule name is invalid")
    validate_timezone(schedule.timezone);schedule.trigger=validate_trigger(schedule.trigger);schedule.job_template=validate_job_template(schedule.job_template)
    if schedule.misfire_policy not in {"skip","fire_once"}:raise ScheduleValidationError("misfire_policy must be skip or fire_once")
    if type(schedule.misfire_grace_seconds) is not int or not 0<=schedule.misfire_grace_seconds<=MAX_MISFIRE_GRACE_SECONDS:raise ScheduleValidationError("misfire grace is out of range")
    for field in ("created_at","updated_at"):
        aware(getattr(schedule,field),field)
    if schedule.next_run_at:aware(schedule.next_run_at,"next_run_at")
    expected=payload_digest(schedule.job_template)
    if schedule.payload_digest!=expected:raise ScheduleValidationError("payload digest mismatch")
    return schedule
