from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import requests
from PIL import Image

from jamesos.core.errors import StateConflictError, ValidationError
from jamesos.integrations.printify_client import PrintifyClient
from jamesos.services import product_orchestrator

_JOB=re.compile(r"product-[A-Za-z0-9._-]{1,120}")
_ROLES={"clean_front","male_model","female_model"}

def _now():return datetime.now().astimezone().isoformat()
def _atomic(path:Path,value:Any):product_orchestrator._atomic_json(path,value)
def _digest(value:Any):return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

class MockupReviewService:
    def __init__(self,orchestrator=None,*,client=None,session=None):
        self.orchestrator=orchestrator or product_orchestrator.ProductOrchestrator();self.client=client or PrintifyClient();self.session=session or requests.Session()
    def _root(self,job_id:str)->Path:
        if not isinstance(job_id,str) or not _JOB.fullmatch(job_id) or Path(job_id).name!=job_id:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Mockup job ID is invalid.",operation="commerce_mockup_intake",stage="input")
        return self.orchestrator._path(job_id).parent
    def _state(self,job_id):
        state=self.orchestrator.load(job_id);e=state.get("evidence") or {};draft=e.get("draft") or {};destination=state.get("destination") or {}
        if not draft.get("printify_product_id") or not state.get("shop_id"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="The existing Printify product binding is unavailable.",operation="commerce_mockup_intake",stage="ownership")
        if state.get("order_status")!="not_created":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Order evidence blocks mockup intake.",operation="commerce_mockup_intake",stage="order")
        return state,draft,destination
    def refresh(self,job_id:str)->dict[str,Any]:
        root=self._root(job_id);state,draft,destination=self._state(job_id);product=self.client.get_product(state["shop_id"],draft["printify_product_id"])
        if str(product.get("id"))!=str(draft["printify_product_id"]):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Printify returned a different product.",operation="commerce_mockup_intake",stage="ownership")
        target=root/"mockup-intake";target.mkdir(parents=True,exist_ok=True);records=[]
        for index,item in enumerate(product.get("images") or []):
            url=str(item.get("src") or "");parsed=urlsplit(url)
            if parsed.scheme!="https" or parsed.hostname!="images.printify.com":continue
            response=self.session.get(url,timeout=(10,45));response.raise_for_status();content=response.content
            if len(content)>20*1024*1024:continue
            try:
                with Image.open(BytesIO(content)) as image:image.verify();width,height=image.size;fmt=image.format
            except (OSError,ValueError):continue
            if fmt not in {"PNG","JPEG","WEBP"}:continue
            digest=sha256(content).hexdigest();suffix={"PNG":"png","JPEG":"jpg","WEBP":"webp"}[fmt];path=target/f"mockup-{digest}.{suffix}"
            if not path.exists():path.write_bytes(content)
            label=" ".join(str(item.get(k) or "") for k in ("title","mockup_id","position", "camera_label")).lower()
            suggested="male_model" if any(x in label for x in ("male","man ","men","guy")) else "female_model" if any(x in label for x in ("female","woman","women","girl")) else "clean_front" if str(item.get("position") or "").lower()=="front" else "unassigned"
            records.append({"asset_id":f"mockup-{digest[:20]}","source_url":url,"sha256":digest,"dimensions":[width,height],"variant_ids":item.get("variant_ids") or [],"position":item.get("position"),"is_default":item.get("is_default") is True,"title":item.get("title") or item.get("mockup_id") or f"Printify mockup {index+1}","suggested_role":suggested,"local_path":str(path)})
        manifest={"schema_version":"1.0","job_id":job_id,"printify_product_id":draft["printify_product_id"],"printify_shop_id":state["shop_id"],"etsy_destination":destination.get("etsy_shop_slug"),"collected_at":_now(),"provider_image_count":len(product.get("images") or []),"mockups":records,"provider_write_performed":False,"etsy_updated":False,"order_created":False}
        _atomic(target/"manifest.json",manifest);return self.public(job_id)
    def public(self,job_id:str)->dict[str,Any]:
        root=self._root(job_id);path=root/"mockup-intake"/"manifest.json"
        try:value=json.loads(path.read_text())
        except (OSError,ValueError):value={"job_id":job_id,"provider_image_count":0,"mockups":[]}
        approval_path=root/"mockup-review"/"approval.json"
        try:approval=json.loads(approval_path.read_text())
        except (OSError,ValueError):approval=None
        return {"job_id":job_id,"provider_image_count":value.get("provider_image_count",0),"collected_at":value.get("collected_at"),"mockups":[{k:item.get(k) for k in ("asset_id","source_url","sha256","dimensions","variant_ids","position","is_default","title","suggested_role")}|{"url":f"/commerce/jobs/{job_id}/mockup-intake/{item.get('asset_id')}"} for item in value.get("mockups") or []],"approval":approval,"sync_warning":"Printify Mockup Library selection has not synchronized to the product API." if len(value.get("mockups") or [])<3 else None,"etsy_updated":False,"order_created":False}
    def prepare(self,job_id:str,selections:list[dict[str,Any]],*,confirmed:bool=False)->dict[str,Any]:
        root=self._root(job_id);state,draft,destination=self._state(job_id);manifest=json.loads((root/"mockup-intake"/"manifest.json").read_text());available={x["asset_id"]:x for x in manifest.get("mockups") or []}
        if len(selections)<3:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Select at least three distinct Printify mockups.",operation="commerce_mockup_review",stage="selection")
        ids=[str(x.get("asset_id") or "") for x in selections];roles=[str(x.get("role") or "") for x in selections]
        if len(ids)!=len(set(ids)) or any(x not in available for x in ids) or not _ROLES.issubset(set(roles)):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Clean front, male model, and female model assignments must reference distinct imported mockups.",operation="commerce_mockup_review",stage="selection")
        ordered=[]
        for rank,item in enumerate(selections,1):
            source=available[item["asset_id"]];ordered.append({"rank":rank,"primary":rank==1,"role":item["role"],"asset_id":source["asset_id"],"sha256":source["sha256"],"source_url":source["source_url"],"variant_ids":source["variant_ids"],"position":source["position"],"is_default":source["is_default"],"title":source["title"]})
        selected=(state.get("evidence",{}).get("selection") or {}).get("selected") or {}
        proposal={"schema_version":"1.0","job_id":job_id,"printify_product_id":draft["printify_product_id"],"etsy_destination":destination.get("etsy_shop_slug"),"artwork_sha256":selected.get("png_sha256"),"ordered_mockups":ordered,"etsy_update_allowed":False,"publication_allowed":False,"order_status":"not_created"};proposal["proposal_sha256"]=_digest(proposal)
        if not confirmed:return {**proposal,"confirmation_required":True,"message":"Approve these mockups locally? Etsy will not be updated."}
        review=root/"mockup-review";review.mkdir(parents=True,exist_ok=True);immutable=review/f"proposal-{proposal['proposal_sha256']}.json"
        if not immutable.exists():_atomic(immutable,proposal)
        approval={"approved":True,"approved_at":_now(),"proposal_sha256":proposal["proposal_sha256"],"ordered_mockups":ordered,"message":"Mockups approved locally. Etsy has not been updated.","etsy_updated":False,"order_created":False};_atomic(review/"approval.json",approval);return approval
    def asset(self,job_id,asset_id):
        root=self._root(job_id).resolve();manifest=json.loads((root/"mockup-intake"/"manifest.json").read_text())
        item=next((x for x in manifest.get("mockups") or [] if x.get("asset_id")==asset_id),None)
        if not item:raise FileNotFoundError(asset_id)
        path=Path(item["local_path"]).resolve(strict=True)
        if root not in path.parents or sha256(path.read_bytes()).hexdigest()!=item["sha256"]:raise FileNotFoundError(asset_id)
        return path
