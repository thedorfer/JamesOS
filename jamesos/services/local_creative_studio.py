"""Agent OS capability contract for reusable local creative providers."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any,Protocol


@dataclass(frozen=True)
class LocalAssetRequest:
    request_id:str
    capability:str
    owner_agent_id:str
    owner_object_id:str
    specification:dict[str,Any]
    source_artifact_sha256:str|None=None
    constraints:dict[str,Any]=field(default_factory=dict)


@dataclass(frozen=True)
class LocalAssetResult:
    request_id:str
    status:str
    artifacts:tuple[dict[str,Any],...]=()
    provider_id:str="none"
    external_provider_calls:int=0
    warnings:tuple[str,...]=()


class LocalCreativeStudioProvider(Protocol):
    provider_id:str
    capabilities:frozenset[str]
    def readiness(self)->dict[str,Any]:...
    def execute(self,request:LocalAssetRequest)->LocalAssetResult:...


class BlankModelTemplateProvider(Protocol):
    """Single future boundary for local blank-template generation, including ComfyUI."""
    provider_id:str
    def create_blank_template(self,request:LocalAssetRequest)->LocalAssetResult:...
