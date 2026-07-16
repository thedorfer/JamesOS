from __future__ import annotations
import unittest
from jamesos.core.agents.models import AgentContext,AgentRequest,RiskLevel
from jamesos.core.agent_manager.manifest import PackageManifest,validate_manifest
class MockSecretProvider:
    def __init__(self,values=None):self.values=values or {};self.resolved=[]
    def resolve(self,handle):self.resolved.append(handle);return self.values[handle]
class MockToolBroker:
    def __init__(self,tools=None):self.tools=tools or {};self.acquired=[]
    def acquire(self,capability):self.acquired.append(capability);return self.tools[capability]
class MockAgentContext(AgentContext):
    def __init__(self,tools=None):super().__init__(tool_broker=MockToolBroker(tools))
def fixture_request(capability="example.hello.read",profile_id=None):return AgentRequest("fixture-task","fixture-run","fixture-workflow",capability,"conformance",input_payload={"profile_id":profile_id} if profile_id else {},risk_level=RiskLevel.READ,idempotency_key="fixture-key")
class AgentConformanceTestCase(unittest.TestCase):
    agent=None;package_manifest:PackageManifest|None=None
    def test_manifest_conforms(self):self.assertIsNotNone(self.package_manifest);validate_manifest(self.package_manifest)
    def test_capabilities_match(self):self.assertEqual(set(self.agent.manifest.capabilities),set(self.package_manifest.capabilities))
    def test_read_plan_is_serializable(self):self.assertIsNotNone(self.agent.plan(fixture_request(self.package_manifest.capabilities[0])))

