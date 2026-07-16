from __future__ import annotations
import base64,hashlib,json,secrets,time
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlencode
import requests
from jamesos.config import VAULT
APP_PATH=VAULT/"JamesOS"/"Secrets"/"etsy-app.json";TOKEN_PATH=VAULT/"JamesOS"/"Secrets"/"etsy-oauth.json";PENDING_PATH=VAULT/"JamesOS"/"Secrets"/"etsy-oauth-pending.json"
AUTHORIZE_URL="https://www.etsy.com/oauth/connect";TOKEN_URL="https://api.etsy.com/v3/public/oauth/token";SCOPES=("listings_r","listings_w");PENDING_TTL=600
def _read(path):
    if not path.is_file() or path.stat().st_mode&0o777!=0o600:raise PermissionError(path)
    return json.loads(path.read_text())
def _write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2));path.chmod(0o600)
def start(app_path=APP_PATH,pending_path=PENDING_PATH,now=None):
    app=_read(Path(app_path));state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)[:96];challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    pending={"state":state,"verifier":verifier,"created_at":now or int(time.time()),"redirect_uri":app["redirect_uri"],"used":False};_write(Path(pending_path),pending)
    query=urlencode({"response_type":"code","redirect_uri":app["redirect_uri"],"scope":" ".join(SCOPES),"client_id":app["keystring"],"state":state,"code_challenge":challenge,"code_challenge_method":"S256"})
    return {"result":"etsy_oauth_authorization_required","authorization_url":f"{AUTHORIZE_URL}?{query}","scopes":list(SCOPES),"pkce_method":"S256"}
def complete(callback_url,app_path=APP_PATH,pending_path=PENDING_PATH,token_path=TOKEN_PATH,session=None,now=None):
    app=_read(Path(app_path));pending=_read(Path(pending_path));current=now or int(time.time());callback=urlsplit(callback_url);registered=urlsplit(app["redirect_uri"])
    if pending.get("used") or current-pending["created_at"]>PENDING_TTL:raise ValueError("OAuth state expired or used")
    if (callback.scheme,callback.netloc,callback.path)!=(registered.scheme,registered.netloc,registered.path) or callback.scheme!="https":raise ValueError("OAuth redirect URI mismatch")
    values=parse_qs(callback.query)
    if values.get("state",[None])[0]!=pending["state"]:raise ValueError("OAuth state mismatch")
    code=values.get("code",[None])[0]
    if not code:raise ValueError("OAuth code missing")
    response=(session or requests).post(TOKEN_URL,data={"grant_type":"authorization_code","client_id":app["keystring"],"redirect_uri":app["redirect_uri"],"code":code,"code_verifier":pending["verifier"]},timeout=(10,45));response.raise_for_status();token=response.json()
    scopes=set(str(token.get("scope") or "").split())
    if not set(SCOPES)<=scopes:raise ValueError("Required Etsy scopes missing")
    stored={**token,"issued_at":current,"expires_at":current+int(token.get("expires_in",3600)),"refresh_expires_at":current+90*86400,"scopes":sorted(scopes)};_write(Path(token_path),stored)
    pending["used"]=True;_write(Path(pending_path),pending);Path(pending_path).unlink()
    return {"result":"etsy_oauth_authorized","required_scopes_present":True,"ready_for_etsy_read":True,"ready_for_etsy_write":True}
def status(app_path=APP_PATH,token_path=TOKEN_PATH,now=None):
    current=now or int(time.time());app_ok=Path(app_path).is_file() and Path(app_path).stat().st_mode&0o777==0o600;token={}
    try:token=_read(Path(token_path))
    except (OSError,PermissionError,ValueError):pass
    scopes=set(token.get("scopes") or str(token.get("scope") or "").split());authorized=bool(token);required=set(SCOPES)<=scopes
    return {"app_configured":app_ok,"oauth_authorized":authorized,"required_scopes_present":required,"access_token_expiration":token.get("expires_at"),
        "refresh_token_expiration":token.get("refresh_expires_at"),"refresh_available":bool(token.get("refresh_token") and current<token.get("refresh_expires_at",0)),
        "ready_for_etsy_read":bool(app_ok and authorized and required and current<token.get("expires_at",0)),"ready_for_etsy_write":bool(app_ok and authorized and required and current<token.get("expires_at",0))}
def refresh(app_path=APP_PATH,token_path=TOKEN_PATH,session=None,now=None):
    app=_read(Path(app_path));token=_read(Path(token_path));current=now or int(time.time())
    if not token.get("refresh_token") or current>=token.get("refresh_expires_at",0):raise ValueError("Etsy refresh token unavailable or expired")
    response=(session or requests).post(TOKEN_URL,data={"grant_type":"refresh_token","client_id":app["keystring"],"refresh_token":token["refresh_token"]},timeout=(10,45));response.raise_for_status();updated=response.json()
    scopes=set(str(updated.get("scope") or "").split()) or set(token.get("scopes") or [])
    if not set(SCOPES)<=scopes:raise ValueError("Required Etsy scopes missing after refresh")
    stored={**token,**updated,"issued_at":current,"expires_at":current+int(updated.get("expires_in",3600)),"scopes":sorted(scopes)};_write(Path(token_path),stored)
    return {"result":"etsy_oauth_refreshed","required_scopes_present":True,"ready_for_etsy_read":True,"ready_for_etsy_write":True}
