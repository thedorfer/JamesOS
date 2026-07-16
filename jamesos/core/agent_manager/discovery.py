from __future__ import annotations
from dataclasses import dataclass
from importlib import metadata
from jamesos.agents import CommerceAgent,EtsyAgent,PrintifyAgent
@dataclass(frozen=True)
class DiscoveredAgent:
    agent_id:str;source:str;entry_point:str;package_name:str;package_version:str;agent:object|None=None
def discover_builtin():return [DiscoveredAgent(a.manifest.agent_id,"builtin",f"{a.__class__.__module__}:{a.__class__.__name__}","jamesos","0.1.0",a) for a in (CommerceAgent(),PrintifyAgent(),EtsyAgent())]
def discover_entry_points(entry_points=None):
    points=entry_points if entry_points is not None else metadata.entry_points()
    selected=points.select(group="jamesos.agents") if hasattr(points,"select") else points.get("jamesos.agents",())
    result=[]
    for point in selected:
        distribution=getattr(point,"dist",None);name=getattr(distribution,"name","") or "unknown";version=getattr(distribution,"version","") or "unknown"
        result.append(DiscoveredAgent(point.name,"entry_point",point.value,name,version,None))
    return result

