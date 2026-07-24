from io import BytesIO
from pathlib import Path
import tempfile,unittest
from PIL import Image
from jamesos.services.commerce_mockup_template_ingest import MockupTemplateIngestService
def png(size,mode="RGBA"):
 b=BytesIO();Image.new(mode,size,255).save(b,"PNG");return b.getvalue()
class IngestTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.s=MockupTemplateIngestService(Path(self.t.name));self.meta={"display_name":"Licensed male","model_category":"male","subject_role":"male_model","template_kind":"licensed_photo","production_allowed":True,"pose":"front","garment_style":"tee","garment_color":"black","print_area":[[100,100],[500,100],[500,600],[100,600]],"provenance":{"source":"fixture","creator":"tester","license":"licensed","created_at":"now","notes":"test"}}
 def tearDown(self):self.t.cleanup()
 def test_production_ingestion_hashes_and_registry(self):
  v=self.s.ingest(template_id="licensed-male",version="1.0",base_bytes=png((800,800)),mask_bytes=png((800,800),"L"),metadata=self.meta,eligibility_confirmed=True);self.assertTrue(v["production_allowed"]);self.assertEqual(len(v["base_sha256"]),64);self.assertEqual(len(self.s.registry.list()["templates"]),1)
 def test_provenance_confirmation_path_mask_and_polygon_fail_closed(self):
  with self.assertRaises(Exception):self.s.ingest(template_id="../bad",version="1.0",base_bytes=png((800,800)),mask_bytes=png((800,800),"L"),metadata=self.meta,eligibility_confirmed=True)
  with self.assertRaises(Exception):self.s.ingest(template_id="bad-mask",version="1.0",base_bytes=png((800,800)),mask_bytes=png((700,800),"L"),metadata=self.meta,eligibility_confirmed=True)
  bad={**self.meta,"print_area":[[1,2]]};
  with self.assertRaises(Exception):self.s.ingest(template_id="bad-poly",version="1.0",base_bytes=png((800,800)),mask_bytes=png((800,800),"L"),metadata=bad,eligibility_confirmed=True)
  missing={**self.meta,"provenance":{}}
  with self.assertRaises(Exception):self.s.ingest(template_id="missing-license",version="1.0",base_bytes=png((800,800)),mask_bytes=png((800,800),"L"),metadata=missing,eligibility_confirmed=True)
if __name__=="__main__":unittest.main()
