from __future__ import annotations

import json, re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class JobSourceAdapter(Protocol):
    def parse(self, source: str | Path | dict[str, Any], **metadata) -> list[dict[str, Any]]: ...


def canonicalize_url(value: str | None) -> str | None:
    if not value:return None
    parts=urlsplit(value.strip());
    if parts.scheme not in {"http","https"} or not parts.netloc:return None
    query=urlencode(sorted((k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True) if not k.casefold().startswith(("utm_","trk","tracking"))))
    return urlunsplit((parts.scheme.casefold(),parts.netloc.casefold(),parts.path.rstrip("/") or "/",query,""))


def _text(source):return Path(source).read_text(encoding="utf-8") if isinstance(source,Path) else str(source)
def _field(text,label):
    match=re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$",text);return match.group(1).strip() if match else None
def _url(text):
    match=re.search(r"https?://[^\s<>\])]+",text);return match.group(0).rstrip(".,") if match else None
def _provider(text):
    lower=text.casefold()
    for name in ("linkedin","indeed","dice","monster"):
        if name in lower:return name
    return "recruiter" if re.search(r"(?i)recruiter|staffing|opportunity",text) else "email"


class EmailJobAlertAdapter:
    def parse(self,source,**metadata):
        text=_text(source);salary=re.search(r"(?i)(?:USD\s*)?\$?([\d,]+)\s*(?:-|to)\s*\$?([\d,]+)",text)
        setting=next((x for x in ("remote","hybrid","onsite") if re.search(rf"(?i)\b{x}\b",text)),None)
        return [{"source":_provider(text),"title":_field(text,"title") or _field(text,"job"),"company":_field(text,"company"),
            "location":_field(text,"location"),"work_setting":setting,"salary_min":int(salary.group(1).replace(',','')) if salary else None,
            "salary_max":int(salary.group(2).replace(',','')) if salary else None,"salary_currency":"USD" if salary else None,
            "source_url":_url(text),"source_job_id":_field(text,"job id"),"date_posted":_field(text,"date posted"),
            "date_received":metadata.get("date_received") or _field(text,"date received"),"description":_field(text,"description") or text[:2000],
            "source_evidence":{"kind":"local_email_text","sha256_only":True}}]


class ManualJobAdapter:
    def parse(self,source,**metadata):
        if isinstance(source,dict):values=[source]
        elif isinstance(source,Path) and source.suffix.casefold()==".json":
            loaded=json.loads(source.read_text(encoding="utf-8"));values=loaded if isinstance(loaded,list) else [loaded]
        else:
            text=_text(source);values=[{"title":_field(text,"title"),"company":_field(text,"company"),"location":_field(text,"location"),
                "description":text,"source_url":metadata.get("url") or _url(text),**{k:v for k,v in metadata.items() if k!="url"}}]
        return [{"source":"manual",**value,"source_evidence":{"kind":"manual_input","sha256_only":True,**(value.get("source_evidence") or {})}} for value in values]


class EmployerCareerAdapter(ABC):
    @abstractmethod
    def records(self)->list[dict[str,Any]]:raise NotImplementedError
    def parse(self,source=None,**metadata):return [{"source":"employer_career_fixture",**row} for row in self.records()]


class GenericATSAdapter:
    def parse(self,source,**metadata):
        rows=source if isinstance(source,list) else [source]
        return [{"source":str(row.get("provider") or "generic_ats").casefold(),"source_job_id":row.get("id") or row.get("job_id"),
            "source_url":row.get("absolute_url") or row.get("url"),"title":row.get("title"),"company":row.get("company"),
            "location":row.get("location"),"description":row.get("description"),"date_posted":row.get("created_at") or row.get("date_posted"),
            "source_evidence":{"kind":"fixture_record","sha256_only":True}} for row in rows]
