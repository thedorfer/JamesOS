from jamesos.core.agents.models import AgentExecutionResult,AgentManifest,AgentPlan,AgentStep,AgentVerificationResult
from jamesos.core.agents.protocol import AgentDefaults
class HelloAgent(AgentDefaults):
    manifest=AgentManifest("hello","Hello Agent","1.0.0","Harmless read-only example",("example.hello.read",),accepted_task_types=("hello_request",),emitted_result_types=("hello_result",),owner="JamesOS Examples")
    def plan(self,request):return AgentPlan(request.task_id,"hello",[AgentStep("hello","example.hello.read","Return a local greeting")],{"name":request.input_payload.get("name","world")})
    def execute(self,plan,context):return AgentExecutionResult("completed",{"result":"hello","message":f"Hello, {plan.public_summary['name']}!","write_performed":False})
    def verify(self,execution,context):return AgentVerificationResult("verified",True)

