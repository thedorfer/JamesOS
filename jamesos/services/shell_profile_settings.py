from __future__ import annotations

import re
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
    def save(self,profile_id:str,values:Any)->dict[str,Any]:
        clean=self.validate(profile_id,values);current={}
        if self.path.is_file():
            import json
            try:current=json.loads(self.path.read_text())
            except (OSError,ValueError):current={}
        current.setdefault(profile_id,{}).update(clean);_atomic_json(self.path,current)
        return {"profile_id":profile_id,"configuration":current[profile_id]}
