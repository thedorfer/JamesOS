class ProfileBindingResolver:
    CAPABILITY_ROLES={"marketplace.":"marketplace","commerce.product.":"fulfillment","commerce.external_":"fulfillment","commerce.workflow.":"orchestrator"}
    def __init__(self,store):self.store=store
    def agent_id_for(self,profile_id,capability):
        profile=self.store.get(profile_id)
        if not profile.enabled:raise PermissionError("profile disabled")
        role=next((role for prefix,role in self.CAPABILITY_ROLES.items() if capability.startswith(prefix)),None)
        if not role or role not in profile.agent_bindings:raise LookupError("profile capability binding missing")
        return profile.agent_bindings[role].agent_id
    def connection_handle_for(self,profile_id,capability):
        agent_id=self.agent_id_for(profile_id,capability);profile=self.store.get(profile_id)
        return next(binding.connection_handle for binding in profile.agent_bindings.values() if binding.agent_id==agent_id)
    def protected_resources_for(self,profile_id):
        return tuple(self.store.get(profile_id).protected_resources)
