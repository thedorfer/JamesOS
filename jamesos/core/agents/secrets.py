import json
from pathlib import Path
class SecretProvider:
    def __init__(self,handles):self.handles={key:Path(value) for key,value in handles.items()}
    def status(self,handle):
        path=self.handles.get(handle);return {"configured":bool(path and path.is_file()),"permissions_valid":bool(path and path.is_file() and path.stat().st_mode&0o777==0o600)}
    def resolve(self,handle):
        path=self.handles[handle]
        if not path.is_file() or path.stat().st_mode&0o777!=0o600:raise PermissionError(f"Secret handle {handle} unavailable")
        return json.loads(path.read_text())

