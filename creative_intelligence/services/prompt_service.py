from __future__ import annotations

from creative_intelligence.models import PromptResult
from creative_intelligence.storage.sqlite import save_prompt_result


def generate_prompt(
    idea: str,
    *,
    style: str = "clean commercial illustration",
    product_type: str = "print-on-demand product",
    persist: bool = True,
) -> PromptResult:
    idea_text = idea.strip() or "original product design"
    prompt = (
        f"{style}, {idea_text}, optimized for {product_type}, high readability, "
        "balanced composition, strong silhouette, transparent background where useful"
    )
    result = PromptResult(
        source_idea=idea_text,
        prompt=prompt,
        negative_prompt="low resolution, blurry, misspelled text, cluttered layout, watermark",
        style_tags=[tag.strip() for tag in style.split(",") if tag.strip()],
        metadata={"product_type": product_type},
    )
    if persist:
        save_prompt_result(result)
    return result


def generate_prompts(ideas: list[str], *, product_type: str = "print-on-demand product") -> list[PromptResult]:
    return [generate_prompt(idea, product_type=product_type) for idea in ideas if idea.strip()]

