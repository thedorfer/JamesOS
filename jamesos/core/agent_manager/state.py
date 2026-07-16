from __future__ import annotations
from dataclasses import asdict,dataclass,field
from datetime import datetime
import json,os,tempfile
from pathlib import Path
from jamesos.config import VAULT

STATE_PATH=VAULT/"JamesOS"/"AgentOS"/"installed-agents.json"
@dataclass
class InstalledAgent:
    agent_id:str;package_name:str;package_version:str;publisher:str;installation_source:str;installation_timestamp:str=field(default_factory=lambda:datetime.now().astimezone().isoformat())
    enabled:bool=False;manifest_hash:str="";package_hash:str|None=None;granted_permissions:dict=field(default_factory=dict);configured_profile_bindings:list[str]=field(default_factory=list)
    compatibility_status:str="compatible";trust_level:str="untrusted"
class InstalledAgentStore:
    def __init__(self,path=STATE_PATH):self.path=Path(path)
    def load(self):
        if not self.path.exists():return {}
        value=json.loads(self.path.read_text());return {item["agent_id"]:InstalledAgent(**item) for item in value.get("agents",[])}
    def save(self,agents):
        sensitive=("authorization","access_token","refresh_token","password","shared_secret","private_key")
        def inspect(value,key=""):
            if any(item in key.lower() for item in sensitive):raise ValueError("installed-agent state cannot contain secrets")
            if isinstance(value,dict):
                for child,item in value.items():inspect(item,str(child))
            elif isinstance(value,(list,tuple)):
                for item in value:inspect(item,key)
        inspect({key:asdict(item) for key,item in agents.items()})
        self.path.parent.mkdir(parents=True,exist_ok=True);payload={"schema_version":1,"agents":[asdict(item) for item in sorted(agents.values(),key=lambda x:x.agent_id)]}
        text=json.dumps(payload,indent=2,sort_keys=True)
        fd,name=tempfile.mkstemp(prefix=self.path.name+".",dir=self.path.parent)
        try:
            with os.fdopen(fd,"w") as handle:handle.write(text);handle.flush();os.fsync(handle.fileno())
            os.chmod(name,0o600);os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)
