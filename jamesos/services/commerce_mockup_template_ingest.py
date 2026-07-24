from __future__ import annotations
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any
from PIL import Image
from jamesos.core.errors import ValidationError
from jamesos.services.commerce_mockup_composer import MockupTemplateRegistry,TEMPLATE_ROOT

class MockupTemplateIngestService:
 def __init__(self,root:Path=TEMPLATE_ROOT):self.root=root;self.registry=MockupTemplateRegistry(root)
 def ingest(self,*,template_id:str,version:str,base_bytes:bytes,mask_bytes:bytes,metadata:dict[str,Any],lighting_bytes:bytes|None=None,displacement_bytes:bytes|None=None,eligibility_confirmed:bool=False):
  if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,80}",template_id) or not re.fullmatch(r"[0-9]+\.[0-9]+",version) or Path(template_id).name!=template_id:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template package identity is invalid.",operation="mockup_template_ingest",stage="path")
  if len(base_bytes)>25*1024*1024 or len(mask_bytes)>25*1024*1024:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template images are oversized.",operation="mockup_template_ingest",stage="image")
  try:
   base=Image.open(BytesIO(base_bytes));base.verify();base=Image.open(BytesIO(base_bytes)).convert("RGBA")
   mask=Image.open(BytesIO(mask_bytes));mask.verify();mask=Image.open(BytesIO(mask_bytes)).convert("L")
  except (OSError,ValueError) as exc:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template images are invalid.",operation="mockup_template_ingest",stage="image") from exc
  if base.size!=mask.size or min(base.size)<400 or max(base.size)>8000:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Mask dimensions must match a valid base image.",operation="mockup_template_ingest",stage="dimensions")
  provenance=metadata.get("provenance") or {};production=metadata.get("production_allowed") is True
  if production and (eligibility_confirmed is not True or not all(str(provenance.get(k) or "").strip() for k in ("source","creator","license","created_at","notes"))):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Production eligibility requires complete provenance, license, and explicit confirmation.",operation="mockup_template_ingest",stage="eligibility")
  package=(self.root/template_id/version).resolve();root=self.root.resolve()
  if root not in package.parents:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Template path is forbidden.",operation="mockup_template_ingest",stage="path")
  package.mkdir(parents=True,exist_ok=True);base_name=f"{template_id}/{version}/base.png";mask_name=f"{template_id}/{version}/mask.png";base.save(self.root/base_name,"PNG");mask.save(self.root/mask_name,"PNG")
  item={**metadata,"template_id":template_id,"version":version,"base_image":base_name,"shirt_mask":mask_name,"base_sha256":sha256((self.root/base_name).read_bytes()).hexdigest(),"mask_sha256":sha256((self.root/mask_name).read_bytes()).hexdigest()}
  for key,data in (("lighting_map",lighting_bytes),("displacement_map",displacement_bytes)):
   if data:
    name=f"{template_id}/{version}/{key}.png";Image.open(BytesIO(data)).save(self.root/name,"PNG");item[key]=name;item[key+"_sha256"]=sha256((self.root/name).read_bytes()).hexdigest()
  self.registry.validate(item);(package/"template.json").write_text(json.dumps(item,indent=2,sort_keys=True));self.registry.register(item);return {k:item.get(k) for k in ("template_id","version","display_name","template_kind","production_allowed","subject_role","base_sha256","mask_sha256","provenance")}
