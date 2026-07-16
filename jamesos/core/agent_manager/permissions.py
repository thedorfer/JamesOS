from __future__ import annotations
from dataclasses import dataclass
PERMISSION_CATEGORIES=("network_domains","filesystem_paths","secret_handles","tool_capabilities","local_writes","remote_writes","publication","destructive_actions","financial_actions","order_actions","side_effects")
@dataclass(frozen=True)
class PermissionReport:
    declared:dict;granted:dict;denied:dict
def compare_permissions(declared,granted):
    clean={key:tuple(declared.get(key,())) for key in PERMISSION_CATEGORIES if declared.get(key)}
    allowed={key:tuple(item for item in granted.get(key,()) if item in clean.get(key,())) for key in clean}
    denied={key:tuple(item for item in values if item not in allowed.get(key,())) for key,values in clean.items()}
    return PermissionReport(clean,allowed,denied)
def required_permissions_satisfied(manifest,granted):
    report=compare_permissions(manifest.declared_permissions,granted)
    return not any(report.denied.values())

