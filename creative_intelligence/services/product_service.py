from __future__ import annotations

from creative_intelligence.config import DEFAULT_PRODUCT_TYPES
from creative_intelligence.models import ProductPlan
from creative_intelligence.services.metadata_service import product_metadata
from creative_intelligence.services.niche_service import suggest_niches
from creative_intelligence.services.prompt_service import generate_prompt
from creative_intelligence.services.scoring_service import rank_candidates
from creative_intelligence.storage.sqlite import save_product_plan


def build_product_plans(query: str = "", *, limit: int = 6) -> list[ProductPlan]:
    niches = rank_candidates(suggest_niches(query, limit=limit))
    plans: list[ProductPlan] = []
    for index, niche in enumerate(niches[:limit]):
        product_type = DEFAULT_PRODUCT_TYPES[index % len(DEFAULT_PRODUCT_TYPES)]
        title = f"{niche['name']} {product_type}".strip().title()
        prompt_result = generate_prompt(title, product_type=product_type, persist=True)
        plan = ProductPlan(
            title=title,
            niche=str(niche["name"]),
            audience=str(niche["audience"]),
            product_type=product_type,
            score=float(niche["score"]),
            keywords=list(niche.get("keywords") or []),
            prompts=[prompt_result.prompt],
            metadata=product_metadata(title, str(niche.get("angle") or "")),
        )
        save_product_plan(plan)
        plans.append(plan)
    return plans

