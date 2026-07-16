from .models import CapabilityMatch
class AgentRegistry:
    def __init__(self,profile_resolver=None):self._agents={};self.profile_resolver=profile_resolver
    def register(self,agent):
        if agent.manifest.agent_id in self._agents:raise ValueError("duplicate agent_id")
        self._agents[agent.manifest.agent_id]=agent;return agent
    def find_capability(self,capability):
        return [CapabilityMatch(a.manifest.agent_id,a.manifest.name,a.manifest.version,capability) for a in self._agents.values() if capability in a.manifest.capabilities]
    def resolve(self,capability,profile_id=None):
        matches=self.find_capability(capability)
        if profile_id and self.profile_resolver:
            bound=self.profile_resolver.agent_id_for(profile_id,capability);matches=[item for item in matches if item.agent_id==bound]
        if len(matches)!=1:raise LookupError(f"Expected one agent for {capability}; found {len(matches)}")
        return self._agents[matches[0].agent_id]
    def get(self,agent_id):return self._agents[agent_id]
