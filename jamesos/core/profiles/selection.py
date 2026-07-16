from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
from jamesos.config import VAULT

PROFILES_ROOT = VAULT / "JamesOS" / "Profiles"
SECRETS_ROOT = VAULT / "JamesOS" / "Secrets"

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
