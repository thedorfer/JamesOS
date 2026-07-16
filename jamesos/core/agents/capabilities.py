class ToolBroker:
    def __init__(self,secret_provider=None):self.secret_provider=secret_provider;self._tools={}
    def register(self,capability,factory,secret_handle=None):self._tools[capability]=(factory,secret_handle)
    def acquire(self,capability,secret_handle=None):
        factory,handle=self._tools[capability];handle=secret_handle or handle;secret=self.secret_provider.resolve(handle) if handle else None
        return factory(secret)
    def scope(self,allowed,secret_handles=None):
        return ScopedToolBroker(self,set(allowed),secret_handles or {})

class ScopedToolBroker:
    def __init__(self,broker,allowed,secret_handles):self._broker,self._allowed,self._secret_handles=broker,allowed,secret_handles
    def acquire(self,capability):
        if capability not in self._allowed:raise PermissionError(f"Tool capability not allowed: {capability}")
        return self._broker.acquire(capability,self._secret_handles.get(capability))
