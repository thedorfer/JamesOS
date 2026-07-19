from __future__ import annotations

from dataclasses import asdict,dataclass,field
import re
from typing import Any

from jamesos.core.errors import ValidationError


REGISTERED_VIEWS={"dashboard","agency.home","commerce.new","commerce.loading","commerce.artwork-review","commerce.review","commerce.diagnostics","jobs.list","jobs.detail","diagnostics","admin.home","profiles","settings"}
BADGES={None,"progress","ready","warning","pending_approval"}
LOCKED_ANCHORS=(
    {"item_id":"home","label":"Home","view_id":"dashboard","locked":True,"source":"system","badge":None},
    {"item_id":"agency","label":"The Agency","view_id":"agency.home","locked":True,"source":"system","badge":None},
    {"item_id":"admin","label":"Admin","view_id":"admin.home","locked":True,"source":"system","badge":None},
)


@dataclass(frozen=True)
class NavItem:
    item_id:str
    label:str
    view_id:str
    locked:bool=False
    source:str="system"
    badge:str|None=None


@dataclass
class NavigationContext:
    active_view:str="dashboard"
    selected_job_id:str=""
    job_stage:str=""
    review_ready:bool=False
    failed:bool=False
    pending_approval:bool=False
    recent_workspaces:list[str]=field(default_factory=list)
    agent_suggestions:list[dict[str,Any]]=field(default_factory=list)
    pointer_interaction:bool=False
    previous_navigation:list[dict[str,Any]]=field(default_factory=list)


def _safe(value:Any,limit:int,field_name:str)->str:
    if not isinstance(value,str):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field_name} must be text.",operation="context_dock",stage="validation")
    value=" ".join(value.split())
    if not value or len(value)>limit or not re.fullmatch(r"[A-Za-z0-9 ._:-]+",value):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field_name} is invalid.",operation="context_dock",stage="validation")
    return value


def validate_nav_item(value:Any,*,agent:bool=False)->dict[str,Any]:
    if isinstance(value,NavItem):value=asdict(value)
    if not isinstance(value,dict) or set(value)-{"item_id","label","view_id","locked","source","badge"}:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation item schema is invalid.",operation="context_dock",stage="validation")
    item_id=_safe(value.get("item_id"),64,"item_id");label=_safe(value.get("label"),80,"label");view_id=_safe(value.get("view_id"),64,"view_id")
    if view_id not in REGISTERED_VIEWS:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation view is not registered.",operation="context_dock",stage="validation")
    badge=value.get("badge")
    if badge not in BADGES:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation badge is invalid.",operation="context_dock",stage="validation")
    if agent and (item_id in {item["item_id"] for item in LOCKED_ANCHORS} or view_id in {item["view_id"] for item in LOCKED_ANCHORS}):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Agent suggestions cannot override locked navigation.",operation="context_dock",stage="locks")
    return {"item_id":item_id,"label":label,"view_id":view_id,"locked":False if agent else bool(value.get("locked",False)),"source":"agent" if agent else str(value.get("source") or "system"),"badge":badge}


def validate_navigation_context(value:Any)->NavigationContext:
    if isinstance(value,NavigationContext):context=value
    elif isinstance(value,dict):
        allowed={field.name for field in __import__("dataclasses").fields(NavigationContext)}
        if set(value)-allowed:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation context schema is invalid.",operation="context_dock",stage="validation")
        context=NavigationContext(**value)
    else:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation context must be an object.",operation="context_dock",stage="validation")
    if context.active_view not in REGISTERED_VIEWS:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Active navigation view is not registered.",operation="context_dock",stage="validation")
    if type(context.review_ready) is not bool or type(context.failed) is not bool or type(context.pending_approval) is not bool or type(context.pointer_interaction) is not bool:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation state flags must be boolean.",operation="context_dock",stage="validation")
    if len(context.recent_workspaces)>8 or len(context.agent_suggestions)>8 or len(context.previous_navigation)>20:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Navigation context exceeds bounds.",operation="context_dock",stage="validation")
    for view in context.recent_workspaces:
        if view not in REGISTERED_VIEWS:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Recent navigation view is not registered.",operation="context_dock",stage="validation")
    return context


def build_navigation(value:NavigationContext|dict[str,Any])->list[dict[str,Any]]:
    context=validate_navigation_context(value)
    if context.pointer_interaction and context.previous_navigation:
        previous=[validate_nav_item(item) for item in context.previous_navigation]
        if all(any(item["item_id"]==anchor["item_id"] for item in previous) for anchor in LOCKED_ANCHORS):return previous
    contextual=[]
    def add(item):
        if item["view_id"] not in {entry["view_id"] for entry in contextual} and item["view_id"] not in {anchor["view_id"] for anchor in LOCKED_ANCHORS}:contextual.append(item)
    if context.selected_job_id:
        if context.failed:add(validate_nav_item({"item_id":"job-diagnostics","label":"Diagnostics","view_id":"diagnostics","badge":"warning"}))
        elif context.review_ready:add(validate_nav_item({"item_id":"job-review","label":"Review","view_id":"commerce.review","badge":"ready"}))
        elif context.pending_approval:add(validate_nav_item({"item_id":"job-approval","label":"Review","view_id":"commerce.review","badge":"pending_approval"}))
        else:add(validate_nav_item({"item_id":"current-job","label":"Current job","view_id":"commerce.loading","badge":"progress"}))
    label=lambda view:"Product Studio" if view=="commerce.new" else view.replace("."," ").title()
    if context.active_view not in {anchor["view_id"] for anchor in LOCKED_ANCHORS}:add(validate_nav_item({"item_id":"active-workspace","label":label(context.active_view),"view_id":context.active_view,"badge":None}))
    for view in context.recent_workspaces:add(validate_nav_item({"item_id":f"recent-{view.replace('.','-')}","label":label(view),"view_id":view,"badge":None}))
    for suggestion in context.agent_suggestions:add(validate_nav_item(suggestion,agent=True))
    return [dict(LOCKED_ANCHORS[0]),*contextual,dict(LOCKED_ANCHORS[1]),dict(LOCKED_ANCHORS[2])]
