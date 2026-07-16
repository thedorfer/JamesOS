from jamesos.core.agents.models import *
from jamesos.core.agents.protocol import AgentDefaults
class CommerceAgent(AgentDefaults):
    manifest=AgentManifest("commerce","CommerceAgent","0.1.0","Coordinates publish-to-inactive-review saga",("commerce.workflow.publish_to_inactive_review",),
        accepted_task_types=("commerce.workflow.publish_to_inactive_review",),emitted_result_types=("publish_to_inactive_review_plan","urgent_manual_review"),maximum_automatic_attempts=1)
    def plan(self,request):
        dry=request.input_payload.get("dry_run",True);tasks=[AgentTaskRequest("marketplace.listing.read",request.target_resources,{"dry_run":dry,"expected_title":request.input_payload.get("expected_title")},RiskLevel.READ,idempotency_key=request.idempotency_key+":etsy-ready"),
            AgentTaskRequest("commerce.product.publish",request.target_resources,{"job_id":request.input_payload["job_id"],"dry_run":dry},RiskLevel.READ if dry else RiskLevel.PUBLICATION,ApprovalRequirement(not dry,"publish-and-deactivate"),request.idempotency_key+":publish"),
            AgentTaskRequest("marketplace.listing.deactivate",{**request.target_resources,"listing_id":"$previous.etsy_listing_id"},{"dry_run":dry,"expected_title":request.input_payload.get("expected_title"),
                "printify_publication_timestamp":"$previous.printify_publication_timestamp","external_id_discovery_timestamp":"$previous.external_id_discovery_timestamp"},RiskLevel.READ if dry else RiskLevel.REMOTE_WRITE,ApprovalRequirement(not dry,"publish-and-deactivate"),request.idempotency_key+":inactive")]
        return AgentPlan(request.task_id,self.manifest.agent_id,[AgentStep("saga","commerce.workflow.publish_to_inactive_review","Coordinate via capability requests",request.risk_level)],{"dry_run":dry},tasks)
    def execute(self,plan,context):return AgentExecutionResult("planned" if plan.public_summary["dry_run"] else "coordinating",{"result":"publish_to_inactive_review_plan","write_performed":False,"task_graph":[task.requested_capability for task in plan.follow_up_tasks],"saga_failure_policy":{"possible_public_exposure":True,"automatic_republish":False,"automatic_delete":False,"automatic_unpublish":False}},follow_up_task_requests=plan.follow_up_tasks)
    def verify(self,execution,context):return AgentVerificationResult("verified",True,public_output={"saga_recorded":True})
    def handle_child_failure(self,child_request,error,last_output,context):
        if child_request.requested_capability!="marketplace.listing.deactivate":return None
        return AgentExecutionResult("urgent_manual_review",{"result":"etsy_deactivation_failed_after_publication","possible_public_exposure":True,
            "etsy_listing_id":child_request.target_resources.get("listing_id"),"urgent_manual_review_required":True,"automatic_republish":False,
            "automatic_delete":False,"automatic_unpublish":False,"order_created":False},protected_diagnostic_reference=getattr(error,"diagnostic_reference",None))
