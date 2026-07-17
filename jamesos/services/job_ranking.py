from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any
from jamesos.core.career.models import CareerProfile, NormalizedJob

def _norm(value):return re.sub(r"[^a-z0-9+#.]+"," ",str(value or "").casefold()).strip()
def _contains(text,terms):return [term for term in terms if _norm(term) and _norm(term) in text]

def rank_job(job:NormalizedJob,profile:CareerProfile)->dict[str,Any]:
    text=_norm(" ".join([job.title or "",job.description or "",*job.requirements,*job.preferred_skills]));components={};evidence={};blockers=[];uncertainties=[];missing=[]
    titles=_contains(_norm(job.title),profile.target_job_titles);components["title_alignment"]=20 if titles else 0;evidence["title_alignment"]=titles
    required=_contains(text,profile.required_technologies);components["required_skill_alignment"]=min(25,5*len(required));evidence["required_skills"]=required
    absent=[x for x in profile.required_technologies if x not in required]
    if absent:blockers.append("missing required profile technologies");evidence["missing_required_technologies"]=absent
    preferred=_contains(text,profile.preferred_technologies);components["preferred_skill_alignment"]=min(15,3*len(preferred));evidence["preferred_skills"]=preferred
    components["seniority"]=5 if not re.search(r"\b(principal|staff|director|vp)\b",_norm(job.title)) else 2
    locations=_contains(_norm(job.location),profile.preferred_locations);components["location_preference"]=8 if locations else 0
    components["work_setting_preference"]=8 if job.work_setting and _norm(job.work_setting) in {_norm(x) for x in profile.work_settings} else 0
    if not job.work_setting:missing.append("work_setting")
    components["compensation"]=8 if profile.minimum_compensation is None else (8 if job.salary_max and job.salary_max>=profile.minimum_compensation else 0)
    if profile.minimum_compensation is not None and job.salary_max is None:uncertainties.append("compensation unavailable");missing.append("compensation")
    components["employment_type"]=5 if not profile.employment_types or _norm(job.employment_type) in {_norm(x) for x in profile.employment_types} else 0
    if _norm(job.company) in {_norm(x) for x in profile.excluded_employers}:blockers.append("excluded employer")
    staffing=_contains(text,profile.excluded_staffing_arrangements)
    if staffing:blockers.append("excluded staffing arrangement");evidence["staffing_patterns"]=staffing
    if profile.sponsorship_requirements and "sponsor" not in text:uncertainties.append("sponsorship compatibility unknown")
    if not profile.work_authorization_facts:uncertainties.append("work authorization facts not configured")
    try:
        posted=datetime.fromisoformat(job.date_posted).astimezone(timezone.utc) if job.date_posted else None;days=max(0,(datetime.now(timezone.utc)-posted).days) if posted else None
    except ValueError:days=None
    components["recency"]=6 if days is not None and days<=7 else 3 if days is not None and days<=30 else 0
    if days is None:missing.append("date_posted")
    total=max(0,sum(components.values())-25*len(blockers))
    return {"job_id":job.job_id,"total_score":total,"component_scores":components,"hard_blockers":blockers,"uncertainties":uncertainties,
        "supporting_evidence":evidence,"missing_information":sorted(set(missing)),"deterministic":True}
