from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,zipfile
from pathlib import Path
from .manifest import PackageManifest
MANIFEST_NAME="jamesos-agent.json"
@dataclass(frozen=True)
class PackageInspection:
    path:str;manifest:PackageManifest;package_hash:str|None;source_type:str;pip_command:str
def inspect_package(path):
    target=Path(path).resolve()
    if not target.exists():raise FileNotFoundError(target)
    if target.is_dir():
        manifest_path=target/MANIFEST_NAME
        if not manifest_path.is_file():raise ValueError(f"{MANIFEST_NAME} missing")
        raw=manifest_path.read_bytes();source="source_directory";package_hash=None;pip=f"python -m pip install {target}"
    elif target.suffix==".whl":
        package_hash=hashlib.sha256(target.read_bytes()).hexdigest();source="wheel";pip=f"python -m pip install {target}"
        with zipfile.ZipFile(target) as archive:
            names=[name for name in archive.namelist() if name.endswith("/"+MANIFEST_NAME) or name==MANIFEST_NAME]
            if len(names)!=1:raise ValueError("wheel must contain exactly one agent manifest")
            raw=archive.read(names[0])
    else:raise ValueError("install source must be a wheel or source directory")
    manifest=PackageManifest.from_dict(json.loads(raw));return PackageInspection(str(target),manifest,package_hash,source,pip)
def manifest_hash(manifest):return hashlib.sha256(json.dumps(manifest.to_dict(),sort_keys=True,default=list,separators=(",",":")).encode()).hexdigest()

