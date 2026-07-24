from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json,re
from pathlib import Path
from typing import Any
from uuid import uuid4
from jamesos.config import VAULT
from jamesos.services.book_opportunity_scout import BookOpportunityScoutService
from jamesos.core.artifacts import AtomicDocumentStore,ApprovalService,AuditEventStore,OperationJournal,ProjectArtifactStore,VersionedDocument,canonical_sha256,now
from jamesos.services.comfyui_creative_studio import ComfyUILocalCreativeStudioProvider
from jamesos.services.local_creative_studio import LocalAssetRequest,LocalCreativeStudioProvider
from jamesos.services.structured_planning import DeterministicPlanProvider,StructuredPlanProvider

ROOT=VAULT/"JamesOS"/"Books"/"Projects";PROJECT=re.compile(r"book-project-[0-9]{8}T[0-9]{6}-[a-f0-9]{8}")
MAXIMUM_ATTEMPTS_PER_PAGE=3
DOCUMENTS=AtomicDocumentStore();APPROVALS=ApprovalService()
class SampleGenerationConflict(ValueError):pass
class SampleGenerationFailure(RuntimeError):pass
def _now():return now()
def _digest(v):return canonical_sha256(v)
def _prompt_hash(value):return sha256(str(value or "").encode("utf-8")).hexdigest()
def _atomic(path,v):
 DOCUMENTS.write_json(path,v)
def _text(path,v):
 DOCUMENTS.write_text(path,v)

class ColoringBookProducer:
 def __init__(self,root:Path=ROOT,scout=None,planner:StructuredPlanProvider|None=None,creative:LocalCreativeStudioProvider|None=None):self.root=root;self.scout=scout or BookOpportunityScoutService();self.artifacts=ProjectArtifactStore(root,DOCUMENTS);self.planner=planner or DeterministicPlanProvider();self.creative=creative or ComfyUILocalCreativeStudioProvider()
 def _source(self,run_id,candidate_id):
  result=self.scout.load(run_id);ranked=result.get("ranked_candidates")
  if not isinstance(ranked,list):raise ValueError("malformed Scout data")
  candidate=next((x for x in ranked if x.get("candidate_id")==candidate_id),None)
  if not candidate:raise ValueError("candidate not found")
  decision=(result.get("decisions") or {}).get(candidate_id)
  if not isinstance(decision,dict) or decision.get("action")!="approve" or candidate.get("decision",decision).get("action")!="approve":raise ValueError("candidate is not approved")
  request=result.get("request") or {};run_root=self.scout.root/run_id;hashes={}
  for name in ("request.json","results.json","evidence.json","decisions.json"):
   path=run_root/name
   if path.is_file():hashes[name]=sha256(path.read_bytes()).hexdigest()
  rank=next(i for i,x in enumerate(ranked,1) if x.get("candidate_id")==candidate_id)
  return {"scout_run_id":run_id,"candidate_id":candidate_id,"concept":candidate.get("concept"),"rank":rank,"total_score":candidate.get("total_score"),"confidence":candidate.get("confidence"),"score_breakdown":candidate.get("score_breakdown"),"differentiation_recommendation":candidate.get("differentiation_recommendation"),"risks":candidate.get("risks") or [],"missing_evidence":candidate.get("missing_evidence") or [],"evidence_references":candidate.get("evidence_references") or [],"research_mode":request.get("source_mode"),"research_label":result.get("research_label"),"research_timestamp":candidate.get("research_timestamp"),"market":request.get("market"),"audience":request.get("audience"),"book_type":request.get("book_type"),"approval_action":"approve","approval_timestamp":decision.get("timestamp"),"source_file_hashes":hashes}
 def defaults(self,source):return {"working_title":source["concept"],"subtitle":"","market":source.get("market") or "","target_audience":source.get("audience") or "","target_age_range":"all ages","book_type":source.get("book_type") or "coloring book","trim_width":8.5,"trim_height":11.0,"coloring_page_count":40,"single_sided":True,"interior_color_mode":"black_and_white","complexity":"simple_to_moderate","visual_style":"bold clean outlines, large open coloring areas, no grayscale shading","recurring_character_notes":"","educational_activity_notes":"","series_name":"","notes":""}
 def _config(self,value,defaults):
  out={**defaults,**(value or {})}
  if not isinstance(out["working_title"],str) or not out["working_title"].strip() or len(out["working_title"])>180:raise ValueError("working title is invalid")
  if type(out["coloring_page_count"]) is not int or not 10<=out["coloring_page_count"]<=200:raise ValueError("page count is invalid")
  if type(out["trim_width"]) not in (int,float) or type(out["trim_height"]) not in (int,float) or not 4<=out["trim_width"]<=14 or not 4<=out["trim_height"]<=14:raise ValueError("trim size is invalid")
  if out["interior_color_mode"]!="black_and_white" or type(out["single_sided"]) is not bool:raise ValueError("production defaults are invalid")
  return out
 def create(self,run_id,candidate_id,configuration=None,confirmed=False):
  source=self._source(run_id,candidate_id);config=self._config(configuration,self.defaults(source));identity=_digest({"run_id":run_id,"candidate_id":candidate_id,"approval_timestamp":source["approval_timestamp"]})
  existing_source=None
  for path in self.root.glob("book-project-*/project.json") if self.root.is_dir() else []:
   try:v=json.loads(path.read_text())
   except (OSError,ValueError):continue
   if v.get("source_identity")==identity:return {**v,"idempotent":True}
   try:stored=json.loads((path.parent/"opportunity-source.json").read_text())
   except (OSError,ValueError):continue
   if stored.get("scout_run_id")==run_id and stored.get("candidate_id")==candidate_id:existing_source=v
  if existing_source:return {**existing_source,"idempotent":True,"existing_project_found":True,"message":"Existing project found. Opening the existing project; no new edition was created."}
  confirmation=f"Create a local Coloring Book Producer project for “{source['concept']}”?\n\nSource:\nScout run {run_id}\nCandidate {candidate_id}\nMarket {source['market']}\nAudience {source['audience']}\n\nThis creates local project files only.\nNo coloring pages, cover art, PDF, Amazon listing, upload, publication, marketplace write, purchase, or order will occur."
  if not confirmed:return {"confirmation_required":True,"confirmation":confirmation,"source":source,"configuration":config,"files_created":0}
  now=_now();pid=f"book-project-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}";root=self.root/pid;source_hash=_digest(source);brief={**config,"concept":source["concept"],"differentiation_direction":source["differentiation_recommendation"],"known_risks":source["risks"],"constraints":["original content only","no protected characters, brands, or properties"]}
  project={"project_id":pid,"agent_id":"jamesos.coloring-book-producer","source_identity":identity,"source_sha256":source_hash,"revision":1,"status":"draft_brief","created_at":now,"updated_at":now,"local_only":True,"images_generated":False,"external_provider_contacted":False,"publication_status":"not_published","order_status":"not_created"}
  files={"project.json":project,"opportunity-source.json":source,"book-brief.json":brief,"production-spec.json":{"trim_width":config["trim_width"],"trim_height":config["trim_height"],"coloring_page_count":config["coloring_page_count"],"single_sided":config["single_sided"],"interior_color_mode":"black_and_white","complexity":config["complexity"],"visual_style":config["visual_style"],"status":"draft","generation_enabled":False,"image_provider":"none","kdp_upload_enabled":False,"publication_enabled":False},"page-plan.json":{"status":"not_generated","pages":[]},"page-prompts.json":{"status":"not_generated","prompts":[]},"approvals.json":{"project_creation":{"confirmed":True,"timestamp":now,"source_identity":identity},"book_brief":None,"production":None}}
  for name,v in files.items():_atomic(root/name,v)
  _text(root/"opportunity-source.sha256",source_hash+"\n");_text(root/"book-brief.md",f"# {config['working_title']}\n\n{config['subtitle']}\n\nAudience: {config['target_audience']}\n\nDifferentiation: {source['differentiation_recommendation']}\n\nOriginal local planning brief. No protected properties.\n");_text(root/"cover-brief.md",f"# Cover brief — {config['working_title']}\n\nSubtitle: {config['subtitle']}\nAudience: {config['target_audience']}\nTheme: {source['concept']}\n\n## Front\nNot planned.\n## Back\nNot planned.\n## Spine\nNot planned.\n\nNo cover image has been generated.\n");_text(root/"events.jsonl",json.dumps({"event":"project_created","timestamp":now,"revision":1,"source_identity":identity})+"\n")
  return {**project,"idempotent":False,"confirmation":confirmation}
 def list(self):
  rows=[];canonical={}
  for p in sorted(self.root.glob("book-project-*/project.json"),reverse=True):
   try:
    project=json.loads(p.read_text());source=json.loads((p.parent/"opportunity-source.json").read_text());brief=json.loads((p.parent/"book-brief.json").read_text())
   except (OSError,ValueError):pass
   else:rows.append({**project,"working_title":brief.get("working_title"),"concept":source.get("concept"),"scout_run_id":source.get("scout_run_id"),"candidate_id":source.get("candidate_id"),"approval_timestamp":source.get("approval_timestamp")})
  for row in sorted(rows,key=lambda x:x.get("created_at") or ""):
   identity=row.get("source_identity")
   if identity not in canonical:canonical[identity]=row["project_id"]
   elif row.get("duplicate_of")!=canonical[identity]:
    row["duplicate_of"]=canonical[identity];row["status"]="superseded_duplicate";_atomic(self.root/row["project_id"]/"project.json",{k:v for k,v in row.items() if k not in {"working_title","concept","scout_run_id","candidate_id","approval_timestamp"}})
  return sorted(rows,key=lambda x:x.get("created_at") or "",reverse=True)
 def load(self,pid):
  if not PROJECT.fullmatch(pid) or Path(pid).name!=pid:raise ValueError("invalid project ID")
  root=self.root/pid;project=self.artifacts.read(pid,"project.json");brief=self.artifacts.read(pid,"book-brief.json");spec=self.artifacts.read(pid,"production-spec.json");approvals=self.artifacts.read(pid,"approvals.json");document=VersionedDocument.bind(project["revision"],brief,spec,names=("book_brief","production_spec"))
  plan=self.artifacts.read(pid,"page-plan.json");prompts=self.artifacts.read(pid,"page-prompts.json");plan_approval=APPROVALS.state(approvals.get("page_plan"),VersionedDocument(int(plan.get("plan_revision") or 0),str(plan.get("page_plan_sha256") or "")))
  return {"project":project,"source":self.artifacts.read(pid,"opportunity-source.json"),"book_brief":brief,"production_spec":spec,"page_plan":plan,"page_prompts":prompts,"cover_brief":(root/"cover-brief.md").read_text(),"approvals":approvals,"book_brief_approval":APPROVALS.state(approvals.get("book_brief"),document),"page_plan_approval":plan_approval}
 def update(self,pid,brief=None,production_spec=None):
  value=self.load(pid);root=self.root/pid;new_brief=self._config(brief,value["book_brief"]);new_spec={**value["production_spec"],**(production_spec or {})}
  allowed={"trim_width","trim_height","coloring_page_count","single_sided","interior_color_mode","complexity","visual_style","status","generation_enabled","image_provider","kdp_upload_enabled","publication_enabled"}
  if set(new_spec)-allowed:raise ValueError("unsupported production field")
  self._config({**new_brief,**{k:new_spec[k] for k in ("trim_width","trim_height","coloring_page_count","single_sided","interior_color_mode","complexity","visual_style")}},new_brief)
  project=value["project"];project["revision"]+=1;project["updated_at"]=_now();project["status"]="draft_brief";approvals=value["approvals"]
  if approvals.get("book_brief"):approvals["book_brief"]={**approvals["book_brief"],"stale":True,"invalidated_at":project["updated_at"],"invalidated_by_revision":project["revision"]}
  plan=value["page_plan"]
  if plan.get("status") not in {None,"not_generated"}:plan["status"]="stale";plan["stale_reason"]="source_brief_or_production_spec_changed";_atomic(root/"page-plan.json",plan)
  if approvals.get("page_plan"):approvals["page_plan"]={**approvals["page_plan"],"stale":True,"invalidated_at":project["updated_at"]}
  _atomic(root/"book-brief.json",new_brief);_text(root/"book-brief.md",f"# {new_brief['working_title']}\n\n{new_brief['subtitle']}\n\nAudience: {new_brief['target_audience']}\n\nDifferentiation: {new_brief['differentiation_direction']}\n\nOriginal local planning brief. No protected properties.\n");_atomic(root/"production-spec.json",new_spec);_atomic(root/"project.json",project);_atomic(root/"approvals.json",approvals)
  AuditEventStore(root/"events.jsonl").append({"event":"project_edited","timestamp":project["updated_at"],"revision":project["revision"]})
  return self.load(pid)
 def approve_brief(self,pid,confirmed=False):
  value=self.load(pid);project=value["project"];document=VersionedDocument.bind(project["revision"],value["book_brief"],value["production_spec"],names=("book_brief","production_spec"));content_hash=document.content_sha256;message=f"Approve Book Brief locally for {value['book_brief']['working_title']} at revision {project['revision']}? No images, PDF, provider call, publication, purchase, or order will occur."
  if not confirmed:return APPROVALS.preview(document,message)
  root=self.root/pid;approvals=value["approvals"]
  if (approvals.get("book_brief") or {}).get("content_hash")==content_hash:return {**approvals["book_brief"],"idempotent":True}
  approval=APPROVALS.record(document);approvals["book_brief"]=approval;project["status"]="brief_approved";project["updated_at"]=approval["timestamp"]
  _atomic(root/"approvals.json",approvals);_atomic(root/"project.json",project)
  AuditEventStore(root/"events.jsonl").append({"event":"book_brief_approved","timestamp":approval["timestamp"],"revision":project["revision"],"content_hash":content_hash})
  return {**approval,"idempotent":False}

 def _plan_validation(self,pages,count):
  titles=[x.get("title") for x in pages];scenes=[x.get("scene_summary") for x in pages];characters=[c for x in pages for c in x.get("characters",[])];categories=[x.get("category") for x in pages];warnings=[]
  if len(pages)!=count:warnings.append(f"Expected {count} pages; found {len(pages)}.")
  if len(set(titles))!=len(titles):warnings.append("Page titles must be unique.")
  if len(set(scenes))!=len(scenes):warnings.append("Scenes must be materially distinct.")
  required={"bear","fox","raccoon","rabbit","squirrel","owl","hedgehog"}
  if not required.issubset(characters):warnings.append("Recurring character coverage is incomplete.")
  return {"valid":not warnings,"warnings":warnings,"category_distribution":{x:categories.count(x) for x in sorted(set(categories))},"character_distribution":{x:characters.count(x) for x in sorted(set(characters))}}

 def generate_page_plan(self,pid,*,confirmed=False,regenerate=False):
  value=self.load(pid);project=value["project"];approval=value["approvals"].get("book_brief") or {}
  if project.get("status") not in {"brief_approved","page_plan_draft","page_plan_approved"} or value["book_brief_approval"]["state"]!="approved":raise ValueError("an approved current book brief is required")
  count=int(value["production_spec"]["coloring_page_count"]);brief_hash=approval["content_hash"];current=value["page_plan"]
  if current.get("status") not in {None,"not_generated","stale"} and current.get("source_brief_revision")==project["revision"] and current.get("source_brief_hash")==brief_hash and not regenerate:return {**current,"idempotent":True}
  preview={"confirmation_required":True,"project_id":pid,"approved_brief_revision":project["revision"],"approved_brief_hash":brief_hash,"requested_page_count":count,"audience":value["book_brief"]["target_audience"],"visual_style":value["production_spec"]["visual_style"],"recurring_character_rules":value["book_brief"].get("recurring_character_notes") or "Balanced recurring woodland friends: bear, fox, raccoon, rabbit, squirrel, owl, and hedgehog.","local_only_safety":{"images":0,"pdfs":0,"external_provider_calls":0,"marketplace_writes":0,"publications":0,"purchases":0,"orders":0},"regeneration":regenerate}
  if not confirmed:return preview
  if current.get("status") not in {None,"not_generated","stale"} and not regenerate:raise ValueError("an existing current plan must be opened; regeneration requires separate confirmation")
  categories=("arrival and unpacking","tents","hiking","maps","campfire activities","cooking","marshmallows","fishing","canoeing","birdwatching","leaves and nature study","weather preparation","camp games","storytelling","stargazing","nighttime camping","teamwork","campsite safety","packing","leave-no-trace cleanup")
  provider=self.planner.propose({"topics":[categories[i%len(categories)] for i in range(count)],"count":count});topics=[x["topic"] for x in provider["items"]]
  cast=("bear","fox","raccoon","rabbit","squirrel","owl","hedgehog");pages=[];prompts=[]
  for index,category in enumerate(topics):
   number=index+1;characters=[cast[index%len(cast)],cast[(index+3)%len(cast)]];title=f"{category.title()} Adventure {index//len(categories)+1}";page_id=f"page-{number:03d}";prompt_id=f"prompt-{number:03d}";action=f"{characters[0]} and {characters[1]} practice {category} together"
   page={"page_number":number,"page_id":page_id,"title":title,"scene_summary":f"A distinct child-friendly campsite scene where {action}.","characters":characters,"setting":"original woodland campsite","foreground_objects":["large simple camping object","open natural shapes"],"background_objects":["widely spaced trees","simple clouds"],"main_action":action,"composition":"one clear centered focal action with large open coloring areas","complexity":"simple_to_moderate","educational_or_activity_element":f"gentle ages 4–8 learning about {category}","continuity_notes":"Use the same original woodland character designs and friendly proportions.","originality_constraints":["original scene","no imitation of commercial artwork"],"protected_property_constraints":["no brands","no copyrighted characters","no commercial-property references"],"category":category,"status":"draft","prompt_id":prompt_id};pages.append(page)
   prompts.append({"prompt_id":prompt_id,"page_id":page_id,"positive_prompt":f"Black-and-white coloring-book line art of {page['scene_summary']} Bold clean outlines, large open coloring spaces, child-friendly expressions, uncluttered composition, white background, no text inside the image.","negative_prompt":"color, grayscale shading, crosshatching, photorealism, clutter, tiny details, logos, watermarks, copyrighted characters, malformed anatomy, duplicate limbs, cropped focal subjects","style_rules":["bold clean outlines","large open coloring spaces","white background","no image text"],"continuity_rules":["consistent original woodland characters","ages 4–8 suitability"],"trim_orientation":"portrait","safe_margin_notes":"Keep all focal subjects inside generous trim-safe margins.","status":"draft","image_generated":False})
  revision=int(current.get("plan_revision") or 0)+1;generated=_now();validation=self._plan_validation(pages,count);plan={"status":"draft","planner_provider_id":provider["provider_id"],"planner_provider_version":"1","source_brief_revision":project["revision"],"source_brief_hash":brief_hash,"plan_revision":revision,"generated_at":generated,"pages":pages,"validation":validation};plan["page_plan_sha256"]=_digest(plan);prompt_set={"status":"draft","source_plan_revision":revision,"generated_at":generated,"prompts":prompts};prompt_set["prompt_set_sha256"]=_digest(prompt_set)
  root=self.root/pid
  if regenerate and current.get("plan_revision"):self.artifacts.write(pid,f"page-plan-revisions/revision-{current['plan_revision']}.json",current);self.artifacts.write(pid,f"page-plan-revisions/prompts-{current['plan_revision']}.json",value["page_prompts"])
  self.artifacts.write(pid,"page-plan.json",plan);self.artifacts.write(pid,"page-prompts.json",prompt_set);project.update(status="page_plan_draft",updated_at=generated);self.artifacts.write(pid,"project.json",project);approvals=value["approvals"];approvals["page_plan"]=None;self.artifacts.write(pid,"approvals.json",approvals);AuditEventStore(root/"events.jsonl").append({"event":"page_plan_generated","timestamp":generated,"plan_revision":revision,"page_plan_sha256":plan["page_plan_sha256"],"provider_id":provider["provider_id"],"external_provider_calls":0});return {**plan,"prompt_set_sha256":prompt_set["prompt_set_sha256"],"idempotent":False}

 def edit_page_plan(self,pid,pages):
  value=self.load(pid);plan=value["page_plan"]
  if plan.get("status") not in {"draft","approved"}:raise ValueError("page plan is not editable")
  if not isinstance(pages,list) or not pages:raise ValueError("pages are required")
  for index,page in enumerate(pages,1):page["page_number"]=index
  plan["pages"]=pages;plan["plan_revision"]=int(plan.get("plan_revision") or 0)+1;plan["status"]="draft";plan["updated_at"]=_now();plan["validation"]=self._plan_validation(pages,int(value["production_spec"]["coloring_page_count"]));plan.pop("page_plan_sha256",None);plan["page_plan_sha256"]=_digest(plan);self.artifacts.write(pid,"page-plan.json",plan);approvals=value["approvals"]
  if approvals.get("page_plan"):approvals["page_plan"]={**approvals["page_plan"],"stale":True,"invalidated_at":plan["updated_at"]};self.artifacts.write(pid,"approvals.json",approvals)
  project=value["project"];project.update(status="page_plan_draft",updated_at=plan["updated_at"]);self.artifacts.write(pid,"project.json",project);AuditEventStore(self.root/pid/"events.jsonl").append({"event":"page_plan_edited","timestamp":plan["updated_at"],"plan_revision":plan["plan_revision"],"external_provider_calls":0});return self.load(pid)

 def approve_page_plan(self,pid,confirmed=False):
  value=self.load(pid);plan=value["page_plan"]
  if plan.get("status") not in {"draft","approved"} or not plan.get("validation",{}).get("valid"):raise ValueError("a valid page plan draft is required")
  document=VersionedDocument(int(plan["plan_revision"]),plan["page_plan_sha256"]);approvals=value["approvals"];existing=approvals.get("page_plan") or {};matches=existing.get("content_hash")==document.content_sha256 and existing.get("revision")==document.revision and existing.get("stale") is not True
  if plan.get("status")=="approved" and not matches:raise ValueError("approved page plan identity does not match its approval")
  message=f"Approve Page Plan locally for project {pid}? Plan revision: {plan['plan_revision']}. Page count: {len(plan['pages'])}. Page-plan hash: {plan['page_plan_sha256']}. This records local approval only. No image generation or external action will occur."
  if not confirmed:return APPROVALS.preview(document,message)|{"project_id":pid,"page_count":len(plan["pages"]),"page_plan_hash":plan["page_plan_sha256"],"validation":plan["validation"],"already_approved":matches}
  if matches:return {**existing,"idempotent":True,"message":"Page plan approved locally.\n\nNext step:\nConfigure the local coloring-page workflow, then generate 3 sample pages.\n\nNo images or external actions occurred."}
  approval=APPROVALS.record(document);approvals["page_plan"]=approval;self.artifacts.write(pid,"approvals.json",approvals);plan["status"]="approved";self.artifacts.write(pid,"page-plan.json",plan);project=value["project"];project.update(status="page_plan_approved",updated_at=approval["timestamp"]);self.artifacts.write(pid,"project.json",project);AuditEventStore(self.root/pid/"events.jsonl").append({"event":"page_plan_approved","timestamp":approval["timestamp"],"plan_revision":plan["plan_revision"],"content_hash":document.content_sha256,"external_provider_calls":0});return {**approval,"idempotent":False,"message":"Page plan approved locally.\n\nNext step:\nConfigure the local coloring-page workflow, then generate 3 sample pages.\n\nNo images or external actions occurred."}

 def _sample_selection(self,value):
  pages=value["page_plan"]["pages"];selected=[];used=set()
  for categories in (("arrival and unpacking","tents","leaves and nature study"),("teamwork","campfire activities","camp games"),("stargazing","nighttime camping")):
   page=next(x for x in pages if x["page_id"] not in used and x.get("category") in categories);used.add(page["page_id"]);selected.append(page)
  return selected

 def sample_status(self,pid):
  value=self.load(pid);path=self.root/pid/"samples/manifest.json"
  try:
   manifest=DOCUMENTS.read_json(path)
   operations=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).read().get("operations",[])
   submitted=next((x for x in reversed(operations) if x.get("state")=="provider_submitted" and x.get("comfyui_prompt_id")),None)
   terminal=next((x for x in reversed(operations) if x.get("state") in {"outputs_received","review_ready","failed","provider_submission_lost_after_restart"}),None)
   if manifest.get("status")=="running" and submitted and (not terminal or operations.index(terminal)<operations.index(submitted)) and hasattr(self.creative,"submission_evidence"):
    evidence=self.creative.submission_evidence(str(submitted["comfyui_prompt_id"]),((submitted.get("instance_identity") or {}).get("instance_id")))
    current_start=(evidence.get("current_instance_identity") or {}).get("process_started_at") or ""
    submitted_at=str(submitted.get("submission_timestamp") or submitted.get("timestamp") or "")
    restarted=evidence.get("instance_changed") is True
    if not submitted.get("instance_identity") and current_start and submitted_at:
     try:
      current_dt=datetime.strptime(current_start.replace(" CDT","").replace(" CST",""),"%a %Y-%m-%d %H:%M:%S");submitted_dt=datetime.fromisoformat(submitted_at).replace(tzinfo=None);restarted=current_dt>submitted_dt
     except ValueError:pass
    if restarted and not evidence.get("queue_evidence") and not evidence.get("history_evidence") and not evidence.get("output_evidence"):
     completed={x.get("page_id") for x in operations if x.get("state")=="outputs_received"}
     retry_pages=[submitted["page_id"]] if submitted.get("page_id") not in completed else []
     message=f"A real ComfyUI prompt ID ({submitted['comfyui_prompt_id']}) was recorded for {submitted.get('page_id')}, but ComfyUI restarted afterward and no queue, history, or output evidence remains. Explicit confirmation is required to retry only unfinished work."
     entry={"operation":"generate_samples","state":"provider_submission_lost_after_restart","timestamp":_now(),"request_id":submitted.get("request_id"),"generation_identity":submitted.get("generation_identity"),"page_id":submitted.get("page_id"),"prompt_id":submitted.get("prompt_id"),"comfyui_prompt_id":submitted.get("comfyui_prompt_id"),"submitted_instance_identity":submitted.get("instance_identity"),"current_instance_identity":evidence.get("current_instance_identity"),"api_url":evidence.get("api_url"),"safe_failure_message":message,"queue_evidence":False,"history_evidence":False,"output_evidence":False,"retry_page_ids":retry_pages,"external_provider_calls":0};OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).append(entry);manifest.update(status="failed",operation_state="provider_submission_lost_after_restart",safe_failure_message=message,reconciliation_allowed=True,retry_page_ids=retry_pages);self.artifacts.write(pid,"samples/manifest.json",manifest)
  except (OSError,ValueError):
   operations=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).read().get("operations",[])
   latest=operations[-1] if operations else {}
   submitted=[str(x.get("comfyui_prompt_id")) for x in operations if x.get("state")=="provider_submitted" and x.get("comfyui_prompt_id")]
   selected=next((x.get("page_ids") for x in reversed(operations) if x.get("page_ids")),[])
   operation_state=latest.get("state") or "not_generated"
   reconciliation_allowed=bool(operation_state in {"submission_started","failed"} and not submitted and not any(x.get("state")=="reconciled_no_submission" for x in operations))
   if operation_state=="submission_started" and reconciliation_allowed:operation_state="reconciliation_required"
   safe_message=latest.get("safe_failure_message") or ("The prior operation stopped before any recorded ComfyUI prompt submission. Explicit no-submission reconciliation is required." if operation_state=="reconciliation_required" else None)
   manifest={"status":"failed" if operation_state in {"failed","reconciliation_required"} else "running" if operation_state in {"provider_submitted","outputs_received"} else "not_generated","operation_state":operation_state,"safe_failure_message":safe_message,"submitted_prompt_ids":submitted,"selected_page_ids":selected,"artifact_count":0,"artifacts":[],"approval":None,"reconciliation_allowed":reconciliation_allowed}
  manifest.setdefault("operation_state",manifest.get("status"));manifest.setdefault("safe_failure_message",None);manifest.setdefault("submitted_prompt_ids",[]);manifest["artifact_count"]=len(manifest.get("artifacts",[]))
  retry_ids=manifest.get("retry_page_ids") or manifest.get("next_unfinished_page_ids") or []
  titles={x.get("page_id"):x.get("title") for x in value["page_plan"].get("pages",[])}
  manifest["retry_pages"]=[{"page_id":page_id,"title":titles.get(page_id) or page_id} for page_id in retry_ids]
  prompt_by_page={x["page_id"]:x for x in value["page_prompts"].get("prompts",[])}
  try:overrides=DOCUMENTS.read_json(self.root/pid/"samples/prompt-overrides.json").get("overrides",{})
  except (OSError,ValueError):overrides={}
  try:reference=DOCUMENTS.read_json(self.root/pid/"samples/reference-candidates.json").get("reference_asset_id")
  except (OSError,ValueError):reference=None
  for artifact in manifest.get("artifacts",[]):
   source=prompt_by_page.get(artifact.get("page_id"),{});override=overrides.get(artifact.get("page_id"))
   effective=override or source
   artifact["prompt_details"]={"positive_prompt":effective.get("positive_prompt",""),"negative_prompt":effective.get("negative_prompt",""),"prompt_revision":int((override or {}).get("prompt_revision") or 0),"prompt_hash":(override or {}).get("new_prompt_hash") or _digest({"page_id":source.get("page_id"),"prompt_id":source.get("prompt_id"),"positive_prompt":source.get("positive_prompt"),"negative_prompt":source.get("negative_prompt")}),"override_saved":bool(override),"previous_prompt_hash":(override or {}).get("previous_prompt_hash"),"edited_at":(override or {}).get("edited_at")}
   artifact.setdefault("profile_id","kids-bold-line-art-v1")
   artifact["reference_candidate"]=artifact.get("asset_id")==reference
   artifact["output_designation"]="processed" if artifact.get("raw_local_path") else "raw"
   technical=artifact.get("technical_validation") or {};derived=[label for key,label in (("dimensions_valid","invalid dimensions"),("mostly_white_background","mostly white background failed"),("not_blank","blank image"),("safe_margins","safe margins failed"),("processed_image_valid","processed image invalid")) if technical.get(key) is False]
   artifact["validation_failed_reasons"]=technical.get("failed_reasons") or ([] if technical.get("valid") else derived or ["technical validation failed"])
  v6_attempts=[x for x in operations if x.get("operation")=="regenerate_single_page" and x.get("new_profile")=="kids-bold-line-art-v6" and x.get("state")=="submission_started"]
  current_override=overrides.get("page-001") or {}
  current_positive_hash=_prompt_hash(current_override.get("positive_prompt"))
  current_negative_hash=_prompt_hash(current_override.get("negative_prompt"))
  v6_ready=self.creative.for_profile("kids-bold-line-art-v6").readiness() if hasattr(self.creative,"for_profile") else self.creative.readiness()
  current_attempt_identity=_digest({"project_id":pid,"page_id":"page-001","profile_id":"kids-bold-line-art-v6","prompt_revision":int(current_override.get("prompt_revision") or 0),"positive_prompt_hash":current_positive_hash,"negative_prompt_hash":current_negative_hash,"workflow_hash":v6_ready.get("workflow_hash")})
  duplicate=any(x.get("generation_attempt_identity")==current_attempt_identity for x in v6_attempts)
  exhausted=len(v6_attempts)>=MAXIMUM_ATTEMPTS_PER_PAGE
  latest_generated_revision=max((int(x.get("prompt_revision") or 0) for x in operations if x.get("operation")=="regenerate_single_page" and x.get("new_profile")=="kids-bold-line-art-v6" and x.get("state")=="completed"),default=0)
  blocked_reason="Maximum attempts reached. Human intervention required." if exhausted else "This exact page, profile, prompt revision, prompt hashes, and workflow attempt has already been submitted." if duplicate else None
  manifest["page_generation_policy"]={"page_id":"page-001","profile_id":"kids-bold-line-art-v6","attempts_used":len(v6_attempts),"maximum_attempts_per_page":MAXIMUM_ATTEMPTS_PER_PAGE,"attempts_remaining":max(0,MAXIMUM_ATTEMPTS_PER_PAGE-len(v6_attempts)),"current_prompt_revision":int(current_override.get("prompt_revision") or 0),"latest_generated_revision":latest_generated_revision,"positive_prompt_hash":current_positive_hash,"negative_prompt_hash":current_negative_hash,"current_attempt_identity":current_attempt_identity,"generation_available":not duplicate and not exhausted,"generation_state":"maximum_attempts_reached" if exhausted else "exact_attempt_already_used" if duplicate else "generation_available","new_prompt_revision":int(current_override.get("prompt_revision") or 0)>latest_generated_revision,"blocked_reason":blocked_reason}
  ready=self.creative.readiness();state_entries=[x for x in operations if x.get("state")]
  attempt_entries=[x for x in state_entries if x.get("operation")=="regenerate_single_page" and x.get("generation_attempt_identity")==current_attempt_identity]
  latest=attempt_entries[-1] if attempt_entries else {}
  if not latest:
   unrelated_latest=state_entries[-1] if state_entries else {}
   if unrelated_latest.get("operation")!="regenerate_single_page":latest=unrelated_latest
  identity_key=next((key for key in ("regeneration_identity","generation_identity","request_id") if latest.get(key)),None)
  current=[x for x in state_entries if x.get("operation")==latest.get("operation") and (not identity_key or x.get(identity_key)==latest.get(identity_key))] if latest else []
  raw_state=str(latest.get("state") or manifest.get("operation_state") or manifest.get("status") or "not_generated")
  if not latest and manifest["page_generation_policy"]["new_prompt_revision"]:raw_state="not_started"
  if raw_state=="completed":raw_state="review_ready"
  if manifest.get("operation_state") in {"retry_authorized","provider_submission_lost_after_restart"}:raw_state=manifest["operation_state"]
  if manifest.get("status")=="sample_style_approved":raw_state="sample_style_approved"
  started=next((x.get("timestamp") for x in current if x.get("state") in {"submission_started","retry_submission_started"}),None)
  updated=latest.get("timestamp") or (current_override.get("edited_at") if not latest else None) or manifest.get("generated_at") or started
  page_ids=[]
  for entry in current:
   for page_id in list(entry.get("page_ids") or [])+([entry.get("page_id")] if entry.get("page_id") else []):
    if page_id not in page_ids:page_ids.append(page_id)
  if not page_ids and raw_state in {"retry_authorized","provider_submission_lost_after_restart"}:page_ids=list(manifest.get("retry_page_ids") or [])
  prompt_ids=[]
  for entry in current:
   prompt_id=entry.get("comfyui_prompt_id")
   if prompt_id and prompt_id not in prompt_ids:prompt_ids.append(prompt_id)
  submitted=next((x for x in reversed(current) if x.get("state")=="provider_submitted"),{})
  instance=submitted.get("instance_identity") or ready.get("instance_identity")
  queue_state="not_submitted";provider_evidence={"queue_evidence":False,"history_evidence":False,"output_evidence":False}
  if submitted.get("comfyui_prompt_id"):
   queue_state="submitted_unconfirmed"
   if hasattr(self.creative,"submission_evidence"):
    try:provider_evidence=self.creative.submission_evidence(str(submitted["comfyui_prompt_id"]),((submitted.get("instance_identity") or {}).get("instance_id")))
    except Exception:provider_evidence={"queue_evidence":False,"history_evidence":False,"output_evidence":False}
   if provider_evidence.get("output_evidence"):queue_state="output_confirmed"
   elif provider_evidence.get("history_evidence"):queue_state="history_confirmed"
   elif provider_evidence.get("queue_evidence"):queue_state="queue_confirmed"
  if raw_state in {"outputs_received","review_ready","sample_style_approved"} and current:queue_state="output_confirmed"
  confirmed_running=queue_state=="queue_confirmed"
  elapsed=0
  if started:
   try:
    end=datetime.now().astimezone() if raw_state in {"previewed","submission_started","provider_submitted","running","outputs_received"} else datetime.fromisoformat(updated or started)
    elapsed=max(0,int((end-datetime.fromisoformat(started)).total_seconds()))
   except ValueError:pass
  expected=len(page_ids) or len(manifest.get("selected_page_ids") or []) or 0
  progress={"operation_type":"regenerate_single_page" if latest.get("operation") in {"regenerate_with_updated_prompt","regenerate_single_page"} else latest.get("operation"),"operation_state":raw_state,"active":raw_state in {"previewed","submission_started","provider_submitted","running","outputs_received"},"generation_attempt_identity":latest.get("generation_attempt_identity"),"prompt_revision":latest.get("prompt_revision"),"positive_prompt_hash":latest.get("positive_prompt_hash"),"negative_prompt_hash":latest.get("negative_prompt_hash"),"page_ids":page_ids,"source_artifact_id":latest.get("asset_id"),"old_prompt_revision":latest.get("old_prompt_revision"),"new_prompt_revision":latest.get("prompt_revision"),"old_prompt_hash":latest.get("old_prompt_hash"),"new_prompt_hash":latest.get("new_prompt_hash"),"old_profile_id":latest.get("old_profile"),"new_profile_id":latest.get("new_profile"),"submitted_prompt_ids":prompt_ids,"started_at":started,"elapsed_seconds":elapsed,"comfyui_instance_identity":instance,"queue_confirmation_state":queue_state,"provider_state_confirmed":confirmed_running or queue_state in {"history_confirmed","output_confirmed"},"queue_evidence":bool(provider_evidence.get("queue_evidence")),"history_evidence":bool(provider_evidence.get("history_evidence")),"output_evidence":bool(provider_evidence.get("output_evidence")),"artifact_count":len(manifest.get("artifacts",[])),"operation_artifact_count":sum(1 for x in current if x.get("new_asset_id") or x.get("artifact_id")),"expected_artifact_count":expected,"safe_failure_message":latest.get("safe_failure_message") or manifest.get("safe_failure_message"),"last_status_update_at":updated}
  manifest["progress"]=progress
  return {"project_id":pid,"project_status":value["project"]["status"],"provider_readiness":ready,**manifest}

 def edit_sample_prompt(self,pid,page_id,positive_prompt,negative_prompt):
  value=self.load(pid);source=next((x for x in value["page_prompts"].get("prompts",[]) if x.get("page_id")==page_id),None)
  if not source:raise ValueError("sample page prompt not found")
  positive=str(positive_prompt or "").strip();negative=str(negative_prompt or "").strip()
  if not positive or not negative:raise ValueError("positive and negative prompts are required")
  path=self.root/pid/"samples/prompt-overrides.json"
  try:document=DOCUMENTS.read_json(path)
  except (OSError,ValueError):document={"schema_version":"1.0","project_id":pid,"overrides":{}}
  previous=document.get("overrides",{}).get(page_id)
  original_hash=_digest({"page_id":source["page_id"],"prompt_id":source["prompt_id"],"positive_prompt":source["positive_prompt"],"negative_prompt":source["negative_prompt"]})
  previous_hash=(previous or {}).get("new_prompt_hash") or original_hash
  edited_at=_now();revision=int((previous or {}).get("prompt_revision") or 0)+1
  new_hash=_digest({"page_id":page_id,"prompt_id":source["prompt_id"],"positive_prompt":positive,"negative_prompt":negative})
  override={"source_page_id":page_id,"prompt_id":source["prompt_id"],"prompt_revision":revision,"previous_prompt_hash":previous_hash,"new_prompt_hash":new_hash,"edited_at":edited_at,"positive_prompt":positive,"negative_prompt":negative,"original_prompt_hash":original_hash}
  document.setdefault("overrides",{})[page_id]=override;document["updated_at"]=edited_at;self.artifacts.write(pid,"samples/prompt-overrides.json",document)
  status=self.sample_status(pid)
  for artifact in status.get("artifacts",[]):
   if artifact.get("page_id")==page_id:
    artifact.update(review_state="rejected",prompt_stale=True,prompt_stale_at=edited_at)
  manifest={k:v for k,v in status.items() if k not in {"provider_readiness","project_status"}}
  manifest.update(status="review_in_progress",approval=None);manifest["manifest_sha256"]=_digest({k:v for k,v in manifest.items() if k!="manifest_sha256"});self.artifacts.write(pid,"samples/manifest.json",manifest)
  entry={"operation":"sample_prompt_edited","timestamp":edited_at,"source_page_id":page_id,"prompt_revision":revision,"previous_prompt_hash":previous_hash,"new_prompt_hash":new_hash,"external_provider_calls":0,"marketplace_actions":0};OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).append(entry);AuditEventStore(self.root/pid/"events.jsonl").append({"event":"sample_prompt_edited",**entry})
  return {**override,"status":"saved_locally","image_generated":False,"page_plan_changed":False,"marketplace_actions":0}

 def regenerate_with_updated_prompt(self,pid,asset_id,*,confirmed=False,regeneration_identity=None,profile_id="kids-bold-line-art-v1"):
  status=self.sample_status(pid);old=next((x for x in status.get("artifacts",[]) if x.get("asset_id")==asset_id),None)
  if not old:raise ValueError("sample asset not found")
  if old.get("page_id")!="page-001":raise ValueError("profile evaluation is currently authorized only for page-001 regeneration")
  details=old.get("prompt_details") or {}
  if not details.get("override_saved"):raise ValueError("save a prompt override before regenerating")
  if status.get("progress",{}).get("active") and old["page_id"] in status["progress"].get("page_ids",[]):raise SampleGenerationConflict(f"a regeneration operation is already active for {old['page_id']}")
  target_profile=str(profile_id or "kids-bold-line-art-v1")
  if target_profile not in {"kids-bold-line-art-v1","kids-bold-line-art-v3","kids-bold-line-art-v4","kids-bold-line-art-v5","kids-bold-line-art-v6"}:raise ValueError("unsupported regeneration profile")
  operations=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).read().get("operations",[])
  if target_profile=="kids-bold-line-art-v3" and any(x.get("new_profile")=="kids-bold-line-art-v3" and x.get("state") in {"submission_started","provider_submitted","completed"} for x in operations):raise SampleGenerationConflict("the one explicit kids-bold-line-art-v3 regeneration has already been used or submitted")
  if target_profile=="kids-bold-line-art-v4" and any(x.get("new_profile")=="kids-bold-line-art-v4" and x.get("state") in {"submission_started","provider_submitted","completed"} for x in operations):raise SampleGenerationConflict("the one explicit kids-bold-line-art-v4 regeneration has already been used or submitted")
  if target_profile=="kids-bold-line-art-v5" and any(x.get("new_profile")=="kids-bold-line-art-v5" and x.get("state") in {"submission_started","provider_submitted","completed"} for x in operations):raise SampleGenerationConflict("the one explicit kids-bold-line-art-v5 regeneration has already been used or submitted")
  provider=self.creative.for_profile(target_profile) if hasattr(self.creative,"for_profile") else self.creative;ready=provider.readiness()
  if not ready.get("configured"):raise SampleGenerationFailure(ready.get("message") or f"{target_profile} is not ready")
  positive_hash=_prompt_hash(details["positive_prompt"]);negative_hash=_prompt_hash(details["negative_prompt"])
  attempt_identity_fields={"project_id":pid,"page_id":old["page_id"],"profile_id":target_profile,"prompt_revision":details["prompt_revision"],"positive_prompt_hash":positive_hash,"negative_prompt_hash":negative_hash,"workflow_hash":ready.get("workflow_hash")}
  attempt_identity=_digest(attempt_identity_fields)
  submitted_attempts=[x for x in operations if x.get("operation")=="regenerate_single_page" and x.get("new_profile")==target_profile and x.get("page_id")==old["page_id"] and x.get("state")=="submission_started"]
  if any(x.get("generation_attempt_identity")==attempt_identity for x in submitted_attempts):raise SampleGenerationConflict("This exact page, profile, prompt revision, prompt hashes, and workflow attempt has already been submitted.")
  if len(submitted_attempts)>=MAXIMUM_ATTEMPTS_PER_PAGE:raise SampleGenerationConflict("Maximum attempts reached. Human intervention required.")
  reference_path=self.root/pid/"samples/reference-candidates.json"
  try:reference_id=DOCUMENTS.read_json(reference_path).get("reference_asset_id")
  except (OSError,ValueError):reference_id=None
  bound={"project_id":pid,"asset_id":asset_id,"page_id":old["page_id"],"old_prompt_revision":max(0,int(details["prompt_revision"])-1),"old_prompt_hash":details["previous_prompt_hash"],"new_prompt_hash":details["prompt_hash"],"prompt_revision":details["prompt_revision"],"positive_prompt_hash":positive_hash,"negative_prompt_hash":negative_hash,"old_profile":old.get("profile_id") or "kids-bold-line-art-v1","new_profile":target_profile,"profile_id":target_profile,"checkpoint":ready.get("checkpoint"),"workflow_hash":ready.get("workflow_hash"),"postprocessing":ready.get("postprocessing"),"validation_thresholds":ready.get("validation_thresholds"),"reference_candidate_id":reference_id,"attempt_number":len(submitted_attempts)+1,"maximum_attempts_per_page":MAXIMUM_ATTEMPTS_PER_PAGE,"generation_attempt_identity":attempt_identity}
  bound["request_id"]=f"regenerate-prompt-{pid}-{old['page_id']}-{details['prompt_revision']}";bound["regeneration_identity"]=_digest(bound)
  preview={"confirmation_required":True,**bound,"local_gpu_effect":{"uses_local_gpu":True,"page_count":1},"safety":{"external_provider_calls":0,"marketplace_actions":0,"pdf":False,"upload":False,"publication":False,"purchase":False,"order":False},"confirmation":f"Regenerate only {old['page_id']} locally? Old profile: {bound['old_profile']}. New profile: {target_profile}. Workflow: {bound['workflow_hash']}. Checkpoint: {bound['checkpoint']}. Uses the local GPU. No marketplace, PDF, upload, publication, purchase, or order action will occur."}
  if not confirmed:return preview
  if any((regeneration_identity or {}).get(k)!=v for k,v in bound.items()):raise SampleGenerationConflict("updated-prompt regeneration preview is stale or incomplete")
  journal=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS)
  if any(x.get("operation") in {"regenerate_with_updated_prompt","regenerate_single_page"} and x.get("regeneration_identity")==bound["regeneration_identity"] and x.get("state")=="completed" for x in journal.read().get("operations",[])):return {**self.sample_status(pid),"idempotent":True}
  value=self.load(pid);page={"page_id":old["page_id"],"prompt_id":old["prompt_id"],"positive_prompt":details["positive_prompt"],"negative_prompt":details["negative_prompt"]}
  journal.append({"operation":"regenerate_single_page","state":"submission_started","timestamp":_now(),**bound,"external_provider_calls":0,"marketplace_actions":0})
  def provider_event(event):
   journal.append({"operation":"regenerate_single_page","state":"provider_submitted","timestamp":_now(),**bound,**dict(event),"external_provider_calls":0,"marketplace_actions":0})
  resolution=ready.get("sample_resolution") or {};request=LocalAssetRequest(bound["request_id"],"coloring_page.line_art","jamesos.coloring-book-producer",pid,{"profile_id":target_profile,"pages":[page],"candidates_per_page":1,"output_directory":str(self.root/pid/"samples/outputs"),"owner_root":str(self.root/pid),"width":int(resolution.get("width") or 768),"height":int(resolution.get("height") or 992),"operation_event_sink":provider_event},value["page_plan"]["page_plan_sha256"],{"max_outputs":1,"local_only":True})
  try:result=provider.execute(request)
  except Exception as exc:
   message=f"Updated-prompt regeneration failed safely for {old['page_id']}: {str(exc)[:180]}";journal.append({"operation":"regenerate_single_page","state":"failed","timestamp":_now(),**bound,"safe_failure_message":message,"external_provider_calls":0,"marketplace_actions":0});raise SampleGenerationFailure(message) from exc
  if result.status!="completed" or len(result.artifacts)!=1:
   message=f"Updated-prompt regeneration returned {result.status} with {len(result.artifacts)} artifacts.";journal.append({"operation":"regenerate_single_page","state":"failed","timestamp":_now(),**bound,"safe_failure_message":message,"warnings":list(result.warnings),"external_provider_calls":0,"marketplace_actions":0});raise SampleGenerationFailure(message)
  artifact=dict(result.artifacts[0]);artifact.update(profile_id=target_profile,prompt_revision=details["prompt_revision"],prompt_hash=details["prompt_hash"],positive_prompt_hash=positive_hash,negative_prompt_hash=negative_hash,generation_attempt_identity=attempt_identity,attempt_number=bound["attempt_number"],prompt_stale=False)
  if target_profile in {"kids-bold-line-art-v5","kids-bold-line-art-v6"}:artifact["semantic_review"]={"review_mode":"human_required","automated_certainty":False,"bear":{"expected":True,"detected":None},"rabbit":{"expected":True,"detected":None},"tent":{"expected":True,"detected":None},"unpacking_action":{"expected":"backpack, sleeping bag, and lantern","matched":None},"summary":"Human semantic review required. No automated subject or action claim has been made."}
  old["review_state"]="superseded";artifacts=status["artifacts"]+[artifact]
  if len({x["file_sha256"] for x in artifacts})!=len(artifacts):raise SampleGenerationFailure("duplicate sample output hashes were rejected")
  manifest={k:v for k,v in status.items() if k not in {"provider_readiness","project_status"}};manifest.update(status="review_in_progress",artifacts=artifacts,approval=None,safe_failure_message=None);manifest["manifest_sha256"]=_digest({k:v for k,v in manifest.items() if k!="manifest_sha256"});self.artifacts.write(pid,"samples/manifest.json",manifest)
  journal.append({"operation":"regenerate_single_page","state":"completed","timestamp":_now(),**bound,"new_asset_id":artifact["asset_id"],"file_sha256":artifact["file_sha256"],"external_provider_calls":0,"marketplace_actions":0});AuditEventStore(self.root/pid/"events.jsonl").append({"event":"sample_regenerated_with_updated_prompt","timestamp":_now(),"page_id":old["page_id"],"asset_id":artifact["asset_id"],"prompt_revision":details["prompt_revision"],"marketplace_actions":0})
  return manifest

 def mark_reference_candidate(self,pid,asset_id):
  status=self.sample_status(pid);artifact=next((x for x in status.get("artifacts",[]) if x.get("asset_id")==asset_id and x.get("page_id")=="page-001"),None)
  if not artifact:raise ValueError("page-001 reference candidate not found")
  timestamp=_now();record={"project_id":pid,"page_id":"page-001","reference_asset_id":asset_id,"marked_at":timestamp,"planning_metadata_only":True,"approval":False,"external_actions":0};self.artifacts.write(pid,"samples/reference-candidates.json",record);OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).append({"operation":"mark_reference_candidate","timestamp":timestamp,"page_id":"page-001","asset_id":asset_id,"approval":False,"external_provider_calls":0,"marketplace_actions":0});return record

 def reconcile_sample_generation(self,pid,*,confirmed=False):
  journal=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS);operations=journal.read().get("operations",[])
  lost=next((x for x in reversed(operations) if x.get("state")=="provider_submission_lost_after_restart"),None)
  if lost:
   if any(x.get("state")=="reconciled_lost_after_restart" and x.get("comfyui_prompt_id")==lost.get("comfyui_prompt_id") for x in operations):raise SampleGenerationConflict("the one explicit retry for this lost ComfyUI submission was already authorized")
   message=f"Retry unfinished page {lost.get('page_id')} once? A real prompt ID ({lost.get('comfyui_prompt_id')}) was recorded, ComfyUI restarted afterward, and no output, queue, or history evidence remains. Completed outputs will not be resubmitted."
   if not confirmed:return {"confirmation_required":True,"confirmation":message,"operation_state":"provider_submission_lost_after_restart","recorded_prompt_id":lost.get("comfyui_prompt_id"),"retry_page_ids":lost.get("retry_page_ids") or [lost.get("page_id")],"retry_limit":1}
   entry={"operation":"generate_samples","state":"reconciled_lost_after_restart","timestamp":_now(),"request_id":lost.get("request_id"),"generation_identity":lost.get("generation_identity"),"comfyui_prompt_id":lost.get("comfyui_prompt_id"),"retry_page_ids":lost.get("retry_page_ids") or [lost.get("page_id")],"retry_limit":1,"external_provider_calls":0};journal.append(entry);manifest_path=self.root/pid/"samples/manifest.json";manifest=DOCUMENTS.read_json(manifest_path);manifest.update(operation_state="retry_authorized",reconciliation_allowed=False,retry_page_ids=entry["retry_page_ids"]);self.artifacts.write(pid,"samples/manifest.json",manifest);return {**entry,"message":"Lost submission reconciled without deleting audit history. One explicit retry of unfinished work is authorized."}
  submitted=[x for x in operations if x.get("state")=="provider_submitted" and x.get("comfyui_prompt_id")]
  reconciled=[x for x in operations if x.get("state")=="reconciled_no_submission"]
  started=[x for x in operations if x.get("state")=="submission_started"]
  if reconciled:raise SampleGenerationConflict("the one explicit no-submission reconciliation was already used")
  if submitted:raise SampleGenerationConflict("reconciliation is unsafe because a ComfyUI prompt ID was recorded")
  if not started:raise SampleGenerationConflict("there is no interrupted submission to reconcile")
  message="Reconcile the interrupted sample operation as not submitted? ComfyUI has no recorded prompt ID. This preserves the prior journal and permits one explicit future retry; it does not generate images."
  if not confirmed:return {"confirmation_required":True,"confirmation":message,"operation_state":"reconciliation_required","retry_limit":1}
  entry={"operation":"generate_samples","state":"reconciled_no_submission","timestamp":_now(),"request_id":started[-1].get("request_id"),"generation_identity":started[-1].get("generation_identity"),"reason":"no ComfyUI prompt ID was ever recorded","retry_limit":1,"external_provider_calls":0};journal.append(entry);return {**entry,"message":"Interrupted operation reconciled without deleting audit history. One explicit generation retry is now permitted."}

 def retry_unfinished_samples(self,pid,*,confirmed=False,retry_identity=None):
  status=self.sample_status(pid)
  if status.get("operation_state") not in {"retry_authorized","remaining_samples_authorized"}:raise SampleGenerationConflict("no authorized unfinished sample retry is available")
  retry_ids=list(status.get("retry_page_ids") or status.get("next_unfinished_page_ids") or [])
  if not retry_ids:raise SampleGenerationConflict("no unfinished retry pages remain")
  operations=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).read().get("operations",[])
  lost=next((x for x in reversed(operations) if x.get("state")=="provider_submission_lost_after_restart"),{})
  ready=status["provider_readiness"];attempt=1+sum(1 for x in operations if x.get("state")=="retry_submission_started")
  bound={"project_id":pid,"retry_page_ids":retry_ids,"original_lost_prompt_id":lost.get("comfyui_prompt_id"),"page_plan_revision":status["page_plan_revision"],"page_plan_hash":status["page_plan_hash"],"workflow_profile":status["workflow_profile"],"workflow_hash":status["workflow_hash"],"checkpoint":status["checkpoint"],"request_id":status["request_id"],"generation_identity":status["generation_identity"],"comfyui_instance_identity":ready.get("instance_identity"),"retry_attempt":attempt}
  bound["retry_identity"]=_digest(bound)
  preview={"confirmation_required":True,**bound,"retry_pages":status.get("retry_pages") or [],"confirmation":f"Retry only unfinished sample pages {', '.join(retry_ids)} locally? The earlier ComfyUI prompt {lost.get('comfyui_prompt_id')} was lost after the desktop restarted and no output was recovered. Completed sample outputs will never be regenerated automatically. No Amazon, Etsy, Printify, PDF, publication, purchase, or order action will occur."}
  if not confirmed:return preview
  supplied=dict(retry_identity or {})
  if any(supplied.get(key)!=value for key,value in bound.items()):raise SampleGenerationConflict("authorized sample retry preview is stale or incomplete")
  generation={key:bound[key] for key in ("project_id","page_plan_revision","page_plan_hash","workflow_profile","workflow_hash","checkpoint","request_id","generation_identity")}
  generation["selected_page_ids"]=status["selected_page_ids"];generation["workflow"]=ready.get("workflow_reference")
  return self.generate_samples(pid,confirmed=True,generation_identity=generation,execution_page_ids=retry_ids,retry_attempt=attempt)

 def generate_samples(self,pid,*,confirmed=False,candidates_per_page=1,generation_identity=None,execution_page_ids=None,retry_attempt=None):
  value=self.load(pid)
  if value["project"].get("status") not in {"page_plan_approved","samples_ready"} or value["page_plan"].get("status")!="approved" or value["page_plan_approval"]["state"]!="approved":raise ValueError("an approved current page plan is required")
  selected=self._sample_selection(value);prompt_by_id={x["prompt_id"]:x for x in value["page_prompts"]["prompts"]};ready=self.creative.readiness();output=self.root/pid/"samples/outputs"
  request_id=f"samples-{pid}-{value['page_plan']['page_plan_sha256'][:12]}"
  identity={"project_id":pid,"page_plan_revision":value["page_plan"]["plan_revision"],"page_plan_hash":value["page_plan"]["page_plan_sha256"],"selected_page_ids":[x["page_id"] for x in selected],"workflow_profile":ready.get("profile_id"),"workflow":ready.get("workflow_reference"),"workflow_hash":ready.get("workflow_hash"),"checkpoint":ready.get("checkpoint"),"request_id":request_id}
  identity["generation_identity"]=_digest(identity)
  preview={"confirmation_required":True,**identity,"selected_sample_page_ids":identity["selected_page_ids"],"selected_samples":[{"page_id":x["page_id"],"title":x["title"],"prompt_id":x["prompt_id"],"prompt_summary":prompt_by_id[x["prompt_id"]]["positive_prompt"][:240]} for x in selected],"provider_readiness":ready,"output_directory":str(output),"provider_effects":{"local_gpu":bool(ready.get("configured")),"local_comfyui":bool(ready.get("configured")),"external_provider":False},"safety":{"full_book_generation":False,"pdf_created":False,"amazon_upload":False,"publication":False,"marketplace_write":False,"purchase":False,"order":False}}
  journal=OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS)
  if not confirmed:
   operations=journal.read().get("operations",[])
   if not any(x.get("state")=="previewed" and x.get("generation_identity")==identity["generation_identity"] for x in operations):journal.append({"operation":"generate_samples","state":"previewed","timestamp":_now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"page_ids":identity["selected_page_ids"],"workflow_hash":identity["workflow_hash"],"checkpoint":identity["checkpoint"],"external_provider_calls":0})
   return preview
  supplied=dict(generation_identity or {})
  required=tuple(identity)
  if any(supplied.get(key)!=identity[key] for key in required):raise SampleGenerationConflict("sample generation preview is stale or incomplete; request a new preview")
  manifest_path=self.root/pid/"samples/manifest.json"
  if manifest_path.is_file():
   existing=DOCUMENTS.read_json(manifest_path)
   if existing.get("generation_identity")==identity["generation_identity"] and existing.get("status")=="review_ready":return {**existing,"idempotent":True}
   authorized=any(x.get("state")=="reconciled_lost_after_restart" for x in journal.read().get("operations",[]))
   if existing.get("generation_identity")==identity["generation_identity"] and not authorized:raise SampleGenerationConflict(existing.get("safe_failure_message") or "sample generation is already running or requires reconciliation")
   if existing.get("generation_identity")!=identity["generation_identity"]:raise SampleGenerationConflict("samples already exist for a different immutable generation identity")
  prior=[x for x in journal.read().get("operations",[]) if x.get("generation_identity")==identity["generation_identity"]]
  unresolved=any(x.get("state")=="submission_started" for x in prior) and not any(x.get("state") in {"review_ready","reconciled_no_submission","reconciled_lost_after_restart"} for x in prior)
  if unresolved:
   submitted=any(x.get("state")=="provider_submitted" and x.get("comfyui_prompt_id") for x in prior);message="A prior ComfyUI submission is uncertain and must not be retried." if submitted else "A prior operation stopped before any recorded ComfyUI submission. Use the explicit no-submission reconciliation before retrying."
   if not any(x.get("state")=="failed" for x in prior):journal.append({"operation":"generate_samples","state":"failed","timestamp":_now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"safe_failure_message":message,"reconciliation_allowed":not submitted,"external_provider_calls":0})
   raise SampleGenerationConflict(message)
  if not ready.get("configured"):
   message="Local image provider is not configured.";journal.append({"operation":"generate_samples","state":"failed","timestamp":_now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"safe_failure_message":message,"external_provider_calls":0});raise SampleGenerationFailure(message)
  completed_page_ids={x.get("page_id") for x in (existing.get("artifacts",[]) if manifest_path.is_file() else [])}
  allowed=set(execution_page_ids or identity["selected_page_ids"])
  pages=[{"page_id":x["page_id"],"prompt_id":x["prompt_id"],"positive_prompt":prompt_by_id[x["prompt_id"]]["positive_prompt"],"negative_prompt":prompt_by_id[x["prompt_id"]]["negative_prompt"]} for x in selected if x["page_id"] not in completed_page_ids and x["page_id"] in allowed]
  if not pages:raise SampleGenerationConflict("all authorized retry pages already have completed outputs")
  started={"operation":"generate_samples","state":"retry_submission_started" if retry_attempt else "submission_started","timestamp":_now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"page_ids":[x["page_id"] for x in pages],"retry_attempt":retry_attempt,"workflow_hash":identity["workflow_hash"],"checkpoint":identity["checkpoint"],"external_provider_calls":0};journal.append(started)
  existing_artifacts=list(existing.get("artifacts",[])) if manifest_path.is_file() else []
  progress={"status":"running","operation_state":"submission_started","project_id":pid,"page_plan_revision":identity["page_plan_revision"],"page_plan_hash":identity["page_plan_hash"],"selected_page_ids":identity["selected_page_ids"],"generation_identity":identity["generation_identity"],"request_id":request_id,"workflow_profile":identity["workflow_profile"],"workflow_hash":identity["workflow_hash"],"checkpoint":identity["checkpoint"],"submitted_prompt_ids":list(existing.get("submitted_prompt_ids",[])) if manifest_path.is_file() else [],"safe_failure_message":None,"artifacts":existing_artifacts,"artifact_count":len(existing_artifacts),"approval":None};self.artifacts.write(pid,"samples/manifest.json",progress)
  artifacts=existing_artifacts
  def persist_failure(message,response=None):
   entry={"operation":"generate_samples","state":"failed","timestamp":_now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"safe_failure_message":message,"provider_response":response,"external_provider_calls":0};journal.append(entry);progress.update(status="failed",operation_state="failed",safe_failure_message=message,artifact_count=len(artifacts),artifacts=artifacts);self.artifacts.write(pid,"samples/manifest.json",progress)
  for page in pages:
   def provider_event(event,page=page):
    prompt_id=str(event.get("comfyui_prompt_id") or "")
    entry={"operation":"generate_samples","state":"provider_submitted","timestamp":event.get("submission_timestamp") or _now(),"submission_timestamp":event.get("submission_timestamp") or _now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"page_id":page["page_id"],"prompt_id":page["prompt_id"],"comfyui_prompt_id":prompt_id,"api_url":event.get("api_url"),"http_status":event.get("http_status"),"instance_identity":event.get("instance_identity"),"retry_attempt":retry_attempt,"workflow_hash":identity["workflow_hash"],"checkpoint":identity["checkpoint"],"seed":event.get("seed"),"external_provider_calls":0};journal.append(entry);progress["operation_state"]="provider_submitted";progress["submitted_prompt_ids"].append(prompt_id);self.artifacts.write(pid,"samples/manifest.json",progress)
   page_request=LocalAssetRequest(f"{request_id}-{page['page_id']}","coloring_page.line_art","jamesos.coloring-book-producer",pid,{"pages":[page],"candidates_per_page":1,"output_directory":str(output),"owner_root":str(self.root/pid),"width":1024,"height":1280,"operation_event_sink":provider_event},value["page_plan"]["page_plan_sha256"],{"max_outputs":1,"local_only":True})
   try:result=self.creative.execute(page_request)
   except Exception as exc:
    message=f"Local creative provider failed for {page['page_id']}: {str(exc)[:180]}";persist_failure(message,{"exception_type":type(exc).__name__});raise SampleGenerationFailure(message) from exc
   if result.status!="completed" or len(result.artifacts)!=1:
    message=f"Local creative provider returned {result.status} with {len(result.artifacts)} artifacts for {page['page_id']}.";persist_failure(message,{"status":result.status,"warnings":list(result.warnings),"artifact_count":len(result.artifacts)});raise SampleGenerationFailure(message)
   artifact=dict(result.artifacts[0]);artifacts.append(artifact);journal.append({"operation":"generate_samples","state":"outputs_received","timestamp":_now(),"request_id":request_id,"generation_identity":identity["generation_identity"],"page_id":page["page_id"],"comfyui_prompt_id":artifact.get("comfyui_prompt_id"),"instance_identity":artifact.get("instance_identity"),"http_status":artifact.get("http_status"),"queue_history_confirmation":artifact.get("queue_history_confirmation"),"output_evidence":artifact.get("output_evidence"),"artifact_id":artifact.get("asset_id"),"file_sha256":artifact.get("file_sha256"),"retry_attempt":retry_attempt,"external_provider_calls":0});progress.update(operation_state="outputs_received",artifacts=artifacts,artifact_count=len(artifacts));self.artifacts.write(pid,"samples/manifest.json",progress)
  hashes=[x["file_sha256"] for x in artifacts]
  if len(hashes)!=len(set(hashes)):
   message="duplicate sample output hashes were rejected";persist_failure(message,{"artifact_count":len(artifacts)});raise SampleGenerationFailure(message)
  remaining=[x["page_id"] for x in selected if x["page_id"] not in {a.get("page_id") for a in artifacts}]
  final_status="review_ready" if not remaining else "failed";operation_state="review_ready" if not remaining else "remaining_samples_authorized"
  manifest={"status":final_status,"operation_state":operation_state,"project_id":pid,"page_plan_revision":value["page_plan"]["plan_revision"],"page_plan_hash":value["page_plan"]["page_plan_sha256"],"selected_page_ids":[x["page_id"] for x in selected],"generation_identity":identity["generation_identity"],"request_id":request_id,"workflow_profile":identity["workflow_profile"],"workflow_hash":identity["workflow_hash"],"checkpoint":identity["checkpoint"],"submitted_prompt_ids":progress["submitted_prompt_ids"],"safe_failure_message":None,"generated_at":_now(),"provider_id":result.provider_id,"artifacts":artifacts,"artifact_count":len(artifacts),"retry_page_ids":remaining,"next_unfinished_page_ids":remaining,"approval":None,"full_book_generation_started":False,"pdf_created":False,"amazon_upload":False,"marketplace_write":False,"publication_status":"not_published","purchase_status":"not_created","order_status":"not_created"};manifest["manifest_sha256"]=_digest({k:v for k,v in manifest.items() if k!="manifest_sha256"});self.artifacts.write(pid,"samples/manifest.json",manifest);journal.append({"operation":"generate_samples","state":operation_state,"timestamp":manifest["generated_at"],"request_id":request_id,"generation_identity":identity["generation_identity"],"page_ids":[x["page_id"] for x in pages],"next_unfinished_page_ids":remaining,"artifact_count":len(artifacts),"retry_attempt":retry_attempt,"provider_id":result.provider_id,"external_provider_calls":0});AuditEventStore(self.root/pid/"events.jsonl").append({"event":"sample_pages_generated" if not remaining else "sample_retry_page_completed","timestamp":manifest["generated_at"],"asset_count":len(artifacts),"manifest_sha256":manifest["manifest_sha256"],"external_provider_calls":0});return manifest

 def review_sample(self,pid,asset_id,action):
  if action not in {"approve","reject"}:raise ValueError("unsupported sample review action")
  status=self.sample_status(pid);artifact=next((x for x in status.get("artifacts",[]) if x.get("asset_id")==asset_id),None)
  if not artifact:raise ValueError("sample asset not found")
  if action=="approve" and not (artifact.get("technical_validation") or {}).get("valid"):raise ValueError("technically invalid sample artifacts cannot be approved")
  artifact["review_state"]="approved" if action=="approve" else "rejected";artifact["reviewed_at"]=_now();manifest={k:v for k,v in status.items() if k not in {"provider_readiness","project_status"}};manifest["status"]="review_in_progress";manifest["manifest_sha256"]=_digest({k:v for k,v in manifest.items() if k!="manifest_sha256"});self.artifacts.write(pid,"samples/manifest.json",manifest);OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).append({"operation":f"sample_{action}","timestamp":artifact["reviewed_at"],"asset_id":asset_id,"external_provider_calls":0});return manifest

 def regenerate_sample(self,pid,asset_id,confirmed=False):
  status=self.sample_status(pid);old=next((x for x in status.get("artifacts",[]) if x.get("asset_id")==asset_id),None)
  if not old:raise ValueError("sample asset not found")
  if not confirmed:return {"confirmation_required":True,"confirmation":f"Regenerate sample {asset_id} locally with ComfyUI? No PDF, marketplace, publication, purchase, or order action will occur.","page_id":old["page_id"]}
  value=self.load(pid);prompt=next(x for x in value["page_prompts"]["prompts"] if x["prompt_id"]==old["prompt_id"]);request=LocalAssetRequest(f"regenerate-{asset_id}-{uuid4().hex[:8]}","coloring_page.line_art","jamesos.coloring-book-producer",pid,{"pages":[{"page_id":old["page_id"],"prompt_id":old["prompt_id"],"positive_prompt":prompt["positive_prompt"],"negative_prompt":prompt["negative_prompt"]}],"candidates_per_page":1,"output_directory":str(self.root/pid/"samples/outputs"),"owner_root":str(self.root/pid),"width":1024,"height":1280},value["page_plan"]["page_plan_sha256"],{"max_outputs":1,"local_only":True});result=self.creative.execute(request)
  if result.status!="completed":return {"status":result.status,"warnings":list(result.warnings)}
  old["review_state"]="superseded";artifacts=status["artifacts"]+[dict(result.artifacts[0])];hashes=[x["file_sha256"] for x in artifacts]
  if len(hashes)!=len(set(hashes)):raise ValueError("duplicate sample output hashes were rejected")
  manifest={k:v for k,v in status.items() if k not in {"provider_readiness","project_status"}};manifest.update(status="review_in_progress",artifacts=artifacts,approval=None);manifest["manifest_sha256"]=_digest({k:v for k,v in manifest.items() if k!="manifest_sha256"});self.artifacts.write(pid,"samples/manifest.json",manifest);OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).append({"operation":"regenerate_sample","timestamp":_now(),"old_asset_id":asset_id,"new_asset_id":result.artifacts[0]["asset_id"],"external_provider_calls":0});return manifest

 def approve_sample_style(self,pid,confirmed=False):
  status=self.sample_status(pid);approved={x["page_id"]:x for x in status.get("artifacts",[]) if x.get("review_state")=="approved" and (x.get("technical_validation") or {}).get("valid") and not x.get("prompt_stale")}
  if set(status.get("selected_page_ids",[]))!=set(approved):raise ValueError("one approved image for each selected sample page is required")
  document=VersionedDocument(int(status["page_plan_revision"]),status["manifest_sha256"]);message=f"Approve Sample Style locally for {pid}? Three selected sample pages are approved. Full-book generation will not start. No PDF, Amazon, marketplace, publication, purchase, or order action will occur."
  if not confirmed:return APPROVALS.preview(document,message)|{"approved_page_ids":sorted(approved)}
  approval=APPROVALS.record(document);manifest={k:v for k,v in status.items() if k not in {"provider_readiness","project_status"}};manifest.update(status="sample_style_approved",approval=approval);self.artifacts.write(pid,"samples/manifest.json",manifest);project=self.artifacts.read(pid,"project.json");project.update(status="sample_style_approved",updated_at=approval["timestamp"]);self.artifacts.write(pid,"project.json",project);OperationJournal(self.root/pid/"samples/operations.json",DOCUMENTS).append({"operation":"approve_sample_style","timestamp":approval["timestamp"],"external_provider_calls":0});AuditEventStore(self.root/pid/"events.jsonl").append({"event":"sample_style_approved","timestamp":approval["timestamp"],"external_provider_calls":0});return {**approval,"message":"Sample style approved locally. Full-book generation has not started. No PDF, Amazon, marketplace, purchase, or order action occurred."}

 def sample_asset(self,pid,asset_id):
  item=next((x for x in self.sample_status(pid).get("artifacts",[]) if x.get("asset_id")==asset_id),None)
  if not item:raise FileNotFoundError(asset_id)
  root=(self.root/pid/"samples").resolve();path=Path(item["local_path"]).resolve(strict=True)
  if root not in path.parents or sha256(path.read_bytes()).hexdigest()!=item["file_sha256"]:raise FileNotFoundError(asset_id)
  return path
