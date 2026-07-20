"""Public, read-only research adapters for Book Opportunity Scout.

Network retrieval, caching, parsing, and throttling live here so neither the
agent nor the deterministic scoring domain contains browser/site logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Protocol
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


def _now() -> str:return datetime.now(timezone.utc).astimezone().isoformat()


@dataclass(frozen=True)
class BrowserResponse:
    url:str;status:int;body:str;fetched_at:str;cache_age_seconds:float=0


class PublicResearchBrowser(Protocol):
    def fetch(self,url:str,*,timeout:float)->BrowserResponse:...


class ReadOnlyPublicBrowser:
    """Minimal replaceable browser transport: public GET only, no credentials."""
    def fetch(self,url:str,*,timeout:float)->BrowserResponse:
        request=Request(url,headers={"User-Agent":"JamesOS-BookOpportunityScout/0.1 (public read-only research)","Accept":"text/html,application/xhtml+xml"},method="GET")
        with urlopen(request,timeout=timeout) as response:
            body=response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8",errors="replace")
            return BrowserResponse(response.geturl(),response.status,body,_now())


class ChromiumPublicBrowser:
    """Read-only headless browser transport used by the Amazon adapter."""
    def __init__(self,executable:str|None=None):self.executable=executable or shutil.which("google-chrome") or shutil.which("chromium")
    def fetch(self,url:str,*,timeout:float)->BrowserResponse:
        if not self.executable:raise RuntimeError("local Chromium browser is unavailable")
        completed=subprocess.run([self.executable,"--headless=new","--disable-gpu","--disable-extensions","--disable-sync","--no-first-run","--dump-dom",url],capture_output=True,text=True,timeout=timeout,check=False)
        if completed.returncode:returncode=completed.returncode;raise RuntimeError(f"local browser failed with status {returncode}")
        return BrowserResponse(url,200,completed.stdout[:2_000_000],_now())


class CachedThrottledBrowser:
    def __init__(self,browser:PublicResearchBrowser,cache_root:Path,*,ttl_seconds:int=21600,min_interval_seconds:float=2,timeout:float=10,max_attempts:int=2,sleep:Callable[[float],None]=time.sleep,clock:Callable[[],float]=time.time):
        self.browser=browser;self.cache_root=Path(cache_root);self.ttl_seconds=ttl_seconds;self.min_interval_seconds=min_interval_seconds;self.timeout=timeout;self.max_attempts=max(1,min(max_attempts,3));self.sleep=sleep;self.clock=clock;self._last_request=0.0
    def fetch(self,url:str)->BrowserResponse:
        parsed=urlparse(url)
        if parsed.scheme!="https" or not parsed.hostname:raise ValueError("live research requires a public HTTPS URL")
        key=sha256(url.encode()).hexdigest();path=self.cache_root/f"{key}.json";now=self.clock()
        if path.is_file():
            try:
                value=json.loads(path.read_text(encoding="utf-8"));age=max(0,now-float(value["cached_at"]))
                if age<=self.ttl_seconds:return BrowserResponse(value["url"],value["status"],value["body"],value["fetched_at"],round(age,3))
            except (OSError,ValueError,KeyError,TypeError):pass
        error=None
        for attempt in range(self.max_attempts):
            wait=self.min_interval_seconds-(self.clock()-self._last_request)
            if wait>0:self.sleep(wait)
            try:
                self._last_request=self.clock();response=self.browser.fetch(url,timeout=self.timeout)
                if response.status>=500:raise RuntimeError(f"remote HTTP {response.status}")
                self.cache_root.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(".tmp")
                temporary.write_text(json.dumps({"url":response.url,"status":response.status,"body":response.body,"fetched_at":response.fetched_at,"cached_at":self.clock()}),encoding="utf-8");temporary.replace(path)
                return response
            except Exception as exc: # adapter boundary returns sanitized failures upstream
                error=exc
                if attempt+1<self.max_attempts:self.sleep(min(2**attempt,2))
        raise RuntimeError(f"public research retrieval failed: {type(error).__name__}")


@dataclass(frozen=True)
class PublicObservation:
    source_id:str;source_type:str;metric:str;raw_value:Any;normalized_value:float|None;summary:str;url:str|None;confidence:float;status:str;error:str|None=None;collected_at:str="";cache_age_seconds:float|None=None


class PublicResearchAdapter(Protocol):
    source_id:str
    def collect(self,query:str)->list[PublicObservation]:...


def _blocked(body:str)->bool:
    value=body.casefold();return any(marker in value for marker in ("enter the characters you see below","captcha","robot check","automated access"))


class AmazonPublicSearchAdapter:
    source_id="amazon.public-search.v1"
    def __init__(self,browser:CachedThrottledBrowser,market_host:str="www.amazon.com"):self.browser=browser;self.market_host=market_host
    def collect(self,query:str)->list[PublicObservation]:
        url=f"https://{self.market_host}/s?k={quote_plus(query)}";stamp=_now()
        try:response=self.browser.fetch(url)
        except Exception as exc:return [PublicObservation(self.source_id,"public_amazon_search","demand_signal",None,None,"Amazon public search could not be collected.",url,0,"failed",str(exc),stamp)]
        if response.status in {403,429} or _blocked(response.body):return [PublicObservation(self.source_id,"public_amazon_search","demand_signal",None,None,"Amazon challenged the read-only request; collection stopped without bypass.",response.url,0,"blocked","challenge_detected",stamp,response.cache_age_seconds)]
        cards=re.findall(r"<div[^>]+data-component-type=[\"']s-search-result[\"'][^>]*>(.*?)</div>\s*</div>",response.body,re.I|re.S) or [response.body]
        titles=re.findall(r"<h2[^>]*>.*?<span[^>]*>(.*?)</span>",response.body,re.I|re.S)
        prices=[float(x.replace(",","")) for x in re.findall(r"class=[\"'][^\"']*a-price-whole[^\"']*[\"'][^>]*>([0-9,]+)",response.body,re.I)]
        ratings=[float(x) for x in re.findall(r"([0-5](?:\.[0-9])?)\s+out of 5 stars",response.body,re.I)]
        reviews=[int(x.replace(",","")) for x in re.findall(r"aria-label=[\"']([0-9,]+) ratings",response.body,re.I)]
        publication=re.findall(r"(?:Publication date|Published)\s*:?\s*([^<]+)",response.body,re.I)
        formats=re.findall(r">(Paperback|Hardcover|Kindle|Spiral-bound)<",response.body,re.I)
        ranks=[int(x.replace(",","")) for x in re.findall(r"Best Sellers Rank[^#]*#([0-9,]+)",response.body,re.I)]
        raw={"visible_result_cards":len(cards),"titles":[re.sub("<[^>]+>","",x).strip() for x in titles[:20]],"prices":prices[:20],"ratings":ratings[:20],"review_counts":reviews[:20],"publication_information":publication[:20],"formats":formats[:20],"visible_bestseller_ranks":ranks[:20]}
        # Result/review visibility is an opportunity signal, never a sales-volume claim.
        normalized=min(1,(len(titles)/20)*.45+(min(sum(reviews),5000)/5000)*.35+(min(len(ratings),20)/20)*.2) if titles else None
        return [PublicObservation(self.source_id,"public_amazon_search","demand_signal",raw,normalized,"Public search visibility only; it is not verified sales volume.",response.url,.65 if normalized is not None else 0,"available" if normalized is not None else "unavailable",None if normalized is not None else "no_parseable_results",stamp,response.cache_age_seconds)]


class PublicWebSearchAdapter:
    source_id="web.public-search.v1"
    def __init__(self,browser:CachedThrottledBrowser):self.browser=browser
    def collect(self,query:str)->list[PublicObservation]:
        url=f"https://html.duckduckgo.com/html/?q={quote_plus(query)}";stamp=_now()
        try:response=self.browser.fetch(url)
        except Exception as exc:return [PublicObservation(self.source_id,"public_web_search","competition_opportunity",None,None,"Public web search was unavailable.",url,0,"failed",str(exc),stamp)]
        titles=[re.sub("<[^>]+>","",x).strip() for x in re.findall(r"class=[\"']result__a[\"'][^>]*>(.*?)</a>",response.body,re.I|re.S)]
        count=len(titles);normalized=max(0,1-min(count,30)/30) if titles else None
        return [PublicObservation(self.source_id,"public_web_search","competition_opportunity",{"visible_result_count":count,"competing_titles":titles[:20]},normalized,"Visible public results and competing titles; no total-result estimate was invented.",response.url,.6 if titles else 0,"available" if titles else "unavailable",None if titles else "no_parseable_results",stamp,response.cache_age_seconds)]


class PublicTrendAdapter:
    source_id="trends.public.v1"
    def __init__(self,browser:CachedThrottledBrowser):self.browser=browser
    def collect(self,query:str)->list[PublicObservation]:
        # The public Explore page is attempted conservatively. Without parseable
        # structured interest data, the metric remains unavailable.
        url=f"https://trends.google.com/trends/explore?q={quote_plus(query)}";stamp=_now()
        try:response=self.browser.fetch(url)
        except Exception as exc:return [PublicObservation(self.source_id,"public_trend_signal","seasonal_timing",None,None,"Public trend signal was unavailable.",url,0,"failed",str(exc),stamp)]
        match=re.search(r'"averages"\s*:\s*\[\s*([0-9]+)',response.body)
        value=min(100,int(match.group(1)))/100 if match else None
        return [PublicObservation(self.source_id,"public_trend_signal","seasonal_timing",int(match.group(1)) if match else None,value,"Public trend interest where parseable; unavailable otherwise.",response.url,.55 if match else 0,"available" if match else "unavailable",None if match else "no_parseable_public_trend_signal",stamp,response.cache_age_seconds)]


class PublicReviewInsightAdapter:
    source_id="reviews.public-visible.v1"
    def __init__(self,browser:CachedThrottledBrowser):self.browser=browser
    def collect(self,query:str)->list[PublicObservation]:
        url=f"https://html.duckduckgo.com/html/?q={quote_plus(query+' coloring book reviews')}";stamp=_now()
        try:response=self.browser.fetch(url)
        except Exception as exc:return [PublicObservation(self.source_id,"public_review_insights","customer_purchase_intent",None,None,"Public review insights were unavailable.",url,0,"failed",str(exc),stamp)]
        snippets=[re.sub("<[^>]+>","",x).strip() for x in re.findall(r"class=[\"']result__snippet[\"'][^>]*>(.*?)</(?:a|div)>",response.body,re.I|re.S)]
        useful=[x for x in snippets if x];normalized=min(1,len(useful)/10) if useful else None
        return [PublicObservation(self.source_id,"public_review_insights","customer_purchase_intent",{"visible_review_snippets":useful[:10],"snippet_count":len(useful)},normalized,"Insights use only publicly visible snippets; no private account or review content was accessed.",response.url,.5 if useful else 0,"available" if useful else "unavailable",None if useful else "no_public_review_snippets",stamp,response.cache_age_seconds)]


class LiveResearchAdapters:
    source_id="live.public-read-only.v1"
    def __init__(self,adapters:list[PublicResearchAdapter]):self.adapters=adapters
    def collect(self,query:str)->tuple[list[PublicObservation],dict[str,Any]]:
        observations=[]
        for adapter in self.adapters:
            try:observations.extend(adapter.collect(query))
            except Exception as exc:observations.append(PublicObservation(adapter.source_id,"public_research","unknown",None,None,"Adapter failed safely.",None,0,"failed",type(exc).__name__,_now()))
        statuses={item.source_id:item.status for item in observations};ages=[item.cache_age_seconds for item in observations if item.cache_age_seconds is not None]
        summary={"sources_attempted":list(dict.fromkeys(adapter.source_id for adapter in self.adapters)),"sources_completed":[key for key,value in statuses.items() if value in {"available","unavailable"}],"sources_blocked":[key for key,value in statuses.items() if value=="blocked"],"sources_failed":[key for key,value in statuses.items() if value=="failed"],"evidence_collected":sum(item.status=="available" for item in observations),"cache_age_seconds":max(ages) if ages else None,"collection_warnings":[item.summary for item in observations if item.status!="available"]}
        return observations,summary


def default_live_adapters(cache_root:Path)->LiveResearchAdapters:
    browser=CachedThrottledBrowser(ReadOnlyPublicBrowser(),cache_root);amazon_browser=CachedThrottledBrowser(ChromiumPublicBrowser(),cache_root)
    return LiveResearchAdapters([AmazonPublicSearchAdapter(amazon_browser),PublicWebSearchAdapter(browser),PublicTrendAdapter(browser),PublicReviewInsightAdapter(browser)])
