from datetime import datetime
from jamesos.core.structured_logging import redact
from .approvals import ApprovalPolicy
from .models import *
class AgentRunner:
    def __init__(self,registry,ledger,approval_policy=None,tool_broker=None,max_trace_depth=8):
        self.registry,self.ledger,self.approval_policy,self.tool_broker=registry,ledger,approval_policy or ApprovalPolicy(),tool_broker;self.max_trace_depth=max_trace_depth;self._keys={};self._active=[];self._capabilities=[];self._tasks=set()
    def _record(self,request,agent,phase,status,attempt=1,**extra):
        return self.ledger.append({"run_id":request.run_id,"task_id":request.task_id,"parent_task_id":request.parent_task_id,"agent_id":agent.manifest.agent_id,
            "capability":request.requested_capability,"phase":phase,"timestamp":datetime.now().astimezone().isoformat(),"status":status,
            "approval_reference":extra.pop("approval_reference",None),"idempotency_key":request.idempotency_key,"attempt_number":attempt,**redact(extra)})
    def run(self,request,approval_reference=None):
        if request.trace_depth>self.max_trace_depth:raise RuntimeError("maximum trace depth exceeded")
        if request.task_id in self._active:raise RuntimeError("agent task cycle detected")
        if request.requested_capability in self._capabilities:raise RuntimeError("agent capability cycle detected")
        if request.idempotency_key and request.idempotency_key in self._keys:return self._keys[request.idempotency_key]
        if request.task_id in self._tasks:raise RuntimeError("duplicate task detected")
        profile_id=request.input_payload.get("profile_id")
        agent=self.registry.resolve(request.requested_capability,profile_id)
        protected=set(agent.manifest.protected_resources)
        if profile_id and self.registry.profile_resolver:
            protected.update(item.split(":",2)[-1] for item in self.registry.profile_resolver.protected_resources_for(profile_id))
        if set(request.target_resources.values())&protected:raise PermissionError("protected resource")
        if request.attempt_limit>agent.manifest.maximum_automatic_attempts:raise RuntimeError("attempt limit exceeds agent policy")
        self._active.append(request.task_id);self._capabilities.append(request.requested_capability)
        try:
            secret_handles={}
            if profile_id and self.registry.profile_resolver:
                handle=self.registry.profile_resolver.connection_handle_for(profile_id,request.requested_capability)
                secret_handles={tool:handle for tool in agent.manifest.required_tool_permissions}
            broker=self.tool_broker.scope(agent.manifest.required_tool_permissions,secret_handles) if self.tool_broker else None
            context=AgentContext(approval_reference,broker,{"runner":self})
            self._record(request,agent,"discover","started");agent.discover(request);self._record(request,agent,"discover","completed")
            plan=agent.plan(request);self._record(request,agent,"plan","completed")
            if not self.approval_policy.evaluate(request,approval_reference):
                self._record(request,agent,"approval","denied");raise PermissionError("required approval missing or denied")
            self._record(request,agent,"approval","approved",approval_reference=approval_reference)
            self._tasks.add(request.task_id)
            execution=agent.execute(plan,context)
            allowed=set(agent.manifest.supported_side_effects)
            if not set(execution.side_effects_attempted+execution.side_effects_completed)<=allowed:raise PermissionError("agent emitted a disallowed side effect")
            execution.public_output=redact(execution.public_output)
            self._record(request,agent,"execute",execution.status,side_effect_summary=execution.side_effects_completed,evidence_references=execution.evidence_references,diagnostic_reference=execution.protected_diagnostic_reference)
            verification=agent.verify(execution,context);self._record(request,agent,"verify",verification.status,evidence_references=verification.evidence_references)
            proposal=agent.learn(AgentOutcome(request,execution,verification),context);self._record(request,agent,"learn","proposed" if proposal.facts else "none")
            result={"execution":execution,"verification":verification,"learning_proposal":proposal}
            last_output={};child_write_performed=False
            for index,child in enumerate(execution.follow_up_task_requests):
                targets={key:(last_output.get(value.removeprefix("$previous."),request.target_resources.get(key)) if isinstance(value,str) and value.startswith("$previous.") else value) for key,value in child.target_resources.items()}
                inputs={key:(last_output.get(value.removeprefix("$previous.")) if isinstance(value,str) and value.startswith("$previous.") else value) for key,value in child.input_payload.items()}
                child_request=AgentRequest(task_id=f"{request.task_id}.{index+1}",run_id=request.run_id,workflow_id=request.workflow_id,requested_capability=child.requested_capability,
                    requesting_agent_id=agent.manifest.agent_id,target_resources=targets,input_payload={**inputs,**({"profile_id":profile_id} if profile_id else {})},risk_level=child.risk_level,
                    approval_requirement=child.approval_requirement,idempotency_key=child.idempotency_key,attempt_limit=child.attempt_limit,parent_task_id=request.task_id,trace_depth=request.trace_depth+1)
                try:child_result=self.run(child_request,approval_reference)
                except Exception as exc:
                    handler=getattr(agent,"handle_child_failure",None)
                    if not handler:raise
                    failure=handler(child_request,exc,last_output,context)
                    if failure is None:raise
                    failure.public_output=redact(failure.public_output);failure_verification=agent.verify(failure,context)
                    self._record(request,agent,"saga_failure",failure.status,side_effect_summary=failure.side_effects_completed)
                    result={"execution":failure,"verification":failure_verification,"learning_proposal":LearningProposal()}
                    if request.idempotency_key:self._keys[request.idempotency_key]=result
                    return result
                last_output=child_result["execution"].public_output
                child_write_performed=child_write_performed or bool(last_output.get("write_performed"))
            if execution.follow_up_task_requests:
                for key,value in last_output.items():execution.public_output.setdefault(key,value)
                execution.public_output["write_performed"]=child_write_performed
            if request.idempotency_key:self._keys[request.idempotency_key]=result
            return result
        finally:self._active.remove(request.task_id);self._capabilities.remove(request.requested_capability)
