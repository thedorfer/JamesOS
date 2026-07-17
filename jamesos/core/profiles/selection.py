from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
import re
from jamesos.config import VAULT

PROFILES_ROOT = VAULT / "JamesOS" / "Profiles"
SECRETS_ROOT = VAULT / "JamesOS" / "Secrets"
PROFILE_ID_PATTERN=re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

def load_commerce_profile_by_id(profile_id:str,*,required:bool=False)->dict[str,Any]:
    if not isinstance(profile_id,str) or not PROFILE_ID_PATTERN.fullmatch(profile_id):
        if required:raise ValueError("Commerce profile ID is invalid")
        return {}
    path=PROFILES_ROOT/f"{profile_id}.json"
    if not path.is_file():
        if required:raise FileNotFoundError(f"Commerce profile is not configured: {profile_id}")
        return {}
    value=json.loads(path.read_text(encoding="utf-8"))
    if value.get("profile_id") not in (None,profile_id) or value.get("profile_type")!="commerce_shop":
        if required:raise ValueError("Profile must be an exact commerce_shop profile")
        return {}
    return value

def list_commerce_profiles(enabled_only:bool=True)->list[dict[str,Any]]:
    rows=[]
    if not PROFILES_ROOT.is_dir():return rows
    for path in sorted(PROFILES_ROOT.glob("*.json")):
        profile_id=path.stem
        if not PROFILE_ID_PATTERN.fullmatch(profile_id):continue
        try:value=load_commerce_profile_by_id(profile_id,required=True)
        except (OSError,ValueError,json.JSONDecodeError):continue
        config=value.get("configuration") or {}
        if enabled_only and value.get("enabled") is not True:continue
        if type(config.get("printify_shop_id")) is not int or not str(config.get("etsy_shop_slug") or "").strip():continue
        rows.append(value)
    return rows

def selected_profile_id() -> str:
    configured=os.getenv("JAMESOS_COMMERCE_PROFILE_ID","").strip()
    if configured:return configured
    pointer=PROFILES_ROOT/"selected_commerce_profile"
    return pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else "commerce_shop"

def load_commerce_profile(*,required:bool=False)->dict[str,Any]:
    path=PROFILES_ROOT/f"{selected_profile_id()}.json"
    if not path.is_file():
        if required:raise FileNotFoundError(f"Selected commerce profile is not configured: {path.name}")
        return {}
    value=json.loads(path.read_text(encoding="utf-8"))
    if value.get("profile_type")!="commerce_shop":raise ValueError("Selected profile must have profile_type commerce_shop")
    return value

def commerce_configuration()->dict[str,Any]:return dict(load_commerce_profile().get("configuration") or {})
def protected_resources()->tuple[str,...]:return tuple(str(x) for x in load_commerce_profile().get("protected_resources") or [])
def secret_handle(binding:str)->str|None:
    value=(load_commerce_profile().get("secret_handle_bindings") or {}).get(binding)
    return str(value) if value else None
