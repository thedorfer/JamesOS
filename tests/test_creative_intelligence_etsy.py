from __future__ import annotations

import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path

from creative_intelligence.services import etsy_readonly_service
from creative_intelligence.services.scoring_service import score_candidate
from creative_intelligence.storage.sqlite import init_db


SAFETY_FLAGS = {
    "readonly": True,
    "writes_enabled": False,
    "publishing_enabled": False,
    "order_fulfillment_enabled": False,
}


class CreativeIntelligenceEtsyTests(unittest.TestCase):
    def test_missing_tokens_return_not_configured(self) -> None:
        result = etsy_readonly_service.auth_status()
        self.assertEqual(result["status"], "not_configured")
        for key, value in SAFETY_FLAGS.items():
            self.assertEqual(result[key], value)

    def test_health_is_safe_readonly(self) -> None:
        result = etsy_readonly_service.health()
        for key, value in SAFETY_FLAGS.items():
            self.assertEqual(result[key], value)
        self.assertFalse(result["writes_enabled"])
        self.assertFalse(result["publishing_enabled"])
        self.assertFalse(result["order_fulfillment_enabled"])

    def test_performance_history_schema_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "creative_intelligence.db"
            init_db(db_path)
            with sqlite3.connect(db_path) as conn:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(performance_history)").fetchall()
                }
        expected = {
            "listing_id",
            "title",
            "product_type",
            "niche",
            "views",
            "favorites",
            "orders",
            "revenue",
            "quantity_sold",
            "conversion_rate",
            "profit_estimate",
            "active_state",
            "created_timestamp",
            "updated_timestamp",
            "last_synced_at",
        }
        self.assertTrue(expected.issubset(columns))

    def test_scoring_works_without_etsy_data(self) -> None:
        score = score_candidate(
            {
                "name": "custom teacher appreciation mug",
                "audience": "teachers",
                "keywords": ["teacher", "gift", "mug"],
            }
        )
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_etsy_route_functions_return_safe_flags(self) -> None:
        try:
            from creative_intelligence.routes import etsy
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("fastapi is not installed in this Python environment")
            raise

        responses = [
            etsy.health(),
            etsy.auth_status(),
            etsy.sync_readonly(),
            etsy.performance(),
            etsy.top_products(),
            etsy.underperforming_products(),
        ]
        for response in responses:
            for key, value in SAFETY_FLAGS.items():
                self.assertEqual(response[key], value)

    def test_no_publish_edit_delete_functions_are_implemented(self) -> None:
        forbidden_fragments = ("publish", "edit", "delete", "deactivate", "renew", "fulfill", "message")
        public_functions = [
            name
            for name, value in inspect.getmembers(etsy_readonly_service, inspect.isfunction)
            if not name.startswith("_")
        ]
        offenders = [
            name
            for name in public_functions
            if any(fragment in name.lower() for fragment in forbidden_fragments)
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
