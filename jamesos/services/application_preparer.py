from __future__ import annotations
import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from jamesos.core.career.models import ApplicationProposal, CareerProfile, now
from jamesos.core.career.storage import CareerStore
from jamesos.services.job_ranking import rank_job

SENSITIVE_QUESTIONS=("sponsorship","work authorization","salary","relocation","criminal","disability","veteran","clearance","travel","race","gender","demographic")
def proposal_hash(value):return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

class ApplicationPreparer:
    def __init__(self,store:CareerStore,profile:CareerProfile):self.store=store;self.profile=profile
    def prepare(self,job_id,*,confirmed=False,resume_reference=None,destination=None,submission_method="manual"):
        job=self.store.get_job(job_id);ranking=rank_job(job,self.profile);resume=resume_reference or (self.profile.resume_file_references[0] if self.profile.resume_file_references else None)
        resume_path=Path(resume).expanduser() if resume else None;resume_sha=sha256(resume_path.read_bytes()).hexdigest() if resume_path and resume_path.is_file() else None
        known=[x for x in self.profile.required_technologies+self.profile.preferred_technologies if x.casefold() in (job.description or "").casefold()]
        answers={};unanswered=[]
        for question in SENSITIVE_QUESTIONS:
            stored=next((v for k,v in self.profile.reusable_answers.items() if question in k.casefold()),None)
            if stored is not None:answers[question]=stored
            else:unanswered.append(question)
        proposal={"normalized_job":job.to_dict(),"match_analysis":ranking,"strengths":known,"concerns":ranking["uncertainties"],"missing_qualifications":ranking["supporting_evidence"].get("missing_required_technologies",[]),
            "resume_reference":resume,"resume_sha256":resume_sha,"tailored_summary":f"Candidate profile aligns with: {', '.join(known)}." if known else "No tailored claims can be made from the configured profile.",
            "resume_bullet_emphasis":known,"cover_letter":f"I am interested in the {job.title or 'role'} at {job.company or 'the organization'}. This draft uses only configured career-profile facts.",
            "recruiter_message":f"I am interested in the {job.title or 'role'}. Please share any missing role details.","screening_answers":answers,
            "unanswered_questions":unanswered,"original_source_references":{"source":job.source,"canonical_url":job.canonical_url,"source_job_id":job.source_job_id},
            "application_checklist":["human review","verify resume","verify answers","submit manually"],"intended_destination":destination or job.canonical_url,
            "intended_submission_method":submission_method}
        digest=proposal_hash(proposal);app=ApplicationProposal(f"application-{uuid4().hex[:16]}",job_id,"awaiting_review",proposal,digest,transitions=[{"from":"shortlisted","to":"awaiting_review","at":now()}])
        if confirmed:self.store.save_application(app);job.status="awaiting_review";job.updated_at=now();self.store.save_job(job)
        return {"result":"application_prepared" if confirmed else "application_preparation_plan","dry_run":not confirmed,"write_performed":confirmed,"application":app.to_dict()}
    def review(self,app_id):return self.store.get_application(app_id).to_dict()
    def approve(self,app_id,digest,*,confirmed=False):
        app=self.store.get_application(app_id);current=proposal_hash(app.proposal)
        if digest!=current or digest!=app.proposal_sha256:raise ValueError("proposal hash does not match current application proposal")
        if confirmed:app.status="approved";app.approval={"approved":True,"proposal_sha256":digest,"approved_at":now()};app.transitions.append({"from":"awaiting_review","to":"approved","at":now()});app.updated_at=now();self.store.save_application(app)
        return {"result":"application_approved" if confirmed else "application_approval_plan","dry_run":not confirmed,"write_performed":confirmed,"proposal_sha256":digest}
    def mark_submitted(self,app_id,*,confirmed=False):
        app=self.store.get_application(app_id)
        if app.status!="approved" or not app.approval or app.approval.get("proposal_sha256")!=proposal_hash(app.proposal):raise ValueError("exact approved proposal is required before marking submitted")
        if confirmed:app.status="submitted";app.transitions.append({"from":"approved","to":"submitted","at":now(),"external_submission_performed_by_jamesos":False});app.updated_at=now();self.store.save_application(app);job=self.store.get_job(app.job_id);job.status="submitted";job.updated_at=now();self.store.save_job(job)
        return {"result":"application_marked_submitted" if confirmed else "mark_submitted_plan","dry_run":not confirmed,"write_performed":confirmed,"external_request_performed":False}
