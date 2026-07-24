"""Single shared local ComfyUI adapter for Agent OS creative capabilities."""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

from jamesos.core.artifacts import AtomicDocumentStore,canonical_sha256,now
from jamesos.services import comfyui_client
from jamesos.services.coloring_page_postprocessor import process_coloring_page
from jamesos.services.local_creative_studio import LocalAssetRequest,LocalAssetResult


class ComfyUILocalCreativeStudioProvider:
    provider_id="comfyui-local-creative-studio"
    provider_version="1"
    capabilities=frozenset({"coloring_page.line_art","cover.local","commerce.artwork","mockup.blank_template"})

    PROFILE_ID="kids-bold-line-art-v1"
    DEFAULT_PROFILE=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio/profiles/kids-bold-line-art-v1.json"

    def __init__(self,*,api_url:str="http://127.0.0.1:8188",profile_path:Path|None=None,workflow_path:Path|None=None,checkpoint:str|None=None,client=None):
        self.api_url=api_url;self.profile_path=profile_path or Path(os.environ.get("JAMESOS_COLORING_PROFILE",self.DEFAULT_PROFILE));self.client=client or comfyui_client;self.documents=AtomicDocumentStore();self._workflow_override=workflow_path;self._checkpoint_override=checkpoint

    def _profile(self)->dict[str,Any]:
        if not self.profile_path.is_file():return {}
        try:
            value=json.loads(self.profile_path.read_text())
            return value if isinstance(value,dict) else {}
        except (OSError,json.JSONDecodeError):return {}

    @staticmethod
    def _choices(node:dict[str,Any],field:str)->set[str]:
        value=((node.get("input") or {}).get("required") or {}).get(field) or []
        choices=value[0] if isinstance(value,list) and value and isinstance(value[0],list) else []
        return {str(x) for x in choices}

    def readiness(self)->dict[str,Any]:
        health=self.client.health(self.api_url,timeout=1.0);reachable=bool(health.get("running"));profile=self._profile();profile_ok=str(profile.get("profile_id") or "").startswith("kids-bold-line-art-v") and profile.get("asset_type")=="coloring_page"
        workflow_value=self._workflow_override or profile.get("workflow_json_path") or "";workflow_path=Path(workflow_value).expanduser() if workflow_value else Path("");workflow=bool(workflow_value) and workflow_path.is_file();workflow_hash=sha256(workflow_path.read_bytes()).hexdigest() if workflow else None
        checkpoint=self._checkpoint_override if self._checkpoint_override is not None else str(profile.get("checkpoint_identifier") or "");nodes=self.client.object_info(self.api_url,timeout=3.0) if reachable and hasattr(self.client,"object_info") else {};mappings=profile.get("node_mapping") or {};required=profile.get("required_node_classes") or [];missing_nodes=[x for x in required if x not in nodes];missing_custom=[x for x in (profile.get("required_custom_nodes") or []) if x not in nodes]
        checkpoint_exists=bool(checkpoint and checkpoint in self._choices(nodes.get("CheckpointLoaderSimple",{}),"ckpt_name"));checkpoint_metadata=profile.get("checkpoint") or {};checkpoint_path=Path(str(checkpoint_metadata.get("path") or "")).expanduser() if checkpoint_metadata else None;checkpoint_file_exists=bool(not checkpoint_metadata or checkpoint_path and checkpoint_path.is_file());checkpoint_file_hash=sha256(checkpoint_path.read_bytes()).hexdigest() if checkpoint_metadata and checkpoint_file_exists else None;checkpoint_hash_valid=bool(not checkpoint_metadata or checkpoint_file_hash==checkpoint_metadata.get("sha256"));checkpoint_trigger_valid=bool(not checkpoint_metadata or not checkpoint_metadata.get("trigger_phrase") or str(profile.get("positive_prompt_prefix") or "").startswith(str(checkpoint_metadata.get("trigger_phrase") or "")));embedding=profile.get("embedding") or {};embedding_path=Path(str(embedding.get("path") or "")).expanduser() if embedding else None;embedding_exists=bool(embedding_path and embedding_path.is_file());embedding_hash=sha256(embedding_path.read_bytes()).hexdigest() if embedding_exists else None;embedding_hash_valid=bool(not embedding or embedding_hash==embedding.get("sha256"));loaded_embeddings=self.client.list_embeddings(self.api_url,timeout=3.0) if reachable and embedding and hasattr(self.client,"list_embeddings") else [];embedding_loaded=bool(not embedding or embedding.get("installed_filename") in loaded_embeddings or Path(str(embedding.get("installed_filename") or "")).stem in loaded_embeddings);embedding_token_valid=bool(not embedding or str(embedding.get("comfyui_token") or "") in str(profile.get("positive_prompt_prefix") or ""));lora=profile.get("lora") or {};lora_path=Path(str(lora.get("path") or "")).expanduser() if lora else None;lora_exists=bool(lora_path and lora_path.is_file());lora_hash=sha256(lora_path.read_bytes()).hexdigest() if lora_exists else None;lora_hash_valid=bool(not lora or lora_hash==lora.get("sha256"));lora_registered=bool(not lora or lora.get("installed_filename") in self._choices(nodes.get("LoraLoader",{}),"lora_name"));lora_trigger_valid=bool(not lora or str(lora.get("trigger_word") or "") in str(profile.get("positive_prompt_prefix") or ""));expected_checkpoint=checkpoint_metadata.get("installed_filename") if checkpoint_metadata else "DreamShaper.safetensors";family=str(profile.get("checkpoint_family") or "");checkpoint_family_compatible=bool(not embedding and not lora and not checkpoint_metadata or family in {"sd15","sdxl"} and (not embedding or embedding.get("compatible_checkpoint_family")==family) and (not lora or lora.get("compatible_checkpoint_family")==family) and (not checkpoint_metadata or checkpoint_metadata.get("compatible_checkpoint_family")==family) and checkpoint==expected_checkpoint)
        mapping_valid=bool(mappings)
        workflow_json={}
        if workflow:
            try:workflow_json=json.loads(workflow_path.read_text())
            except (OSError,json.JSONDecodeError):mapping_valid=False
        for role in ("prompt","negative_prompt","seed","width","height","sampler","output_image"):
            item=mappings.get(role) or {};node=workflow_json.get(str(item.get("node_id"))) if isinstance(workflow_json,dict) else None
            if not isinstance(node,dict) or (item.get("input") and item["input"] not in (node.get("inputs") or {})):mapping_valid=False
        output=mappings.get("output_image") or {};output_valid=bool(workflow_json.get(str(output.get("node_id")),{}).get("class_type") in {"SaveImage","PreviewImage"})
        if not reachable:status="comfyui_unreachable"
        elif not profile_ok or not workflow:status="workflow_missing"
        elif not checkpoint_exists:status="checkpoint_missing"
        elif checkpoint_metadata and (not checkpoint_file_exists or not checkpoint_hash_valid):status="checkpoint_invalid"
        elif embedding and (not embedding_exists or not embedding_hash_valid):status="embedding_missing"
        elif embedding and not embedding_loaded:status="embedding_not_loaded"
        elif lora and (not lora_exists or not lora_hash_valid):status="lora_missing"
        elif lora and not lora_registered:status="lora_not_loaded"
        elif (embedding or lora or checkpoint_metadata) and (not embedding_token_valid or not lora_trigger_valid or not checkpoint_trigger_valid or not checkpoint_family_compatible):status="adapter_incompatible"
        elif missing_custom or missing_nodes:status="custom_node_missing"
        elif not output_valid and bool((mappings.get("output_image") or {}).get("node_id")):status="output_node_missing"
        elif not mapping_valid:status="invalid_node_mapping"
        elif workflow_hash!=profile.get("workflow_sha256"):status="invalid_node_mapping"
        else:status="ready"
        configured=status=="ready";messages={"comfyui_unreachable":"Local ComfyUI is unreachable.","workflow_missing":"The coloring-page workflow profile or workflow is missing.","checkpoint_missing":"The configured checkpoint is not installed.","checkpoint_invalid":"The configured checkpoint file is missing or has the wrong hash.","embedding_missing":"The configured textual-inversion embedding is missing or has the wrong hash.","embedding_not_loaded":"ComfyUI has not loaded the configured textual-inversion embedding.","lora_missing":"The configured LoRA is missing or has the wrong hash.","lora_not_loaded":"ComfyUI has not registered the configured LoRA.","adapter_incompatible":"The embedding, adapter trigger, or SD1.5 checkpoint compatibility is invalid.","custom_node_missing":"A required ComfyUI node is unavailable.","invalid_node_mapping":"The workflow node mapping or hash is invalid.","output_node_missing":"The workflow output image node is missing.","ready":"Local coloring-page generation is ready."}
        system=(health.get("system_stats") or {});devices=system.get("devices") or []
        instance=self.client.instance_identity(self.api_url,timeout=1.0) if reachable and hasattr(self.client,"instance_identity") else None
        return {"provider_id":self.provider_id,"provider_version":self.provider_version,"profile_id":profile.get("profile_id") or self.PROFILE_ID,"asset_type":profile.get("asset_type") or "coloring_page","configured":configured,"reachable":reachable,"api_url":self.api_url,"instance_identity":instance,"workflow_configured":workflow,"workflow_reference":workflow_path.name if workflow_value else None,"workflow_path":str(workflow_path) if workflow_value else None,"workflow_hash":workflow_hash,"checkpoint_configured":checkpoint_exists,"checkpoint":checkpoint or None,"checkpoint_metadata":checkpoint_metadata or None,"checkpoint_file_exists":checkpoint_file_exists if checkpoint_metadata else None,"checkpoint_sha256":checkpoint_file_hash,"checkpoint_hash_valid":checkpoint_hash_valid if checkpoint_metadata else None,"checkpoint_trigger_valid":checkpoint_trigger_valid if checkpoint_metadata else None,"checkpoint_family":profile.get("checkpoint_family"),"checkpoint_family_compatible":checkpoint_family_compatible,"embedding":embedding or None,"embedding_exists":embedding_exists if embedding else None,"embedding_sha256":embedding_hash,"embedding_hash_valid":embedding_hash_valid if embedding else None,"embedding_loaded":embedding_loaded if embedding else None,"embedding_token_valid":embedding_token_valid if embedding else None,"lora":lora or None,"lora_exists":lora_exists if lora else None,"lora_sha256":lora_hash,"lora_hash_valid":lora_hash_valid if lora else None,"lora_registered":lora_registered if lora else None,"lora_trigger_valid":lora_trigger_valid if lora else None,"vae":profile.get("vae_identifier"),"loras":profile.get("lora_identifiers") or [],"status":status,"message":messages[status],"missing_nodes":missing_nodes,"missing_custom_nodes":missing_custom,"node_mapping_valid":mapping_valid,"output_node_valid":output_valid,"sample_resolution":profile.get("sample_resolution"),"generation_bounds":profile.get("generation_bounds"),"expected_output_format":profile.get("expected_output_format"),"postprocessing":profile.get("postprocessing"),"validation_thresholds":profile.get("validation_thresholds"),"semantic_review_policy":profile.get("semantic_review_policy"),"local_only":True,"gpu_effects":{"uses_local_gpu":configured,"device":devices[0].get("name") if devices else None,"external_provider_calls":0,"marketplace_actions":0}}

    def for_profile(self,profile_id:str):
        return type(self)(api_url=self.api_url,profile_path=self.DEFAULT_PROFILE.parent/f"{profile_id}.json",client=self.client)

    def submission_evidence(self,prompt_id:str,submitted_instance_id:str|None)->dict[str,Any]:
        current=self.client.instance_identity(self.api_url,timeout=1.0) if hasattr(self.client,"instance_identity") else {}
        queue=self.client.queue_snapshot(self.api_url,timeout=3.0) if hasattr(self.client,"queue_snapshot") else {}
        try:history=self.client.get_history(prompt_id,api_url=self.api_url).get("history",{})
        except Exception:history={}
        queued=any(str(item[1])==prompt_id for name in ("queue_running","queue_pending") for item in (queue.get(name) or []) if isinstance(item,list) and len(item)>1)
        historical=bool(isinstance(history,dict) and history.get(prompt_id))
        return {"prompt_id":prompt_id,"submitted_instance_id":submitted_instance_id,"current_instance_identity":current,"instance_changed":bool(submitted_instance_id and current.get("instance_id") and submitted_instance_id!=current.get("instance_id")),"queue_evidence":queued,"history_evidence":historical,"output_evidence":bool(historical and (history.get(prompt_id,{}).get("outputs") or {})),"api_url":self.api_url}

    def _replace(self,value:Any,replacements:dict[str,str])->Any:
        if isinstance(value,str):
            for key,item in replacements.items():value=value.replace(key,item)
            return value
        if isinstance(value,list):return [self._replace(x,replacements) for x in value]
        if isinstance(value,dict):return {k:self._replace(v,replacements) for k,v in value.items()}
        return value

    def _validation(self,content:bytes,expected_width:int,expected_height:int)->tuple[dict[str,Any],tuple[int,int]]:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            gray=image.convert("L");width,height=gray.size;pixels=list(gray.getdata());total=max(1,len(pixels));white=sum(x>=240 for x in pixels)/total;dark=sum(x<=80 for x in pixels)/total;margin=max(4,min(width,height)//30);edges=list(gray.crop((0,0,width,margin)).getdata())+list(gray.crop((0,height-margin,width,height)).getdata())+list(gray.crop((0,0,margin,height)).getdata())+list(gray.crop((width-margin,0,width,height)).getdata());edge_dark=sum(x<=80 for x in edges)/max(1,len(edges));valid=(width,height)==(expected_width,expected_height) and white>=.55 and .005<=dark<=.35 and edge_dark<=.03
            return {"valid":valid,"dimensions_valid":(width,height)==(expected_width,expected_height),"format":image.format,"mostly_white_background":white>=.55,"white_ratio":round(white,4),"black_line_coverage":round(dark,4),"not_blank":dark>=.005,"safe_margins":edge_dark<=.03,"edge_dark_ratio":round(edge_dark,4)},(width,height)

    def execute(self,request:LocalAssetRequest)->LocalAssetResult:
        ready=self.readiness()
        if not ready["configured"]:return LocalAssetResult(request.request_id,"provider_unavailable",provider_id=self.provider_id,warnings=(ready["message"],))
        specs=request.specification;pages=specs.get("pages") or [];candidate_count=int(specs.get("candidates_per_page") or 1)
        if len(pages)>3 or candidate_count<1 or len(pages)*candidate_count>6:return LocalAssetResult(request.request_id,"rejected",provider_id=self.provider_id,warnings=("Sample generation is bounded to six local outputs.",))
        output_root=Path(specs["output_directory"]).resolve();owner_root=Path(specs["owner_root"]).resolve()
        if owner_root not in output_root.parents:return LocalAssetResult(request.request_id,"rejected",provider_id=self.provider_id,warnings=("Output directory escaped the owning project.",))
        profile=self._profile();self.workflow_path=Path(ready["workflow_path"]);self.checkpoint=str(ready["checkpoint"]);workflow=json.loads(self.workflow_path.read_text());artifacts=[];hashes=set();event_sink=specs.get("operation_event_sink");resolution=profile.get("sample_resolution") or {};width=int(specs.get("width") or resolution.get("width") or 768);height=int(specs.get("height") or resolution.get("height") or 992);positive_prefix=str(profile.get("positive_prompt_prefix") or "").strip();negative_prefix=str(profile.get("negative_prompt_prefix") or "").strip()
        for page in pages:
            for candidate in range(candidate_count):
                seed=int(sha256(f"{request.request_id}:{page['page_id']}:{candidate}".encode()).hexdigest()[:12],16);positive=", ".join(x for x in (positive_prefix,page["positive_prompt"]) if x);negative=", ".join(x for x in (negative_prefix,page["negative_prompt"]) if x);prepared=self._replace(workflow,{"{{POSITIVE_PROMPT}}":positive,"{{NEGATIVE_PROMPT}}":negative,"{{CHECKPOINT}}":self.checkpoint,"{{SEED}}":str(seed),"{{WIDTH}}":str(width),"{{HEIGHT}}":str(height)})
                mapped=profile["node_mapping"]
                for role,value in (("prompt",positive),("negative_prompt",negative),("seed",seed),("width",width),("height",height)):
                    item=mapped[role];prepared[str(item["node_id"])]["inputs"][item["input"]]=value
                for node in prepared.values():
                    if node.get("class_type")=="CLIPTextEncodeSDXL":
                        inputs=node["inputs"];inputs["text_l"]=inputs["text_g"];inputs.update(width=width,height=height,target_width=width,target_height=height)
                queued=self.client.queue_prompt(prepared,api_url=self.api_url);prompt_id=str(queued.get("prompt_id") or "")
                if not prompt_id:return LocalAssetResult(request.request_id,"failed",tuple(artifacts),self.provider_id,0,("ComfyUI did not return a prompt ID.",))
                if callable(event_sink):event_sink({"state":"provider_submitted","comfyui_prompt_id":prompt_id,"page_id":page["page_id"],"prompt_id":page["prompt_id"],"workflow_hash":ready["workflow_hash"],"checkpoint":self.checkpoint,"seed":seed,"api_url":queued.get("api_url") or self.api_url,"http_status":queued.get("http_status"),"submission_timestamp":queued.get("submission_timestamp") or now(),"instance_identity":queued.get("instance_identity") or ready.get("instance_identity")})
                completed=self.client.wait_for_completion(prompt_id,api_url=self.api_url)
                if completed.get("status")!="completed":return LocalAssetResult(request.request_id,"failed",tuple(artifacts),self.provider_id,0,("Local generation did not complete.",))
                images=self.client.get_output_images(prompt_id,api_url=self.api_url)
                if not images:return LocalAssetResult(request.request_id,"failed",tuple(artifacts),self.provider_id,0,("Local generation returned no image.",))
                content=images[0]["content"];raw_digest=sha256(content).hexdigest();base=f"sample-{page['page_id']}-{raw_digest[:16]}";raw_path=output_root/"raw"/f"{base}.raw.png";path=output_root/f"{base}.png"
                if profile.get("postprocessing",{}).get("enabled"):
                    processed=process_coloring_page(content,raw_path,path,profile_id=ready["profile_id"],workflow_hash=ready["workflow_hash"],expected_width=width,expected_height=height,parameters=profile.get("postprocessing"),thresholds=profile.get("validation_thresholds"));digest=processed["processed_file_sha256"];validation=processed["technical_validation"];dimensions=(processed["width"],processed["height"])
                else:
                    digest=raw_digest;validation,dimensions=self._validation(content,width,height);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content);raw_path=None
                if digest in hashes:validation["valid"]=False;validation["duplicate_hash"]=True
                hashes.add(digest);asset_id=f"sample-{page['page_id']}-{digest[:16]}"
                artifacts.append({"asset_id":asset_id,"page_id":page["page_id"],"prompt_id":page["prompt_id"],"comfyui_prompt_id":prompt_id,"instance_identity":queued.get("instance_identity") or ready.get("instance_identity"),"http_status":queued.get("http_status"),"queue_history_confirmation":{"completion_status":completed.get("status"),"prompt_in_history":bool((completed.get("history") or {}).get(prompt_id))},"output_evidence":True,"provider_id":self.provider_id,"provider_version":self.provider_version,"profile_id":ready["profile_id"],"workflow_hash":ready["workflow_hash"],"model_checkpoint":self.checkpoint,"seed":seed,"width":dimensions[0],"height":dimensions[1],"raw_file_sha256":raw_digest,"raw_local_path":str(raw_path) if raw_path else None,"file_sha256":digest,"processing_parameters":profile.get("postprocessing") if raw_path else None,"validation_thresholds":profile.get("validation_thresholds") if raw_path else None,"generated_at":now(),"provider_effects":{"local_gpu":True,"local_comfyui_write":True,"external_network":False,"marketplace_write":False},"review_state":"pending","local_path":str(path),"technical_validation":validation})
        return LocalAssetResult(request.request_id,"completed",tuple(artifacts),self.provider_id,0)
