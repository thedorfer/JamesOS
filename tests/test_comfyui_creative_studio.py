import json
import tempfile
import unittest
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image,ImageDraw

from jamesos.services.comfyui_creative_studio import ComfyUILocalCreativeStudioProvider
from jamesos.services.coloring_page_postprocessor import process_coloring_page
from jamesos.services.local_creative_studio import LocalAssetRequest


class Client:
    @staticmethod
    def health(url,timeout=1):return {"running":True}
    @staticmethod
    def object_info(url,timeout=3):return {
        "CheckpointLoaderSimple":{"input":{"required":{"ckpt_name":[["fixture.ckpt"]]}}},
        "CLIPTextEncode":{"input":{"required":{"text":["STRING"],"clip":["CLIP"]}}},
        "EmptyLatentImage":{"input":{"required":{"width":["INT"],"height":["INT"],"batch_size":["INT"]}}},
        "KSampler":{"input":{"required":{"seed":["INT"],"sampler_name":[["dpmpp_2m"]]}}},
        "VAEDecode":{"input":{"required":{}}},"SaveImage":{"input":{"required":{"images":["IMAGE"]}}}}
    @staticmethod
    def instance_identity(url,timeout=1):return {"instance_id":"instance-a","main_pid":101,"process_started_at":"Thu 2026-07-23 14:40:28 CDT"}
    @staticmethod
    def queue_snapshot(url,timeout=3):return {"queue_running":[],"queue_pending":[]}
    @staticmethod
    def queue_prompt(workflow,api_url=None):return {"prompt_id":"prompt-1","http_status":200,"submission_timestamp":"2026-07-23T15:05:48-05:00","api_url":api_url,"instance_identity":{"instance_id":"instance-a","main_pid":101,"process_started_at":"Thu 2026-07-23 14:40:28 CDT"}}
    @staticmethod
    def get_history(prompt_id,api_url=None):return {"history":{}}
    @staticmethod
    def wait_for_completion(prompt_id,api_url=None):return {"status":"completed"}
    @staticmethod
    def get_output_images(prompt_id,api_url=None):
        image=Image.new("L",(1024,1280),255);draw=ImageDraw.Draw(image);draw.rectangle((150,180,870,1080),outline=0,width=14);data=BytesIO();image.save(data,"PNG");return [{"content":data.getvalue()}]


class ComfyUICreativeStudioTests(unittest.TestCase):
    def fixture(self,root,*,checkpoint="fixture.ckpt",custom=(),output="SaveImage"):
        workflow=root/"workflow.json";workflow.write_text(json.dumps({"1":{"inputs":{"ckpt_name":"{{CHECKPOINT}}"},"class_type":"CheckpointLoaderSimple"},"2":{"inputs":{"text":"{{POSITIVE_PROMPT}}"},"class_type":"CLIPTextEncode"},"3":{"inputs":{"text":"{{NEGATIVE_PROMPT}}"},"class_type":"CLIPTextEncode"},"4":{"inputs":{"width":"{{WIDTH}}","height":"{{HEIGHT}}"},"class_type":"EmptyLatentImage"},"5":{"inputs":{"seed":"{{SEED}}","sampler_name":"dpmpp_2m"},"class_type":"KSampler"},"6":{"inputs":{},"class_type":"VAEDecode"},"7":{"inputs":{"images":["6",0]},"class_type":output}}));profile=root/"profile.json";profile.write_text(json.dumps({"profile_id":"kids-bold-line-art-v1","asset_type":"coloring_page","workflow_json_path":str(workflow),"workflow_sha256":sha256(workflow.read_bytes()).hexdigest(),"checkpoint_identifier":checkpoint,"required_node_classes":["CheckpointLoaderSimple","CLIPTextEncode","EmptyLatentImage","KSampler","VAEDecode","SaveImage"],"required_custom_nodes":list(custom),"node_mapping":{"prompt":{"node_id":"2","input":"text"},"negative_prompt":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"},"width":{"node_id":"4","input":"width"},"height":{"node_id":"4","input":"height"},"sampler":{"node_id":"5","input":"sampler_name"},"output_image":{"node_id":"7","input":"images"}},"sample_resolution":{"width":1024,"height":1280}}));return profile,workflow

    def test_unconfigured_is_explicit_and_nonwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            provider=ComfyUILocalCreativeStudioProvider(profile_path=Path(directory)/"missing.json",client=Client)
            self.assertFalse(provider.readiness()["configured"])
            self.assertEqual("workflow_missing",provider.readiness()["status"])
            result=provider.execute(LocalAssetRequest("r","coloring_page.line_art","a","p",{}))
            self.assertEqual("provider_unavailable",result.status);self.assertEqual(0,result.external_provider_calls)

    def test_deployed_v1_is_unchanged_and_v2_is_distinct(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio";v1=root/"profiles/kids-bold-line-art-v1.json";v2=root/"profiles/kids-bold-line-art-v2.json"
        self.assertEqual("c3b76b4c3cb8396292b61bde316fb092bc18d4fb29dbeb2f670a8b14c55746cb",sha256(v1.read_bytes()).hexdigest())
        self.assertEqual("530255ad90095404d80d17960853c7f257456e37dd65394b8e4628ec3f974139",sha256(v2.read_bytes()).hexdigest())
        first=json.loads(v1.read_text());second=json.loads(v2.read_text());self.assertEqual("kids-bold-line-art-v1",first["profile_id"]);self.assertEqual("kids-bold-line-art-v2",second["profile_id"]);self.assertNotEqual(first["workflow_sha256"],second["workflow_sha256"])

    def test_v3_proposal_is_disabled_and_based_on_v1(self):
        proposal=json.loads((Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio/proposals/kids-bold-line-art-v3.proposal.json").read_text())
        self.assertEqual("kids-bold-line-art-v1",proposal["base_profile_id"]);self.assertFalse(proposal["enabled"]);self.assertEqual("proposal",proposal["status"]);self.assertEqual("dpmpp_2m",proposal["sampler"]);self.assertEqual("karras",proposal["scheduler"]);self.assertFalse(proposal["postprocessing"]["hard_binary_threshold"]);self.assertFalse(proposal["postprocessing"]["outline_thickening"]);self.assertTrue(proposal["checkpoint_strategy"]["fallback_only"])

    def test_deployed_v3_embedding_readiness_and_token_mapping(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio";profile=root/"profiles/kids-bold-line-art-v3.json";value=json.loads(profile.read_text());embedding=value["embedding"];installed=Path(embedding["path"])
        self.assertTrue(installed.is_file());self.assertEqual(embedding["sha256"],sha256(installed.read_bytes()).hexdigest());self.assertEqual(3819,installed.stat().st_size);self.assertTrue(value["positive_prompt_prefix"].startswith("embedding:color-page"));self.assertEqual("sd15",value["checkpoint_family"]);self.assertEqual("sd15",embedding["compatible_checkpoint_family"])
        class V3Client(Client):
            @staticmethod
            def object_info(url,timeout=3):
                value=Client.object_info(url,timeout);value["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"]=[["DreamShaper.safetensors"]];return value
        ready=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=V3Client).readiness()
        self.assertEqual("embedding_not_loaded",ready["status"])
        class Loaded(V3Client):
            @staticmethod
            def list_embeddings(url,timeout=3):return ["color-page"]
        ready=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Loaded).readiness();self.assertEqual("ready",ready["status"]);self.assertTrue(ready["embedding_exists"]);self.assertTrue(ready["embedding_loaded"]);self.assertTrue(ready["embedding_token_valid"]);self.assertTrue(ready["checkpoint_family_compatible"])

    def test_deployed_v4_uses_only_verified_final_lora_through_shared_loader(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio";profile=root/"profiles/kids-bold-line-art-v4.json";value=json.loads(profile.read_text());lora=value["lora"];installed=Path(lora["path"])
        self.assertEqual("whitebearhands/lineart-lora",lora["repository"]);self.assertEqual("5f9089d145828dd00486c333833aa44b2cf37de7",lora["revision"]);self.assertEqual("MIT",lora["license"]);self.assertEqual("pytorch_lora_weights.safetensors",lora["source_filename"]);self.assertEqual(51058040,installed.stat().st_size);self.assertEqual("a888c0211c9312052a385b0c2551c2271c6125b1fe8ca8feb584a8667c66a299",sha256(installed.read_bytes()).hexdigest())
        self.assertEqual(["whitebearhands-lineart-lora.safetensors"],value["lora_identifiers"]);self.assertIn("embedding:color-page",value["positive_prompt_prefix"]);self.assertIn("lineart_style",value["positive_prompt_prefix"]);self.assertFalse(value["postprocessing"]["hard_binary_threshold"]);self.assertFalse(value["postprocessing"]["outline_thickening"])
        workflow=json.loads(Path(value["workflow_json_path"]).read_text());self.assertEqual("LoraLoader",workflow["8"]["class_type"]);self.assertEqual(["8",0],workflow["5"]["inputs"]["model"]);self.assertEqual(["8",1],workflow["2"]["inputs"]["clip"]);self.assertEqual(1,workflow["4"]["inputs"]["batch_size"])
        class Loaded(Client):
            @staticmethod
            def object_info(url,timeout=3):
                nodes=Client.object_info(url,timeout);nodes["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"]=[["DreamShaper.safetensors"]];nodes["LoraLoader"]={"input":{"required":{"lora_name":[["whitebearhands-lineart-lora.safetensors"]]}}};return nodes
            @staticmethod
            def list_embeddings(url,timeout=3):return ["color-page"]
        ready=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Loaded).readiness();self.assertEqual("ready",ready["status"]);self.assertTrue(ready["lora_exists"]);self.assertTrue(ready["lora_hash_valid"]);self.assertTrue(ready["lora_registered"]);self.assertTrue(ready["lora_trigger_valid"]);self.assertTrue(ready["checkpoint_family_compatible"])
        installation=json.loads((root/"loras/whitebearhands-lineart-lora.installation.json").read_text());self.assertEqual(0,installation["training_checkpoints_installed"])

    def test_deployed_v1_v2_v3_profiles_remain_byte_unchanged(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio/profiles"
        expected={"kids-bold-line-art-v1.json":"c3b76b4c3cb8396292b61bde316fb092bc18d4fb29dbeb2f670a8b14c55746cb","kids-bold-line-art-v2.json":"530255ad90095404d80d17960853c7f257456e37dd65394b8e4628ec3f974139","kids-bold-line-art-v3.json":"ef17bc09c6a814db3e08d2cdd07e078cc987b2613a80173ea2e7c6299d0c4b59"}
        self.assertEqual(expected,{name:sha256((root/name).read_bytes()).hexdigest() for name in expected})

    def test_deployed_v5_checkpoint_trigger_workflow_and_readiness(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio";profile=root/"profiles/kids-bold-line-art-v5.json";value=json.loads(profile.read_text());checkpoint=value["checkpoint"];installed=Path(checkpoint["path"])
        self.assertEqual("artificialguybr/ColoringBookSD",checkpoint["repository"]);self.assertEqual("1a047d2532840546722031dc89cfec12c2f4e8ce",checkpoint["revision"]);self.assertEqual("creativeml-openrail-m",checkpoint["license"]);self.assertEqual(2132625464,installed.stat().st_size);self.assertEqual("c876cc07f3b7f5b0d4bb4275136d63070c6078cee264b66adaf3d16656ac85cb",sha256(installed.read_bytes()).hexdigest());self.assertTrue(value["positive_prompt_prefix"].startswith("in VARPJ1 Coloring Book Art Style"));self.assertEqual([],value["lora_identifiers"])
        workflow=json.loads(Path(value["workflow_json_path"]).read_text());self.assertNotIn("LoraLoader",{x["class_type"] for x in workflow.values()});self.assertEqual(1,workflow["4"]["inputs"]["batch_size"]);self.assertEqual(768,value["sample_resolution"]["width"]);self.assertEqual(992,value["sample_resolution"]["height"]);self.assertEqual("dpmpp_2m",value["sampler"]);self.assertEqual("karras",value["scheduler"]);self.assertFalse(value["postprocessing"]["hard_binary_threshold"])
        class Loaded(Client):
            @staticmethod
            def object_info(url,timeout=3):
                nodes=Client.object_info(url,timeout);nodes["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"]=[["ColoringBookSD-VARPJ1.safetensors"]];return nodes
            @staticmethod
            def list_embeddings(url,timeout=3):return ["color-page"]
        ready=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Loaded).readiness();self.assertEqual("ready",ready["status"]);self.assertTrue(ready["checkpoint_hash_valid"]);self.assertTrue(ready["checkpoint_trigger_valid"]);self.assertTrue(ready["checkpoint_family_compatible"]);self.assertEqual([],ready["loras"])

    def test_v4_profile_and_workflow_remain_byte_unchanged(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio"
        self.assertEqual("d264d0ed57464393789f7be58726caed36d4d9f406b612e43cc79a80a0349269",sha256((root/"profiles/kids-bold-line-art-v4.json").read_bytes()).hexdigest())
        self.assertEqual("a71374a275b287bced6c7606f14d7fc564575c3cbb58240ca1864f625efb5e84",sha256((root/"workflows/kids-bold-line-art-v4.api.json").read_bytes()).hexdigest())

    def test_deployed_v6_is_native_sdxl_without_sd15_assets(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio";profile=root/"profiles/kids-bold-line-art-v6.json";value=json.loads(profile.read_text());checkpoint=value["checkpoint"];lora=value["lora"]
        self.assertEqual("sdxl",value["checkpoint_family"]);self.assertEqual("stabilityai/stable-diffusion-xl-base-1.0",checkpoint["repository"]);self.assertEqual("462165984030d82259a11f4367a4eed129e94a7b",checkpoint["revision"]);self.assertEqual("artificialguybr/ColoringBookRedmond-V2",lora["repository"]);self.assertEqual("0e67e0de2b603db085e525e7f6194b24dc60033d",lora["revision"]);self.assertEqual("ColoringBookAF, Coloring Book",lora["trigger_word"]);self.assertTrue(value["positive_prompt_prefix"].startswith("ColoringBookAF, Coloring Book"));self.assertNotIn("embedding",value);self.assertEqual(["embedding:color-page","whitebearhands-lineart-lora.safetensors","ColoringBookSD-VARPJ1.safetensors"],value["excluded_sd15_assets"])
        self.assertEqual(6938078334,Path(checkpoint["path"]).stat().st_size);self.assertEqual(checkpoint["sha256"],sha256(Path(checkpoint["path"]).read_bytes()).hexdigest());self.assertEqual(170540036,Path(lora["path"]).stat().st_size);self.assertEqual(lora["sha256"],sha256(Path(lora["path"]).read_bytes()).hexdigest())
        workflow=json.loads(Path(value["workflow_json_path"]).read_text());self.assertEqual("CLIPTextEncodeSDXL",workflow["2"]["class_type"]);self.assertEqual("LoraLoader",workflow["8"]["class_type"]);self.assertEqual(1,workflow["4"]["inputs"]["batch_size"]);self.assertEqual(768,value["sample_resolution"]["width"]);self.assertEqual(1024,value["sample_resolution"]["height"]);self.assertFalse(value["generation_bounds"]["refiner"]);self.assertTrue(value["generation_bounds"]["low_vram"])
        class Loaded(Client):
            @staticmethod
            def object_info(url,timeout=3):
                nodes=Client.object_info(url,timeout);nodes["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"]=[["sd_xl_base_1.0.safetensors"]];nodes["LoraLoader"]={"input":{"required":{"lora_name":[["ColoringBookRedmond-V2.safetensors"]]}}};nodes["CLIPTextEncodeSDXL"]={"input":{"required":{"text_g":["STRING"],"text_l":["STRING"],"clip":["CLIP"],"width":["INT"],"height":["INT"],"crop_w":["INT"],"crop_h":["INT"],"target_width":["INT"],"target_height":["INT"]}}};return nodes
        ready=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Loaded).readiness();self.assertEqual("ready",ready["status"]);self.assertTrue(ready["checkpoint_hash_valid"]);self.assertTrue(ready["lora_hash_valid"]);self.assertTrue(ready["checkpoint_family_compatible"])

    def test_v5_profile_and_workflow_remain_byte_unchanged(self):
        root=Path.home()/"JamesOSData/JamesOS/AI/LocalCreativeStudio"
        self.assertEqual("6ac04d931b8934e773ddbf32a4c1ecaaf2e39ceab32051b456aa13791bb07eb4",sha256((root/"profiles/kids-bold-line-art-v5.json").read_bytes()).hexdigest())
        self.assertEqual("44d58495739de9c94a7cd84d2cdd3d67a25824b99ed4b1a859cb3d7b4215a3f6",sha256((root/"workflows/kids-bold-line-art-v5.api.json").read_bytes()).hexdigest())

    def test_single_shared_adapter_writes_valid_local_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile,workflow=self.fixture(root);output=root/"project/samples/outputs"
            provider=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Client)
            events=[];request=LocalAssetRequest("r","coloring_page.line_art","producer","project",{"pages":[{"page_id":"page-1","prompt_id":"prompt-1","positive_prompt":"line art","negative_prompt":"color"}],"output_directory":str(output),"owner_root":str(root/"project"),"width":1024,"height":1280,"operation_event_sink":events.append})
            result=provider.execute(request);self.assertEqual("completed",result.status);self.assertEqual(1,len(result.artifacts));self.assertTrue(result.artifacts[0]["technical_validation"]["valid"]);self.assertTrue(Path(result.artifacts[0]["local_path"]).is_file());self.assertEqual(0,result.external_provider_calls)
            self.assertEqual("instance-a",events[0]["instance_identity"]["instance_id"]);self.assertEqual(200,events[0]["http_status"]);self.assertEqual("prompt-1",events[0]["comfyui_prompt_id"])

    def test_restart_evidence_compares_process_identity_and_missing_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile,_=self.fixture(root)
            class Restarted(Client):
                @staticmethod
                def instance_identity(url,timeout=1):return {"instance_id":"instance-b","main_pid":202,"process_started_at":"Thu 2026-07-23 15:06:28 CDT"}
            evidence=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Restarted).submission_evidence("prompt-1","instance-a")
            self.assertTrue(evidence["instance_changed"]);self.assertFalse(evidence["queue_evidence"]);self.assertFalse(evidence["history_evidence"]);self.assertFalse(evidence["output_evidence"])

    def test_readiness_states_hash_checkpoint_nodes_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile,workflow=self.fixture(root)
            class Offline(Client):
                @staticmethod
                def health(url,timeout=1):return {"running":False}
            self.assertEqual("comfyui_unreachable",ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Offline).readiness()["status"])
            value=json.loads(profile.read_text());value["checkpoint_identifier"]="missing.ckpt";profile.write_text(json.dumps(value));self.assertEqual("checkpoint_missing",ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Client).readiness()["status"])
            value["checkpoint_identifier"]="fixture.ckpt";value["required_custom_nodes"]=["MissingCustomNode"];profile.write_text(json.dumps(value));self.assertEqual("custom_node_missing",ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Client).readiness()["status"])
            value["required_custom_nodes"]=[];value["node_mapping"]["seed"]["node_id"]="99";profile.write_text(json.dumps(value));self.assertEqual("invalid_node_mapping",ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Client).readiness()["status"])
            value["node_mapping"]["seed"]["node_id"]="5";workflow_value=json.loads(workflow.read_text());workflow_value["7"]["class_type"]="NotAnOutput";workflow.write_text(json.dumps(workflow_value));value["workflow_sha256"]=sha256(workflow.read_bytes()).hexdigest();profile.write_text(json.dumps(value));self.assertEqual("output_node_missing",ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Client).readiness()["status"])
            workflow_value["7"]["class_type"]="SaveImage";workflow.write_text(json.dumps(workflow_value));value["workflow_sha256"]=sha256(workflow.read_bytes()).hexdigest();profile.write_text(json.dumps(value));ready=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Client).readiness();self.assertEqual("ready",ready["status"]);self.assertEqual(value["workflow_sha256"],ready["workflow_hash"]);self.assertTrue(ready["configured"]);self.assertEqual(0,ready["gpu_effects"]["external_provider_calls"])

    def test_shared_postprocessor_preserves_raw_binary_cleans_speckles_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);image=Image.new("L",(160,200),255);draw=ImageDraw.Draw(image);draw.rectangle((35,40,125,160),outline=0,width=3);draw.point((80,20),fill=0);data=BytesIO();image.save(data,"PNG")
            result=process_coloring_page(data.getvalue(),root/"raw.png",root/"processed.png",profile_id="kids-bold-line-art-v2",workflow_hash="b"*64,expected_width=160,expected_height=200,parameters={"edge_margin_pixels":8})
            self.assertTrue((root/"raw.png").is_file());self.assertTrue((root/"processed.png").is_file());self.assertNotEqual(result["raw_file_sha256"],result["processed_file_sha256"]);self.assertTrue(result["technical_validation"]["valid"])
            with Image.open(root/"processed.png") as processed:self.assertEqual({0,255},set(processed.getdata()));self.assertEqual(255,processed.getpixel((80,20)))
            self.assertEqual("kids-bold-line-art-v2",json.loads((root/"processed.processing.json").read_text())["profile_id"])

    def test_shared_postprocessor_rejects_large_black_regions_and_unsafe_edges(self):
        for name,paint,reason in (
            ("black",lambda draw:draw.rectangle((20,20,140,180),fill=0),"largest black component"),
            ("edge",lambda draw:draw.line((0,20,0,180),fill=0,width=4),"safe margins"),
            ("gray",lambda draw:draw.rectangle((20,20,140,180),fill=170),"excessive grayscale"),
        ):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);image=Image.new("L",(160,200),255);draw=ImageDraw.Draw(image);paint(draw);data=BytesIO();image.save(data,"PNG")
                result=process_coloring_page(data.getvalue(),root/"raw.png",root/"processed.png",profile_id="kids-bold-line-art-v2",workflow_hash="b"*64,expected_width=160,expected_height=200,parameters={"edge_margin_pixels":8})
                self.assertFalse(result["technical_validation"]["valid"]);self.assertIn(reason,result["technical_validation"]["failed_reasons"])

    def test_v5_white_canvas_padding_repairs_only_margins_not_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);image=Image.new("L",(160,200),255);draw=ImageDraw.Draw(image);draw.rectangle((0,30,120,170),outline=0,width=4);data=BytesIO();image.save(data,"PNG")
            result=process_coloring_page(data.getvalue(),root/"raw.png",root/"processed.png",profile_id="kids-bold-line-art-v5",workflow_hash="c"*64,expected_width=160,expected_height=200,parameters={"hard_binary_threshold":False,"edge_margin_pixels":8,"white_canvas_padding_on_margin_failure":True,"canvas_padding_pixels":16})
            self.assertTrue(result["canvas_padding_applied"]);self.assertFalse(result["semantic_content_modified"]);self.assertTrue(result["technical_validation"]["safe_margins"]);self.assertEqual((160,200),(result["width"],result["height"]))

    def test_v2_profile_is_distinct_and_merges_prompt_prefixes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile,workflow=self.fixture(root);value=json.loads(profile.read_text());value.update(profile_id="kids-bold-line-art-v2",positive_prompt_prefix="STRICT POSITIVE",negative_prompt_prefix="STRICT NEGATIVE");profile.write_text(json.dumps(value))
            class Capture(Client):
                queued=None
                @classmethod
                def queue_prompt(cls,workflow,api_url=None):cls.queued=workflow;return super().queue_prompt(workflow,api_url)
            provider=ComfyUILocalCreativeStudioProvider(profile_path=profile,client=Capture);output=root/"project/samples/outputs";request=LocalAssetRequest("r","coloring_page.line_art","producer","project",{"pages":[{"page_id":"page-001","prompt_id":"prompt-001","positive_prompt":"PAGE POSITIVE","negative_prompt":"PAGE NEGATIVE"}],"output_directory":str(output),"owner_root":str(root/"project"),"width":1024,"height":1280})
            result=provider.execute(request);self.assertEqual("completed",result.status);self.assertIn("STRICT POSITIVE",Capture.queued["2"]["inputs"]["text"]);self.assertIn("PAGE POSITIVE",Capture.queued["2"]["inputs"]["text"]);self.assertIn("STRICT NEGATIVE",Capture.queued["3"]["inputs"]["text"])


if __name__=="__main__":unittest.main()
