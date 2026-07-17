from __future__ import annotations
import json,re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4
from jamesos.core.career.models import CareerProfile, NormalizedJob, now, validate_profile
from jamesos.core.career.storage import CareerStore
from jamesos.services.job_ingestion import EmailJobAlertAdapter,ManualJobAdapter,canonicalize_url
from jamesos.services.job_ranking import rank_job

def _sha(value):return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def _norm(value):return re.sub(r"[^a-z0-9]+"," ",str(value or "").casefold()).strip()

def load_career_profile(path:Path)->CareerProfile:
    value=json.loads(path.read_text(encoding="utf-8"));return validate_profile(CareerProfile.from_dict(value))

class JobSearchService:
    def __init__(self,store:CareerStore,profile:CareerProfile):self.store=store;self.profile=validate_profile(profile)
    def _normalize(self,row):
        source=str(row.get("source") or "unknown");url=canonicalize_url(row.get("source_url") or row.get("canonical_url"));content={k:row.get(k) for k in ("title","company","location","description","requirements","preferred_skills")}
        digest=_sha(content);job_id=f"job-{digest[:16]}"
        return NormalizedJob(job_id=job_id,source=source,source_job_id=row.get("source_job_id"),canonical_url=url,title=row.get("title"),company=row.get("company"),
            location=row.get("location"),work_setting=row.get("work_setting"),salary_min=row.get("salary_min"),salary_max=row.get("salary_max"),salary_currency=row.get("salary_currency"),
            employment_type=row.get("employment_type"),description=row.get("description"),requirements=list(row.get("requirements") or []),preferred_skills=list(row.get("preferred_skills") or []),
            date_posted=row.get("date_posted"),source_evidence=dict(row.get("source_evidence") or {}),content_sha256=digest)
    def duplicate_assessment(self,job,other):
        evidence=[]
        if job.canonical_url and job.canonical_url==other.canonical_url:evidence.append("canonical_url")
        if job.source_job_id and job.source==other.source and job.source_job_id==other.source_job_id:evidence.append("source_job_id")
        identity=(_norm(job.company),_norm(job.title),_norm(job.location));other_identity=(_norm(other.company),_norm(other.title),_norm(other.location))
        if all(identity) and identity==other_identity:evidence.append("company_title_location")
        if job.content_sha256==other.content_sha256:evidence.append("description_fingerprint")
        left=set(_norm(job.description).split());right=set(_norm(other.description).split());similarity=len(left&right)/max(1,len(left|right))
        if similarity>=.85:evidence.append("conservative_text_similarity")
        confidence="exact" if set(evidence)&{"canonical_url","source_job_id","description_fingerprint"} else "uncertain" if evidence or similarity>=.65 else "none"
        return {"confidence":confidence,"matching_evidence":evidence,"text_similarity":round(similarity,3),"reason":", ".join(evidence) or "no conservative match"}
    def ingest(self,adapter,source,*,confirmed=False,**metadata):
        candidates=[]
        for row in adapter.parse(source,**metadata):
            job=self._normalize(row);matches=[]
            for other in self.store.list_jobs():
                assessment=self.duplicate_assessment(job,other)
                if assessment["confidence"]!="none":matches.append({"job_id":other.job_id,**assessment})
            exact=next((x for x in matches if x["confidence"]=="exact"),None)
            group=exact["job_id"] if exact else f"dup-{_sha(sorted(x['job_id'] for x in matches))[:12]}" if matches else None
            job.duplicate_group_id=group;candidates.append({"job":job.to_dict(),"duplicates":matches})
            if confirmed and not exact:self.store.save_job(job)
        return {"result":"jobs_ingested" if confirmed else "job_ingestion_plan","dry_run":not confirmed,"write_performed":confirmed,"candidates":candidates}
    def ingest_email(self,source,**kwargs):return self.ingest(EmailJobAlertAdapter(),source,**kwargs)
    def ingest_manual(self,source,**kwargs):return self.ingest(ManualJobAdapter(),source,**kwargs)
    def rank(self,job_id):return rank_job(self.store.get_job(job_id),self.profile)
    def shortlist(self,job_id,*,confirmed=False):return self._transition_job(job_id,"shortlisted",confirmed)
    def _transition_job(self,job_id,status,confirmed):
        job=self.store.get_job(job_id)
        if confirmed:job.status=status;job.updated_at=now();self.store.save_job(job)
        return {"result":f"job_{status}" if confirmed else f"job_{status}_plan","job_id":job_id,"target_status":status,"dry_run":not confirmed,"write_performed":confirmed}
    def report(self,write=False):
        jobs=self.store.list_jobs();apps=self.store.list_applications();ranked=sorted((rank_job(j,self.profile) for j in jobs),key=lambda x:x["total_score"],reverse=True)
        uncertain=[j for j in jobs if j.duplicate_group_id];by_status=lambda status:[a for a in apps if a.status==status]
        lines=["# Job Search Report",f"Generated: {now()}","","## Recently discovered",*[f"- {j.title or 'Untitled'} — {j.company or 'Unknown'} ({j.status})" for j in jobs[-20:]],
            "","## Highest ranked",*[f"- {r['total_score']}: {r['job_id']}" for r in ranked[:20]],"","## Hard blocked",*[f"- {r['job_id']}: {', '.join(r['hard_blockers'])}" for r in ranked if r['hard_blockers']],
            "","## Uncertain duplicates",*[f"- {j.job_id}: {j.duplicate_group_id}" for j in uncertain],"","## Shortlisted jobs",*[f"- {j.job_id}" for j in jobs if j.status=="shortlisted"],
            "","## Applications being prepared",*[f"- {a.application_id}" for a in by_status("preparing")],"","## Applications awaiting review",*[f"- {a.application_id}" for a in by_status("awaiting_review")],
            "","## Approved but not submitted",*[f"- {a.application_id}" for a in by_status("approved")],"","## Submitted applications",*[f"- {a.application_id}" for a in by_status("submitted")],
            "","## Follow-up dates","- No follow-up dates recorded." ]
        text="\n".join(lines)+"\n";path=None
        if write:path=self.store.write_text(self.store.report_path(),text)
        return {"result":"career_report_ready","report":text,"report_path":str(path) if path else None,"write_performed":bool(write)}


class CareerOperations:
    """Capability-shaped facade used by CareerAgent's local tool binding."""
    def __init__(self,jobs,applications):self.jobs,self.applications=jobs,applications
    def jobs_ingest(self,source,source_type="manual",dry_run=True,**metadata):
        adapter=EmailJobAlertAdapter() if source_type=="email" else ManualJobAdapter()
        return self.jobs.ingest(adapter,source,confirmed=not dry_run,**metadata)
    def jobs_read(self,job_id,**_):return self.jobs.store.get_job(job_id).to_dict()
    def jobs_rank(self,job_id,**_):return self.jobs.rank(job_id)
    def jobs_shortlist(self,job_id,dry_run=True,**_):return self.jobs.shortlist(job_id,confirmed=not dry_run)
    def application_prepare(self,job_id,dry_run=True,**kwargs):return self.applications.prepare(job_id,confirmed=not dry_run,**kwargs)
    def application_review(self,application_id,**_):return self.applications.review(application_id)
    def application_approve(self,application_id,proposal_sha256,dry_run=True,**_):return self.applications.approve(application_id,proposal_sha256,confirmed=not dry_run)
    def application_mark_submitted(self,application_id,dry_run=True,**_):return self.applications.mark_submitted(application_id,confirmed=not dry_run)
