from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import design_variation_service, job_queue, recipe_library
from jamesos.services.design_critic import critique_design_plan
from jamesos.services.design_dna import design_dna_from_recipe
from jamesos.services.design_planner import (
    design_plan_from_recipe,
    design_plan_health,
    load_design_plan,
    save_design_plan,
)


class DesignPlannerCriticTests(unittest.TestCase):
    def recipe(self, recipe_id: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            return recipe_library.get_recipe(recipe_id, Path(tmp) / "Recipes")["recipe"]

    def test_design_planner_health_works(self) -> None:
        result = design_plan_health()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["external_execution_enabled"])
        self.assertFalse(result["safety"]["provider_writes_enabled"])

    def test_underwear_plan_avoids_large_typography_and_uses_repeat(self) -> None:
        recipe = self.recipe("underwear/pride_pattern")
        dna = design_dna_from_recipe(recipe, brand_id="brand", product_type="womens_underwear", niche="trans pride")
        plan = design_plan_from_recipe(recipe, dna, brand_id="brand", product_type="womens_underwear", niche="trans pride")

        self.assertIn(plan["typography_strategy"], {"no_text", "minimal_hidden_text"})
        self.assertIn("repeat", plan["pattern_strategy"].lower())
        self.assertGreaterEqual(plan["coverage_percent"], 40)
        self.assertLessEqual(plan["coverage_percent"], 65)

    def test_shirt_plan_can_use_typography_strategy(self) -> None:
        recipe = self.recipe("pride/typography_badge")
        dna = design_dna_from_recipe(recipe, brand_id="brand", product_type="t_shirt", niche="pride")
        plan = design_plan_from_recipe(recipe, dna, brand_id="brand", product_type="t_shirt", niche="pride")

        self.assertIn(plan["typography_strategy"], {"readable_typography", "optional_short_text"})
        self.assertGreaterEqual(plan["coverage_percent"], 65)

    def test_design_plan_saves_and_loads(self) -> None:
        recipe = self.recipe("underwear/pride_pattern")
        plan = design_plan_from_recipe(recipe, {}, brand_id="brand", product_type="womens_underwear", niche="trans pride")
        with tempfile.TemporaryDirectory() as tmp:
            saved = save_design_plan(plan, root=Path(tmp))
            loaded = load_design_plan(plan["plan_id"], root=Path(tmp))

        self.assertEqual(saved["status"], "ok")
        self.assertEqual(loaded["plan"]["plan_id"], plan["plan_id"])

    def test_critic_rewards_underwear_no_text_pattern(self) -> None:
        recipe = self.recipe("underwear/pride_pattern")
        plan = design_plan_from_recipe(recipe, {}, brand_id="brand", product_type="womens_underwear", niche="trans pride")
        critique = critique_design_plan(plan, artifact={"transparent_background": True, "width": 1024, "height": 1024})

        self.assertGreaterEqual(critique["typography_score"], 90)
        self.assertGreaterEqual(critique["product_fit_score"], 90)
        self.assertIn(critique["promotion_recommendation"], {"ready_for_printify_review", "best_candidate_needs_review"})

    def test_critic_penalizes_underwear_large_text(self) -> None:
        recipe = self.recipe("underwear/pride_pattern")
        plan = design_plan_from_recipe(recipe, {}, brand_id="brand", product_type="womens_underwear", niche="trans pride")
        plan["typography_strategy"] = "large_readable_text"
        critique = critique_design_plan(plan, artifact={"transparent_background": True})

        self.assertLess(critique["typography_score"], 60)
        self.assertEqual(critique["promotion_recommendation"], "reject")

    def test_critic_penalizes_mockup_person_photo_language(self) -> None:
        recipe = self.recipe("underwear/pride_pattern")
        plan = design_plan_from_recipe(recipe, {}, brand_id="brand", product_type="womens_underwear", niche="trans pride")
        plan["prompt_intent"]["layout"] = "person wearing underwear product photo mockup"
        critique = critique_design_plan(plan, artifact={"transparent_background": True})

        self.assertTrue(any("Mockup/person" in issue for issue in critique["blocking_issues"]))

    def test_critic_requires_transparency_metadata_for_high_score(self) -> None:
        recipe = self.recipe("underwear/pride_pattern")
        plan = design_plan_from_recipe(recipe, {}, brand_id="brand", product_type="womens_underwear", niche="trans pride")
        plan["prompt_intent"]["transparent_background_requested"] = False
        critique = critique_design_plan(plan, artifact={})

        self.assertLess(critique["transparency_score"], 90)
        self.assertTrue(any("Transparency metadata" in warning for warning in critique["warnings"]))

    def test_design_run_variations_include_plan_and_critique_and_promotion_uses_critic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_root = root / "Queue"
            patches = [
                patch.object(recipe_library, "RECIPE_ROOT", root / "Recipes"),
                patch.object(design_variation_service, "DESIGN_RUN_ROOT", root / "DesignRuns"),
                patch.object(design_variation_service, "get_recipe", lambda recipe_id: recipe_library.get_recipe(recipe_id, root / "Recipes")),
                patch.object(job_queue, "QUEUE_ROOT", queue_root),
                patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"),
                patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"),
                patch.object(job_queue, "REPORT_PATH", root / "Reports" / "Job Queue.md"),
                patch.object(design_variation_service, "create_job", job_queue.create_job),
            ]
            for item in patches:
                item.start()
            try:
                run = design_variation_service.create_design_run(
                    brand_id="commerce_shop",
                    product_type="womens_underwear",
                    niche="trans pride",
                    recipe_id="underwear/pride_pattern",
                    variations=4,
                    provider="printify",
                )
                for variation in run["variations"]:
                    self.assertTrue(Path(variation["design_plan_path"]).exists())
                    self.assertTrue(Path(variation["pre_generation_critique_path"]).exists())
                    self.assertEqual(variation["pre_generation_critique"]["promotion_recommendation"], "ready_for_printify_review")
                winner = design_variation_service.promote_best(run["run_id"])["winner"]
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(winner["critic_promotion_recommendation"], "ready_for_printify_review")
        self.assertEqual(winner["status"], "ready_for_printify_review")


if __name__ == "__main__":
    unittest.main()
