from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from jamesos.services import product_orchestrator
from jamesos.services.commerce_artwork import provider_free_preflight,render_typography_candidates


PHRASE="UNREALIZED LOSSES\nBUILD CHARACTER"
PROFILE={"profile_id":"bagholder-supply","profile_type":"commerce_shop","enabled":True,"configuration":{"printify_shop_id":123,"etsy_shop_slug":"shop","default_garment_colors":["Black","White"],"artwork_palette":["acid green","warning red"]}}


class CommerceArtworkTests(unittest.TestCase):
    def test_multiline_transparent_print_ready_candidates_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(product_orchestrator,"ROOT",Path(temporary)):
            result=render_typography_candidates(phrase=PHRASE,profile=PROFILE)
            self.assertEqual(result["exact_phrase"],PHRASE);self.assertEqual(result["candidate_count"],3);self.assertFalse(result["decorative_generation_performed"])
            self.assertTrue(all(row["eligible"] for row in result["candidates"]));self.assertTrue(all(row["generation_method"]=="deterministic_local_typography" for row in result["candidates"]));self.assertTrue(all((row["width"],row["height"])==(4500,5400) for row in result["candidates"]));self.assertTrue(all(row["transparency_present"] and row["safe_margin_result"]=="pass" for row in result["candidates"]));self.assertTrue(all(row["palette_summary"]==PROFILE["configuration"]["artwork_palette"] for row in result["candidates"]));self.assertNotEqual(PROFILE["configuration"]["default_garment_colors"],result["candidates"][0]["palette_summary"])
            files=list(Path(temporary).rglob("*.png"));self.assertGreaterEqual(len(files),4)
            with Image.open(next(path for path in files if path.name.startswith("prompt_centered"))) as image:
                self.assertEqual(image.size,(4500,5400));self.assertEqual(image.mode,"RGBA");self.assertAlmostEqual(image.info["dpi"][0],300,delta=1)

    def test_profile_colors_bypass_artwork_palette_prompt_color_detection(self):
        brief=product_orchestrator.normalize_prompt("Exact phrase:\n"+PHRASE+"\n\nArtwork palette acid green and warning red.",garment_colors=["Black","White"])
        self.assertEqual(brief["garment_colors"],["Black","White"]);self.assertEqual(brief["color_resolution"]["unresolved_colors"],[])

    def test_provider_free_preflight_fails_closed_and_passes_complete_job(self):
        selected={"candidate_id":"c","quality_checks":{"hard_dimensions":True,"hard_valid_transparency":True,"hard_safe_bounds":True}}
        state={"shop_id":123,"commerce_profile_id":"bagholder-supply","blueprint_id":12,"print_provider_id":29,"destination":{"printify_shop_id":123,"etsy_shop_slug":"shop"},"product_brief":{"exact_phrase":PHRASE,"brief":"Typography brief","requested_listing_title":"Unrealized Losses Shirt","special_instructions":"Transparent unpublished draft; no order"},"evidence":{"selection":{"selected":selected},"listing":{"title":"Unrealized Losses Shirt","description":"A typography-led shirt.","tags":[f"market tag {i}" for i in range(13)]}},"publish_status":"not_published","order_status":"not_created"}
        passed=provider_free_preflight(state,PROFILE,credential_configured=True);self.assertTrue(passed["passed"]);self.assertFalse(passed["provider_contacted"])
        for change,code in (({"destination":{}},"destination_bound"),({"blueprint_id":None},"product_mapping_configured"),({"evidence":{"selection":{"selected":{}},"listing":state["evidence"]["listing"]}},"local_candidate_exists")):
            failed=provider_free_preflight({**state,**change},PROFILE,credential_configured=True);self.assertFalse(failed["passed"]);self.assertIn(code,failed["failure_codes"]);self.assertFalse(failed["provider_contacted"])

    def test_no_font_binary_is_committed(self):
        extensions={".ttf",".otf",".woff",".woff2"};self.assertFalse([path for path in Path(".").rglob("*") if path.is_file() and path.suffix.casefold() in extensions and ".git" not in path.parts])


if __name__=="__main__":unittest.main()
