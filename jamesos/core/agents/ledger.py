import json,os
from pathlib import Path
from uuid import uuid4
from jamesos.config import VAULT
from jamesos.core.structured_logging import redact
class RunLedger:
    def __init__(self,path=None):self.path=Path(path or VAULT/"JamesOS"/"AgentOS"/"run-ledger.jsonl")
    def append(self,entry):
        self.path.parent.mkdir(parents=True,exist_ok=True);safe=redact(entry)
        line=json.dumps(safe,sort_keys=True,default=str)+"\n"
        with self.path.open("a",encoding="utf-8") as handle:handle.write(line);handle.flush();os.fsync(handle.fileno())
        return f"ledger:{self.path.name}:{uuid4().hex[:8]}"
    def read(self):return [json.loads(line) for line in self.path.read_text().splitlines()] if self.path.exists() else []

