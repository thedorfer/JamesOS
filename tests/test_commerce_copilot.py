from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from jamesos.services.commerce_copilot import CommerceCopilotService,parse_json_object,safe_profile_context
from jamesos.services import ollama_service


PROFILE={"profile_id":"bagholder-supply","profile_type":"commerce_shop","display_name":"Bagholder Supply Co","configuration":{
    "niche":"market chaos","voice":"dry trading humor","style":"bold terminal","palette":["green","red"],"printify_shop_title":"Bound Shop","printify_shop_id":123,
    "etsy_shop_slug":"BoundEtsy","garment_colors":["Black","White"],"listing_policy":{"tag_count":13},"pricing_policy":{"default_cents":2499},
    "listing_tags":["stock market shirt","bagholder shirt","trader humor tee","investor gift","finance joke shirt","market crash tee","wall street humor","stock trader gift","buy the dip shirt","bear market shirt","bull market tee","investment humor","finance nerd gift"]}}


class CommerceCopilotTests(unittest.TestCase):
    def response(self,**changes):
        suggestions={"exact_phrase":"HOLD THE LINE","product_brief":"Market chaos typography","listing_title":"Hold The Line Trader Tee",
            "special_instructions":"Keep artwork high contrast","garment_colors":["Black","White"],"artwork_palette":["acid green","warning red"],
            "listing_tags":PROFILE["configuration"]["listing_tags"],"risk_notes":["Check phrase clearance"]};suggestions.update(changes)
        return {"message":"A bounded idea","suggestions":suggestions}

    def test_bounded_parser_accepts_direct_fenced_leading_and_trailing_json(self):
        value=self.response();raw=json.dumps(value)
        for text in (raw,f"```json\n{raw}\n```",f"Here is the result:\n{raw}",f"{raw}\nReview before use."):
            with self.subTest(text=text[:20]):self.assertEqual(parse_json_object(text),value)

    def test_safe_context_is_selected_profile_and_form(self):
        context=safe_profile_context(PROFILE,{"exact_phrase":"HOLD FOREVER","product_brief":"terminal joke"})
        self.assertEqual(context["profile_id"],"bagholder-supply");self.assertEqual(context["destination"]["printify_shop_id"],123)
        self.assertEqual(context["brand"]["niche"],"market chaos");self.assertEqual(context["form"]["exact_phrase"],"HOLD FOREVER")

    def test_structured_suggestions_are_local_and_keep_color_domains_separate(self):
        provider=Mock(side_effect=AssertionError("provider must not be called"))
        model=Mock(return_value=json.dumps(self.response()))
        with tempfile.TemporaryDirectory() as temporary:
            result=CommerceCopilotService(model=model,readiness=lambda:{"ready":True},root=Path(temporary)).message(session_id="session_12345678901234567890",profile=PROFILE,message="Build a concept",form={})
        self.assertEqual(result["suggestions"]["garment_colors"],["Black","White"]);self.assertEqual(result["suggestions"]["artwork_palette"],["acid green","warning red"])
        self.assertEqual(len(result["suggestions"]["listing_tags"]),13);self.assertTrue(result["tags_valid"]);self.assertNotIn("provider",json.dumps(result).casefold())
        self.assertIn("Apply all",result["actions"]);provider.assert_not_called()

    def test_malformed_response_is_repaired_once_and_short_tags_are_supplemented(self):
        repaired=self.response(listing_tags=["stock market shirt","bagholder shirt","trader humor tee"])
        model=Mock(side_effect=["not json at all",json.dumps(repaired)])
        with tempfile.TemporaryDirectory() as temporary:
            result=CommerceCopilotService(model=model,readiness=lambda:{"ready":True},root=Path(temporary)).message(session_id="session_12345678901234567890",profile=PROFILE,message="Build",form={})
        self.assertEqual(model.call_count,2);self.assertEqual(len(result["suggestions"]["listing_tags"]),13)
        self.assertEqual(len({x.casefold() for x in result["suggestions"]["listing_tags"]}),13);self.assertFalse(result["used_local_fallback"])

    def test_two_malformed_responses_use_visible_fallback_without_raw_output(self):
        raw="PRIVATE RAW MODEL OUTPUT <<<"
        model=Mock(side_effect=[raw,"still not json"])
        with tempfile.TemporaryDirectory() as temporary,patch("jamesos.services.commerce_copilot.handle_error") as diagnostic:
            result=CommerceCopilotService(model=model,readiness=lambda:{"ready":True},root=Path(temporary)).message(session_id="session_12345678901234567890",profile=PROFILE,message="Remember my request",form={})
            saved=json.loads((Path(temporary)/"session_12345678901234567890.json").read_text())
        self.assertEqual(model.call_count,2);self.assertTrue(result["used_local_fallback"]);self.assertTrue(result["safe_warning"]);diagnostic.assert_called_once()
        self.assertNotIn(raw,json.dumps(result));self.assertEqual(saved["messages"][-1]["user"],"Remember my request");self.assertNotIn(raw,json.dumps(saved))
        self.assertIn("local fallback",result["message"].casefold());self.assertEqual(len(result["suggestions"]["listing_tags"]),13)

    def test_unrecoverable_tag_pool_omits_tags_and_adds_risk_note(self):
        weak={**PROFILE,"configuration":{**PROFILE["configuration"],"listing_tags":[]}}
        response=self.response(listing_tags=["bad"," "])
        with tempfile.TemporaryDirectory() as temporary:
            result=CommerceCopilotService(model=Mock(return_value=json.dumps(response)),readiness=lambda:{"ready":True},root=Path(temporary)).message(session_id="session_12345678901234567890",profile=weak,message="Build",form={})
        self.assertNotIn("listing_tags",result["suggestions"]);self.assertFalse(result["tags_valid"]);self.assertTrue(any("omitted" in x for x in result["suggestions"]["risk_notes"]))

    def test_ollama_structured_format_is_sent_server_side(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=json.dumps({"response":"{}"}).encode()
        with patch.object(ollama_service,"get_config",return_value={"ollama":{"host":"http://desktop:11434","model":"model","timeout_seconds":5}}),patch.object(ollama_service.urllib.request,"urlopen",return_value=response),patch.object(ollama_service.urllib.request,"Request",wraps=ollama_service.urllib.request.Request) as request:
            ollama_service.ask_ollama("prompt",format_schema={"type":"object"})
        payload=json.loads(request.call_args.kwargs["data"]);self.assertEqual(payload["format"],{"type":"object"});self.assertEqual(request.call_args.args[0],"http://desktop:11434/api/generate")

    def test_session_cannot_switch_profiles(self):
        model=Mock(return_value=json.dumps({"message":"ok","listing_tags":PROFILE["configuration"]["listing_tags"]}))
        with tempfile.TemporaryDirectory() as temporary:
            service=CommerceCopilotService(model=model,readiness=lambda:{"ready":True},root=Path(temporary));session="session_12345678901234567890"
            service.message(session_id=session,profile=PROFILE,message="first",form={})
            changed={**PROFILE,"profile_id":"another-shop"}
            with self.assertRaises(Exception):service.message(session_id=session,profile=changed,message="switch",form={})

    def test_readiness_failure_is_safe_and_model_is_not_called(self):
        model=Mock()
        with tempfile.TemporaryDirectory() as temporary:
            service=CommerceCopilotService(model=model,readiness=Mock(side_effect=ConnectionError("private desktop cause")),root=Path(temporary))
            with self.assertRaises(Exception) as raised:service.message(session_id="session_12345678901234567890",profile=PROFILE,message="idea",form={})
        self.assertEqual(raised.exception.user_message,"Product Studio is temporarily unavailable because the local AI service is not ready.");model.assert_not_called()


if __name__=="__main__":unittest.main()
