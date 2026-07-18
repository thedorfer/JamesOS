from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from jamesos.services.commerce_copilot import CommerceCopilotService,safe_profile_context


PROFILE={"profile_id":"bagholder-supply","profile_type":"commerce_shop","display_name":"Bagholder Supply Co","configuration":{
    "niche":"market chaos","voice":"dry trading humor","style":"bold terminal","palette":["green","red"],"printify_shop_title":"Bound Shop","printify_shop_id":123,
    "etsy_shop_slug":"BoundEtsy","garment_colors":["Black","White"],"listing_policy":{"tag_count":13},"pricing_policy":{"default_cents":2499},
    "listing_tags":["stock market shirt","bagholder shirt","trader humor tee","investor gift","finance joke shirt","market crash tee","wall street humor","stock trader gift","buy the dip shirt","bear market shirt","bull market tee","investment humor","finance nerd gift"]}}


class CommerceCopilotTests(unittest.TestCase):
    def test_safe_context_is_selected_profile_and_form(self):
        context=safe_profile_context(PROFILE,{"exact_phrase":"HOLD FOREVER","product_brief":"terminal joke"})
        self.assertEqual(context["profile_id"],"bagholder-supply");self.assertEqual(context["destination"]["printify_shop_id"],123)
        self.assertEqual(context["brand"]["niche"],"market chaos");self.assertEqual(context["form"]["exact_phrase"],"HOLD FOREVER")

    def test_structured_suggestions_are_local_and_keep_color_domains_separate(self):
        provider=Mock(side_effect=AssertionError("provider must not be called"))
        model=Mock(return_value=json.dumps({"response":"A bounded idea","exact_phrase":"HOLD THE LINE","product_brief":"Market chaos typography",
            "garment_colors":["Black","White"],"artwork_palette":["acid green","warning red"],"listing_title":"Hold The Line Trader Tee",
            "special_instructions":"Keep artwork high contrast","tags":PROFILE["configuration"]["listing_tags"],"concerns":["Check phrase clearance"]}))
        with tempfile.TemporaryDirectory() as temporary:
            result=CommerceCopilotService(model=model,root=Path(temporary)).message(session_id="session_12345678901234567890",profile=PROFILE,message="Build a concept",form={})
        self.assertEqual(result["garment_colors"],["Black","White"]);self.assertEqual(result["artwork_palette"],["acid green","warning red"])
        self.assertEqual(len(result["tags"]),13);self.assertTrue(result["tags_valid"]);self.assertFalse(result["provider_calls_performed"]);self.assertFalse(result["form_submitted"])
        self.assertIn("Apply all",result["actions"]);provider.assert_not_called()

    def test_session_cannot_switch_profiles(self):
        model=Mock(return_value=json.dumps({"response":"ok","tags":PROFILE["configuration"]["listing_tags"]}))
        with tempfile.TemporaryDirectory() as temporary:
            service=CommerceCopilotService(model=model,root=Path(temporary));session="session_12345678901234567890"
            service.message(session_id=session,profile=PROFILE,message="first",form={})
            changed={**PROFILE,"profile_id":"another-shop"}
            with self.assertRaises(Exception):service.message(session_id=session,profile=changed,message="switch",form={})


if __name__=="__main__":unittest.main()
