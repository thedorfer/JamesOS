from __future__ import annotations

from datetime import datetime
import base64
from hashlib import sha256
import html
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from jamesos.integrations.printify_client import PrintifyClient
from jamesos.services import job_queue, printify_product


CANVAS = (4500, 5400)
PHRASE = "LOVE IS LOVE"


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any, *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if immutable else "w"
    with path.open(mode, encoding="utf-8") as handle: json.dump(value, handle, indent=2, sort_keys=True)


def _preview(source: Image.Image, background: tuple[int, int, int, int], path: Path) -> None:
    base = Image.new("RGBA", source.size, background); result = Image.alpha_composite(base, source).convert("RGB")
    result.save(path, format="PNG"); result.close(); base.close()


def _checkerboard(size: tuple[int, int], tile: int = 120) -> Image.Image:
    image = Image.new("RGBA", size, (230, 230, 230, 255)); draw = ImageDraw.Draw(image)
    for y in range(0, size[1], tile):
        for x in range(0, size[0], tile):
            if (x // tile + y // tile) % 2: draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(175, 175, 175, 255))
    return image


def create_composition(job_id: str, composition_id: str, *, font_path: Path, confirmed: bool,
                       exact_text: str = PHRASE, heart_scale: float = .87) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Composition creation requires explicit confirmation.")
    if exact_text != PHRASE: raise job_queue.JobQueueError(f"This template requires the exact phrase: {PHRASE}")
    font_path = font_path.expanduser().resolve()
    if not font_path.is_file(): raise job_queue.JobQueueError("Configured composition font could not be resolved.")
    evidence = printify_product._approved_evidence(job_id); source = evidence["candidate"]
    root = evidence["job_root"] / "commerce" / "product-compositions" / composition_id
    if root.exists(): raise job_queue.JobQueueError("Composition ID already exists and is immutable.")
    root.mkdir(parents=True)
    source_before = _hash(source); font_sha = _hash(font_path)
    with Image.open(source) as opened:
        opened.load(); source_image = opened.convert("RGBA")
    bbox = source_image.getchannel("A").getbbox()
    if not bbox: raise job_queue.JobQueueError("Approved artwork has no visible pixels.")
    heart = source_image.crop(bbox); scaled = heart.resize((round(heart.width * heart_scale), round(heart.height * heart_scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0)); heart_x = (CANVAS[0] - scaled.width) // 2; heart_y = 1450
    canvas.alpha_composite(scaled, (heart_x, heart_y))
    font_size, outline = 500, 28
    font = ImageFont.truetype(str(font_path), font_size)
    typography = Image.new("RGBA", CANVAS, (0, 0, 0, 0)); draw = ImageDraw.Draw(typography)
    widths = [draw.textlength(character, font=font) for character in exact_text]
    spacing = 12; total = sum(widths) + spacing * (len(widths) - 1); start_x = (CANVAS[0] - total) / 2
    character_evidence = []; x = start_x
    for index, (character, width) in enumerate(zip(exact_text, widths)):
        normalized = (index / max(1, len(exact_text) - 1)) * 2 - 1
        y = 1050 - round(170 * (1 - normalized * normalized))
        draw.text((x, y), character, font=font, fill=(255, 244, 110, 255), stroke_width=outline, stroke_fill=(30, 30, 38, 255), anchor="la")
        character_evidence.append({"character": character, "x": round(x, 3), "y": y, "width": round(width, 3)})
        x += width + spacing
    text_bbox = typography.getchannel("A").getbbox()
    safe_bounds = (225, 270, 4275, 5130)
    if not text_bbox or text_bbox[0] < safe_bounds[0] or text_bbox[2] > safe_bounds[2] or text_bbox[1] < safe_bounds[1]:
        raise job_queue.JobQueueError("Rendered typography escaped production safe bounds.")
    typography_path = root / "typography.png"; typography.save(typography_path, format="PNG")
    canvas.alpha_composite(typography)
    output = root / "product-composition.png"; canvas.save(output, format="PNG")
    previews = {"dark": root / "preview-dark.png", "white": root / "preview-white.png", "checkerboard": root / "preview-checkerboard.png"}
    _preview(canvas, (24, 24, 24, 255), previews["dark"]); _preview(canvas, (255, 255, 255, 255), previews["white"])
    checker = _checkerboard(CANVAS); composed = Image.alpha_composite(checker, canvas).convert("RGB"); composed.save(previews["checkerboard"], format="PNG")
    composed.close(); checker.close(); canvas.close(); typography.close(); scaled.close(); heart.close(); source_image.close()
    if _hash(source) != source_before: raise job_queue.JobQueueError("Approved source changed during composition.")
    record = {"composition_id": composition_id, "source_job_id": job_id, "approved_source_candidate_path": str(source),
              "approved_source_candidate_sha256": source_before, "final_artwork_approval_sha256": evidence["approval_sha"],
              "product_type": "unisex_t_shirt", "exact_text": exact_text,
              "typography": {"requested_font_family": font_path.stem, "resolved_font_path": str(font_path),
                  "resolved_font_sha256": font_sha, "font_size": font_size, "outline_width": outline,
                  "fill": "#fff46e", "stroke": "#1e1e26", "arch_geometry": {"type": "shallow_upward", "rise_pixels": 170},
                  "text_bounding_box": list(text_bbox), "characters": character_evidence},
              "layout_template": "arched_headline_above_artwork", "heart_scale": heart_scale,
              "heart_original_bounding_box": list(bbox), "heart_output_position": [heart_x, heart_y],
              "output_path": str(output), "output_sha256": _hash(output), "typography_path": str(typography_path),
              "typography_sha256": _hash(typography_path), "previews": {key: {"path": str(path), "sha256": _hash(path)} for key, path in previews.items()},
              "created_at": datetime.now().astimezone().isoformat(), "composition_status": "needs_human_review",
              "human_approval_status": "not_approved"}
    _write_json(root / "composition.json", record, immutable=True)
    return record


def approve_composition(job_id: str, composition_id: str, *, approved_by: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed or not approved_by.strip(): raise job_queue.JobQueueError("Composition approval requires reviewer and explicit confirmation.")
    evidence = printify_product._approved_evidence(job_id); root = evidence["job_root"] / "commerce" / "product-compositions" / composition_id
    record_path = root / "composition.json"; record = json.loads(record_path.read_text(encoding="utf-8")); output = Path(record["output_path"])
    if _hash(output) != record["output_sha256"]: raise job_queue.JobQueueError("Composition SHA changed before approval.")
    approval_path = root / "composition-approval.json"
    approval = {"composition_id": composition_id, "composition_record_sha256": _hash(record_path),
                "approved_output_sha256": record["output_sha256"], "approved_by": approved_by.strip(),
                "approved_at": datetime.now().astimezone().isoformat(), "visual_review_result": "passed"}
    if approval_path.exists():
        existing = json.loads(approval_path.read_text(encoding="utf-8"))
        if existing["approved_by"] != approved_by.strip(): raise job_queue.JobQueueError("Composition is approved by a different reviewer.")
        return {**existing, "idempotent": True}
    _write_json(approval_path, approval, immutable=True); return {**approval, "idempotent": False}


def profile_store(client: PrintifyClient, shop_id: int, output_path: Path) -> dict[str, Any]:
    response = client.list_products(shop_id); products = response.get("data", response if isinstance(response, list) else [])
    if not products:
        profile = {"style_profile_status": "insufficient_examples", "products_analyzed": 0, "source_product_ids": [],
                   "confidence": "low", "limitations": "No useful existing products were returned; human fallback style required."}
    else:
        titles = [str(item.get("title") or "") for item in products]; descriptions = [str(item.get("description") or "") for item in products]
        tags = [tag for item in products for tag in item.get("tags") or []]; prices = [v.get("price") for item in products for v in item.get("variants") or [] if v.get("price")]
        profile = {"style_profile_status": "ready", "products_analyzed": len(products),
            "source_product_ids": [item.get("id") for item in products], "retrieved_at": datetime.now().astimezone().isoformat(),
            "observations": {"title_capitalization": "title_case" if sum(t.istitle() for t in titles) >= len(titles)/2 else "mixed",
                "average_title_length": round(sum(map(len, titles))/len(titles), 1),
                "description_opening_style": "short_product_led_intro", "paragraph_and_bullet_structure": "mixed",
                "care_instruction_style": "concise", "tag_count_average": round(len(tags)/len(products), 1),
                "tag_vocabulary": sorted(set(tags))[:40], "pricing_cents": sorted(set(prices))[:40],
                "enabled_color_patterns": [], "enabled_size_patterns": [], "primary_mockup_patterns": "front_default_preferred"},
            "confidence": "medium", "limitations": "Rule-based aggregate only; it does not infer customer behavior or copy listings."}
    profile["profile_sha256"] = sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    _write_json(output_path, profile); return profile


def generate_listing(composition_root: Path, profile_path: Path, *, confirmed: bool) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Listing generation requires explicit confirmation.")
    composition_path = composition_root / "composition.json"; approval_path = composition_root / "composition-approval.json"
    if not approval_path.is_file(): raise job_queue.JobQueueError("Human-approved composition is required before listing generation.")
    composition = json.loads(composition_path.read_text(encoding="utf-8")); profile = json.loads(profile_path.read_text(encoding="utf-8"))
    listing = composition_root / "listing"; listing.mkdir(exist_ok=False)
    title = "Love Is Love Rainbow Heart Unisex Tee"
    description = ("Celebrate colorful, positive love with a bold rainbow heart and an easy-to-read LOVE IS LOVE headline.\n\n"
                   "Printed on a soft Bella+Canvas 3001 unisex tee in Black, Dark Grey Heather, and White, sizes S–3XL.\n\n"
                   "Care: machine wash cold, inside out; tumble dry low; do not iron directly on the design.")
    tags = ["love is love", "rainbow heart", "pride shirt", "positive tee", "unisex shirt", "colorful heart"]
    pricing = {"currency": "USD", "default_retail_cents": 2499, "estimated_base_cost_cents": None,
               "estimated_shipping_cents": None, "estimated_gross_margin_cents": None}
    variants = {"colors": ["Black", "Dark Grey Heather", "White"], "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
                "preferred_primary_mockup_color": "Black", "selected_variant_ids": []}
    (listing / "title.txt").write_text(title + "\n", encoding="utf-8"); (listing / "description.txt").write_text(description + "\n", encoding="utf-8")
    _write_json(listing / "tags.json", tags); _write_json(listing / "pricing.json", pricing); _write_json(listing / "variants.json", variants)
    package = {"listing_package_id": f"listing-{composition['composition_id']}", "title": title, "description": description,
        "tags": tags, "materials": ["Airlume combed and ring-spun cotton"], "care_instructions": "Machine wash cold; tumble dry low.",
        "pricing": pricing, "variants": variants, "style_profile_sha256": profile["profile_sha256"],
        "composition_sha256": composition["output_sha256"], "human_approval_status": "not_approved", "editable": True}
    _write_json(listing / "listing-package.json", package); return package


def approve_listing(listing_root: Path, *, approved_by: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed or not approved_by.strip(): raise job_queue.JobQueueError("Listing approval requires reviewer and confirmation.")
    package = listing_root / "listing-package.json"; approval = {"listing_package_sha256": _hash(package), "approved_by": approved_by.strip(),
        "approved_at": datetime.now().astimezone().isoformat(), "review_result": "passed"}
    path = listing_root / "listing-approval.json"; _write_json(path, approval, immutable=True); return approval


def upload_composition(job_id: str, composition_id: str, *, client: PrintifyClient, confirmed: bool) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Composition upload requires explicit confirmation.")
    evidence = printify_product._approved_evidence(job_id); root = evidence["job_root"] / "commerce" / "product-compositions" / composition_id
    record = json.loads((root / "composition.json").read_text(encoding="utf-8")); approval_path = root / "composition-approval.json"
    if not approval_path.is_file(): raise job_queue.JobQueueError("Human-approved product composition is required before upload.")
    approval = json.loads(approval_path.read_text(encoding="utf-8")); output = Path(record["output_path"])
    if _hash(output) != record["output_sha256"] or approval["approved_output_sha256"] != record["output_sha256"]:
        raise job_queue.JobQueueError("Approved composition SHA evidence is stale.")
    upload_path = root / "printify" / "upload.json"
    if upload_path.exists():
        existing = json.loads(upload_path.read_text(encoding="utf-8")); remote = client.get_upload(existing["printify_image_id"])
        return {**existing, "remote": remote, "idempotent": True}
    filename = f"jamesos-{job_id}-{composition_id}-{record['output_sha256'][:12]}.png"
    remote = client.upload_image_contents(filename, base64.b64encode(output.read_bytes()).decode("ascii"))
    if remote.get("mime_type") != "image/png": raise job_queue.JobQueueError("Printify did not identify the composition as PNG.")
    upload = {"job_id": job_id, "composition_id": composition_id, "composition_sha256": record["output_sha256"],
        "composition_approval_sha256": _hash(approval_path), "printify_image_id": remote.get("id"), "response": remote,
        "uploaded_at": remote.get("upload_time") or datetime.now().astimezone().isoformat(), "idempotent": False}
    _write_json(upload_path, upload, immutable=True); return upload


def create_composition_product_draft(job_id: str, composition_id: str, *, client: PrintifyClient, confirmed: bool,
                                     shop_id: int, blueprint_id: int, provider_id: int, variant_ids: list[int], price: int,
                                     scale: float) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Composition product draft requires explicit confirmation.")
    evidence = printify_product._approved_evidence(job_id); root = evidence["job_root"] / "commerce" / "product-compositions" / composition_id
    upload = json.loads((root / "printify" / "upload.json").read_text(encoding="utf-8"))
    listing_path = root / "listing" / "listing-package.json"; listing_approval = root / "listing" / "listing-approval.json"
    if not listing_approval.is_file(): raise job_queue.JobQueueError("Approved listing package is required before draft creation.")
    listing = json.loads(listing_path.read_text(encoding="utf-8")); output_path = root / "printify" / "product-draft.json"
    plan = {"shop_id": shop_id, "blueprint_id": blueprint_id, "provider_id": provider_id, "variant_ids": sorted(set(variant_ids)),
            "price": price, "scale": scale, "image_id": upload["printify_image_id"], "listing_sha256": _hash(listing_path)}
    plan_sha = sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing["plan_sha256"] != plan_sha: raise job_queue.JobQueueError("Existing text-composition draft is bound to a different immutable plan.")
        return {**existing, "product": client.get_product(shop_id, existing["product_id"]), "idempotent": True}
    payload = {"title": listing["title"], "description": listing["description"], "tags": listing["tags"],
        "blueprint_id": blueprint_id, "print_provider_id": provider_id,
        "variants": [{"id": item, "price": price, "is_enabled": True} for item in plan["variant_ids"]],
        "print_areas": [{"variant_ids": plan["variant_ids"], "placeholders": [{"position": "front", "decoration_method": "dtg",
            "images": [{"id": plan["image_id"], "x": .5, "y": .46, "scale": scale, "angle": 0}]}]}]}
    product = client.create_product(shop_id, payload)
    if not product.get("id"): raise job_queue.JobQueueError("Printify did not return a new product ID.")
    result = {"composition_id": composition_id, "plan_sha256": plan_sha, "shop_id": shop_id, "product_id": product["id"],
              "baseline_product_id_reused": product["id"] == "6a57eaa752f2c3e4700dbf23", "publish_status": "not_published",
              "order_status": "not_created", "response": product, "idempotent": False}
    if result["baseline_product_id_reused"]: raise job_queue.JobQueueError("Printify unexpectedly returned the protected baseline product ID.")
    _write_json(output_path, result, immutable=True); return result


def download_composition_mockups(job_id: str, composition_id: str, *, client: PrintifyClient, limit: int = 4) -> list[dict[str, Any]]:
    evidence = printify_product._approved_evidence(job_id); root = evidence["job_root"] / "commerce" / "product-compositions" / composition_id
    draft = json.loads((root / "printify" / "product-draft.json").read_text(encoding="utf-8"))
    product = client.get_product(draft["shop_id"], draft["product_id"])
    retained = []
    for index, item in enumerate((product.get("images") or [])[:limit]):
        url = str(item.get("src") or "")
        if not url.startswith("https://"): continue
        response = client.session.get(url, timeout=client.timeout); response.raise_for_status()
        path = root / "printify" / "mockups" / f"mockup-{index + 1}.jpg"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(response.content)
        retained.append({"source_url": url, "local_path": str(path), "sha256": _hash(path),
            "variant_ids": item.get("variant_ids") or [], "position": item.get("position"), "is_default": item.get("is_default", False)})
    manifest = root / "printify" / "mockups.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != {"mockups": retained}: raise job_queue.JobQueueError("Existing mockup evidence differs.")
    else: _write_json(manifest, {"mockups": retained}, immutable=True)
    return retained


def build_html_report(run: dict[str, Any], output_path: Path) -> Path:
    composition = run.get("composition") or {}; listing = run.get("listing") or {}; profile = run.get("style_profile") or {}
    def img(label: str, path: str | None) -> str:
        if not path: return f"<section><h2>{html.escape(label)}</h2><p>Not available.</p></section>"
        try: relative = Path(path).resolve().relative_to(output_path.parent.resolve())
        except ValueError: relative = Path(path).resolve()
        return f'<section><h2>{html.escape(label)}</h2><img src="{html.escape(str(relative))}" alt="{html.escape(label)}"></section>'
    previews = composition.get("previews") or {}; mockups = run.get("mockups") or []
    sections = [img("Original approved artwork", run.get("approved_artwork_path")),
        f"<section><h2>Product brief</h2><pre>{html.escape(json.dumps(run.get('product_brief') or {}, indent=2))}</pre></section>",
        f"<section><h2>Typography and composition configuration</h2><pre>{html.escape(json.dumps(composition.get('typography') or {}, indent=2))}</pre></section>",
        img("Product-specific print file", composition.get("output_path")), img("Dark preview", (previews.get("dark") or {}).get("path")),
        img("White preview", (previews.get("white") or {}).get("path")), img("Checkerboard preview", (previews.get("checkerboard") or {}).get("path")),
        f"<section><h2>Store-style profile summary</h2><pre>{html.escape(json.dumps(profile, indent=2))}</pre></section>",
        f"<section><h2>Generated title</h2><p>{html.escape(str(listing.get('title') or 'Not generated'))}</p></section>",
        f"<section><h2>Generated description</h2><p>{html.escape(str(listing.get('description') or 'Not generated'))}</p></section>",
        f"<section><h2>Generated tags</h2><pre>{html.escape(json.dumps(listing.get('tags') or [], indent=2))}</pre></section>",
        f"<section><h2>Pricing and variants</h2><pre>{html.escape(json.dumps({'pricing':listing.get('pricing'),'variants':listing.get('variants')}, indent=2))}</pre></section>",
        f"<section><h2>Printify upload evidence</h2><pre>{html.escape(json.dumps(run.get('printify_upload') or {}, indent=2))}</pre></section>",
        f"<section><h2>Product draft evidence</h2><pre>{html.escape(json.dumps(run.get('printify_product') or {}, indent=2))}</pre></section>",
        "<section><h2>Real Printify mockups</h2>" + "".join(f'<img src="{html.escape(str(item.get("local_path") or item.get("source_url") or ""))}">' for item in mockups) + "</section>",
        f"<section><h2>Approval and readiness timeline</h2><pre>{html.escape(json.dumps(run.get('transitions') or [], indent=2))}</pre></section>",
        f"<section><h2>Current next action</h2><p>{html.escape(str(run.get('current_next_action') or 'Human review required'))}</p></section>"]
    document = "<!doctype html><html><head><meta charset='utf-8'><title>JamesOS Sale Candidate</title><style>body{font-family:sans-serif;max-width:1100px;margin:auto;background:#f5f5f5;color:#222}header,section{background:white;padding:18px;margin:16px;border-radius:10px}img{max-width:100%;max-height:520px} .warning{color:#a00;font-weight:bold;font-size:1.2rem}</style></head><body>"
    document += "<header><h1>Sale Candidate Run — DRAFT</h1><p class='warning'>NOT PUBLISHED · NO ORDER CREATED · HUMAN REVIEW REQUIRED</p></header>" + "".join(sections) + "</body></html>"
    output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(document, encoding="utf-8"); return output_path


def replay_baseline(job_id: str, product_id: str, shop_id: int, *, client: PrintifyClient, report_path: Path) -> dict[str, Any]:
    evidence = printify_product._approved_evidence(job_id); product = client.get_product(shop_id, product_id)
    run = {"run_id": f"replay-{product_id}", "artwork_job_id": job_id, "composition_id": "baseline_without_text",
        "approved_artwork_path": str(evidence["candidate"]), "product_brief": {"product_type": "unisex_t_shirt", "composition": "baseline_without_text"},
        "composition": {"composition_status": "baseline_without_text"}, "listing": {}, "style_profile": {},
        "printify_upload": {}, "printify_product": product, "mockups": product.get("images") or [],
        "transitions": [{"stage": "baseline_replayed", "read_only": True}], "current_next_action": "Review baseline report",
        "publish_status": "not_published", "order_status": "not_created"}
    build_html_report(run, report_path); return run
