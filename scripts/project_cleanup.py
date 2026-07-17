#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,os,shutil,subprocess,sys
from dataclasses import asdict,dataclass
from pathlib import Path
from typing import Iterable

PROTECTED_NAMES={".git",".venv","JamesOSData","Profiles","Secrets"}
CACHE_DIRS={"__pycache__",".pytest_cache",".mypy_cache",".ruff_cache","htmlcov","build","dist",".dart_tool",".gradle",".kotlin"}
CACHE_SUFFIXES={".pyc",".pyo"}
CACHE_FILES={".coverage","coverage.xml"}
BACKUP_SUFFIXES={".tmp",".temp",".bak",".orig",".swp",".swo"}

@dataclass(frozen=True)
class Candidate:
    path:str;tracked:bool;size:int;category:str;reason:str;confidence:str;references_found:list[str];recommended_action:str

def repository_root(start:Path|None=None)->Path:
    base=(start or Path(__file__).resolve().parents[1]).resolve()
    result=subprocess.run(["git","rev-parse","--show-toplevel"],cwd=base,text=True,capture_output=True,check=False)
    if result.returncode:raise ValueError("repository root could not be detected safely")
    root=Path(result.stdout.strip()).resolve()
    if not root.is_dir() or not (root/".git").exists():raise ValueError("detected repository root is invalid")
    return root

def _inside(root:Path,path:Path)->bool:
    try:path.resolve(strict=False).relative_to(root.resolve());return True
    except ValueError:return False

def _size(path:Path)->int:
    if path.is_symlink():return path.lstat().st_size
    if path.is_file():return path.stat().st_size
    total=0
    for current,dirs,files in os.walk(path,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(current)/d).is_symlink()]
        for name in files:
            item=Path(current)/name
            if not item.is_symlink():
                try:total+=item.stat().st_size
                except OSError:pass
    return total

def _tracked(root:Path)->set[str]:
    result=subprocess.run(["git","ls-files","-z"],cwd=root,capture_output=True,check=True)
    return {item.decode(errors="surrogateescape") for item in result.stdout.split(b"\0") if item}

class CleanupAudit:
    def __init__(self,root:Path,tracked:set[str]|None=None):
        self.root=root.resolve();self.tracked=_tracked(self.root) if tracked is None else set(tracked);self.unsafe=[]
        if not (self.root/".git").exists():raise ValueError("cleanup root is not a repository")
    def relative(self,path:Path)->str:return path.relative_to(self.root).as_posix()
    def is_tracked(self,path:Path)->bool:
        rel=self.relative(path);prefix=rel.rstrip("/")+"/";return rel in self.tracked or any(item.startswith(prefix) for item in self.tracked)
    def protected(self,path:Path)->bool:return any(part in PROTECTED_NAMES for part in path.relative_to(self.root).parts)
    def scan(self)->list[Candidate]:
        found=[]
        for current,dirs,files in os.walk(self.root,topdown=True,followlinks=False):
            base=Path(current);kept=[]
            for name in sorted(dirs):
                path=base/name
                if name in PROTECTED_NAMES:continue
                if path.is_symlink():
                    if name in CACHE_DIRS:self.unsafe.append(self.relative(path))
                    continue
                if name in CACHE_DIRS:
                    found.append(self._candidate(path,"cache_directory",f"known generated cache/build directory: {name}"));continue
                kept.append(name)
            dirs[:]=kept
            for name in sorted(files):
                path=base/name
                if path.is_symlink():
                    if path.suffix in CACHE_SUFFIXES or name in CACHE_FILES:self.unsafe.append(self.relative(path))
                    continue
                if path.suffix in CACHE_SUFFIXES or name in CACHE_FILES:
                    found.append(self._candidate(path,"cache_file","known generated interpreter or coverage file"))
                elif path.suffix.casefold() in BACKUP_SUFFIXES or name.endswith("~"):
                    found.append(self._candidate(path,"temporary_file","editor or temporary backup file"))
                elif path.suffix.casefold()==".log":
                    found.append(self._candidate(path,"local_log","local log should normally live outside Git",automatic=False,action="move to JamesOSData"))
                elif any(term in name.casefold() for term in ("unitystitches","unity_stitches","unity-stitches")):
                    found.append(self._candidate(path,"obsolete_private_name","legacy private deployment filename",automatic=False,action="manual review"))
                elif path.suffix.casefold() in {".png",".jpg",".jpeg",".gif",".webp",".html"} or "report" in name.casefold():
                    found.append(self._candidate(path,"repository_asset_or_report","image/report may be intentional source or generated output",automatic=False,
                        action="keep" if self.is_tracked(path) else "manual review"))
        represented={item.path for item in found}
        for current,dirs,files in os.walk(self.root,topdown=True,followlinks=False):
            base=Path(current);dirs[:]=[name for name in dirs if name not in PROTECTED_NAMES and name not in CACHE_DIRS and not (base/name).is_symlink()]
            if base==self.root or self.protected(base) or self.relative(base) in represented:continue
            try:empty=not any(base.iterdir())
            except OSError:empty=False
            if empty:found.append(self._candidate(base,"empty_directory","empty repository directory",automatic=False,action="manual review"))
        return sorted(found,key=lambda item:item.path)
    def _candidate(self,path:Path,category:str,reason:str,automatic=True,action=None)->Candidate:
        tracked=self.is_tracked(path);safe=automatic and not tracked and not self.protected(path)
        return Candidate(self.relative(path),tracked,_size(path),category,reason,"high" if safe else "medium",[],action or ("safe automatic cleanup" if safe else "keep" if tracked else "manual review"))
    def plan(self)->list[Candidate]:return [item for item in self.scan() if item.recommended_action=="safe automatic cleanup"]
    def clean(self,confirm=False)->dict:
        candidates=self.plan();planned=sum(item.size for item in candidates);removed=[];reclaimed=0
        if self.unsafe:return {"result":"unsafe_path_detected","exit_code":2,"dry_run":not confirm,"unsafe_paths":self.unsafe,"planned_deletions":[asdict(x) for x in candidates],"planned_bytes":planned,"reclaimed_bytes":0}
        if confirm:
            for item in candidates:
                path=self.root/item.path
                if not _inside(self.root,path) or self.protected(path) or self.is_tracked(path) or path.is_symlink():raise ValueError(f"unsafe cleanup target: {item.path}")
                if path.is_dir():shutil.rmtree(path)
                elif path.exists():path.unlink()
                removed.append(item.path);reclaimed+=item.size
        return {"result":"cache_cleanup_completed" if confirm else "cache_cleanup_plan","exit_code":0,"dry_run":not confirm,
            "planned_deletions":[asdict(x) for x in candidates],"planned_bytes":planned,"removed_paths":removed,"reclaimed_bytes":reclaimed}

def audit_result(audit:CleanupAudit)->dict:
    candidates=audit.scan();return {"repository_root":str(audit.root),"candidate_count":len(candidates),"estimated_removable_bytes":sum(x.size for x in candidates if x.recommended_action=="safe automatic cleanup"),
        "unsafe_paths":audit.unsafe,"candidates":[asdict(x) for x in candidates]}

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description="Audit and safely remove known generated repository caches")
    sub=parser.add_subparsers(dest="command",required=True);sub.add_parser("audit");sub.add_parser("report");clean=sub.add_parser("clean-caches");clean.add_argument("--confirm",action="store_true")
    args=parser.parse_args(argv)
    try:audit=CleanupAudit(repository_root())
    except (ValueError,subprocess.SubprocessError) as exc:print(json.dumps({"result":"unsafe_repository","error":str(exc)}));return 2
    if args.command in {"audit","report"}:result=audit_result(audit);code=2 if result["unsafe_paths"] else 0
    else:result=audit.clean(confirm=args.confirm);code=result["exit_code"]
    print(json.dumps(result,indent=2));return code
if __name__=="__main__":raise SystemExit(main())
