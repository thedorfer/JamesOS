from copy import deepcopy
from datetime import datetime
import unittest

from jamesos.core.commerce.proposal import canonical_proposal_sha256,compile_public_proposal


class CommerceProposalTests(unittest.TestCase):
    def fields(self):
        return {"job_id":"job-fixture","profile_binding_reference":"commerce-profile:opaque","artwork_sha256":"a"*64,"artwork_phrase":"PUBLIC PHRASE",
            "colors":["White","Black","Dark Grey Heather"],"sizes":["S","M","L","XL","2XL","3XL"],"enabled_variant_count":18,
            "enabled_variants":list(range(18,0,-1)),"placement":{"x":.5,"y":.46,"scale":.85,"angle":0},"title":"Public title",
            "description":"Public description","tags":[f"public tag {item}" for item in range(1,14)],"price_cents":2499,"currency":"USD",
            "product_model":"Public model","print_provider":"Public provider","expected_marketplace":"Marketplace","expected_final_state":"inactive",
            "mockups":[{"color":color,"downloaded_sha256":str(index)*64,"verified":True} for index,color in enumerate(("White","Black","Dark Grey Heather"),1)],
            "warnings":["Second warning","First warning"],"required_manual_confirmations":["Review price","Review artwork"],
            "publication_status":"not_published","order_status":"not_created","provider_draft_status":"unpublished_job_owned_draft"}

    def test_hash_is_deterministic_and_excludes_presentation_fields(self):
        first=compile_public_proposal(self.fields(),generated_at="2026-01-01T00:00:00Z")
        second=compile_public_proposal(self.fields(),generated_at="2027-01-01T00:00:00Z")
        second["review_path"]="/different/absolute/path.html"
        self.assertEqual(first["proposal_sha256"],canonical_proposal_sha256(second))
        reordered=self.fields();reordered["tags"].reverse();reordered["colors"].reverse();reordered["mockups"].reverse()
        self.assertEqual(first["proposal_sha256"],compile_public_proposal(reordered,generated_at="later")["proposal_sha256"])

    def test_every_approval_bound_change_changes_hash(self):
        base=compile_public_proposal(self.fields(),generated_at="now")["proposal_sha256"]
        mutations={"title":lambda value:value.update(title="Changed"),"description":lambda value:value.update(description="Changed"),
            "tag":lambda value:value["tags"].__setitem__(0,"changed tag"),"price":lambda value:value.update(price_cents=2500),
            "artwork":lambda value:value.update(artwork_sha256="b"*64),"mockup":lambda value:value["mockups"][0].update(downloaded_sha256="f"*64),
            "placement":lambda value:value["placement"].update(scale=.86),"variant":lambda value:value["enabled_variants"].__setitem__(0,99),
            "destination":lambda value:value.update(expected_marketplace="Other"),"final_state":lambda value:value.update(expected_final_state="active")}
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                fields=deepcopy(self.fields());mutate(fields)
                self.assertNotEqual(base,compile_public_proposal(fields,generated_at="now")["proposal_sha256"])


if __name__=="__main__":unittest.main()
