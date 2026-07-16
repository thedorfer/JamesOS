from jamesos.core.agents.models import *
from datetime import datetime
from jamesos.core.agents.protocol import AgentDefaults
class EtsyAgent(AgentDefaults):
    manifest=AgentManifest("etsy","EtsyAgent","0.1.0","Owns Etsy listing reads and inactive transitions",
        ("marketplace.listing.read","marketplace.listing.deactivate","marketplace.listing.verify_state"),
        accepted_task_types=("listing_read","listing_state_transition"),emitted_result_types=("etsy_listing_result",),required_tool_permissions=("etsy.client",),
        required_secret_handles=("marketplace.connection",),supported_side_effects=("etsy.listing.inactive",),maximum_automatic_attempts=1)
    def plan(self,request):
        action="deactivate" if request.requested_capability=="marketplace.listing.deactivate" else "read"
        return AgentPlan(request.task_id,self.manifest.agent_id,[AgentStep("read","marketplace.listing.read","Read and verify Etsy listing"),*( [AgentStep("inactive","marketplace.listing.deactivate","Set active listing inactive",RiskLevel.REMOTE_WRITE,"etsy.listing.inactive")] if action=="deactivate" else [])],{"action":action,"request":request.input_payload,"targets":request.target_resources})
    def execute(self,plan,context):
        data=plan.public_summary;listing_id=int(data["targets"]["listing_id"]);dry=bool(data["request"].get("dry_run",True))
        if dry:return AgentExecutionResult("planned",{"result":"etsy_deactivation_plan","listing_id":listing_id,"etsy_listing_id":listing_id,"write_performed":False,"target_state":"inactive"})
        client=context.tool_broker.acquire("etsy.client");listing=client.get_listing(listing_id)
        if int(listing.get("listing_id",listing_id))!=listing_id:raise ValueError("Etsy listing ownership mismatch")
        shop_id=int(listing["shop_id"]);expected=data["request"].get("expected_title")
        if expected and listing.get("title")!=expected:raise ValueError("Etsy listing title mismatch")
        if data["action"]=="read":return AgentExecutionResult("completed",{"result":"etsy_listing_readiness_verified","listing_id":listing_id,"etsy_listing_id":listing_id,"shop_id":shop_id,"state":listing.get("state"),"write_performed":False},verification_status="verified")
        if listing.get("state")=="inactive":return AgentExecutionResult("completed",{"result":"etsy_listing_already_inactive","listing_id":listing_id,"etsy_listing_id":listing_id,"shop_id":shop_id,"state":"inactive","write_performed":False},verification_status="verified")
        if listing.get("state")!="active":raise ValueError("Only active Etsy listings may be deactivated")
        requested=datetime.now().astimezone();client.update_listing_state(shop_id,listing_id,"inactive");output={"result":"etsy_listing_deactivated","listing_id":listing_id,"etsy_listing_id":listing_id,"shop_id":shop_id,"state":"inactive","write_performed":True,
            "etsy_deactivation_request_timestamp":requested.isoformat(),"printify_publication_timestamp":data["request"].get("printify_publication_timestamp"),"external_id_discovery_timestamp":data["request"].get("external_id_discovery_timestamp")}
        return AgentExecutionResult("completed",output,side_effects_attempted=["etsy.listing.inactive"],side_effects_completed=["etsy.listing.inactive"])
    def verify(self,execution,context):
        if execution.public_output.get("write_performed"):
            listing=context.tool_broker.acquire("etsy.client").get_listing(execution.public_output["listing_id"]);ok=listing.get("state")=="inactive";verified=datetime.now().astimezone();execution.public_output["etsy_inactive_verification_timestamp"]=verified.isoformat()
            publication=execution.public_output.get("printify_publication_timestamp")
            if publication:
                try:execution.public_output["public_exposure_window_seconds"]=max(.001,(verified-datetime.fromisoformat(publication)).total_seconds())
                except ValueError:pass
        else:ok=True
        return AgentVerificationResult("verified" if ok else "failed",ok,public_output={"state":"inactive" if ok else "unknown"})
