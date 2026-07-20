"""Shared, non-agent persistence primitives for Agent OS artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def now() -> str:
    return datetime.now().astimezone().isoformat()


def canonical_sha256(value: Any) -> str:
    payload=json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()
    return sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest=sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


class AtomicDocumentStore:
    def write_json(self,path:Path,value:Any)->None:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,prefix=f".{path.name}.",suffix=".tmp",delete=False) as handle:
            json.dump(value,handle,indent=2,sort_keys=True,default=str);handle.write("\n");handle.flush();os.fsync(handle.fileno());temporary=Path(handle.name)
        temporary.replace(path)

    def write_text(self,path:Path,value:str)->None:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,prefix=f".{path.name}.",suffix=".tmp",delete=False) as handle:
            handle.write(value);handle.flush();os.fsync(handle.fileno());temporary=Path(handle.name)
        temporary.replace(path)

    def read_json(self,path:Path)->Any:
        return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class VersionedDocument:
    revision:int
    content_sha256:str

    @classmethod
    def bind(cls,revision:int,*documents:Any,names:tuple[str,...]|None=None)->"VersionedDocument":
        value={name:document for name,document in zip(names,documents)} if names else {"documents":documents}
        return cls(revision,canonical_sha256({**value,"revision":revision}))


class ApprovalService:
    def preview(self,document:VersionedDocument,message:str)->dict[str,Any]:
        return {"confirmation_required":True,"confirmation":message,"revision":document.revision,"content_hash":document.content_sha256,"external_actions":0}

    def record(self,document:VersionedDocument,*,timestamp:str|None=None)->dict[str,Any]:
        return {"state":"approved","timestamp":timestamp or now(),"revision":document.revision,"content_hash":document.content_sha256,"stale":False,"local_only":True}

    def state(self,approval:dict[str,Any]|None,document:VersionedDocument)->dict[str,Any]:
        stale=bool(approval and (approval.get("stale") is True or approval.get("revision")!=document.revision or approval.get("content_hash")!=document.content_sha256))
        return {"state":"stale" if stale else "approved" if approval else "not_approved","stale":stale}


class OperationJournal:
    def __init__(self,path:Path,documents:AtomicDocumentStore|None=None):self.path=path;self.documents=documents or AtomicDocumentStore()
    def read(self)->dict[str,Any]:
        try:return self.documents.read_json(self.path)
        except (OSError,ValueError):return {"schema_version":"1.0","operations":[]}
    def append(self,entry:dict[str,Any])->dict[str,Any]:
        value=self.read();value.setdefault("operations",[]).append(entry);self.documents.write_json(self.path,value);return entry


class AuditEventStore:
    def __init__(self,path:Path):self.path=path
    def append(self,event:dict[str,Any])->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as handle:handle.write(json.dumps(event,sort_keys=True,default=str)+"\n");handle.flush();os.fsync(handle.fileno())


class ProjectArtifactStore:
    def __init__(self,root:Path,documents:AtomicDocumentStore|None=None):self.root=root;self.documents=documents or AtomicDocumentStore()
    def project(self,project_id:str)->Path:return self.root/project_id
    def read(self,project_id:str,name:str)->Any:return self.documents.read_json(self.project(project_id)/name)
    def write(self,project_id:str,name:str,value:Any)->None:self.documents.write_json(self.project(project_id)/name,value)
    def snapshot(self,project_id:str,names:list[str])->dict[str,str]:
        root=self.project(project_id);return {name:file_sha256(root/name) for name in names if (root/name).is_file()}


def local_safety_declaration()->dict[str,Any]:
    return {"external_provider_calls":0,"images_generated":False,"pdf_generated":False,"publication_status":"not_published","purchase_status":"not_created","order_status":"not_created"}
