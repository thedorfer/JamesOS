from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ProductPlan(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    niche: str
    audience: str
    product_type: str
    score: float = 0.0
    keywords: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    brand_id: str = "commerce_shop"
    brand_name: str = "Commerce Shop"
    brand_voice: str = ""
    brand_compatibility_status: str = "unknown"
    brand_compatibility_reason: str = ""
    compatibility_status: str = "unknown"
    compatibility_reason: str = ""
    blocked_terms: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
