from jamesos.core.agents.models import *
from jamesos.core.agents.protocol import AgentDefaults


class CareerAgent(AgentDefaults):
    manifest=AgentManifest("career","CareerAgent","0.1.0","Coordinates local job discovery and application preparation",
        ("career.jobs.ingest","career.jobs.read","career.jobs.rank","career.jobs.shortlist","career.application.prepare",
         "career.application.review","career.application.approve","career.application.mark_submitted"),
        accepted_task_types=("career_work",),emitted_result_types=("career_result",),required_tool_permissions=("career.service",),
        supported_side_effects=("career.local.write",),maximum_automatic_attempts=1)
    def plan(self,request):
        if request.requested_capability=="career.application.submit":raise PermissionError("application submission is unsupported")
        dry=request.input_payload.get("dry_run",True)
        return AgentPlan(request.task_id,self.manifest.agent_id,[AgentStep("career",request.requested_capability,"Perform local career workflow",RiskLevel.READ if dry else RiskLevel.LOCAL_WRITE,"career.local.write" if not dry else None)],{"request":request,"dry_run":dry})
    def execute(self,plan,context):
        request=plan.public_summary["request"];service=context.tool_broker.acquire("career.service") if context.tool_broker else None
        if service is None:return AgentExecutionResult("planned",{"result":"career_operation_plan","capability":request.requested_capability,"write_performed":False})
        method=request.requested_capability.removeprefix("career.").replace(".","_")
        if not hasattr(service,method):raise LookupError("career capability is not bound")
        result=getattr(service,method)(**request.input_payload);wrote=bool(result.get("write_performed"))
        return AgentExecutionResult("completed",result,side_effects_attempted=["career.local.write"] if wrote else [],side_effects_completed=["career.local.write"] if wrote else [])
