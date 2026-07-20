from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json,re
from pathlib import Path
from typing import Any
from uuid import uuid4
from jamesos.config import VAULT
from jamesos.services.book_opportunity_scout import BookOpportunityScoutService
from jamesos.core.artifacts import AtomicDocumentStore,ApprovalService,AuditEventStore,ProjectArtifactStore,VersionedDocument,canonical_sha256,now
from jamesos.services.structured_planning import DeterministicPlanProvider,StructuredPlanProvider

ROOT=VAULT/"JamesOS"/"Books"/"Projects";PROJECT=re.compile(r"book-project-[0-9]{8}T[0-9]{6}-[a-f0-9]{8}")
DOCUMENTS=AtomicDocumentStore();APPROVALS=ApprovalService()
def _now():return now()
def _digest(v):return canonical_sha256(v)
def _atomic(path,v):
 DOCUMENTS.write_json(path,v)
def _text(path,v):
 DOCUMENTS.write_text(path,v)

class ColoringBookProducer:
 def __init__(self,root:Path=ROOT,scout=None,planner:StructuredPlanProvider|None=None):self.root=root;self.scout=scout or BookOpportunityScoutService();self.artifacts=ProjectArtifactStore(root,DOCUMENTS);self.planner=planner or DeterministicPlanProvider()
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
  if plan.get("status")!="draft" or not plan.get("validation",{}).get("valid"):raise ValueError("a valid page plan draft is required")
  document=VersionedDocument(int(plan["plan_revision"]),plan["page_plan_sha256"]);message=f"Approve Page Plan locally for {pid}? Exact page count: {len(plan['pages'])}. Plan revision {plan['plan_revision']} and hash {plan['page_plan_sha256']}. Characters: {', '.join(plan['validation']['character_distribution'])}. Categories: {plan['validation']['category_distribution']}. Validation passed. No images or external actions will occur."
  if not confirmed:return APPROVALS.preview(document,message)|{"page_count":len(plan["pages"]),"validation":plan["validation"]}
  approvals=value["approvals"]
  if (approvals.get("page_plan") or {}).get("content_hash")==document.content_sha256:return {**approvals["page_plan"],"idempotent":True}
  approval=APPROVALS.record(document);approvals["page_plan"]=approval;self.artifacts.write(pid,"approvals.json",approvals);plan["status"]="approved";self.artifacts.write(pid,"page-plan.json",plan);project=value["project"];project.update(status="page_plan_approved",updated_at=approval["timestamp"]);self.artifacts.write(pid,"project.json",project);AuditEventStore(self.root/pid/"events.jsonl").append({"event":"page_plan_approved","timestamp":approval["timestamp"],"plan_revision":plan["plan_revision"],"content_hash":document.content_sha256,"external_provider_calls":0});return {**approval,"idempotent":False,"message":"Page plan approved locally. Image generation is not implemented yet. No external provider or marketplace action occurred."}
