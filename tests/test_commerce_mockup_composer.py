from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image,ImageDraw
from jamesos.services.commerce_mockup_composer import DeterministicMockupComposer,MockupTemplateRegistry

class O:
 def __init__(self,root):self.root=root
 def _path(self,j):return self.root/j/"orchestrator-state.json"
 def load(self,j):return json.loads(self._path(j).read_text())

class ComposerTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();root=Path(self.t.name);self.templates=root/"templates";self.templates.mkdir();self.job="product-test";job=root/self.job;job.mkdir()
  art=job/"art.png";im=Image.new("RGBA",(100,80),(0,0,0,0));ImageDraw.Draw(im).rectangle((10,10,90,70),fill=(255,0,0,230));im.save(art)
  import hashlib
  state={"job_id":self.job,"order_status":"not_created","evidence":{"selection":{"selected":{"png_path":str(art),"png_sha256":hashlib.sha256(art.read_bytes()).hexdigest()}}}};(job/"orchestrator-state.json").write_text(json.dumps(state));self.registry=MockupTemplateRegistry(self.templates);self.composer=DeterministicMockupComposer(O(root),self.registry)
  for role,category,color in (("clean_product","product-only","white"),("male_model","male","blue"),("female_model","female","pink")):
   base=Image.new("RGBA",(400,400),color);mask=Image.new("L",(400,400),0);ImageDraw.Draw(mask).polygon([(90,80),(310,95),(300,330),(100,320)],fill=255);base.save(self.templates/f"{role}.png");mask.save(self.templates/f"{role}-mask.png")
   self.registry.register({"template_id":role,"version":"1.0","model_category":category,"subject_role":role,"template_kind":"locally_generated","production_allowed":True,"pose":"front","garment_style":"tee","garment_color":color,"base_image":f"{role}.png","shirt_mask":f"{role}-mask.png","print_area":[[130,130],[270,135],[265,280],[135,275]],"provenance":{"source":"synthetic test","creator":"test","license":"CC0-test","created_at":"now","notes":"synthetic"}})
 def tearDown(self):self.t.cleanup()
 def test_registry_validation_and_deterministic_perspective_mask_hashing(self):
  with self.assertRaises(Exception):self.registry.register({"template_id":"bad","version":"x"})
  first=self.composer.compose(self.job,"clean_product","1.0","clean_product");second=self.composer.compose(self.job,"clean_product","1.0","clean_product");self.assertEqual(first["outputs"][0]["output_sha256"],second["outputs"][0]["output_sha256"])
  path=self.composer.asset(self.job,first["outputs"][0]["asset_id"]);out=Image.open(path).convert("RGB");self.assertEqual(out.size,(400,400));self.assertEqual(out.getpixel((20,20)),(255,255,255));self.assertNotEqual(out.getpixel((200,200)),(255,255,255))
 def test_roles_primary_order_idempotent_approval_and_no_providers(self):
  for role in ("clean_product","male_model","female_model"):self.composer.compose(self.job,role,"1.0",role)
  value=self.composer.public(self.job);self.assertEqual(value["stage"],"mockups_review_ready");ids=[x["asset_id"] for x in reversed(value["outputs"])]
  preview=self.composer.approve(self.job,ids,ids[1]);self.assertTrue(preview["confirmation_required"]);done=self.composer.approve(self.job,ids,ids[1],True);again=self.composer.approve(self.job,ids,ids[1],True)
  self.assertEqual(done["proposal_sha256"],again["proposal_sha256"]);self.assertEqual([x["asset_id"] for x in done["ordered_mockups"]],ids);self.assertTrue(done["ordered_mockups"][1]["primary"]);self.assertEqual(done["message"],"Mockups approved locally. Etsy and Printify have not been updated.");self.assertFalse(done["etsy_updated"]);self.assertFalse(done["printify_updated"]);self.assertFalse(done["order_created"]);self.assertEqual(len(list((Path(self.t.name)/self.job/"mockup-composer"/"review").glob("proposal-*.json"))),1)
 def test_source_ownership_and_role_coverage_fail_closed(self):
  state=O(Path(self.t.name)).load(self.job);state["evidence"]["selection"]["selected"]["png_sha256"]="0"*64;O(Path(self.t.name))._path(self.job).write_text(json.dumps(state))
  with self.assertRaises(Exception):self.composer.compose(self.job,"clean_product","1.0","clean_product")
 def test_placeholder_cannot_satisfy_production_approval(self):
  for role in ("clean_product","male_model","female_model"):
   item=self.registry.get(role,"1.0");item["template_kind"]="placeholder";item["production_allowed"]=False;self.registry.register(item);self.composer.compose(self.job,role,"1.0",role)
  value=self.composer.public(self.job);ids=[x["asset_id"] for x in value["outputs"]]
  with self.assertRaises(Exception):self.composer.approve(self.job,ids,ids[0],True)

if __name__=="__main__":unittest.main()
