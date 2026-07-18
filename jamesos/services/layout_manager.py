from __future__ import annotations

import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from jamesos.config import VAULT
from jamesos.core.errors import ValidationError
from jamesos.services.application_shell import COMPONENT_REGISTRY,VIEWS
from jamesos.services.product_orchestrator import _atomic_json


ROOT=VAULT/"JamesOS"/"Layouts"
SCHEMA_VERSION=1
VIEW_RE=re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
THEMES=MappingProxyType({"jamesos-dark":MappingProxyType({
    "color_bg":"#0b0d13","color_panel":"#11131b","color_surface":"#191c28","color_text":"#f1f3ff","color_muted":"#a6adc8",
    "color_accent":"#8b5cf6","color_ready":"#39d98a","color_warning":"#d49b20","radius":"10px","spacing":"8px",
})})
THEME_TOKEN_NAMES={"color_bg","color_panel","color_surface","color_text","color_muted","color_accent","color_ready","color_warning","radius","spacing"}
LOCKED_DEFAULTS=MappingProxyType({
    "destination":{"panel_id":"destination","component":"card","title":"Destination","column":9,"row":1,"width":4,"height":2,"collapsed":False,"hidden":False,"layout_locked":True,"value_locked":True,"action_locks":["hide","move","resize","reorder"],"lock_reason":"Job destination is immutable and must remain visible."},
    "publication_status":{"panel_id":"publication_status","component":"status_banner","title":"Publication safeguards","column":9,"row":3,"width":4,"height":2,"collapsed":False,"hidden":False,"layout_locked":True,"value_locked":True,"action_locks":["hide","move","resize","reorder"],"lock_reason":"Publication and order status must remain visible."},
    "external_confirmation":{"panel_id":"external_confirmation","component":"confirmation","title":"External action confirmation","column":9,"row":5,"width":4,"height":2,"collapsed":False,"hidden":False,"layout_locked":True,"value_locked":True,"action_locks":["hide","move","resize","reorder"],"lock_reason":"Provider actions always require visible confirmation."},
})


def default_layout(view_id:str)->dict[str,Any]:
    _view(view_id);panels=[]
    if view_id=="commerce.new":panels=[{"panel_id":"commerce_form","component":"form","title":"Commerce Creator","column":1,"row":1,"width":8,"height":7,"collapsed":False,"hidden":False,"layout_locked":False,"value_locked":False,"action_locks":[],"lock_reason":""},*map(dict,LOCKED_DEFAULTS.values())]
    elif view_id=="commerce.loading":panels=[{"panel_id":"generation_progress","component":"progress_steps","title":"Generation progress","column":1,"row":1,"width":8,"height":5,"collapsed":False,"hidden":False,"layout_locked":False,"value_locked":True,"action_locks":[],"lock_reason":"Progress values are system-owned."},*map(dict,LOCKED_DEFAULTS.values())]
    elif view_id=="commerce.review":panels=[{"panel_id":"review_gallery","component":"image_gallery","title":"Product review","column":1,"row":1,"width":8,"height":7,"collapsed":False,"hidden":False,"layout_locked":False,"value_locked":True,"action_locks":[],"lock_reason":"Review evidence is system-owned."},*map(dict,LOCKED_DEFAULTS.values())]
    else:
        primary={"panel_id":"primary","component":"card","title":view_id.replace("."," ").title(),"column":1,"row":1,"width":8 if view_id.startswith("commerce.") else 12,"height":4,"collapsed":False,"hidden":False,"layout_locked":False,"value_locked":False,"action_locks":[],"lock_reason":""}
        panels=[primary,*map(dict,LOCKED_DEFAULTS.values())] if view_id.startswith("commerce.") else [primary]
    return {"schema_version":SCHEMA_VERSION,"view_id":view_id,"theme_id":"jamesos-dark","shell":{"chat_width":420,"chat_collapsed":False},"panels":panels}


def _view(value:Any)->str:
    value=str(value or "")
    if not VIEW_RE.fullmatch(value) or value not in VIEWS:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout view ID is invalid.",operation="layout_manager",stage="validation")
    return value


def _boolean(value:Any,field:str)->bool:
    if type(value) is not bool:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} must be a boolean.",operation="layout_manager",stage="validation")
    return value


def _integer(value:Any,minimum:int,maximum:int,field:str)->int:
    if type(value) is not int or not minimum<=value<=maximum:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} is outside the allowed grid.",operation="layout_manager",stage="validation")
    return value


def _safe_text(value:Any,limit:int,field:str)->str:
    if not isinstance(value,str):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} must be text.",operation="layout_manager",stage="validation")
    value=" ".join(value.split())
    if not value or len(value)>limit or re.search(r"<[^>]+>|javascript:|https?://|[{}]",value,re.I):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} contains unsafe content.",operation="layout_manager",stage="validation")
    return value


def validate_theme_tokens(value:Any)->dict[str,str]:
    if not isinstance(value,dict) or set(value)!=THEME_TOKEN_NAMES:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Theme must contain only the approved design tokens.",operation="layout_manager",stage="theme")
    clean={}
    for key,item in value.items():
        if not isinstance(item,str) or len(item)>32 or re.search(r"<|>|javascript:|https?://|url\s*\(|[{};]",item,re.I):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Theme contains executable or remote content.",operation="layout_manager",stage="theme")
        if key.startswith("color_") and not re.fullmatch(r"#[0-9A-Fa-f]{6}",item):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Theme color token is invalid.",operation="layout_manager",stage="theme")
        if key in {"radius","spacing"} and not re.fullmatch(r"\d{1,2}px",item):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Theme size token is invalid.",operation="layout_manager",stage="theme")
        clean[key]=item
    return clean


def validate_layout(value:Any,view_id:str,*,user_write:bool=True)->dict[str,Any]:
    view_id=_view(view_id)
    if not isinstance(value,dict) or value.get("schema_version")!=SCHEMA_VERSION or value.get("view_id")!=view_id:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout schema or view binding is invalid.",operation="layout_manager",stage="validation")
    theme_id=str(value.get("theme_id") or "")
    if theme_id not in THEMES:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout theme is not registered.",operation="layout_manager",stage="validation")
    shell=value.get("shell")
    if not isinstance(shell,dict):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout shell is invalid.",operation="layout_manager",stage="validation")
    clean={"schema_version":SCHEMA_VERSION,"view_id":view_id,"theme_id":theme_id,"shell":{"chat_width":_integer(shell.get("chat_width"),300,2000,"shell.chat_width"),"chat_collapsed":_boolean(shell.get("chat_collapsed"),"shell.chat_collapsed")},"panels":[]}
    panels=value.get("panels")
    if not isinstance(panels,list) or not 1<=len(panels)<=40:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout panels must be a bounded list.",operation="layout_manager",stage="validation")
    seen=set()
    for raw in panels:
        if not isinstance(raw,dict):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout panel must be an object.",operation="layout_manager",stage="validation")
        panel_id=_safe_text(raw.get("panel_id"),64,"panel_id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",panel_id) or panel_id in seen:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout panel ID is invalid or duplicated.",operation="layout_manager",stage="validation")
        seen.add(panel_id);component=str(raw.get("component") or "")
        if component not in COMPONENT_REGISTRY:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout component is not registered.",operation="layout_manager",stage="validation")
        column=_integer(raw.get("column"),1,12,"panel.column");width=_integer(raw.get("width"),1,12,"panel.width")
        if column+width-1>12:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Layout panel extends beyond the 12-column grid.",operation="layout_manager",stage="validation")
        panel={"panel_id":panel_id,"component":component,"title":_safe_text(raw.get("title"),120,"panel.title"),"column":column,"row":_integer(raw.get("row"),1,100,"panel.row"),"width":width,"height":_integer(raw.get("height"),1,50,"panel.height"),
            "collapsed":_boolean(raw.get("collapsed"),"panel.collapsed"),"hidden":_boolean(raw.get("hidden"),"panel.hidden"),"layout_locked":_boolean(raw.get("layout_locked"),"panel.layout_locked"),"value_locked":_boolean(raw.get("value_locked"),"panel.value_locked"),
            "action_locks":[],"lock_reason":str(raw.get("lock_reason") or "")[:300]}
        locks=raw.get("action_locks")
        if not isinstance(locks,list) or any(item not in {"hide","move","resize","reorder","collapse"} for item in locks):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Panel action locks are invalid.",operation="layout_manager",stage="validation")
        panel["action_locks"]=list(dict.fromkeys(locks));system=LOCKED_DEFAULTS.get(panel_id)
        if system:
            if user_write and any(raw.get(key)!=system[key] for key in ("component","column","row","width","height","hidden","layout_locked","value_locked")):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"System-locked panel {panel_id} cannot be changed.",operation="layout_manager",stage="locks")
            panel=dict(system)
        clean["panels"].append(panel)
    required=set(LOCKED_DEFAULTS) if view_id.startswith("commerce.") else set()
    missing=required-seen
    if user_write and missing:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Required locked commerce panels cannot be removed.",operation="layout_manager",stage="locks")
    for panel_id in missing:clean["panels"].append(dict(LOCKED_DEFAULTS[panel_id]))
    return clean


class LayoutManager:
    def __init__(self,root:Path=ROOT):self.root=root
    def path(self,view_id:str)->Path:return self.root/f"{_view(view_id)}.json"
    def get(self,view_id:str)->dict[str,Any]:
        path=self.path(view_id)
        if not path.is_file():return default_layout(view_id)
        try:value=json.loads(path.read_text(encoding="utf-8"));return validate_layout(value,view_id,user_write=False)
        except (OSError,ValueError,ValidationError):return default_layout(view_id)
    def save(self,view_id:str,value:Any)->dict[str,Any]:
        clean=validate_layout(value,view_id,user_write=True);_atomic_json(self.path(view_id),clean);return clean
    def reset(self,view_id:str)->dict[str,Any]:
        path=self.path(view_id)
        if path.exists():path.unlink()
        return default_layout(view_id)
