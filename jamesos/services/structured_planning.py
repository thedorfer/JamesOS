"""Reusable structured-plan provider boundary; providers do not own workflows."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Protocol


class StructuredPlanProvider(Protocol):
    provider_id:str
    def propose(self,request:dict[str,Any])->dict[str,Any]:...


@dataclass(frozen=True)
class DeterministicPlanProvider:
    provider_id:str="deterministic-plan-v1"
    def propose(self,request:dict[str,Any])->dict[str,Any]:
        topics=request.get("topics") or []
        count=int(request.get("count") or len(topics))
        items=[{"position":index+1,"topic":str(topic),"source":"deterministic_input"} for index,topic in enumerate(topics[:count])]
        return {"provider_id":self.provider_id,"status":"candidate","items":items,"external_provider_calls":0}


class OllamaPlanProvider(Protocol):
    """Future local adapter contract. No implementation or network call here."""
    provider_id:str
    def propose(self,request:dict[str,Any])->dict[str,Any]:...
