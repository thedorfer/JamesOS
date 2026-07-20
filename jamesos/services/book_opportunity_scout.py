from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Protocol
from uuid import uuid4

from jamesos.config import VAULT
from jamesos.core.agents.ledger import RunLedger
from jamesos.core.artifacts import AtomicDocumentStore
from jamesos.services.book_research_adapters import LiveResearchAdapters,PublicObservation,default_live_adapters


ROOT = VAULT / "JamesOS" / "Books" / "OpportunityScout" / "runs"
MODEL = "qwen3:14b"
RUN_ID = re.compile(r"^book-scout-[0-9]{8}T[0-9]{6}-[a-f0-9]{8}$")
DECISIONS = {"approve", "reject", "save_for_later"}
METRICS = ("demand_signal", "competition_opportunity", "customer_purchase_intent", "clear_differentiation", "seasonal_timing", "estimated_profitability", "production_simplicity", "series_potential")
DEFAULT_WEIGHTS = {"demand_signal":25,"competition_opportunity":20,"customer_purchase_intent":15,"clear_differentiation":10,"seasonal_timing":10,"estimated_profitability":10,"production_simplicity":5,"series_potential":5}


def _now() -> str:return datetime.now().astimezone().isoformat()


_DOCUMENTS=AtomicDocumentStore()
def _atomic(path:Path,value:Any)->None:_DOCUMENTS.write_json(path,value)


def _atomic_text(path:Path,value:str)->None:_DOCUMENTS.write_text(path,value)


@dataclass(frozen=True)
class BookOpportunityResearchRequest:
    market:str;audience:str;book_type:str;candidate_count:int=20;result_count:int=5;source_mode:str="demo"
    @classmethod
    def from_dict(cls,value:dict[str,Any])->"BookOpportunityResearchRequest":
        market=str(value.get("market") or "").strip();audience=str(value.get("audience") or "").strip();book_type=str(value.get("book_type") or "").strip()
        candidate_count=value.get("candidate_count",20);result_count=value.get("result_count",5);source_mode=str(value.get("source_mode") or "demo")
        if source_mode=="fixture":source_mode="demo" # migrate pre-live MVP requests
        if not market or not audience or not book_type:raise ValueError("market, audience, and book_type are required")
        if type(candidate_count) is not int or not 5<=candidate_count<=100:raise ValueError("candidate_count must be between 5 and 100")
        if type(result_count) is not int or not 1<=result_count<=candidate_count:raise ValueError("result_count must be between 1 and candidate_count")
        if source_mode not in {"demo","manual","live"}:raise ValueError("research mode must be demo, manual, or live")
        return cls(market,audience,book_type,candidate_count,result_count,source_mode)


@dataclass(frozen=True)
class BookConcept:
    candidate_id:str;concept:str;target_audience:str;book_type:str;recommended_angle:str;suggested_theme:str;seasonality:str;production_complexity:str;series_potential:str


@dataclass(frozen=True)
class ResearchEvidence:
    evidence_id:str;source_id:str;source_type:str;collection_timestamp:str;concept_id:str;metric:str;raw_value:Any;normalized_value:float|None;summary:str;source_reference:str|None;confidence:float;collection_status:str;error_details:str|None=None


class BookResearchSource(Protocol):
    source_id:str
    def collect(self,concept:BookConcept,request:BookOpportunityResearchRequest)->list[ResearchEvidence]:...


class FixtureResearchSource:
    source_id="fixture.book-market.v1"
    def collect(self,concept:BookConcept,request:BookOpportunityResearchRequest)->list[ResearchEvidence]:
        seed=int(sha256(f"{concept.candidate_id}:{request.market}:{request.audience}".encode()).hexdigest()[:8],16)
        values={metric:round(.35+((seed>>(index*3))%61)/100,2) for index,metric in enumerate(METRICS)}
        return [ResearchEvidence(f"ev-{concept.candidate_id}-{index+1}",self.source_id,"deterministic_fixture",_now(),concept.candidate_id,metric,value,value,f"Fixture demonstration signal for {metric.replace('_',' ')}.","fixture://book-opportunity-scout/v1",.82,"available") for index,(metric,value) in enumerate(values.items())]


class ManualResearchSource:
    source_id="manual.structured.v1"
    def __init__(self,records:dict[str,dict[str,Any]]|None=None):self.records=records or {}
    def collect(self,concept:BookConcept,request:BookOpportunityResearchRequest)->list[ResearchEvidence]:
        supplied=self.records.get(concept.candidate_id,{})
        rows=[]
        for index,metric in enumerate(METRICS):
            value=supplied.get(metric);valid=isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=float(value)<=1
            rows.append(ResearchEvidence(f"ev-{concept.candidate_id}-{index+1}",self.source_id,"manual_structured",_now(),concept.candidate_id,metric,value,float(value) if valid else None,"Manually supplied structured evidence." if valid else "Metric unavailable; no manual evidence was supplied.",None,.9 if valid else 0,"available" if valid else "unavailable",None if valid else "missing_evidence"))
        return rows


class LiveResearchSource:
    source_id="live.public-read-only.v1"
    def __init__(self,adapters:LiveResearchAdapters):self.adapters=adapters;self.summaries=[]
    def collect(self,concept:BookConcept,request:BookOpportunityResearchRequest)->list[ResearchEvidence]:
        observations,summary=self.adapters.collect(f"{concept.concept} {request.book_type} {request.audience}");self.summaries.append(summary);rows=[]
        for index,item in enumerate(observations,1):
            rows.append(ResearchEvidence(f"live-{concept.candidate_id}-{index:03d}",item.source_id,item.source_type,item.collected_at or _now(),concept.candidate_id,item.metric,item.raw_value,item.normalized_value,item.summary,item.url,item.confidence,item.status,item.error))
        present={item.metric for item in observations}
        for metric in METRICS:
            if metric not in present:rows.append(ResearchEvidence(f"live-{concept.candidate_id}-missing-{metric}",self.source_id,"public_research",_now(),concept.candidate_id,metric,None,None,"No live adapter supplied this metric.",None,0,"unavailable","missing_live_source"))
        return rows
    def summary(self)->dict[str,Any]:
        attempted=list(dict.fromkeys(item for row in self.summaries for item in row["sources_attempted"]));completed=list(dict.fromkeys(item for row in self.summaries for item in row["sources_completed"]));blocked=list(dict.fromkeys(item for row in self.summaries for item in row["sources_blocked"]));failed=list(dict.fromkeys(item for row in self.summaries for item in row["sources_failed"]));ages=[row["cache_age_seconds"] for row in self.summaries if row["cache_age_seconds"] is not None]
        return {"sources_attempted":attempted,"sources_completed":completed,"sources_blocked":blocked,"sources_failed":failed,"evidence_collected":sum(row["evidence_collected"] for row in self.summaries),"cache_age_seconds":max(ages) if ages else None,"collection_warnings":list(dict.fromkeys(warning for row in self.summaries for warning in row["collection_warnings"]))}


@dataclass(frozen=True)
class ScoringProfile:
    profile_id:str="book-opportunity-default-v1";weights:dict[str,int]=field(default_factory=lambda:dict(DEFAULT_WEIGHTS))
    def __post_init__(self):
        if set(self.weights)!=set(METRICS) or any(type(value) is not int or value<0 for value in self.weights.values()) or sum(self.weights.values())!=100:raise ValueError("scoring weights must contain every category and total 100")


CONCEPTS=(
    ("Cozy Forest Animals","gentle woodland scenes with bold shapes","woodland","evergreen","low","high"),("Construction Vehicles","large machines doing simple jobs","vehicles","evergreen","low","high"),("Backyard Bugs","friendly insects with observation prompts","nature","seasonal","low","high"),("Ocean Friends","underwater animals in uncluttered scenes","ocean","evergreen","low","high"),("Dinosaur Day","original dinosaur activities without franchise references","dinosaurs","evergreen","medium","high"),("Space Explorers","planets and original astronaut adventures","space","evergreen","medium","high"),("Farm Morning","farm animals and daily routines","farm","evergreen","low","medium"),("Rainy Day Adventures","indoor play and weather scenes","weather","seasonal","low","medium"),("Neighborhood Helpers","community roles without uniforms or logos","community","evergreen","medium","high"),("Garden Seasons","plants and garden changes through the year","gardening","seasonal","medium","high"),("Camping With Critters","original animal camping scenes","outdoors","seasonal","medium","high"),("Tiny Dragons","original gentle fantasy creatures","fantasy","evergreen","medium","high"),("Around the World Foods","simple food illustrations with careful cultural review","food","evergreen","medium","high"),("Mandalas for Calm Kids","age-appropriate geometric patterns without therapeutic claims","patterns","evergreen","low","medium"),("First Day Feelings","school situations without educational guarantees","school","seasonal","medium","medium"),("Winter Holiday Magic","generic winter celebrations without branded characters","winter","seasonal","medium","medium"),("Celebrity Style Stars","color famous celebrity likenesses","celebrity","evergreen","high","low"),("Superhero Movie Favorites","characters from named superhero franchises","franchise","evergreen","high","low"),("Healthy Healing Coloring","medical recovery and therapeutic outcome claims","medical","evergreen","medium","medium"),("Luxury Logo Fashion","famous fashion logos and branded accessories","brands","evergreen","high","low"),
)


def generate_candidates(request:BookOpportunityResearchRequest)->list[BookConcept]:
    rows=[]
    for index in range(request.candidate_count):
        name,angle,theme,seasonality,complexity,series=CONCEPTS[index%len(CONCEPTS)];cycle=index//len(CONCEPTS);suffix=f" Series {cycle+1}" if cycle else ""
        rows.append(BookConcept(f"concept-{index+1:03d}",name+suffix,request.audience,request.book_type,angle,theme,seasonality,complexity,series))
    return rows


def analyze_risks(concept:BookConcept)->list[str]:
    text=f"{concept.concept} {concept.recommended_angle}".casefold();risks=[]
    for terms,label in ((('franchise','superhero movie'),'copyrighted_or_franchise_dependent'),(('celebrity','famous celebrity','public figure'),'celebrity_likeness'),(('logo','branded'),'brand_or_logo'),(('trademark','officially licensed'),'trademark_sensitive_title'),(('named competitor','in the style of'),'named_competitor_imitation'),(('guaranteed learning','guaranteed educational','teaches every child'),'misleading_age_or_educational_claim'),(('therapeutic','medical recovery'),'medical_or_therapeutic_claim')):
        if any(term in text for term in terms):risks.append(label)
    if concept.seasonality=="seasonal":risks.append("seasonal_timing")
    return risks


def score_candidate(concept:BookConcept,evidence:list[ResearchEvidence],profile:ScoringProfile)->dict[str,Any]:
    by_metric={item.metric:item for item in evidence};breakdown={};available=[]
    for metric,weight in profile.weights.items():
        row=by_metric.get(metric);normalized=row.normalized_value if row and row.collection_status=="available" else None
        value=max(0,min(1,float(normalized))) if normalized is not None else 0;breakdown[metric]=round(weight*value,2)
        if normalized is not None:available.append(row.confidence)
    total=round(sum(breakdown.values()),2);confidence=round((len(available)/len(METRICS))*(sum(available)/len(available) if available else 0),3)
    return {"score_breakdown":breakdown,"total_score":total,"confidence":confidence,"missing_evidence":[metric for metric in METRICS if not by_metric.get(metric) or by_metric[metric].collection_status!="available"]}


def rank_candidates(rows:list[dict[str,Any]])->list[dict[str,Any]]:return sorted(rows,key=lambda item:(item["manual_review_required"],-item["total_score"],item["candidate_id"]))


class BookOpportunityScoutService:
    def __init__(self,root:Path|None=None,*,ledger:RunLedger|None=None,ollama_available=lambda:False,live_adapters:LiveResearchAdapters|None=None):self.root=Path(root or ROOT);self.ledger=ledger or RunLedger();self.ollama_available=ollama_available;self.live_adapters=live_adapters
    def run(self,value:dict[str,Any],*,manual_evidence:dict[str,dict[str,Any]]|None=None)->dict[str,Any]:
        request=BookOpportunityResearchRequest.from_dict(value);run_id=f"book-scout-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}";run_root=self.root/run_id
        if request.source_mode=="manual":source=ManualResearchSource(manual_evidence)
        elif request.source_mode=="live":source=LiveResearchSource(self.live_adapters or default_live_adapters(self.root.parent/"cache"))
        else:source=FixtureResearchSource()
        candidates=generate_candidates(request);profile=ScoringProfile();all_evidence=[];ranked=[]
        for concept in candidates:
            evidence=source.collect(concept,request);all_evidence.extend(evidence);score=score_candidate(concept,evidence,profile);risks=analyze_risks(concept)
            competition=next((item.normalized_value for item in evidence if item.metric=="competition" and item.collection_status=="available"),None)
            if competition is not None and competition < .35:risks.append("excessively_saturated_concept")
            if score["missing_evidence"]:risks.append("insufficient_supporting_evidence")
            high_risk=any(item in risks for item in ("copyrighted_or_franchise_dependent","celebrity_likeness","brand_or_logo","medical_or_therapeutic_claim"))
            ranked.append({**asdict(concept),**score,"evidence_collection_status":"complete" if not score["missing_evidence"] else "incomplete","risks":risks,"manual_review_required":high_risk,"differentiation_recommendation":f"Differentiate through {concept.recommended_angle}; avoid named competitors and protected properties.","evidence_references":[item.evidence_id for item in evidence if item.collection_status=="available"],"research_timestamp":_now()})
        ranked=rank_candidates(ranked)
        for position,item in enumerate(ranked,1):item["rank"]=position
        top=[item for item in ranked if not item["manual_review_required"]][:request.result_count]
        research_summary=source.summary() if isinstance(source,LiveResearchSource) else {"sources_attempted":[source.source_id],"sources_completed":[source.source_id],"sources_blocked":[],"sources_failed":[],"evidence_collected":len([row for row in all_evidence if row.collection_status=="available"]),"cache_age_seconds":None,"collection_warnings":[]}
        missing=sorted({metric for item in ranked for metric in item["missing_evidence"]});overall_confidence=round(sum(item["confidence"] for item in ranked)/len(ranked),3) if ranked else 0
        partial=request.source_mode=="live" and (bool(missing) or bool(research_summary["sources_blocked"]) or bool(research_summary["sources_failed"]))
        label="LIVE" if request.source_mode=="live" else "DEMO" if request.source_mode=="demo" else "MANUAL"
        warnings=(["DEMO fixture evidence is deterministic and is not live market research."] if request.source_mode=="demo" else [])+research_summary["collection_warnings"]
        result={"run_id":run_id,"status":"partial" if partial else "completed","degraded_reason":"Live public research completed with missing, blocked, or failed evidence." if partial else None,"research_label":label,"fixture_evidence":request.source_mode=="demo","research_summary":{**research_summary,"missing_metrics":missing,"overall_confidence":overall_confidence},"model":{"name":MODEL,"version":None,"provider":"ollama_local","used":False,"prompt_sha256":None},"request":asdict(request),"candidate_count":len(candidates),"ranked_candidates":ranked,"top_candidates":top,"scoring_profile":asdict(profile),"warnings":warnings,"side_effects":{"provider_calls":0,"marketplace_writes":0,"publications":0,"purchases":0,"images_generated":0}}
        for name,data in (("request.json",asdict(request)),("candidates.json",[asdict(item) for item in candidates]),("evidence.json",[asdict(item) for item in all_evidence]),("scoring-profile.json",asdict(profile)),("results.json",result)):_atomic(run_root/name,data)
        report=self._report(result);_atomic_text(run_root/"report.html",report);result["local_report_reference"]=f"book-scout-report:{run_id}";_atomic(run_root/"results.json",result)
        self.ledger.append({"run_id":run_id,"task_id":run_id,"agent_id":"jamesos.book-opportunity-scout","capability":"books.opportunity.research","phase":"execute","timestamp":_now(),"status":result["status"],"side_effect_summary":["local_research_artifacts"]})
        return result
    def load(self,run_id:str)->dict[str,Any]:
        self._run_id(run_id);path=self.root/run_id/"results.json"
        if not path.is_file():raise FileNotFoundError("research run not found")
        result=json.loads(path.read_text(encoding="utf-8"));decisions=self._decisions(run_id)
        result["decisions"]=decisions
        for collection in (result.get("ranked_candidates") or [],result.get("top_candidates") or []):
            for candidate in collection:candidate["decision"]=decisions.get(candidate.get("candidate_id"))
        return result
    def list_runs(self)->list[dict[str,Any]]:
        rows=[]
        for path in sorted(self.root.glob("book-scout-*/results.json"),reverse=True):
            try:value=json.loads(path.read_text(encoding="utf-8"));rows.append({key:value.get(key) for key in ("run_id","status","candidate_count")}|{"created_at":value.get("top_candidates",[{}])[0].get("research_timestamp")})
            except (OSError,ValueError):continue
        return rows[:25]
    def decide(self,run_id:str,candidate_id:str,action:str,*,confirmed:bool=False,reason:str="")->dict[str,Any]:
        result=self.load(run_id)
        if action not in DECISIONS:raise ValueError("unsupported candidate decision")
        if candidate_id not in {item["candidate_id"] for item in result["ranked_candidates"]}:raise ValueError("unknown candidate")
        if not confirmed:return {"run_id":run_id,"candidate_id":candidate_id,"action":action,"confirmation_required":True,"changed":False}
        path=self.root/run_id/"decisions.json";value=json.loads(path.read_text()) if path.is_file() else {"run_id":run_id,"decisions":{}}
        existing=value["decisions"].get(candidate_id)
        if existing and existing["action"]==action and existing.get("reason","")==reason:return {**existing,"changed":False,"idempotent":True}
        record={"run_id":run_id,"candidate_id":candidate_id,"action":action,"reason":str(reason)[:500],"timestamp":_now(),"changed":True};value["decisions"][candidate_id]=record;_atomic(path,value)
        _atomic_text(self.root/run_id/"report.html",self._report(self.load(run_id)))
        self.ledger.append({"run_id":run_id,"task_id":f"decision:{candidate_id}","agent_id":"jamesos.book-opportunity-scout","capability":"books.opportunity.decide","phase":"local_decision","timestamp":record["timestamp"],"status":"completed","side_effect_summary":["local_candidate_decision"]})
        return record
    @staticmethod
    def verify(result:dict[str,Any])->dict[str,Any]:
        errors=[];request=result.get("request") or {};ranked=result.get("ranked_candidates") or []
        if len(ranked)!=request.get("candidate_count"):errors.append("candidate_count_mismatch")
        for item in result.get("top_candidates") or []:
            if set(item.get("score_breakdown") or {})!=set(METRICS) or round(sum(item["score_breakdown"].values()),2)!=item.get("total_score"):errors.append(f"invalid_score:{item.get('candidate_id')}")
            if not item.get("evidence_references") and not item.get("missing_evidence"):errors.append(f"missing_evidence_disclosure:{item.get('candidate_id')}")
        if any(result.get("side_effects",{}).get(key) for key in ("provider_calls","marketplace_writes","publications","purchases","images_generated")):errors.append("prohibited_side_effect")
        return {"verified":not errors,"status":"verified" if not errors else "failed","errors":errors}
    @staticmethod
    def _report(result:dict[str,Any])->str:
        def decision_html(item:dict[str,Any])->str:
            decision=item.get("decision") or (result.get("decisions") or {}).get(item["candidate_id"])
            if not decision:return "<p>Decision: Not reviewed</p>"
            label={"approve":"Approved","reject":"Rejected","save_for_later":"Saved for Later"}.get(decision.get("action"),"Not reviewed");reason=decision.get("reason") or ""
            approved=("<p><strong>Approved for production planning</strong></p><p><strong>Next step:</strong><br>Coloring Book Producer is not installed yet. No book has been generated.</p><button disabled>Create Book Project</button><p>Available after the Coloring Book Producer agent is installed.</p>" if decision.get("action")=="approve" else "")
            return f"<p><strong>Decision: {escape(label)}</strong><br>Recorded: {escape(str(decision.get('timestamp') or 'unknown'))}</p>{f'<p>Reason: {escape(str(reason))}</p>' if reason else ''}{approved}"
        rows="".join(f"<article><h2>{index}. {escape(item['concept'])}</h2><p>Score: {item['total_score']} · Confidence: {item['confidence']}</p><p>{escape(item['differentiation_recommendation'])}</p><p>Risks: {escape(', '.join(item['risks']) or 'none')}</p><p>Evidence: {escape(', '.join(item['evidence_references']) or 'unavailable')}</p>{decision_html(item)}</article>" for index,item in enumerate(result["top_candidates"],1))
        return f"<!doctype html><meta charset='utf-8'><title>Book Opportunity Scout</title><h1>Book Opportunity Scout</h1><p>Research mode: {escape(result['research_label'])} · No book was generated or published.</p>{rows}"
    def _decisions(self,run_id:str)->dict[str,dict[str,Any]]:
        path=self.root/run_id/"decisions.json"
        if not path.is_file():return {}
        try:value=json.loads(path.read_text(encoding="utf-8"));rows=value.get("decisions") or {}
        except (OSError,ValueError):return {}
        return rows if isinstance(rows,dict) else {}
    @staticmethod
    def _run_id(run_id:str)->None:
        if not isinstance(run_id,str) or not RUN_ID.fullmatch(run_id) or Path(run_id).name!=run_id:raise ValueError("invalid research run ID")
