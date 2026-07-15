from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

TARGET_WIDTH = 4500
TARGET_HEIGHT = 5400
EXTERIOR_WHITE_THRESHOLD = 240
EXTERIOR_NEUTRAL_TOLERANCE = 15
EXTERIOR_MIN_IMAGE_FRACTION = 0.10
EXTERIOR_MIN_BORDER_FRACTION = 0.50


def _connected_near_white_exterior(image: Image.Image) -> dict[str, Any]:
    """Measure a likely removable background without treating enclosed white as exterior."""
    rgb = image.convert("RGB")
    rgb.thumbnail((512, 512), Image.Resampling.NEAREST)
    width, height = rgb.size
    pixels = rgb.load()

    def eligible(x: int, y: int) -> bool:
        red, green, blue = pixels[x, y]
        return (
            min(red, green, blue) >= EXTERIOR_WHITE_THRESHOLD
            and max(red, green, blue) - min(red, green, blue) <= EXTERIOR_NEUTRAL_TOLERANCE
        )

    border = {(x, 0) for x in range(width)} | {(x, height - 1) for x in range(width)}
    border |= {(0, y) for y in range(height)} | {(width - 1, y) for y in range(height)}
    seeds = [point for point in border if eligible(*point)]
    seen = set(seeds)
    pending = list(seeds)
    while pending:
        x, y = pending.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            nx, ny = neighbor
            if 0 <= nx < width and 0 <= ny < height and neighbor not in seen and eligible(nx, ny):
                seen.add(neighbor)
                pending.append(neighbor)
    image_fraction = len(seen) / max(1, width * height)
    border_fraction = len(seeds) / max(1, len(border))
    return {
        "connected_near_white_pixel_count": len(seen),
        "connected_near_white_image_fraction": image_fraction,
        "near_white_border_fraction": border_fraction,
        "near_white_threshold": EXTERIOR_WHITE_THRESHOLD,
        "neutral_tolerance": EXTERIOR_NEUTRAL_TOLERANCE,
        "sample_dimensions": [width, height],
        "likely_connected_exterior_background": (
            image_fraction >= EXTERIOR_MIN_IMAGE_FRACTION
            and border_fraction >= EXTERIOR_MIN_BORDER_FRACTION
        ),
    }


def inspect_generated_image(image_path: str | Path, transparency_required: bool = False) -> dict[str, Any]:
    path = Path(image_path).expanduser()
    if not path.exists() or not path.is_file():
        readiness_statuses = ["generated_concept", "needs_design_review", "not_print_ready"]
        if transparency_required:
            readiness_statuses.insert(1, "needs_background_removal")
        return {
            "image_path": str(path),
            "exists": False,
            "file_size_bytes": 0,
            "format": None,
            "width": 0,
            "height": 0,
            "mode": None,
            "alpha_channel_present": False,
            "meaningful_transparency_present": False,
            "fully_opaque": False,
            "target_width": TARGET_WIDTH,
            "target_height": TARGET_HEIGHT,
            "background_removal_required": bool(transparency_required),
            "production_canvas_required": False,
            "visual_review_required": True,
            "final_print_ready": False,
            "readiness_statuses": readiness_statuses,
            "provider_status": "not_ready",
            "printify_status": "not_ready",
        }

    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            mode = image.mode
            alpha_channel_present = "A" in mode
            meaningful_transparency_present = False
            fully_opaque = True

            if alpha_channel_present:
                alpha = image.getchannel("A")
                transparent_pixels = 0
                for pixel in alpha.tobytes():
                    if pixel < 255:
                        transparent_pixels += 1
                meaningful_transparency_present = transparent_pixels > 0
                fully_opaque = transparent_pixels == 0
            else:
                fully_opaque = True

            exterior = _connected_near_white_exterior(image)
            background_removal_required = (
                not meaningful_transparency_present
                and fully_opaque
                and exterior["likely_connected_exterior_background"]
            )
            production_canvas_required = width < TARGET_WIDTH or height < TARGET_HEIGHT
            visual_review_required = True
            readiness_statuses: list[str] = ["generated_concept"]
            if background_removal_required:
                readiness_statuses.append("needs_background_removal")
            if production_canvas_required:
                readiness_statuses.append("needs_production_canvas")
            readiness_statuses.extend(["needs_design_review", "not_print_ready"])

            final_print_ready = False

            provider_status = "not_ready"
            printify_status = "not_ready"
            if final_print_ready:
                provider_status = "ready"
                printify_status = "ready"

            return {
                "image_path": str(path),
                "exists": True,
                "file_size_bytes": path.stat().st_size,
                "format": (image.format or "PNG") if image.format else "PNG",
                "width": width,
                "height": height,
                "mode": mode,
                "alpha_channel_present": alpha_channel_present,
                "meaningful_transparency_present": meaningful_transparency_present,
                "fully_opaque": fully_opaque,
                "exterior_background_analysis": exterior,
                "target_width": TARGET_WIDTH,
                "target_height": TARGET_HEIGHT,
                "background_removal_required": background_removal_required,
                "production_canvas_required": production_canvas_required,
                "visual_review_required": visual_review_required,
                "final_print_ready": final_print_ready,
                "readiness_statuses": readiness_statuses,
                "provider_status": provider_status,
                "printify_status": printify_status,
            }
    except Exception:
        return {
            "image_path": str(path),
            "exists": True,
            "file_size_bytes": path.stat().st_size if path.exists() else 0,
            "format": None,
            "width": 0,
            "height": 0,
            "mode": None,
            "alpha_channel_present": False,
            "meaningful_transparency_present": False,
            "fully_opaque": False,
            "target_width": TARGET_WIDTH,
            "target_height": TARGET_HEIGHT,
            "background_removal_required": False,
            "production_canvas_required": False,
            "visual_review_required": True,
            "final_print_ready": False,
            "readiness_statuses": ["needs_design_review"],
            "provider_status": "not_ready",
            "printify_status": "not_ready",
        }
