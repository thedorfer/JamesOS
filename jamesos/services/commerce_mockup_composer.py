from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from PIL import Image,ImageChops

from jamesos.config import VAULT
from jamesos.core.errors import StateConflictError,ValidationError
from jamesos.services import product_orchestrator
from jamesos.services.local_creative_studio import BlankModelTemplateProvider,LocalAssetRequest,LocalAssetResult,LocalCreativeStudioProvider

TEMPLATE_ROOT=VAULT/"JamesOS"/"Commerce"/"MockupTemplates"
ROLES={"clean_product":"product-only","male_model":"male","female_model":"female"}
BlankModelProvider=LocalCreativeStudioProvider  # compatibility for the former local protocol
_ID=re.compile(r"[a-z0-9][a-z0-9._-]{1,80}")
def _now():return datetime.now().astimezone().isoformat()
def _json(path,value):product_orchestrator._atomic_json(path,value)
def _hash(path):return sha256(path.read_bytes()).hexdigest()
def _digest(value):return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _solve(matrix,values):
    a=[list(map(float,row))+[float(value)] for row,value in zip(matrix,values)];n=len(a)
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(a[r][col]));a[col],a[pivot]=a[pivot],a[col]
        if abs(a[col][col])<1e-9:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template print area is degenerate.",operation="mockup_composer",stage="perspective")
        scale=a[col][col];a[col]=[x/scale for x in a[col]]
        for row in range(n):
            if row==col:continue
            factor=a[row][col];a[row]=[x-factor*y for x,y in zip(a[row],a[col])]
    return [row[-1] for row in a]

def _perspective_coefficients(destination,source):
    matrix=[];values=[]
    for (x,y),(u,v) in zip(destination,source):
        matrix.extend(([x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]));values.extend((u,v))
    return _solve(matrix,values)

class MockupTemplateRegistry:
    def __init__(self,root:Path=TEMPLATE_ROOT):self.root=root
    def _registry(self):return self.root/"registry.json"
    def list(self):
        try:value=json.loads(self._registry().read_text())
        except (OSError,ValueError):value={"schema_version":"1.0","templates":[]}
        return value
    def validate(self,item):
        if not _ID.fullmatch(str(item.get("template_id") or "")) or not re.fullmatch(r"[0-9]+\.[0-9]+",str(item.get("version") or "")):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template identity or version is invalid.",operation="mockup_template_registry",stage="metadata")
        if item.get("model_category") not in {"male","female","product-only","lifestyle"}:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template model category is invalid.",operation="mockup_template_registry",stage="metadata")
        if item.get("template_kind") not in {"placeholder","licensed_photo","user_photo","locally_generated"} or type(item.get("production_allowed")) is not bool:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template kind and production eligibility are required.",operation="mockup_template_registry",stage="metadata")
        if item.get("subject_role") not in {"clean_product","male_model","female_model","lifestyle"}:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template subject role is invalid.",operation="mockup_template_registry",stage="metadata")
        if not all(isinstance(item.get(k),str) and item[k].strip() for k in ("pose","garment_style","garment_color")):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template pose, garment style, and color are required.",operation="mockup_template_registry",stage="metadata")
        points=item.get("print_area") or []
        if len(points)!=4 or any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) for v in p) for p in points):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template requires four print-area coordinates.",operation="mockup_template_registry",stage="print_area")
        for key in ("base_image","shirt_mask"):
            path=(self.root/str(item.get(key) or "")).resolve()
            if self.root.resolve() not in path.parents or not path.is_file():raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template binary is unavailable.",operation="mockup_template_registry",stage="binary")
        if item.get("lighting_map"):
            lighting=(self.root/str(item["lighting_map"])).resolve()
            if self.root.resolve() not in lighting.parents or not lighting.is_file():raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template lighting map is unavailable.",operation="mockup_template_registry",stage="binary")
        provenance=item.get("provenance")
        if not isinstance(provenance,dict) or not all(str(provenance.get(k) or "").strip() for k in ("source","creator","license","created_at","notes")):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Complete template provenance and license are required.",operation="mockup_template_registry",stage="license")
        if item["template_kind"]=="placeholder" and item["production_allowed"]:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Placeholder templates cannot be production eligible.",operation="mockup_template_registry",stage="eligibility")
        return item
    def register(self,item):
        self.root.mkdir(parents=True,exist_ok=True);self.validate(item);registry=self.list();items=[x for x in registry["templates"] if (x.get("template_id"),x.get("version"))!=(item["template_id"],item["version"])];items.append(item);value={"schema_version":"1.0","templates":sorted(items,key=lambda x:(x["template_id"],x["version"]))};_json(self._registry(),value);return item
    def get(self,template_id,version):
        item=next((x for x in self.list()["templates"] if x.get("template_id")==template_id and x.get("version")==version),None)
        if not item:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Mockup template is not registered.",operation="mockup_template_registry",stage="lookup")
        return self.validate(item)

class DeterministicMockupComposer:
    def __init__(self,orchestrator=None,registry=None):self.orchestrator=orchestrator or product_orchestrator.ProductOrchestrator();self.registry=registry or MockupTemplateRegistry()
    def _job(self,job_id):
        state=self.orchestrator.load(job_id);selected=((state.get("evidence") or {}).get("selection") or {}).get("selected") or {};path=Path(str(selected.get("png_path") or "")).resolve(strict=True);root=self.orchestrator._path(job_id).parent.resolve()
        if root not in path.parents or _hash(path)!=selected.get("png_sha256"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Approved source artwork identity does not match this job.",operation="mockup_composer",stage="ownership")
        if state.get("order_status")!="not_created":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Order evidence blocks local mockup composition.",operation="mockup_composer",stage="order")
        return root,state,selected,path
    def compose(self,job_id,template_id,version,role):
        if role not in ROLES:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Mockup role is invalid.",operation="mockup_composer",stage="role")
        root,state,selected,art_path=self._job(job_id);template=self.registry.get(template_id,version)
        if template["model_category"]!=ROLES[role]:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template category does not match the selected role.",operation="mockup_composer",stage="role")
        base=Image.open(self.registry.root/template["base_image"]).convert("RGBA");mask=Image.open(self.registry.root/template["shirt_mask"]).convert("L")
        if mask.size!=base.size:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Shirt mask dimensions do not match the template.",operation="mockup_composer",stage="mask")
        quad=[tuple(map(float,p)) for p in template["print_area"]];w,h=base.size
        if any(x<4 or y<4 or x>w-4 or y>h-4 for x,y in quad):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template print area violates safe margins.",operation="mockup_composer",stage="safe_margin")
        art=Image.open(art_path).convert("RGBA");source=[(0,0),(art.width-1,0),(art.width-1,art.height-1),(0,art.height-1)];coeff=_perspective_coefficients(quad,source)
        warped=art.transform(base.size,Image.Transform.PERSPECTIVE,coeff,resample=Image.Resampling.BICUBIC);alpha=ImageChops.multiply(warped.getchannel("A"),mask);warped.putalpha(alpha)
        lighting=template.get("lighting_map")
        if lighting:
            light=Image.open(self.registry.root/lighting).convert("L").resize(base.size);rgb=ImageChops.multiply(warped.convert("RGB"),Image.merge("RGB",(light,light,light)));warped=Image.merge("RGBA",(*rgb.split(),alpha))
        output=Image.alpha_composite(base,warped);out_root=root/"mockup-composer"/"outputs";out_root.mkdir(parents=True,exist_ok=True)
        metadata={"job_id":job_id,"role":role,"template_id":template_id,"template_version":version,"template_category":template["model_category"],"template_kind":template["template_kind"],"production_allowed":template["production_allowed"],"subject_role":template["subject_role"],"pose":template.get("pose"),"garment_style":template.get("garment_style"),"garment_color":template.get("garment_color"),"provenance":template["provenance"],"artwork_sha256":selected["png_sha256"],"print_area":template["print_area"],"mask_sha256":_hash(self.registry.root/template["shirt_mask"]),"dimensions":[w,h],"algorithm":"pillow_perspective_alpha_mask_v1","external_provider_calls":0,"etsy_updated":False,"printify_updated":False,"order_created":False};identity=_digest(metadata);path=out_root/f"mockup-{identity}.png"
        if not path.exists():output.save(path,"PNG")
        metadata.update(asset_id=f"composed-{identity[:20]}",output_sha256=_hash(path),local_path=str(path),generated_at=_now());_json(out_root/f"mockup-{identity}.json",metadata)
        pipeline=root/"mockup-composer"/"state.json";current=self.status(job_id);outputs=[x for x in current.get("outputs",[]) if x.get("role")!=role];outputs.append(metadata);stage="mockups_review_ready" if set(x["role"] for x in outputs)>=set(ROLES) else "mockups_composed";_json(pipeline,{"stage":stage,"templates_selected":[{"template_id":x["template_id"],"version":x["template_version"],"role":x["role"]} for x in outputs],"outputs":outputs,"updated_at":_now(),"etsy_updated":False,"printify_updated":False,"order_created":False});return self.public(job_id)
    def status(self,job_id):
        root=self.orchestrator._path(job_id).parent;path=root/"mockup-composer"/"state.json"
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return {"stage":"mockup_templates_selected","outputs":[],"etsy_updated":False,"printify_updated":False,"order_created":False}
    def public(self,job_id):
        value=self.status(job_id);outputs=[{k:x.get(k) for k in ("asset_id","role","template_id","template_version","template_kind","production_allowed","subject_role","garment_color","output_sha256","dimensions","generated_at","print_area","mask_sha256","algorithm","provenance")}|{"url":f"/commerce/jobs/{job_id}/composed-mockups/{x.get('asset_id')}"} for x in value.get("outputs") or []];return {**value,"outputs":outputs}
    def approve(self,job_id,ordered_ids,primary_id,confirmed=False):
        root,state,selected,_=self._job(job_id);current=self.status(job_id);by_id={x["asset_id"]:x for x in current.get("outputs") or []}
        if len(ordered_ids)<3 or len(set(ordered_ids))!=len(ordered_ids) or any(x not in by_id for x in ordered_ids) or primary_id not in ordered_ids:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Select three distinct composed mockups and a primary image.",operation="mockup_composer",stage="approval")
        ordered=[by_id[x]|{"rank":i+1,"primary":x==primary_id} for i,x in enumerate(ordered_ids)];roles={x["role"] for x in ordered}
        if not set(ROLES)<=roles or len({x["output_sha256"] for x in ordered})!=len(ordered) or any(x.get("production_allowed") is not True or x.get("template_kind")=="placeholder" for x in ordered):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Three distinct production-eligible clean product, male model, and female model templates are required.",operation="mockup_composer",stage="quality")
        proposal={"job_id":job_id,"artwork_sha256":selected["png_sha256"],"ordered_mockups":ordered,"etsy_updated":False,"printify_updated":False,"order_created":False};proposal["proposal_sha256"]=_digest(proposal)
        if not confirmed:return {**proposal,"confirmation_required":True,"message":"Approve these deterministic mockups locally? Etsy and Printify will not be updated."}
        approval={"stage":"mockups_approved","approved_at":_now(),"proposal_sha256":proposal["proposal_sha256"],"ordered_mockups":ordered,"message":"Mockups approved locally. Etsy and Printify have not been updated.","etsy_updated":False,"printify_updated":False,"order_created":False};review=root/"mockup-composer"/"review";review.mkdir(parents=True,exist_ok=True);immutable=review/f"proposal-{proposal['proposal_sha256']}.json"
        if not immutable.exists():_json(immutable,proposal)
        _json(review/"approval.json",approval);current.update(stage="mockups_approved",approval=approval);_json(root/"mockup-composer"/"state.json",current);return approval
    def asset(self,job_id,asset_id):
        root=self.orchestrator._path(job_id).parent.resolve();item=next((x for x in self.status(job_id).get("outputs") or [] if x.get("asset_id")==asset_id),None)
        if not item:raise FileNotFoundError(asset_id)
        path=Path(item["local_path"]).resolve(strict=True)
        if root not in path.parents or _hash(path)!=item["output_sha256"]:raise FileNotFoundError(asset_id)
        return path
