from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import design_variation_service, job_queue, pod_provider_registry, recipe_library
from jamesos.services.design_dna import design_dna_from_recipe
from jamesos.services.print_readiness_scorer import score_variation


class DesignRunTests(unittest.TestCase):
    def run_with_design_runs(self, callback):
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
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_recipe_library_initializes_default_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Recipes"
            result = recipe_library.initialize_recipe_library(root)
            recipes = recipe_library.list_recipes(root)

            self.assertEqual(result["status"], "ok")
            self.assertTrue((root / "pride" / "typography_badge.yaml").exists())
            self.assertTrue((root / "underwear" / "pride_pattern.yaml").exists())
            self.assertGreaterEqual(recipes["recipe_count"], 12)

    def test_underwear_recipes_avoid_large_typography_and_badge_avoids_underwear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Recipes"
            underwear = recipe_library.get_recipe("underwear/pride_pattern", root)["recipe"]
            badge = recipe_library.get_recipe("pride/typography_badge", root)["recipe"]

            self.assertIn("womens_underwear", underwear["product_fit"])
            self.assertIn(underwear["text_strategy"], {"no_text", "minimal_hidden_text"})
            self.assertIn("womens_underwear", badge["avoid_product_types"])

    def test_design_dna_created_from_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipe = recipe_library.get_recipe("underwear/pride_pattern", Path(tmp) / "Recipes")["recipe"]
            dna = design_dna_from_recipe(recipe, brand_id="unitystitches", product_type="womens_underwear", niche="trans pride")

            self.assertEqual(dna["design_family"], recipe["design_family"])
            self.assertIn("womens_underwear", dna["target_products"])
            self.assertEqual(dna["product_type"], "womens_underwear")

    def test_design_run_creates_exactly_four_variations_with_layers_and_prompts(self) -> None:
        def scenario(root: Path) -> None:
            result = design_variation_service.create_design_run(
                brand_id="unitystitches",
                product_type="womens_underwear",
                niche="trans pride",
                recipe_id="underwear/pride_pattern",
                variations=4,
                quality="premium",
                provider="printify",
            )

            self.assertEqual(result["variation_count"], 4)
            for variation in result["variations"]:
                self.assertTrue(Path(variation["layer_manifest_path"]).exists())
                self.assertIn("prompt_package", variation)
                self.assertIn("design_dna", variation)
                self.assertTrue(variation["image_job_id"])
                self.assertEqual(job_queue.get_job(variation["image_job_id"])["status"], "pending")

        self.run_with_design_runs(scenario)

    def test_underwear_no_text_is_not_penalized_but_large_text_is(self) -> None:
        base = {
            "variation_id": "v",
            "product_type": "womens_underwear",
            "design_recipe": {
                "product_fit": ["womens_underwear", "panties", "thong"],
                "avoid_product_types": [],
                "design_type": "repeat_pattern",
                "pattern_strategy": "seamless-style repeat",
                "text_strategy": "no_text",
                "quality_rules": ["high contrast"],
                "composition_rules": ["safe margins"],
                "trademark_safety_notes": "safe",
                "commercial_goal": "wearable pattern",
                "negative_rules": ["large text"],
            },
        }
        no_text = score_variation(base)
        large_text = score_variation({**base, "design_recipe": {**base["design_recipe"], "text_strategy": "large_readable_text"}})

        self.assertGreaterEqual(no_text["typography_score"], 90)
        self.assertLess(large_text["typography_score"], 60)
        self.assertLess(large_text["product_fit_score"], no_text["product_fit_score"])

    def test_promotion_requires_score_90_or_best_candidate_review(self) -> None:
        def scenario(root: Path) -> None:
            good = design_variation_service.create_design_run(
                brand_id="unitystitches",
                product_type="womens_underwear",
                niche="trans pride",
                recipe_id="underwear/pride_pattern",
                variations=4,
                quality="premium",
                provider="printify",
            )
            winner = design_variation_service.promote_best(good["run_id"])["winner"]
            self.assertEqual(winner["status"], "ready_for_printify_review")

            weak = design_variation_service.create_design_run(
                brand_id="unitystitches",
                product_type="womens_underwear",
                niche="trans pride",
                recipe_id="pride/typography_badge",
                variations=4,
                quality="premium",
                provider="printify",
            )
            weak_winner = design_variation_service.promote_best(weak["run_id"])["winner"]
            self.assertEqual(weak_winner["status"], "best_candidate_needs_review")

        self.run_with_design_runs(scenario)

    def test_api_routes_exist_and_provider_writes_remain_false(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise
        paths = {route.path for route in api.app.routes}
        for path in [
            "/recipes",
            "/recipes/{recipe_id:path}",
            "/recipes/by-product/{product_type}",
            "/design-runs/create",
            "/design-runs",
            "/design-runs/{run_id}",
            "/design-runs/{run_id}/score",
            "/design-runs/{run_id}/promote-best",
        ]:
            self.assertIn(path, paths)
        for provider in pod_provider_registry.list_providers()["providers"]:
            self.assertFalse(provider["writes_enabled"])
            self.assertFalse(provider["draft_creation_enabled"])
            self.assertFalse(provider["order_enabled"])

    def test_no_external_provider_code_path_in_design_runs(self) -> None:
        source = Path("jamesos/services/design_variation_service.py").read_text(encoding="utf-8")
        self.assertNotIn("printify.", source.lower())
        self.assertNotIn("inkedjoy.", source.lower())
        self.assertNotIn("etsy.", source.lower())
        self.assertNotIn("upload(", source.lower())
        self.assertNotIn("publish(", source.lower())
        self.assertNotIn("send(", source.lower())


if __name__ == "__main__":
    unittest.main()
