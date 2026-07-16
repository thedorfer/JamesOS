from __future__ import annotations
import json,os,tempfile
from pathlib import Path
from jamesos.config import VAULT
from .models import Profile,now
from .validation import validate_profile
ROOT=VAULT/"JamesOS"/"Profiles"
class ProfileStore:
    def __init__(self,root=ROOT):self.root=Path(root)
    def path(self,profile_id):return self.root/f"{profile_id}.json"
    def list(self):return [Profile.from_dict(json.loads(path.read_text())) for path in sorted(self.root.glob("*.json"))] if self.root.exists() else []
    def get(self,profile_id):return Profile.from_dict(json.loads(self.path(profile_id).read_text()))
    def save(self,profile):
        validate_profile(profile);profile.updated_at=now();self.root.mkdir(parents=True,exist_ok=True);path=self.path(profile.profile_id)
        fd,name=tempfile.mkstemp(prefix=path.name+".",dir=self.root)
        try:
            with os.fdopen(fd,"w") as handle:json.dump(profile.to_dict(),handle,indent=2,sort_keys=True);handle.flush();os.fsync(handle.fileno())
            os.chmod(name,0o600);os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
        return path

