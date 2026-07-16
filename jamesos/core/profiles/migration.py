from copy import deepcopy
from .models import AgentBinding,Profile
UNITYSTITICHES_PROFILE={
    "profile_id":"unitystitches","profile_type":"commerce_shop","display_name":"UnityStitches","owner":"James","enabled":True,"tags":["commerce","etsy","printify"],"policy_id":"commerce-human-review-v1",
    "agent_bindings":{"marketplace":AgentBinding("etsy","etsy.unitystitches"),"fulfillment":AgentBinding("printify","printify.unitystitches"),"orchestrator":AgentBinding("commerce")},
    "secret_handle_bindings":{"marketplace":"etsy.unitystitches","fulfillment":"printify.unitystitches"},
    "configuration":{"printify_shop_id":9437076,"sales_channel":"etsy","default_currency":"USD","approval_mode":"single_final","etsy_final_state":"active","human_review_location":"jamesos_listing_preview","preapproval_printify_draft_allowed":True,"publish_policy":"publish_active_after_approval","default_mockup_policy":"all_current_mockups","pricing_policy_reference":"unitystitches-pricing-v1","listing_policy_reference":"unitystitches-listing-v1"},
    "protected_resources":["printify:product:6a57eaa752f2c3e4700dbf23"]}
def unitystitches_migration_plan():return Profile(**deepcopy(UNITYSTITICHES_PROFILE))
