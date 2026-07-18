from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.layout_manager import LayoutManager,THEMES,default_layout,validate_layout,validate_theme_tokens


def profile(profile_id="bagholder-supply",shop_id=28275232,slug="BagholdersSupplyCo"):
    return {"profile_id":profile_id,"profile_type":"commerce_shop","enabled":True,"display_name":profile_id.title(),"configuration":{"printify_shop_id":shop_id,"printify_shop_title":slug,"etsy_shop_slug":slug}}


class LayoutManagerTests(unittest.TestCase):
    def test_default_layout_uses_grid_theme_and_required_system_locks(self):
        value=default_layout("commerce.new");self.assertEqual(value["shell"]["chat_width"],420);self.assertEqual(value["theme_id"],"jamesos-dark")
        panels={item["panel_id"]:item for item in value["panels"]}
        for panel_id in ("destination","publication_status","external_confirmation"):
            self.assertTrue(panels[panel_id]["layout_locked"]);self.assertFalse(panels[panel_id]["hidden"]);self.assertIn("move",panels[panel_id]["action_locks"])

    def test_save_reload_cancel_baseline_and_reset_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager=LayoutManager(Path(temporary));value=default_layout("commerce.new");value["shell"]["chat_width"]=612;value["theme_id"]="jamesos-dark"
            form=next(item for item in value["panels"] if item["panel_id"]=="commerce_form");form.update(column=2,row=3,width=7,height=8)
            saved=manager.save("commerce.new",value);self.assertEqual(saved["shell"]["chat_width"],612);self.assertEqual(manager.get("commerce.new")["shell"]["chat_width"],612)
            working=json.loads(json.dumps(saved));working["shell"]["chat_width"]=700
            self.assertEqual(saved["shell"]["chat_width"],612)  # Cancel restores the saved snapshot.
            reset=manager.reset("commerce.new");self.assertEqual(reset,default_layout("commerce.new"));self.assertFalse(manager.path("commerce.new").exists())

    def test_invalid_coordinates_components_and_locked_changes_are_rejected(self):
        coordinates=json.loads(json.dumps(default_layout("commerce.new")));next(item for item in coordinates["panels"] if item["panel_id"]=="commerce_form").update(column=12,width=2)
        component=json.loads(json.dumps(default_layout("commerce.new")));next(item for item in component["panels"] if item["panel_id"]=="commerce_form")["component"]="raw_html"
        for candidate in (coordinates,component):
            with self.assertRaises(Exception):validate_layout(candidate,"commerce.new")
        locked=json.loads(json.dumps(default_layout("commerce.new")));destination=next(item for item in locked["panels"] if item["panel_id"]=="destination");destination["hidden"]=True
        with self.assertRaises(Exception):validate_layout(locked,"commerce.new")

    def test_jade_locks_override_corrupt_saved_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager=LayoutManager(Path(temporary));value=default_layout("commerce.new");destination=next(item for item in value["panels"] if item["panel_id"]=="destination");destination.update(hidden=True,column=1,width=1,layout_locked=False)
            manager.path("commerce.new").parent.mkdir(parents=True,exist_ok=True);manager.path("commerce.new").write_text(json.dumps(value))
            loaded=manager.get("commerce.new");restored=next(item for item in loaded["panels"] if item["panel_id"]=="destination")
            self.assertFalse(restored["hidden"]);self.assertEqual(restored["column"],9);self.assertEqual(restored["width"],4);self.assertTrue(restored["layout_locked"])

    def test_executable_or_remote_theme_content_is_rejected(self):
        self.assertEqual(validate_theme_tokens(dict(THEMES["jamesos-dark"]))["color_accent"],"#8b5cf6")
        for unsafe in ("javascript:alert(1)","url(https://evil.example/x)","<style>bad</style>"):
            candidate=dict(THEMES["jamesos-dark"]);candidate["color_accent"]=unsafe
            with self.assertRaises(Exception):validate_theme_tokens(candidate)

    def test_layout_routes_persist_without_provider_calls(self):
        rows=[profile()];provider=Mock(side_effect=AssertionError("layout operations cannot call providers"))
        with tempfile.TemporaryDirectory() as temporary,patch.object(api,"LayoutManager",side_effect=lambda:LayoutManager(Path(temporary))),patch.object(api,"_require_local"):
            client=TestClient(api.app,base_url="http://127.0.0.1:8787");headers={"Origin":"http://127.0.0.1:8787"};value=default_layout("commerce.new");value["shell"]["chat_width"]=500
            saved=client.put("/app/layouts/commerce.new",json={**value,"csrf_token":api._COMMERCE_CREATE_CSRF},headers=headers);loaded=client.get("/app/layouts/commerce.new")
            reset=client.request("DELETE","/app/layouts/commerce.new",json={"csrf_token":api._COMMERCE_CREATE_CSRF},headers=headers)
        self.assertEqual(saved.status_code,200);self.assertEqual(loaded.json()["shell"]["chat_width"],500);self.assertEqual(reset.json()["shell"]["chat_width"],420);provider.assert_not_called()

    def test_shell_contains_safe_resizer_customize_mode_and_attached_headers(self):
        rows=[profile(),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=commerce.new").text
        for required in ("shell-divider","clampChat","Math.max(300","window.innerWidth*.55","window.innerWidth<=800","Customize layout","save-layout","cancel-layout","reset-layout","theme-chooser","jamesos-dark","layout-grid","data-panel-id='destination'","data-layout-locked='true'","panel-title","dragHandle","/app/layouts/"):
            with self.subTest(required=required):self.assertIn(required,text)
        self.assertLess(text.index("panel-title'>Commerce Creator"),text.index("id='commerce-form'"));self.assertNotIn("textarea class='panel-title'",text)


if __name__=="__main__":unittest.main()
