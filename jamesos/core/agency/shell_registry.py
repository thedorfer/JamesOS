from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any,Callable

from jamesos.config import VAULT
from jamesos.services.product_orchestrator import _atomic_json


AGENT_ID=re.compile(r"^[a-z][a-z0-9_.-]{1,95}$")
ADMIN_OPERATIONS=("config.update_commerce_profile","config.update_network_policy","secret.replace","secret.delete_confirmed","layout.restore_defaults","service.restart_confirmed","ehf.acknowledge","ehf.resolve")
MANIFESTS={
    "jade":{"name":"Jade","role":"JamesOS coordinator and workspace guide.","installation_state":"core","version":"1.0.0","workspace":"dashboard","permissions":["workspace navigation","sanitized local context","registered commands"],"capabilities":["conversation","workspace.navigate","workspace.guide"],"removable":False,"disable_allowed":False},
    "merchant":{"name":"The Merchant","role":"Commerce product preparation and review specialist.","installation_state":"installed","version":"1.0.0","workspace":"commerce.new","permissions":["local product forms","commerce job reads","artwork and listing preparation","review workspaces"],"capabilities":["commerce.form.prepare","commerce.jobs.inspect","commerce.review.open"],"removable":True,"disable_allowed":True},
    "administrator":{"name":"The Administrator","role":"Controlled JamesOS configuration and operational administration.","installation_state":"installed","version":"1.0.0","workspace":"admin.home","permissions":["allowlisted configuration","write-only secret replacement","confirmed registered operations"],"capabilities":list(ADMIN_OPERATIONS),"removable":True,"disable_allowed":True},
    "jamesos.book-opportunity-scout":{"name":"Book Opportunity Scout","role":"Local evidence-backed coloring-book opportunity research.","installation_state":"installed","version":"0.1.0","workspace":"agency.book-scout","permissions":["local research artifacts","public read-only research","local candidate decisions"],"capabilities":["books.opportunity.research","books.opportunity.decide"],"removable":True,"disable_allowed":True},
    "jamesos.coloring-book-producer":{"name":"Coloring Book Producer","role":"Local coloring-book project planning and approvals.","installation_state":"optional","version":"0.1.0","workspace":"agency.coloring-book-producer","permissions":["local book project read/write","approved Scout run reads","no network, providers, credentials, or terminal"],"capabilities":["books.project.create","books.brief.edit","books.production_spec.edit","books.project.approve_local","books.projects.browse"],"removable":True,"disable_allowed":True},
}
CATALOG=(
    {"agent_id":"archivist","name":"The Archivist","publisher":"JamesOS","description":"Organizes and searches selected indexed document collections.","version":"planned","compatibility":"planned","verified":True,"implementation_state":"planned","required_capabilities":["documents.search","collections.create"],"filesystem_access":"Read selected document folders","network_access":"None","provider_access":"None","credential_access":"None","terminal_access":"None","confirmation_requirements":["Installation and folder grants"]},
    {"agent_id":"mechanic","name":"The Mechanic","publisher":"JamesOS","description":"Planned diagnostics and confirmed service-recovery specialist.","version":"planned","compatibility":"planned","verified":True,"implementation_state":"planned","required_capabilities":["service.diagnose","service.restart_confirmed"],"filesystem_access":"Sanitized service diagnostics","network_access":"Local services only","provider_access":"None","credential_access":"Configured state only","terminal_access":"No arbitrary terminal","confirmation_requirements":["Service restart"]},
    {"agent_id":"scribe","name":"The Scribe","publisher":"JamesOS","description":"Planned local drafting and structured writing assistant.","version":"planned","compatibility":"planned","verified":True,"implementation_state":"planned","required_capabilities":["documents.draft"],"filesystem_access":"Selected draft locations","network_access":"None","provider_access":"None","credential_access":"None","terminal_access":"None","confirmation_requirements":["Installation and write location"]},
    {"agent_id":"jamesos.book-opportunity-scout","name":"Book Opportunity Scout","category":"Publishing","publisher":"JamesOS","description":"Researches and deterministically ranks coloring-book opportunities using local artifacts and optional public read-only evidence.","version":"0.1.0","compatibility":"current","verified":True,"implementation_state":"implemented","required_capabilities":["books.opportunity.research","books.opportunity.decide"],"filesystem_access":"Private local Scout run artifacts","network_access":"Optional public read-only research","provider_access":"None","credential_access":"None","terminal_access":"No arbitrary terminal","confirmation_requirements":["Install or hire","Candidate decision changes"]},
    {"agent_id":"jamesos.coloring-book-producer","name":"Coloring Book Producer","category":"Publishing","publisher":"JamesOS","description":"Turns approved Scout candidates into structured local planning projects.","version":"0.1.0","compatibility":"current","verified":True,"implementation_state":"implemented","required_capabilities":["books.project.create","books.brief.edit"],"filesystem_access":"Books project root and approved Scout runs","network_access":"None","provider_access":"None","credential_access":"None","terminal_access":"None","confirmation_requirements":["Install or hire","Confirmed local project creation","Local brief approval"]},
)


class ShellAgencyRegistry:
    def __init__(self,path:Path|None=None,*,runs:Callable[[],list[dict[str,Any]]]|None=None):
        self.path=path or VAULT/"JamesOS"/"Agency"/"registry-state.json";self.runs_loader=runs or (lambda:[])

    def _state(self)->dict[str,Any]:
        try:value=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError):value={"schema_version":1,"revision":0,"agents":{},"audit":[]}
        if value.get("schema_version")!=1:raise ValueError("Unsupported Agency state schema")
        value.setdefault("revision",0);value.setdefault("agents",{});value.setdefault("audit",[])
        legacy=value["agents"].pop("book_scout",None)
        if legacy and "jamesos.book-opportunity-scout" not in value["agents"]:value["agents"]["jamesos.book-opportunity-scout"]=legacy
        optional={"jamesos.book-opportunity-scout","jamesos.coloring-book-producer"}
        for agent_id,manifest in MANIFESTS.items():value["agents"].setdefault(agent_id,{"installed":agent_id not in optional,"enabled_state":"enabled" if agent_id not in optional else "disabled","installed_version":manifest["version"],"configuration":{},"permission_grants":list(manifest["permissions"])})
        return value

    def snapshot(self)->dict[str,Any]:
        state=self._state();runs=[self._run(item) for item in self.runs_loader() if isinstance(item,dict)];running=[item for item in runs if item["state"] in {"running","waiting for approval"}];agents=[]
        for agent_id,manifest in MANIFESTS.items():
            record=state["agents"][agent_id]
            if not record.get("installed"):continue
            agent_runs=[item for item in runs if item["agent_id"]==agent_id];current=next((item for item in agent_runs if item in running),None);runtime="waiting for approval" if current and current["waiting_for_approval"] else "running" if current else "idle"
            agents.append({"agent_id":agent_id,**deepcopy(manifest),"enabled_state":record.get("enabled_state","disabled"),"runtime_state":runtime,"update_state":"current","installed_version":record.get("installed_version"),"last_run":agent_runs[0] if agent_runs else None,"ehf_warning":False})
        catalog=[]
        for item in CATALOG:
            record=state["agents"].get(item["agent_id"],{});catalog.append({**deepcopy(item),"installed":bool(record.get("installed"))})
        return {"schema_version":1,"revision":state["revision"],"default_section":"my-agents","agents":agents,"running_now":running,"runs":runs,"approvals":[item for item in runs if item["waiting_for_approval"]],"catalog":catalog,"updates":[],"summary":{"installed_agents":len(agents),"running_now":len(running),"waiting_for_approval":sum(item["waiting_for_approval"] for item in running),"degraded_agents":sum(item["runtime_state"]=="degraded" for item in agents),"updates_available":0}}

    def details(self,agent_id:str)->dict[str,Any]:
        self._id(agent_id);snapshot=self.snapshot()
        try:agent=next(item for item in snapshot["agents"] if item["agent_id"]==agent_id)
        except StopIteration:raise LookupError("Agent is not installed")
        return {**agent,"recent_runs":[item for item in snapshot["runs"] if item["agent_id"]==agent_id],"pending_approvals":[item for item in snapshot["approvals"] if item["agent_id"]==agent_id],"dependencies":[],"available_update":None}

    def mutate(self,agent_id:str,action:str,*,confirmed:bool,revision:int)->dict[str,Any]:
        self._id(agent_id)
        if action not in {"install","enable","disable","remove"}:raise ValueError("Unsupported Agency operation")
        state=self._state()
        if revision!=state["revision"]:raise ValueError("Agency state changed; refresh before saving")
        manifest=MANIFESTS[agent_id];record=state["agents"][agent_id]
        if action=="install" and record.get("installed"):raise ValueError("Agent is already installed")
        if action!="install" and not record.get("installed"):raise LookupError("Agent is not installed")
        if action=="remove" and not manifest["removable"]:raise PermissionError("Core agents cannot be removed")
        if action=="disable" and not manifest["disable_allowed"]:raise PermissionError("Core coordination cannot be disabled")
        if not confirmed:return {"agent_id":agent_id,"action":action,"confirmation_required":True,"changed":False,"permissions":list(manifest["permissions"]),"removed":["installed agent registration","agent-local settings when selected"],"retained":["commerce jobs","drafts","product assets","EHF records","audit history","store profiles"]}
        if action=="install":record.update(installed=True,enabled_state="enabled",installed_version=manifest["version"],permission_grants=list(manifest["permissions"]))
        elif action=="remove":record.update(installed=False,enabled_state="disabled",configuration={})
        else:record["enabled_state"]="enabled" if action=="enable" else "disabled"
        state["revision"]+=1;state["audit"].append({"timestamp":datetime.now().astimezone().isoformat(),"agent_id":agent_id,"event":action,"fields":[]});state["audit"]=state["audit"][-200:];_atomic_json(self.path,state);self.path.chmod(0o600)
        return {"agent_id":agent_id,"action":action,"changed":True,"revision":state["revision"]}

    @staticmethod
    def _id(agent_id:str)->None:
        if not AGENT_ID.fullmatch(agent_id) or agent_id not in MANIFESTS:raise ValueError("Unknown agent ID")

    @staticmethod
    def _run(value:dict[str,Any])->dict[str,Any]:
        state=str(value.get("state") or value.get("status") or "completed").lower();state="waiting for approval" if state in {"waiting","waiting_for_approval","pending_approval"} else state if state in {"running","queued","paused","failed","completed","canceled"} else "completed"
        return {"run_id":str(value.get("run_id") or value.get("job_id") or ""),"agent_id":str(value.get("agent_id") or "merchant"),"operation":str(value.get("operation") or value.get("type") or "registered operation"),"related_job":str(value.get("job_id") or ""),"stage":str(value.get("stage") or state),"progress":str(value.get("progress") or ""),"started_at":value.get("started_at"),"completed_at":value.get("completed_at"),"provider_contacted":bool(value.get("provider_contacted",False)),"waiting_for_approval":state=="waiting for approval","state":state,"draft_state":str(value.get("draft_state") or "none"),"publication_state":str(value.get("publication_state") or "not_published"),"order_state":str(value.get("order_state") or "not_created"),"ehf_error":bool(value.get("ehf_error",False))}
