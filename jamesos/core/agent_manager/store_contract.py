from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
class PricingType(str,Enum):FREE="free";ONE_TIME="one_time";SUBSCRIPTION="subscription";PRIVATE="private"
@dataclass(frozen=True)
class AgentPublisher: publisher_id:str;display_name:str;verified:bool=False
@dataclass(frozen=True)
class AgentPricing: pricing_type:PricingType;amount_minor:int|None=None;currency:str|None=None
@dataclass(frozen=True)
class AgentRelease: version:str;manifest_hash:str;package_hash:str|None=None
@dataclass(frozen=True)
class AgentEntitlement: agent_id:str;principal_id:str;active:bool
@dataclass(frozen=True)
class AgentReview: agent_id:str;rating:int;summary:str
@dataclass(frozen=True)
class AgentSignature: algorithm:str;key_id:str;value:str
@dataclass(frozen=True)
class AgentRepository: repository_type:str;location:str;implemented:bool=False
@dataclass(frozen=True)
class AgentCatalogEntry:
    agent_id:str;publisher:AgentPublisher;releases:tuple[AgentRelease,...];pricing:AgentPricing;repository:AgentRepository|None=None;reviews:tuple[AgentReview,...]=();signatures:tuple[AgentSignature,...]=()

