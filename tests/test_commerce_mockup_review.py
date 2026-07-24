from __future__ import annotations
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image

from jamesos.services.commerce_mockup_review import MockupReviewService

def image(color):
    out=BytesIO();Image.new("RGB",(320,240),color).save(out,"JPEG");return out.getvalue()

class Response:
    def __init__(self,content):self.content=content
    def raise_for_status(self):pass
class Session:
    def __init__(self,values):self.values=values;self.calls=[]
    def get(self,url,timeout):self.calls.append(url);return Response(self.values[url])
class Client:
    def __init__(self,images):self.images=images;self.reads=0;self.writes=0
    def get_product(self,shop,product):self.reads+=1;return {"id":product,"images":self.images}
class Orchestrator:
    def __init__(self,root):self.root=root
    def _path(self,job):return self.root/job/"orchestrator-state.json"
    def load(self,job):return json.loads(self._path(job).read_text())

class MockupReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.job="product-fixture"
        path=self.root/self.job/"orchestrator-state.json";path.parent.mkdir();path.write_text(json.dumps({"job_id":self.job,"shop_id":28275232,"order_status":"not_created","destination":{"etsy_shop_slug":"BagholdersSupplyCo"},"evidence":{"draft":{"printify_product_id":"product-existing"},"selection":{"selected":{"png_sha256":"art-sha"}}}}))
        self.urls=[f"https://images.printify.com/mockup/product/{i}/fixture.jpg" for i in range(3)]
        self.images=[{"src":self.urls[0],"mockup_id":"clean-front","position":"front","is_default":True,"variant_ids":[1]}, {"src":self.urls[1],"mockup_id":"male-model-front","position":"front","variant_ids":[1]}, {"src":self.urls[2],"mockup_id":"female-model-front","position":"front","variant_ids":[1]}]
        self.client=Client(self.images);self.service=MockupReviewService(Orchestrator(self.root),client=self.client,session=Session(dict(zip(self.urls,[image("white"),image("blue"),image("pink")]))))
    def tearDown(self):self.temp.cleanup()
    def test_read_only_intake_records_complete_evidence_and_sync_warning(self):
        value=self.service.refresh(self.job);self.assertEqual(len(value["mockups"]),3);self.assertIsNone(value["sync_warning"]);self.assertEqual(self.client.reads,1);self.assertEqual(self.client.writes,0)
        for item in value["mockups"]:self.assertEqual(item["dimensions"],[320,240]);self.assertEqual(len(item["sha256"]),64);self.assertTrue(item["source_url"].startswith("https://images.printify.com/"));self.assertEqual(item["variant_ids"],[1])
    def test_one_image_discloses_unsynchronized_library(self):
        self.client.images=self.images[:1];value=self.service.refresh(self.job);self.assertIn("has not synchronized",value["sync_warning"]);self.assertEqual(len(value["mockups"]),1)
    def test_order_primary_roles_and_local_approval_are_immutable_and_provider_free(self):
        value=self.service.refresh(self.job);roles=["female_model","clean_front","male_model"];selected=[{"asset_id":item["asset_id"],"role":role} for item,role in zip(reversed(value["mockups"]),roles)]
        preview=self.service.prepare(self.job,selected,confirmed=False);self.assertTrue(preview["confirmation_required"]);self.assertFalse((self.root/self.job/"mockup-review"/"approval.json").exists())
        done=self.service.prepare(self.job,selected,confirmed=True);again=self.service.prepare(self.job,selected,confirmed=True)
        self.assertEqual(done["proposal_sha256"],again["proposal_sha256"]);self.assertEqual(done["ordered_mockups"][0]["asset_id"],selected[0]["asset_id"]);self.assertTrue(done["ordered_mockups"][0]["primary"]);self.assertEqual(done["message"],"Mockups approved locally. Etsy has not been updated.");self.assertFalse(done["etsy_updated"]);self.assertFalse(done["order_created"]);self.assertEqual(self.client.writes,0)
        proposals=list((self.root/self.job/"mockup-review").glob("proposal-*.json"));self.assertEqual(len(proposals),1)
    def test_incomplete_or_duplicate_roles_fail_closed(self):
        value=self.service.refresh(self.job);items=value["mockups"]
        with self.assertRaises(Exception):self.service.prepare(self.job,[{"asset_id":items[0]["asset_id"],"role":"clean_front"}],confirmed=True)
        with self.assertRaises(Exception):self.service.prepare(self.job,[{"asset_id":x["asset_id"],"role":"clean_front"} for x in items],confirmed=True)

if __name__=="__main__":unittest.main()
