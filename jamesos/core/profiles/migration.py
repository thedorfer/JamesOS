from copy import deepcopy
from .models import AgentBinding,Profile

COMMERCE_SHOP_PROFILE={
    "profile_id":"commerce_shop","profile_type":"commerce_shop","display_name":"Commerce Shop","owner":"local-owner","enabled":False,
    "tags":["commerce"],"policy_id":"commerce-human-review-v1",
    "agent_bindings":{"marketplace":AgentBinding("etsy","etsy.commerce_shop"),"fulfillment":AgentBinding("printify","printify.commerce_shop"),"orchestrator":AgentBinding("commerce")},
    "secret_handle_bindings":{"marketplace":"etsy.commerce_shop","fulfillment":"printify.commerce_shop"},
    "configuration":{"sales_channel":"etsy","default_currency":"USD","approval_mode":"single_final","etsy_final_state":"active",
        "human_review_location":"jamesos_listing_preview","preapproval_printify_draft_allowed":True,"publish_policy":"publish_active_after_approval"},
    "protected_resources":[]}

def commerce_shop_migration_plan():
    """Return a public template; deployment values belong outside Git."""
    return Profile(**deepcopy(COMMERCE_SHOP_PROFILE))
