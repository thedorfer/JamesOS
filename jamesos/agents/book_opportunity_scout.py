from __future__ import annotations

from jamesos.core.agents.models import AgentExecutionResult,AgentManifest,AgentPlan,AgentStep,AgentVerificationResult,LearningProposal,RiskLevel
from jamesos.core.agents.protocol import AgentDefaults
from jamesos.services.book_opportunity_scout import BookOpportunityScoutService


class BookOpportunityScoutAgent(AgentDefaults):
    manifest=AgentManifest("jamesos.book-opportunity-scout","Book Opportunity Scout","0.1.0","Researches and deterministically ranks local book opportunities",("books.opportunity.research","books.opportunity.decide"),("book_opportunity_research_request",),("book_opportunity_research_result",),(),(),("local_research_artifacts","local_candidate_decision"),"stable_key",1,(),"JamesOS")
    def __init__(self,service:BookOpportunityScoutService|None=None):self.service=service or BookOpportunityScoutService()
    def discover(self,request):return {"accepted":request.requested_capability=="books.opportunity.research"}
    def plan(self,request):
        if request.requested_capability!="books.opportunity.research":raise ValueError("unsupported scout capability")
        names=("Validate request","Generate candidate concepts","Collect research evidence","Normalize evidence","Run risk analysis","Calculate deterministic scores","Rank candidates","Generate recommendation summaries","Verify evidence and output","Save the local report")
        return AgentPlan(request.task_id,self.manifest.agent_id,[AgentStep(f"step-{index+1}",request.requested_capability,name,RiskLevel.LOCAL_WRITE,"local_research_artifacts" if index==9 else None) for index,name in enumerate(names)],{"request":request.input_payload,"execution_mode":"local_in_process"})
    def execute(self,plan,context):
        result=self.service.run(plan.public_summary["request"]);return AgentExecutionResult(result["status"],result,evidence_references=[result["local_report_reference"]],side_effects_attempted=["local_research_artifacts"],side_effects_completed=["local_research_artifacts"])
    def verify(self,execution,context):
        value=self.service.verify(execution.public_output);return AgentVerificationResult(value["status"],value["verified"],execution.evidence_references,value)
    def learn(self,outcome,context):return LearningProposal("books.opportunity.scout",{"proposal":"Review accepted and rejected concepts to refine a future scoring profile."},.3,False)
