from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from .compatibility import compatibility
from .discovery import discover_builtin,discover_entry_points
from .installation import InstallationPlan
from .package import inspect_package,manifest_hash
from .permissions import compare_permissions,required_permissions_satisfied
from .state import InstalledAgent,InstalledAgentStore

class AgentManager:
    def __init__(self,state_store=None,ledger=None):self.state_store=state_store or InstalledAgentStore();self.ledger=ledger
    def list(self):
        states=self.state_store.load();result=[asdict(item) for item in states.values()]
        for found in discover_builtin():
            if found.agent_id not in states:result.append({"agent_id":found.agent_id,"package_name":found.package_name,"package_version":found.package_version,"publisher":"JamesOS","installation_source":"builtin","enabled":True,"compatibility_status":"compatible","trust_level":"builtin","managed_state":False})
        return sorted(result,key=lambda item:item["agent_id"])
    def info(self,agent_id):
        states=self.state_store.load()
        if agent_id in states:return asdict(states[agent_id])
        found=next(item for item in discover_builtin() if item.agent_id==agent_id)
        return next(item for item in self.list() if item["agent_id"]==found.agent_id)
    def discover(self,entry_points=None):return discover_builtin()+discover_entry_points(entry_points)
    def enabled_registry(self,profile_resolver=None):
        from jamesos.core.agents.registry import AgentRegistry
        registry=AgentRegistry(profile_resolver);states=self.state_store.load()
        for found in discover_builtin():
            state=states.get(found.agent_id)
            if found.agent is not None and (state is None or state.enabled) and (state is None or state.compatibility_status=="compatible"):registry.register(found.agent)
        return registry
    def install(self,path,confirm=False):
        inspection=inspect_package(path);states=self.state_store.load();manifest=inspection.manifest
        if manifest.agent_id in states:raise ValueError("duplicate agent ID")
        details={"source":inspection.path,"source_type":inspection.source_type,"manifest":manifest.to_dict(),"manifest_hash":manifest_hash(manifest),"package_hash":inspection.package_hash,"required_pip_command":inspection.pip_command,"pip_executed":False}
        plan=InstallationPlan("install",manifest.agent_id,not confirm,False,details)
        if confirm:
            states[manifest.agent_id]=InstalledAgent(manifest.agent_id,manifest.package_name,manifest.version,manifest.publisher,inspection.path,enabled=False,manifest_hash=details["manifest_hash"],package_hash=inspection.package_hash,compatibility_status=compatibility(manifest))
            self.state_store.save(states);plan=InstallationPlan("register",manifest.agent_id,False,True,details);self._ledger(plan)
        return plan.to_dict()
    def remove(self,agent_id,confirm=False):
        states=self.state_store.load();item=states[agent_id];details={"package_uninstall_performed":False,"package_retained":True,"profile_bindings_retained":list(item.configured_profile_bindings)}
        if confirm:item.enabled=False;states.pop(agent_id);self.state_store.save(states)
        plan=InstallationPlan("remove",agent_id,not confirm,confirm,details)
        if confirm:self._ledger(plan)
        return plan.to_dict()
    def set_enabled(self,agent_id,enabled,confirm=False):
        states=self.state_store.load();item=states[agent_id]
        if enabled and item.compatibility_status!="compatible":raise ValueError("incompatible agent")
        if confirm:item.enabled=enabled;self.state_store.save(states)
        plan=InstallationPlan("enable" if enabled else "disable",agent_id,not confirm,confirm,{"enabled":enabled,"profile_bindings_retained":list(item.configured_profile_bindings)})
        if confirm:self._ledger(plan)
        return plan.to_dict()
    def permissions(self,agent_id,manifest):return asdict(compare_permissions(manifest.declared_permissions,self.state_store.load()[agent_id].granted_permissions))
    def doctor(self,agent_id,manifest):
        item=self.state_store.load()[agent_id];return {"agent_id":agent_id,"enabled":item.enabled,"compatible":item.compatibility_status=="compatible","permissions_satisfied":required_permissions_satisfied(manifest,item.granted_permissions),"loadable":item.enabled and item.compatibility_status=="compatible" and required_permissions_satisfied(manifest,item.granted_permissions)}
    def _ledger(self,plan):
        if self.ledger:self.ledger.append({"run_id":"agent-manager","task_id":f"{plan.action}:{plan.agent_id}","agent_id":"agent-manager","capability":f"agent.lifecycle.{plan.action}","phase":"state","timestamp":datetime.now().astimezone().isoformat(),"status":"completed","side_effect_summary":["local_agent_state"]})
    def manifest_for(self,agent_id):
        state=self.state_store.load()[agent_id]
        return inspect_package(state.installation_source).manifest
