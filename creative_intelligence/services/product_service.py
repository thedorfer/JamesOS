from __future__ import annotations

from creative_intelligence.config import DEFAULT_PRODUCT_TYPES
from creative_intelligence.models import ProductPlan
from creative_intelligence.services.compatibility_service import assess_compatibility
from creative_intelligence.services.metadata_service import product_metadata
from creative_intelligence.services.niche_service import suggest_niches
from creative_intelligence.services.prompt_service import generate_prompt
from creative_intelligence.services.scoring_service import score_candidate
from creative_intelligence.storage.sqlite import save_product_plan


def build_product_plans(query: str = "", *, limit: int = 6) -> list[ProductPlan]:
    niches = suggest_niches(query, limit=limit * 2)
    plans: list[ProductPlan] = []
    index = 0
    for niche in niches:
        if len(plans) >= limit:
            break
        product_type = DEFAULT_PRODUCT_TYPES[index % len(DEFAULT_PRODUCT_TYPES)]
        compatibility = assess_compatibility(product_type, str(niche["name"]))
        if not compatibility["compatible"]:
            index += 1
            continue
        candidate = {**niche, "product_type": product_type}
        score = score_candidate(candidate)
        title = f"{niche['name']} {product_type}".strip().title()
        prompt_result = generate_prompt(title, product_type=product_type, persist=True)
        plan = ProductPlan(
            title=title,
            niche=str(niche["name"]),
            audience=str(niche["audience"]),
            product_type=product_type,
            score=float(score),
            keywords=list(niche.get("keywords") or []),
            prompts=[prompt_result.prompt],
            compatibility_status=str(compatibility["compatibility_status"]),
            compatibility_reason=str(compatibility["compatibility_reason"]),
            blocked_terms=list(compatibility["blocked_terms"]),
            metadata=product_metadata(title, str(niche.get("angle") or "")),
        )
        save_product_plan(plan)
        plans.append(plan)
        index += 1
    return plans
