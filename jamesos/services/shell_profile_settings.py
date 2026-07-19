from __future__ import annotations

import re
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services.product_orchestrator import _atomic_json


PROFILE_IDS={"bagholder-supply","unitystitches"}
FIELDS={"display_name":120,"printify_shop_title":160,"printify_shop_id":20,"etsy_shop_slug":120,"garment_defaults":500,"artwork_palette":500,"brand_voice":500,"listing_guidance":160}


class ShellProfileSettings:
    def __init__(self,path:Path|None=None):self.path=path or VAULT/"JamesOS"/"Admin"/"commerce-profile-overrides.json"
    def validate(self,profile_id:str,values:Any)->dict[str,Any]:
        if profile_id not in PROFILE_IDS:raise ValueError("Unsupported commerce profile")
        if not isinstance(values,dict) or set(values)-set(FIELDS):raise ValueError("Unsupported profile field")
        clean={}
        for key,value in values.items():
            text=" ".join(str(value).split())
            if not text or len(text)>FIELDS[key] or re.search(r"[<>\x00]",text):raise ValueError("Profile value is invalid")
            if key=="printify_shop_id":
                if not text.isdigit() or int(text)<=0:raise ValueError("Printify shop ID is invalid")
                clean[key]=int(text)
            else:clean[key]=text
        return clean
    def _read(self)->dict[str,Any]:
        if not self.path.is_file():return {}
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError):return {}
    def revision(self)->str:return sha256(json.dumps(self._read(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
    def view(self,profile_id:str)->dict[str,Any]:
        if profile_id not in PROFILE_IDS:raise ValueError("Unsupported commerce profile")
        return {"profile_id":profile_id,"configuration":self._read().get(profile_id,{}) if isinstance(self._read().get(profile_id,{}),dict) else {},"revision":self.revision()}
    def save(self,profile_id:str,values:Any,*,revision:str|None=None)->dict[str,Any]:
        if isinstance(values,dict) and "revision" in values:values=dict(values);revision=str(values.pop("revision"))
        clean=self.validate(profile_id,values);current=self._read();current_revision=self.revision()
        if revision is not None and revision!=current_revision:raise ValueError("Profile configuration changed; refresh before saving")
        if self.path.is_file():
            rollback=self.path.with_name(self.path.stem+".rollback.json");_atomic_json(rollback,current)
        current.setdefault(profile_id,{}).update(clean);_atomic_json(self.path,current)
        audit=self.path.with_name(self.path.stem+".audit.json");events=[]
        if audit.is_file():
            try:events=json.loads(audit.read_text(encoding="utf-8"))
            except (OSError,ValueError):events=[]
        events.append({"timestamp":datetime.now().astimezone().isoformat(),"event":"commerce_profile_updated","profile_id":profile_id,"fields":sorted(clean)});_atomic_json(audit,events[-200:])
        return {"profile_id":profile_id,"configuration":current[profile_id],"revision":self.revision()}
