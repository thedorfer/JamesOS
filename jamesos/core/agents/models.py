from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

def now() -> str:return datetime.now().astimezone().isoformat()
class RiskLevel(str,Enum):
    READ="read";LOCAL_WRITE="local_write";REMOTE_WRITE="remote_write";PUBLICATION="publication";DESTRUCTIVE="destructive";FINANCIAL="financial";ORDER="order"
@dataclass(frozen=True)
class ApprovalRequirement:
    required: bool=False;scope: str="";reference: str|None=None
@dataclass(frozen=True)
class AgentManifest:
    agent_id:str;name:str;version:str;description:str;capabilities:tuple[str,...];accepted_task_types:tuple[str,...]=();emitted_result_types:tuple[str,...]=()
    required_tool_permissions:tuple[str,...]=();required_secret_handles:tuple[str,...]=();supported_side_effects:tuple[str,...]=();idempotency_behavior:str="stable_key"
    maximum_automatic_attempts:int=1;protected_resources:tuple[str,...]=();owner:str="JamesOS"
@dataclass
class AgentRequest:
    task_id:str;run_id:str;workflow_id:str;requested_capability:str;requesting_agent_id:str;target_resources:dict[str,Any]=field(default_factory=dict)
    input_payload:dict[str,Any]=field(default_factory=dict);risk_level:RiskLevel=RiskLevel.READ;approval_requirement:ApprovalRequirement=field(default_factory=ApprovalRequirement)
    idempotency_key:str="";attempt_limit:int=1;created_timestamp:str=field(default_factory=now);parent_task_id:str|None=None;trace_depth:int=0
@dataclass
class AgentStep:
    step_id:str;capability:str;description:str;risk_level:RiskLevel=RiskLevel.READ;side_effect:str|None=None
@dataclass
class AgentPlan:
    task_id:str;agent_id:str;steps:list[AgentStep]=field(default_factory=list);public_summary:dict[str,Any]=field(default_factory=dict);follow_up_tasks:list["AgentTaskRequest"]=field(default_factory=list)
@dataclass
class AgentTaskRequest:
    requested_capability:str;target_resources:dict[str,Any]=field(default_factory=dict);input_payload:dict[str,Any]=field(default_factory=dict);risk_level:RiskLevel=RiskLevel.READ
    approval_requirement:ApprovalRequirement=field(default_factory=ApprovalRequirement);idempotency_key:str="";attempt_limit:int=1
@dataclass
class AgentExecutionResult:
    status:str;public_output:dict[str,Any]=field(default_factory=dict);protected_diagnostic_reference:str|None=None;evidence_references:list[str]=field(default_factory=list)
    side_effects_attempted:list[str]=field(default_factory=list);side_effects_completed:list[str]=field(default_factory=list);verification_status:str="pending";follow_up_task_requests:list[AgentTaskRequest]=field(default_factory=list)
@dataclass
class AgentVerificationResult:
    status:str;verified:bool;evidence_references:list[str]=field(default_factory=list);public_output:dict[str,Any]=field(default_factory=dict)
@dataclass
class LearningProposal:
    namespace:str="";facts:dict[str,Any]=field(default_factory=dict);confidence:float=0.0;persist:bool=False
@dataclass
class AgentOutcome:
    request:AgentRequest;execution:AgentExecutionResult;verification:AgentVerificationResult
@dataclass
class CapabilityQuery: capability:str
@dataclass(frozen=True)
class CapabilityMatch: agent_id:str;name:str;version:str;capability:str
@dataclass
class AgentContext:
    approval_reference:str|None=None;tool_broker:Any=None;metadata:dict[str,Any]=field(default_factory=dict)
def serializable(value:Any)->Any:
    if hasattr(value,"__dataclass_fields__"):return {k:serializable(v) for k,v in asdict(value).items()}
    if isinstance(value,Enum):return value.value
    if isinstance(value,dict):return {str(k):serializable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [serializable(v) for v in value]
    return value

