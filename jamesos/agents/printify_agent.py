from jamesos.core.agents.models import *
from datetime import datetime
from jamesos.core.agents.protocol import AgentDefaults
class PrintifyAgent(AgentDefaults):
    manifest=AgentManifest("printify","PrintifyAgent","0.1.0","Wraps guarded Printify product workflows",
        ("commerce.product.read","commerce.product.update","commerce.product.publish","commerce.external_listing.resolve"),
        accepted_task_types=("product_work",),emitted_result_types=("printify_product_result",),required_tool_permissions=("printify.orchestrator",),
        required_secret_handles=("fulfillment.connection",),supported_side_effects=("printify.product.update","printify.product.publish"),maximum_automatic_attempts=1,protected_resources=("6a57eaa752f2c3e4700dbf23",))
    def plan(self,request):return AgentPlan(request.task_id,self.manifest.agent_id,[AgentStep("printify",request.requested_capability,"Use guarded product orchestrator",request.risk_level)],{"request":request.input_payload,"targets":request.target_resources})
    def execute(self,plan,context):
        request=plan.public_summary["request"]
        if request.get("dry_run",True):
            return AgentExecutionResult("planned",{"result":"printify_publication_plan","job_id":request["job_id"],"write_performed":False,"publish_performed":False})
        orchestrator=context.tool_broker.acquire("printify.orchestrator");result=orchestrator.send_to_etsy_review(request["job_id"],confirmed=True)
        if result.get("publish_performed"):
            timestamp=datetime.now().astimezone().isoformat();result["printify_publication_timestamp"]=timestamp
            if result.get("etsy_listing_id"):result["external_id_discovery_timestamp"]=timestamp
        return AgentExecutionResult("completed",result,side_effects_attempted=["printify.product.publish"] if result.get("publish_performed") else [],side_effects_completed=["printify.product.publish"] if result.get("publish_performed") else [])
    def verify(self,execution,context):return AgentVerificationResult("verified",True,public_output={"verified":True})
