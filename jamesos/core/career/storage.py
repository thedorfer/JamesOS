from __future__ import annotations

import json, os, tempfile
from pathlib import Path
from typing import Any
from jamesos.config import VAULT
from .models import ApplicationProposal, NormalizedJob

CAREER_ROOT = VAULT / "JamesOS" / "Career"


class CareerStore:
    sections=("inbox","jobs","applications","evidence","reports","archive")
    def __init__(self, root: str | Path = CAREER_ROOT): self.root=Path(root)
    def _safe(self, section: str, identifier: str, suffix=".json") -> Path:
        if section not in self.sections or not identifier or Path(identifier).name != identifier or identifier in {".",".."}:
            raise ValueError("unsafe career storage path")
        return self.root/section/f"{identifier}{suffix}"
    def _write(self,path:Path,value:Any):
        path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as handle:json.dump(value,handle,indent=2,sort_keys=True);handle.write("\n");handle.flush();os.fsync(handle.fileno())
            os.chmod(name,0o600);os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
        return path
    def write_text(self,path:Path,value:str):
        path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as handle:handle.write(value);handle.flush();os.fsync(handle.fileno())
            os.chmod(name,0o600);os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
        return path
    def save_job(self,job:NormalizedJob):return self._write(self._safe("jobs",job.job_id),job.to_dict())
    def get_job(self,job_id):return NormalizedJob.from_dict(json.loads(self._safe("jobs",job_id).read_text()))
    def list_jobs(self):return [NormalizedJob.from_dict(json.loads(p.read_text())) for p in sorted((self.root/"jobs").glob("*.json"))] if (self.root/"jobs").exists() else []
    def save_application(self,app:ApplicationProposal):return self._write(self._safe("applications",app.application_id),app.to_dict())
    def get_application(self,app_id):return ApplicationProposal.from_dict(json.loads(self._safe("applications",app_id).read_text()))
    def list_applications(self):return [ApplicationProposal.from_dict(json.loads(p.read_text())) for p in sorted((self.root/"applications").glob("*.json"))] if (self.root/"applications").exists() else []
    def report_path(self):return self._safe("reports","job-search",suffix=".md")
