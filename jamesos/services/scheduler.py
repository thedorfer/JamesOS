from __future__ import annotations

from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any,Callable

from jamesos.config import VAULT
from jamesos.core.errors import StateConflictError,ValidationError
from jamesos.core.scheduling.models import SCHEMA_VERSION,Schedule,ScheduleValidationError,payload_digest,validate_job_template,validate_schedule,validate_timezone,validate_trigger
from jamesos.core.scheduling.recurrence import next_occurrences,utc_text
from jamesos.services import job_queue


DEFAULT_ROOT=VAULT/"JamesOS"/"Scheduler"
UTC=timezone.utc


class JobQueueAdapter:
    def create(self,template:dict[str,Any],provenance:dict[str,Any])->dict[str,Any]:
        payload={"title":template["title"],"scheduled_payload":template["payload"],"scheduling":provenance,"job_template":template}
        if template.get("requested_capability"):payload["requested_capability"]=template["requested_capability"]
        if template.get("profile_binding_reference"):payload["profile_binding_reference"]=template["profile_binding_reference"]
        return job_queue.create_job(template["job_type"],payload,priority=template.get("priority",5),requires_approval=template["requires_approval"])
    def find_occurrence(self,occurrence_id:str)->dict[str,Any]|None:
        for job in job_queue.list_jobs():
            if ((job.get("payload") or {}).get("scheduling") or {}).get("occurrence_id")==occurrence_id:return job
        return None


class SchedulerService:
    def __init__(self,root:Path=DEFAULT_ROOT,job_queue_service:Any|None=None,clock:Callable[[],datetime]|None=None):
        self.root=Path(root);self.job_queue=job_queue_service or JobQueueAdapter();self.clock=clock or (lambda:datetime.now(UTC))
        self._validate_root()

    def _now(self)->datetime:
        value=self.clock()
        if value.tzinfo is None or value.utcoffset() is None:raise ScheduleValidationError("clock must return an aware datetime")
        return value.astimezone(UTC)

    def _validate_root(self)->None:
        if self.root.exists() and self.root.is_symlink():raise ScheduleValidationError("scheduler root cannot be a symlink")
        for parent in (self.root,*self.root.parents):
            if parent.exists() and parent.is_symlink():raise ScheduleValidationError("scheduler root cannot traverse symlinks")
        for child in (self.root/"schedules",self.root/"occurrences"):
            if child.exists() and child.is_symlink():raise ScheduleValidationError("scheduler storage cannot traverse symlinks")

    def _dirs(self)->None:
        self._validate_root()
        for path in (self.root,self.root/"schedules",self.root/"occurrences"):
            path.mkdir(parents=True,exist_ok=True);os.chmod(path,0o700)

    def _schedule_path(self,schedule_id:str)->Path:
        if not isinstance(schedule_id,str) or not __import__("re").fullmatch(r"schedule-[0-9a-f]{24}",schedule_id):raise ScheduleValidationError("malformed schedule ID")
        return self.root/"schedules"/f"{schedule_id}.json"

    def _atomic(self,path:Path,value:dict[str,Any])->None:
        self._dirs();path.parent.mkdir(parents=True,exist_ok=True);os.chmod(path.parent,0o700)
        if path.parent.is_symlink():raise ScheduleValidationError("scheduler storage cannot traverse symlinks")
        fd,name=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(value,stream,indent=2,sort_keys=True);stream.write("\n");stream.flush();os.fsync(stream.fileno())
            os.chmod(name,0o600);os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def _load(self,schedule_id:str)->Schedule:
        self._validate_root()
        path=self._schedule_path(schedule_id)
        if not path.is_file() or path.is_symlink():raise ScheduleValidationError("schedule not found")
        return Schedule.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def plan_create(self,*,name:str,timezone_name:str,trigger:dict[str,Any],job_template:dict[str,Any],misfire_policy:str="fire_once",misfire_grace_seconds:int=3600)->dict[str,Any]:
        now=self._now();validate_timezone(timezone_name);clean_trigger=validate_trigger(trigger);template=validate_job_template(job_template)
        schedule_id=f"schedule-{secrets.token_hex(12)}";next_values=next_occurrences(clean_trigger,timezone_name,now,1,inclusive=True)
        if not next_values:raise ScheduleValidationError("trigger has no future occurrence")
        schedule=Schedule(SCHEMA_VERSION,schedule_id,name,True,timezone_name,clean_trigger,template,misfire_policy,misfire_grace_seconds,
            utc_text(now),utc_text(now),utc_text(next_values[0]),payload_digest=payload_digest(template))
        validate_schedule(schedule)
        return {"result":"schedule_creation_plan","write_performed":False,"schedule":{"name":schedule.name,"enabled":True,"timezone":schedule.timezone,
            "trigger_type":schedule.trigger["type"],"next_run_at":schedule.next_run_at},"payload_digest":schedule.payload_digest,"requires_confirmation":True,"_schedule":schedule}

    def create(self,*,confirmed:bool=False,**values)->dict[str,Any]:
        plan=self.plan_create(**values);schedule=plan.pop("_schedule")
        if not confirmed:return plan
        self._atomic(self._schedule_path(schedule.schedule_id),schedule.to_dict())
        return {"result":"schedule_created","write_performed":True,"schedule_id":schedule.schedule_id,"next_run_at":schedule.next_run_at}

    def list_schedules(self)->dict[str,Any]:
        self._validate_root()
        if not (self.root/"schedules").exists():rows=[]
        else:rows=[self._public(Schedule.from_dict(json.loads(path.read_text(encoding="utf-8")))) for path in sorted((self.root/"schedules").glob("schedule-*.json")) if not path.is_symlink()]
        return {"result":"schedule_list","schedules":rows,"count":len(rows),"write_performed":False}

    def show(self,schedule_id:str)->dict[str,Any]:return {"result":"schedule_details","schedule":self._public(self._load(schedule_id)),"write_performed":False}

    @staticmethod
    def _public(schedule:Schedule)->dict[str,Any]:
        return {"schema_version":schedule.schema_version,"schedule_id":schedule.schedule_id,"name":schedule.name,"enabled":schedule.enabled,
            "completed":schedule.completed,"timezone":schedule.timezone,"trigger":schedule.trigger,"misfire_policy":schedule.misfire_policy,
            "misfire_grace_seconds":schedule.misfire_grace_seconds,"next_run_at":schedule.next_run_at,"last_evaluated_at":schedule.last_evaluated_at,
            "last_enqueued_occurrence":schedule.last_enqueued_occurrence,"payload_digest":schedule.payload_digest,
            "job_template":{"job_type":schedule.job_template["job_type"],"title":schedule.job_template["title"],"requires_approval":schedule.job_template["requires_approval"]}}

    def preview_occurrences(self,schedule_id:str,count:int)->dict[str,Any]:
        schedule=self._load(schedule_id)
        if not schedule.enabled or schedule.completed:return {"result":"schedule_occurrence_preview","schedule_id":schedule_id,"occurrences":[],"write_performed":False}
        start=datetime.fromisoformat(schedule.next_run_at.replace("Z","+00:00")) if schedule.next_run_at else self._now()
        values=next_occurrences(schedule.trigger,schedule.timezone,start,count,inclusive=True)
        return {"result":"schedule_occurrence_preview","schedule_id":schedule_id,"occurrences":[{"scheduled_for":utc_text(item),"occurrence_id":self._occurrence_id(schedule,item)} for item in values],"write_performed":False}

    def enable(self,schedule_id:str,confirmed:bool=False)->dict[str,Any]:return self._set_enabled(schedule_id,True,confirmed)
    def disable(self,schedule_id:str,confirmed:bool=False)->dict[str,Any]:return self._set_enabled(schedule_id,False,confirmed)
    def _set_enabled(self,schedule_id:str,enabled:bool,confirmed:bool)->dict[str,Any]:
        schedule=self._load(schedule_id);action="enable" if enabled else "disable"
        if not confirmed:return {"result":f"schedule_{action}_plan","schedule_id":schedule_id,"enabled":enabled,"write_performed":False,"requires_confirmation":True}
        if enabled and schedule.completed:raise ScheduleValidationError("completed one-time schedule cannot be enabled")
        schedule.enabled=enabled;schedule.updated_at=utc_text(self._now());self._atomic(self._schedule_path(schedule_id),schedule.to_dict())
        return {"result":f"schedule_{action}d","schedule_id":schedule_id,"enabled":enabled,"write_performed":True}

    def tick(self,confirmed:bool=False)->dict[str,Any]:
        now=self._now();due=[];enqueue_count=0;wrote=False
        schedules=[] if not (self.root/"schedules").exists() else [self._load(path.stem) for path in sorted((self.root/"schedules").glob("schedule-*.json"))]
        for schedule in schedules:
            if not schedule.enabled or schedule.completed or not schedule.next_run_at:continue
            next_run=datetime.fromisoformat(schedule.next_run_at.replace("Z","+00:00")).astimezone(UTC)
            if next_run>now:continue
            occurrences=[];current=next_run
            while current<=now and len(occurrences)<10000:
                occurrences.append(current);following=next_occurrences(schedule.trigger,schedule.timezone,current,1)
                if not following:break
                current=following[0]
            if len(occurrences)>=10000:raise StateConflictError("STATE_CONFLICT",diagnostic_message="Missed occurrence evaluation exceeded its safety bound.",operation="scheduler.tick",stage="recurrence",retryable=False)
            latest=occurrences[-1];occurrence_id=self._occurrence_id(schedule,latest);age=(now-latest).total_seconds()
            skip=schedule.misfire_policy=="skip" and age>schedule.misfire_grace_seconds
            disposition="would_skip_misfire" if skip else "would_enqueue"
            row={"schedule_id":schedule.schedule_id,"occurrence_id":occurrence_id,"scheduled_for":utc_text(latest),"disposition":disposition}
            due.append(row)
            if not confirmed:continue
            if skip:
                self._record(schedule,latest,now,"skipped_misfire",None,len(occurrences)-1);self._advance(schedule,current if current>now else None,now);wrote=True;continue
            existing_record=self._occurrence_path(schedule.schedule_id,occurrence_id)
            existing_job=self.job_queue.find_occurrence(occurrence_id)
            if existing_record.is_file():
                self._advance(schedule,current if current>now else None,now);wrote=True;continue
            try:
                provenance={"schedule_id":schedule.schedule_id,"occurrence_id":occurrence_id,"scheduled_for":utc_text(latest),"source":"jamesos.scheduler",
                    "payload_digest":schedule.payload_digest,"idempotency_reference":occurrence_id}
                job=existing_job or self.job_queue.create(schedule.job_template,provenance)
            except Exception as exc:
                raise StateConflictError("STATE_CONFLICT",diagnostic_message="Job Queue rejected the scheduled occurrence; no automatic retry was attempted.",operation="scheduler.tick",stage="queue_enqueue",retryable=False,
                    context={"schedule_id":schedule.schedule_id,"occurrence_id":occurrence_id,"external_write_performed":False}) from exc
            self._record(schedule,latest,now,"enqueued",job.get("job_id") or job.get("id"),len(occurrences)-1)
            schedule.last_enqueued_occurrence=occurrence_id;enqueue_count+=0 if existing_job else 1
            self._advance(schedule,current if current>now else None,now);wrote=True
        return {"result":"scheduler_tick_completed" if confirmed else "scheduler_tick_plan","evaluated_at":utc_text(now),"due_count":len(due),
            "enqueue_count":enqueue_count,"write_performed":wrote,"external_write_performed":False,"due":due}

    def _advance(self,schedule:Schedule,next_value:datetime|None,now:datetime)->None:
        if schedule.trigger["type"]=="once":schedule.enabled=False;schedule.completed=True;schedule.next_run_at=None
        else:schedule.next_run_at=utc_text(next_value) if next_value else None
        schedule.last_evaluated_at=utc_text(now);schedule.updated_at=utc_text(now);self._atomic(self._schedule_path(schedule.schedule_id),schedule.to_dict())

    def _record(self,schedule:Schedule,scheduled_for:datetime,evaluated_at:datetime,disposition:str,job_id:str|None,missed_count:int)->None:
        occurrence_id=self._occurrence_id(schedule,scheduled_for);record={"occurrence_id":occurrence_id,"schedule_id":schedule.schedule_id,
            "scheduled_for":utc_text(scheduled_for),"evaluated_at":utc_text(evaluated_at),"disposition":disposition,"queue_job_id":job_id,
            "payload_digest":schedule.payload_digest,"earlier_missed_occurrences":missed_count}
        self._atomic(self._occurrence_path(schedule.schedule_id,occurrence_id),record)

    def _occurrence_path(self,schedule_id:str,occurrence_id:str)->Path:
        self._schedule_path(schedule_id)
        if not __import__("re").fullmatch(r"occurrence-[0-9a-f]{64}",occurrence_id):raise ScheduleValidationError("malformed occurrence ID")
        return self.root/"occurrences"/schedule_id/f"{occurrence_id}.json"

    @staticmethod
    def _occurrence_id(schedule:Schedule,scheduled_for:datetime)->str:
        source=f"{schedule.schema_version}|{schedule.schedule_id}|{utc_text(scheduled_for)}"
        return f"occurrence-{sha256(source.encode()).hexdigest()}"
