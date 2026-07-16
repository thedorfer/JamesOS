from __future__ import annotations
from dataclasses import asdict,dataclass,field
from datetime import datetime
from typing import Any
def now():return datetime.now().astimezone().isoformat()
@dataclass(frozen=True)
class AgentBinding:
    agent_id:str;connection_handle:str|None=None
@dataclass
class Profile:
    profile_id:str;profile_type:str;display_name:str;owner:str;enabled:bool=True;tags:list[str]=field(default_factory=list);policy_id:str="default"
    agent_bindings:dict[str,AgentBinding]=field(default_factory=dict);secret_handle_bindings:dict[str,str]=field(default_factory=dict);configuration:dict[str,Any]=field(default_factory=dict)
    protected_resources:list[str]=field(default_factory=list);created_at:str=field(default_factory=now);updated_at:str=field(default_factory=now);schema_version:int=1
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,value):
        data=dict(value);data["agent_bindings"]={key:(item if isinstance(item,AgentBinding) else AgentBinding(**item)) for key,item in data.get("agent_bindings",{}).items()};return cls(**data)

