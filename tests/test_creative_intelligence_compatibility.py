from __future__ import annotations

import unittest

from creative_intelligence.services.compatibility_service import assess_compatibility
from creative_intelligence.services.scoring_service import rank_candidates


class CreativeIntelligenceCompatibilityTests(unittest.TestCase):
    def assert_blocked(self, niche: str, product_type: str) -> None:
        result = assess_compatibility(product_type, niche)
        self.assertFalse(result["compatible"])
        self.assertEqual(result["compatibility_status"], "blocked")
        self.assertTrue(result["blocked_terms"])

    def assert_allowed(self, niche: str, product_type: str) -> None:
        result = assess_compatibility(product_type, niche)
        self.assertTrue(result["compatible"])
        self.assertEqual(result["compatibility_status"], "allowed")
        self.assertEqual(result["blocked_terms"], [])

    def test_teacher_womens_underwear_is_blocked(self) -> None:
        self.assert_blocked("inclusive teacher", "womens_underwear")

    def test_school_thong_is_blocked(self) -> None:
        self.assert_blocked("school staff appreciation", "thong")

    def test_back_to_school_panties_is_blocked(self) -> None:
        self.assert_blocked("back-to-school classroom gift", "panties")

    def test_teacher_mug_is_allowed(self) -> None:
        self.assert_allowed("teacher appreciation", "mug")

    def test_pride_womens_underwear_is_allowed(self) -> None:
        self.assert_allowed("LGBTQ+ pride", "womens_underwear")

    def test_thai_english_womens_underwear_is_allowed(self) -> None:
        self.assert_allowed("Thai/English identity", "womens_underwear")

    def test_rank_candidates_filters_incompatible_pairs(self) -> None:
        ranked = rank_candidates(
            [
                {
                    "name": "teacher appreciation",
                    "product_type": "womens_underwear",
                    "audience": "teachers",
                    "keywords": ["teacher", "school"],
                },
                {
                    "name": "teacher appreciation",
                    "product_type": "mug",
                    "audience": "teachers",
                    "keywords": ["teacher", "school"],
                },
            ]
        )
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["product_type"], "mug")


if __name__ == "__main__":
    unittest.main()
