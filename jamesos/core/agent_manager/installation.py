from dataclasses import asdict,dataclass
@dataclass(frozen=True)
class InstallationPlan:
    action:str;agent_id:str;dry_run:bool;state_change_performed:bool;details:dict
    def to_dict(self):return asdict(self)

