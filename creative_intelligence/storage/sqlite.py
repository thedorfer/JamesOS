from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any
from datetime import UTC, datetime

from creative_intelligence.config import DB_PATH, ensure_data_root

if TYPE_CHECKING:
    from creative_intelligence.models import CreativeJob, ProductPlan, PromptResult


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_data_root()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> dict[str, Any]:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS creative_jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                query TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prompt_results (
                id TEXT PRIMARY KEY,
                source_idea TEXT NOT NULL,
                prompt TEXT NOT NULL,
                negative_prompt TEXT NOT NULL DEFAULT '',
                style_tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_plans (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                niche TEXT NOT NULL,
                audience TEXT NOT NULL,
                product_type TEXT NOT NULL,
                score REAL NOT NULL,
                keywords_json TEXT NOT NULL,
                prompts_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS etsy_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS etsy_listings (
                listing_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                product_type TEXT NOT NULL DEFAULT '',
                niche TEXT NOT NULL DEFAULT '',
                views INTEGER NOT NULL DEFAULT 0,
                favorites INTEGER NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                price REAL NOT NULL DEFAULT 0,
                currency_code TEXT NOT NULL DEFAULT '',
                created_timestamp TEXT NOT NULL DEFAULT '',
                updated_timestamp TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                last_synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS etsy_receipts (
                receipt_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT '',
                was_paid INTEGER NOT NULL DEFAULT 0,
                was_shipped INTEGER NOT NULL DEFAULT 0,
                total_price REAL NOT NULL DEFAULT 0,
                currency_code TEXT NOT NULL DEFAULT '',
                created_timestamp TEXT NOT NULL DEFAULT '',
                updated_timestamp TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                last_synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS etsy_transactions (
                transaction_id TEXT PRIMARY KEY,
                receipt_id TEXT NOT NULL DEFAULT '',
                listing_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                price REAL NOT NULL DEFAULT 0,
                currency_code TEXT NOT NULL DEFAULT '',
                created_timestamp TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                last_synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS performance_history (
                listing_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                product_type TEXT NOT NULL DEFAULT '',
                niche TEXT NOT NULL DEFAULT '',
                views INTEGER NOT NULL DEFAULT 0,
                favorites INTEGER NOT NULL DEFAULT 0,
                orders INTEGER NOT NULL DEFAULT 0,
                revenue REAL NOT NULL DEFAULT 0,
                quantity_sold INTEGER NOT NULL DEFAULT 0,
                conversion_rate REAL NOT NULL DEFAULT 0,
                profit_estimate REAL NOT NULL DEFAULT 0,
                active_state TEXT NOT NULL DEFAULT '',
                created_timestamp TEXT NOT NULL DEFAULT '',
                updated_timestamp TEXT NOT NULL DEFAULT '',
                last_synced_at TEXT NOT NULL
            );
            """
        )
    return {"status": "ok", "db_path": str(db_path)}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def record_etsy_sync_run(
    sync_type: str,
    status: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    init_db(db_path)
    timestamp = now_iso()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO etsy_sync_runs
            (sync_type, status, message, started_at, finished_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sync_type,
                status,
                message,
                timestamp,
                timestamp,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        run_id = int(cursor.lastrowid)
    return {
        "id": run_id,
        "sync_type": sync_type,
        "status": status,
        "message": message,
        "started_at": timestamp,
        "finished_at": timestamp,
        "metadata": metadata or {},
    }


def performance_history_exists(db_path: Path = DB_PATH) -> bool:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM performance_history").fetchone()
    return bool(row and int(row["count"]) > 0)


def list_performance_history(
    *,
    limit: int = 50,
    order_by: str = "revenue",
    ascending: bool = False,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    init_db(db_path)
    allowed_order = {
        "revenue",
        "orders",
        "quantity_sold",
        "conversion_rate",
        "views",
        "favorites",
        "last_synced_at",
    }
    order = order_by if order_by in allowed_order else "revenue"
    direction = "ASC" if ascending else "DESC"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM performance_history ORDER BY {order} {direction} LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [dict(row) for row in rows]


def performance_summary(db_path: Path = DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS listing_count,
                COALESCE(SUM(views), 0) AS views,
                COALESCE(SUM(favorites), 0) AS favorites,
                COALESCE(SUM(orders), 0) AS orders,
                COALESCE(SUM(revenue), 0) AS revenue,
                COALESCE(SUM(quantity_sold), 0) AS quantity_sold,
                COALESCE(AVG(conversion_rate), 0) AS average_conversion_rate,
                COALESCE(SUM(profit_estimate), 0) AS profit_estimate
            FROM performance_history
            """
        ).fetchone()
    return dict(row) if row else {}


def rebuild_performance_history_from_local_tables(db_path: Path = DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    timestamp = now_iso()
    with connect(db_path) as conn:
        conn.execute("DELETE FROM performance_history")
        conn.execute(
            """
            INSERT INTO performance_history (
                listing_id,
                title,
                product_type,
                niche,
                views,
                favorites,
                orders,
                revenue,
                quantity_sold,
                conversion_rate,
                profit_estimate,
                active_state,
                created_timestamp,
                updated_timestamp,
                last_synced_at
            )
            SELECT
                listings.listing_id,
                listings.title,
                listings.product_type,
                listings.niche,
                listings.views,
                listings.favorites,
                COUNT(DISTINCT transactions.receipt_id) AS orders,
                COALESCE(SUM(transactions.price * transactions.quantity), 0) AS revenue,
                COALESCE(SUM(transactions.quantity), 0) AS quantity_sold,
                CASE
                    WHEN listings.views > 0
                    THEN CAST(COUNT(DISTINCT transactions.receipt_id) AS REAL) / CAST(listings.views AS REAL)
                    ELSE 0
                END AS conversion_rate,
                COALESCE(SUM(transactions.price * transactions.quantity), 0) * 0.35 AS profit_estimate,
                listings.state,
                listings.created_timestamp,
                listings.updated_timestamp,
                ?
            FROM etsy_listings listings
            LEFT JOIN etsy_transactions transactions
                ON transactions.listing_id = listings.listing_id
            GROUP BY listings.listing_id
            """,
            (timestamp,),
        )
        count = conn.execute("SELECT COUNT(*) AS count FROM performance_history").fetchone()["count"]
    return {"status": "ok", "rebuilt": int(count), "last_synced_at": timestamp}


def save_job(job: "CreativeJob", db_path: Path = DB_PATH) -> "CreativeJob":
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO creative_jobs
            (id, type, query, status, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.type,
                job.query,
                job.status,
                json.dumps(job.payload, sort_keys=True),
                job.created_at,
                job.updated_at,
            ),
        )
    return job


def save_prompt_result(result: "PromptResult", db_path: Path = DB_PATH) -> "PromptResult":
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO prompt_results
            (id, source_idea, prompt, negative_prompt, style_tags_json, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.source_idea,
                result.prompt,
                result.negative_prompt,
                json.dumps(result.style_tags, sort_keys=True),
                json.dumps(result.metadata, sort_keys=True),
                result.created_at,
            ),
        )
    return result


def save_product_plan(plan: "ProductPlan", db_path: Path = DB_PATH) -> "ProductPlan":
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO product_plans
            (id, title, niche, audience, product_type, score, keywords_json, prompts_json, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.id,
                plan.title,
                plan.niche,
                plan.audience,
                plan.product_type,
                plan.score,
                json.dumps(plan.keywords, sort_keys=True),
                json.dumps(plan.prompts, sort_keys=True),
                json.dumps(plan.metadata, sort_keys=True),
                plan.created_at,
            ),
        )
    return plan
