from __future__ import annotations

import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.context_dock import NavigationContext,build_navigation,validate_nav_item,validate_navigation_context


def profile(profile_id="bagholder-supply",shop_id=28275232,slug="BagholdersSupplyCo"):
    return {"profile_id":profile_id,"profile_type":"commerce_shop","enabled":True,"display_name":profile_id.title(),"configuration":{"printify_shop_id":shop_id,"printify_shop_title":slug,"etsy_shop_slug":slug}}


class ContextDockTests(unittest.TestCase):
    def test_locked_home_agency_admin_are_always_present_in_order(self):
        for context in (NavigationContext(),NavigationContext(active_view="commerce.new",selected_job_id="job",job_stage="generating"),NavigationContext(active_view="diagnostics",selected_job_id="job",failed=True)):
            items=build_navigation(context);locked=[item["item_id"] for item in items if item["locked"]]
            self.assertEqual(locked,["home","agency","admin"]);self.assertEqual(items[0]["item_id"],"home");self.assertLess([x["item_id"] for x in items].index("agency"),[x["item_id"] for x in items].index("admin"))

    def test_job_context_badges_are_deterministic(self):
        generating=build_navigation(NavigationContext(active_view="commerce.loading",selected_job_id="job",job_stage="generating"));self.assertTrue(any(item["item_id"]=="current-job" and item["badge"]=="progress" for item in generating))
        ready=build_navigation(NavigationContext(active_view="commerce.loading",selected_job_id="job",review_ready=True));self.assertTrue(any(item["label"]=="Review" and item["badge"]=="ready" for item in ready))
        failed=build_navigation(NavigationContext(active_view="commerce.loading",selected_job_id="job",failed=True));self.assertTrue(any(item["view_id"]=="diagnostics" and item["badge"]=="warning" for item in failed))
        pending=build_navigation(NavigationContext(active_view="commerce.loading",selected_job_id="job",pending_approval=True));self.assertTrue(any(item["badge"]=="pending_approval" for item in pending))

    def test_product_studio_has_human_readable_context_label(self):
        self.assertEqual(next(item for item in build_navigation(NavigationContext(active_view="commerce.new")) if item["view_id"]=="commerce.new")["label"],"Product Studio")

    def test_agents_cannot_override_locked_navigation_or_unknown_views(self):
        for suggestion in ({"item_id":"home","label":"Replace Home","view_id":"commerce.new"},{"item_id":"x","label":"Fake","view_id":"not.registered"},{"item_id":"x","label":"Admin copy","view_id":"admin.home"}):
            with self.assertRaises(Exception):build_navigation(NavigationContext(agent_suggestions=[suggestion]))
        with self.assertRaises(Exception):validate_navigation_context({"active_view":"unknown"})
        with self.assertRaises(Exception):validate_nav_item({"item_id":"x","label":"X","view_id":"unknown"})

    def test_pointer_interaction_preserves_previous_order(self):
        previous=build_navigation(NavigationContext(active_view="commerce.new"));held=build_navigation(NavigationContext(active_view="jobs.list",selected_job_id="job",pointer_interaction=True,previous_navigation=previous))
        self.assertEqual(held,previous)
        transitioned=build_navigation(NavigationContext(active_view="jobs.list",selected_job_id="job",pointer_interaction=False,previous_navigation=previous));self.assertNotEqual(transitioned,previous)

    def test_shell_renders_locked_dock_agency_admin_and_transition_guard(self):
        rows=[profile(),profile("unitystitches",9437076,"UnityStitches")];provider=Mock(side_effect=AssertionError("navigation cannot call providers"))
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=commerce.new").text
        for required in ("id='context-dock'","data-nav-id='home'","data-nav-id='agency'","data-nav-id='admin'",">Home<",">The Agency<",">Admin<","Active agents","Current runs","Pending approvals","Recent results","Agent tools","Profiles · Service status · Themes · Layouts · Permissions · Diagnostics","dockInteracting","lastDockKey","pointerdown","pendingDockState","pending_approval"):
            with self.subTest(required=required):self.assertIn(required,text)
        provider.assert_not_called();self.assertLess(text.index("data-nav-id='home'"),text.index("data-nav-id='agency'"));self.assertLess(text.index("data-nav-id='agency'"),text.index("data-nav-id='admin'"))


if __name__=="__main__":unittest.main()
