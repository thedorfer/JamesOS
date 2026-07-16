import re
from .models import Profile
ID=re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
SENSITIVE=("token","password","secret_value","authorization","shared_secret","access_token","refresh_token")
def validate_profile(profile:Profile):
    if profile.schema_version!=1:raise ValueError("unsupported profile schema")
    if not ID.fullmatch(profile.profile_id):raise ValueError("invalid profile ID")
    if profile.profile_type not in ("commerce_shop",):raise ValueError("unsupported profile type")
    if not profile.owner or not profile.display_name:raise ValueError("owner and display name required")
    def walk(value,key=""):
        if any(item in key.lower() for item in SENSITIVE):raise ValueError("profile contains a secret value field")
        if isinstance(value,dict):
            for child,item in value.items():walk(item,str(child))
        elif isinstance(value,(list,tuple)):
            for item in value:walk(item,key)
    walk(profile.to_dict());return profile

