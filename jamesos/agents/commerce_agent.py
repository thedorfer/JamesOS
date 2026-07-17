from jamesos.core.agents.models import *
from jamesos.core.agents.protocol import AgentDefaults
from jamesos.core.profiles.selection import selected_profile_id
class CommerceAgent(AgentDefaults):
    manifest=AgentManifest("commerce","CommerceAgent","0.1.0","Coordinates profile-selected final publication workflows",("commerce.workflow.publish_to_inactive_review","commerce.workflow.publish_active_after_approval"),
        accepted_task_types=("commerce.workflow.publish_to_inactive_review","commerce.workflow.publish_active_after_approval"),emitted_result_types=("publish_to_inactive_review_plan","publish_active_after_approval_plan","urgent_manual_review"),maximum_automatic_attempts=1)
    def plan(self,request):
        dry=request.input_payload.get("dry_run",True);active=request.requested_capability=="commerce.workflow.publish_active_after_approval";profile_id=request.input_payload.get("profile_id") or selected_profile_id()
        scope="final-proposal" if active else "publish-and-deactivate";proposal_sha=request.input_payload.get("proposal_sha256") if active else None
        if active and not proposal_sha:raise ValueError("single-final publication requires a complete proposal hash")
        tasks=[AgentTaskRequest("commerce.product.publish",request.target_resources,{"job_id":request.input_payload["job_id"],"dry_run":dry,"profile_id":profile_id},RiskLevel.READ if dry else RiskLevel.PUBLICATION,ApprovalRequirement(not dry,"publish-and-deactivate"),request.idempotency_key+":publish"),
            AgentTaskRequest("marketplace.listing.verify_state" if active else "marketplace.listing.deactivate",{**request.target_resources,"listing_id":"$previous.etsy_listing_id"},{"dry_run":dry,"expected_title":request.input_payload.get("expected_title"),"expected_state":"active",
                "printify_publication_timestamp":"$previous.printify_publication_timestamp","external_id_discovery_timestamp":"$previous.external_id_discovery_timestamp"},RiskLevel.READ if dry else RiskLevel.REMOTE_WRITE,ApprovalRequirement(not dry,"publish-and-deactivate"),request.idempotency_key+":inactive")]
        if not active:tasks.insert(0,AgentTaskRequest("marketplace.listing.read",request.target_resources,{"dry_run":dry,"expected_title":request.input_payload.get("expected_title")},RiskLevel.READ,idempotency_key=request.idempotency_key+":etsy-ready"))
        publish_index=0 if active else 1;final_index=1 if active else 2
        tasks[publish_index].approval_requirement=ApprovalRequirement(not dry,scope,proposal_sha)
        if active:
            tasks[final_index].risk_level=RiskLevel.READ;tasks[final_index].approval_requirement=ApprovalRequirement(False,"");tasks[final_index].idempotency_key=request.idempotency_key+":verify-active"
        else:tasks[final_index].approval_requirement=ApprovalRequirement(not dry,scope)
        return AgentPlan(request.task_id,self.manifest.agent_id,[AgentStep("saga",request.requested_capability,"Coordinate via capability requests",request.risk_level)],{"dry_run":dry,"active":active},tasks)
    def execute(self,plan,context):
        active=plan.public_summary["active"]
        return AgentExecutionResult("planned" if plan.public_summary["dry_run"] else "coordinating",{"result":"publish_active_after_approval_plan" if active else "publish_to_inactive_review_plan","write_performed":False,"task_graph":[task.requested_capability for task in plan.follow_up_tasks],"expected_final_state":"active" if active else "inactive","saga_failure_policy":{"possible_public_exposure":not active,"automatic_republish":False,"automatic_delete":False,"automatic_unpublish":False}},follow_up_task_requests=plan.follow_up_tasks)
    def verify(self,execution,context):return AgentVerificationResult("verified",True,public_output={"saga_recorded":True})
    def handle_child_failure(self,child_request,error,last_output,context):
        if child_request.requested_capability!="marketplace.listing.deactivate":return None
        return AgentExecutionResult("urgent_manual_review",{"result":"etsy_deactivation_failed_after_publication","possible_public_exposure":True,
            "etsy_listing_id":child_request.target_resources.get("listing_id"),"urgent_manual_review_required":True,"automatic_republish":False,
            "automatic_delete":False,"automatic_unpublish":False,"order_created":False},protected_diagnostic_reference=getattr(error,"diagnostic_reference",None))
