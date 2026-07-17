from __future__ import annotations
from typing import Any
import requests
ETSY_API_BASE="https://openapi.etsy.com/v3/application"
class EtsyAPIError(RuntimeError):
    def __init__(self,operation,status,message):self.operation,self.status,self.safe_message=operation,status,str(message)[:500];super().__init__(f"Etsy {operation} failed ({status})")
class EtsyShopResponseError(RuntimeError):
    def __init__(self,code):self.code=code;super().__init__(code)
def normalize_owner_shop_response(value:Any,authenticated_user_id:int)->dict[str,Any]:
    """Validate Etsy's documented single-Shop owner response without name matching."""
    shop=value
    if isinstance(value,dict) and "results" in value:
        results=value.get("results")
        shop=results[0] if isinstance(results,list) and len(results)==1 else None
    elif isinstance(value,list):shop=value[0] if len(value)==1 else None
    if not isinstance(shop,dict):raise EtsyShopResponseError("ETSY_SHOP_RESPONSE_INVALID")
    shop_id=shop.get("shop_id");owner_id=shop.get("user_id");shop_name=shop.get("shop_name")
    if type(shop_id) is not int or shop_id<=0 or type(owner_id) is not int or owner_id<=0 or not isinstance(shop_name,str) or not shop_name.strip():
        raise EtsyShopResponseError("ETSY_SHOP_RESPONSE_INVALID")
    if owner_id!=authenticated_user_id:raise EtsyShopResponseError("ETSY_SHOP_OWNERSHIP_MISMATCH")
    return {"shop_id":shop_id,"user_id":owner_id,"shop_name":shop_name.strip(),"status":shop.get("status")}
class EtsyClient:
    def __init__(self,credentials:dict[str,Any],session=None,base_url=ETSY_API_BASE,timeout=(10,45)):
        self.credentials,self.session,self.base_url,self.timeout=credentials,session or requests.Session(),base_url.rstrip("/"),timeout
    def _headers(self):
        key=f'{self.credentials["keystring"]}:{self.credentials["shared_secret"]}';token=self.credentials["access_token"]
        return {"x-api-key":key,"Authorization":f"Bearer {token}","Accept":"application/json"}
    def _request(self,method,path,operation,data=None):
        headers=self._headers()
        if data is not None:headers["Content-Type"]="application/x-www-form-urlencoded"
        try:response=self.session.request(method,f"{self.base_url}{path}",headers=headers,data=data,timeout=self.timeout)
        except requests.RequestException as exc:raise EtsyAPIError(operation,None,type(exc).__name__) from exc
        if 200<=response.status_code<300:
            try:return response.json()
            except ValueError:return {}
        try:body=response.json()
        except ValueError:body={}
        raise EtsyAPIError(operation,response.status_code,body.get("error") or "Etsy rejected the request")
    def get_listing(self,listing_id:int):return self._request("GET",f"/listings/{listing_id}","get_listing")
    def get_shop_by_owner_user_id(self,user_id:int):
        if type(user_id) is not int or user_id<=0:raise ValueError("Etsy owner user ID must be a positive integer")
        return normalize_owner_shop_response(self._request("GET",f"/users/{user_id}/shops","get_shop_by_owner_user_id"),user_id)
    def update_listing_state(self,shop_id:int,listing_id:int,state:str):
        if state not in ("active","inactive"):raise ValueError("Etsy update state must be active or inactive")
        return self._request("PATCH",f"/shops/{shop_id}/listings/{listing_id}","update_listing_state",data={"state":state})
