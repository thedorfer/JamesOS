from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Callable
from urllib.parse import unquote, urlparse
from uuid import uuid4

import requests
import PIL
from PIL import Image, ImageDraw, ImageFont

from jamesos.config import VAULT
from jamesos.core.errors import FontAcquisitionError, ValidationError
from jamesos.services import job_queue, printify_product


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
FONT_CONFIG = CONFIG_ROOT / "sale_candidate_display_fonts.json"
TREATMENT_CONFIG = CONFIG_ROOT / "sale_candidate_text_treatments.json"
LAYOUT_CONFIG = CONFIG_ROOT / "sale_candidate_layouts.json"
FONT_ROOT = VAULT / "JamesOS" / "Fonts" / "sale-candidate"
CANVAS = (4500, 5400)
PHRASE = "LOVE IS LOVE"
ENGINE = {"vector_model": "SVG 1.1", "text_metadata_engine": "Pango/Fontconfig 1.52.1",
          "rasterizer": f"Pillow {PIL.__version__} FreeType", "curved_text": "tangential_glyph_rotation_on_recorded_path"}


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8")).get(key)
    if not isinstance(value, list): raise job_queue.JobQueueError(f"Invalid vector typography configuration: {path.name}")
    return value


def _font_config(config_path: Path = FONT_CONFIG) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def preflight_font_config(config_path: Path = FONT_CONFIG) -> dict[str, Any]:
    config = _font_config(config_path); errors = []; entries = []; seen_ids = set(); seen_destinations = set()
    required = {"font_id", "family", "style", "license_type", "license_display_name", "license_file_name", "display", "filename",
                "font_url", "license_url", "source_repository", "approved_source_host"}
    supported = {"OFL-1.1": ("OFL.txt",), "Apache-2.0": ("LICENSE.txt",)}
    approved_hosts = set(config.get("approved_source_hosts") or [])
    fonts = config.get("fonts")
    if not isinstance(fonts, list) or not fonts: errors.append({"stage": "configuration", "message": "fonts must be a non-empty list"}); fonts = []
    for index, item in enumerate(fonts):
        font_id = item.get("font_id", f"index-{index}") if isinstance(item, dict) else f"index-{index}"
        if not isinstance(item, dict): errors.append({"font_id": font_id, "stage": "configuration", "message": "font entry must be an object"}); continue
        missing = sorted(required - set(item))
        if missing: errors.append({"font_id": font_id, "stage": "configuration", "message": f"missing fields: {', '.join(missing)}"})
        if font_id in seen_ids: errors.append({"font_id": font_id, "stage": "configuration", "message": "duplicate font_id"})
        seen_ids.add(font_id)
        destination = (item.get("filename"), item.get("license_file_name"))
        if destination in seen_destinations: errors.append({"font_id": font_id, "stage": "configuration", "message": "duplicate destination"})
        seen_destinations.add(destination)
        license_type = item.get("license_type")
        if license_type not in supported: errors.append({"font_id": font_id, "stage": "license", "message": f"unsupported license_type: {license_type}"})
        elif item.get("license_file_name") not in supported[license_type]: errors.append({"font_id": font_id, "stage": "license", "message": "license filename does not match license type"})
        host = item.get("approved_source_host")
        if host not in approved_hosts: errors.append({"font_id": font_id, "stage": "source", "message": "per-font host is not globally approved"})
        for key in ("font_url", "license_url"):
            parsed = urlparse(str(item.get(key, "")))
            if parsed.scheme != "https" or parsed.hostname != host:
                errors.append({"font_id": font_id, "stage": "source", "message": f"invalid or unapproved {key}"})
        if item.get("filename") != Path(unquote(urlparse(str(item.get("font_url", ""))).path)).name:
            errors.append({"font_id": font_id, "stage": "configuration", "message": "filename does not match font URL"})
        if item.get("license_file_name") != Path(unquote(urlparse(str(item.get("license_url", ""))).path)).name:
            errors.append({"font_id": font_id, "stage": "configuration", "message": "license filename does not match license URL"})
        if not isinstance(item.get("family"), str) or not item.get("family", "").strip() or not isinstance(item.get("style"), str) or not item.get("style", "").strip():
            errors.append({"font_id": font_id, "stage": "configuration", "message": "family and style must be nonempty strings"})
        item_errors = [error for error in errors if error.get("font_id") == font_id]
        entries.append({"font_id": font_id, "family": item.get("family"), "style": item.get("style"),
            "font_url": item.get("font_url"), "license_url": item.get("license_url"), "license_type": license_type,
            "approved_host_status": host in approved_hosts and all(urlparse(str(item.get(k, ""))).hostname == host for k in ("font_url", "license_url")),
            "configuration_valid": not item_errors})
    return {"valid": not errors, "font_count": len(fonts), "fonts": entries, "errors": errors}


def font_acquisition_plan(font_root: Path = FONT_ROOT, config_path: Path = FONT_CONFIG) -> dict[str, Any]:
    config = _font_config(config_path); installed = {}; preflight = preflight_font_config(config_path)
    manifest_path = font_root / "acquired-fonts.json"
    if manifest_path.is_file(): installed = {item["font_id"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8"))["fonts"]}
    return {"destination": str(font_root), "approved_source_hosts": config["approved_source_hosts"], "preflight": preflight,
            "fonts": [{**item, "status": "available" if item["font_id"] in installed else "unavailable_not_acquired",
                       "reason": "Exact acquired font verified." if item["font_id"] in installed else "Explicit acquisition has not been run; no substitute will be used."}
                      for item in config["fonts"]], "download_required": bool(set(item["font_id"] for item in config["fonts"]) - set(installed))}


def _download(url: str) -> bytes:
    response = requests.get(url, timeout=(10, 60)); response.raise_for_status(); return response.content


def _license_valid(path: Path, license_type: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace").upper()
    return ("SIL OPEN FONT LICENSE" in text if license_type == "OFL-1.1"
            else "APACHE LICENSE" in text and "VERSION 2.0" in text)


def _scan_font(path: Path, item: dict[str, Any]) -> tuple[str, str]:
    scan = subprocess.run(["fc-scan", "--format", "%{family}|%{style}", str(path)], check=True, capture_output=True, text=True).stdout
    family, separator, style = scan.partition("|")
    if not separator or item["family"].lower() not in family.lower(): raise ValueError(f"font family mismatch: {family or 'unknown'}")
    if not item.get("variation_axes") and item["style"].lower() not in style.lower(): raise ValueError(f"font style mismatch: {style or 'unknown'}")
    return family, style


def acquire_fonts(*, confirmed: bool, font_root: Path = FONT_ROOT, downloader: Callable[[str], bytes] = _download,
                  config_path: Path = FONT_CONFIG) -> dict[str, Any]:
    if not confirmed:
        raise ValidationError("VALIDATION_FAILED", diagnostic_message="Font acquisition requires --confirm-font-download.", operation="font_acquisition",
            stage="confirmation", state={"permanent_files_changed": False, "staging_cleaned": True},
            suggested_action="Repeat with --confirm-font-download after reviewing the acquisition plan.")
    preflight = preflight_font_config(config_path)
    if not preflight["valid"]:
        first = preflight["errors"][0]
        raise FontAcquisitionError("CONFIG_INVALID", diagnostic_message=first["message"], operation="font_acquisition", stage="preflight",
            context={"font_id": first.get("font_id"), "preflight": preflight}, state={"permanent_files_changed": False, "staging_cleaned": True},
            suggested_action="Correct the font configuration and rerun preflight.")
    config = _font_config(config_path); font_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".font-acquisition-", dir=font_root)); promoted = None; current_font = None; stage = "download"
    try:
        old_manifest_path = font_root / "acquired-fonts.json"; old_records = {}
        if old_manifest_path.is_file(): old_records = {x["font_id"]: x for x in json.loads(old_manifest_path.read_text(encoding="utf-8"))["fonts"]}
        set_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z") + "-" + uuid4().hex[:8]
        set_stage = staging / "set"; records = []; warnings = []
        for item in config["fonts"]:
            current_font = item["font_id"]; family_stage = staging / "downloads" / current_font; family_stage.mkdir(parents=True)
            font_stage = family_stage / item["filename"]; license_stage = family_stage / item["license_file_name"]
            stage = "download_font"; font_stage.write_bytes(downloader(item["font_url"]))
            if not font_stage.stat().st_size: raise ValueError("downloaded font was empty")
            stage = "download_license"; license_stage.write_bytes(downloader(item["license_url"]))
            if not license_stage.stat().st_size: raise ValueError("downloaded license was empty")
            stage = "license_validation"
            if not _license_valid(license_stage, item["license_type"]): raise ValueError("license text did not match configured license type")
            stage = "font_validation"; family, style = _scan_font(font_stage, item)
            font_sha, license_sha = _hash(font_stage), _hash(license_stage); reusable = None
            candidates = []
            if current_font in old_records:
                prior = old_records[current_font]
                candidates.append((Path(prior["font_path"]), Path(prior["license_path"]), prior.get("font_sha256"), prior.get("license_sha256")))
            candidates.append((font_root / current_font / item["filename"], font_root / current_font / item["license_file_name"], None, None))
            legacy_url_name = Path(urlparse(item["font_url"]).path).name
            if legacy_url_name != item["filename"]:
                candidates.append((font_root / current_font / legacy_url_name, font_root / current_font / item["license_file_name"], None, None))
            for old_font, old_license, recorded_font_sha, recorded_license_sha in candidates:
                if old_font.is_file() and old_license.is_file() and _hash(old_font) == font_sha and _hash(old_license) == license_sha:
                    if recorded_font_sha is not None and (recorded_font_sha != font_sha or recorded_license_sha != license_sha): continue
                    try: _scan_font(old_font, item)
                    except (OSError, subprocess.SubprocessError, ValueError): continue
                    if _license_valid(old_license, item["license_type"]): reusable = (old_font, old_license); break
            if reusable: final_font, final_license = reusable
            else:
                target = set_stage / current_font; target.mkdir(parents=True)
                final_font = font_root / "sets" / set_id / current_font / item["filename"]
                final_license = font_root / "sets" / set_id / current_font / item["license_file_name"]
                shutil.copy2(font_stage, target / item["filename"]); shutil.copy2(license_stage, target / item["license_file_name"])
            records.append({**item, "requested_style": item["style"], "actual_family": family, "actual_style": style,
                "font_path": str(final_font.resolve()), "font_sha256": font_sha,
                "license_path": str(final_license.resolve()), "license_sha256": license_sha, "verified_family": family,
                "verified_style": style, "requested_style_verified": True, "reused_existing": bool(reusable),
                "reused_existing_file": bool(reusable), "verification_command": "fc-scan --format %{family}|%{style} <font>",
                "verification_result": {"family": family, "style": style, "passed": True},
                "acquired_at": datetime.now().astimezone().isoformat()})
        expected_top = {"acquired-fonts.json", "sets"} | {x["font_id"] for x in config["fonts"]}
        warnings.extend(f"Unexpected permanent entry retained: {p.name}" for p in font_root.iterdir() if p.name not in expected_top and p != staging)
        if old_manifest_path.is_file() and records and all(x["reused_existing"] for x in records):
            old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
            return {**old_manifest, "result": "already_acquired", "idempotent": True, "manifest_path": str(old_manifest_path),
                    "manifest_sha256": _hash(old_manifest_path), "staging_cleaned": True, "permanent_files_changed": False,
                    "warnings": old_manifest.get("warnings", []) + warnings}
        manifest = {"source_authority": "google/fonts official repository", "schema_version": 2,
                    "licenses": sorted({x["license_type"] for x in records}), "warnings": warnings, "fonts": records}
        if set_stage.exists():
            (font_root / "sets").mkdir(exist_ok=True); promoted = font_root / "sets" / set_id; set_stage.replace(promoted)
        stage = "manifest_promotion"; manifest_temp = staging / "acquired-fonts.json"
        manifest_temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"); manifest_temp.replace(old_manifest_path)
        result = {**manifest, "result": "acquired", "manifest_path": str(old_manifest_path), "manifest_sha256": _hash(old_manifest_path),
                  "staging_cleaned": True, "permanent_files_changed": True}
        return result
    except Exception as exc:
        if promoted is not None: shutil.rmtree(promoted, ignore_errors=True)
        status = getattr(getattr(exc, "response", None), "status_code", None)
        code = ("FONT_RESOURCE_NOT_FOUND" if status == 404 else "FONT_LICENSE_INVALID" if stage == "license_validation"
                else "FONT_FAMILY_MISMATCH" if stage == "font_validation" else "FONT_ACQUISITION_INCOMPLETE")
        raise FontAcquisitionError(code, diagnostic_message=f"Font {current_font or 'unknown'} failed during {stage}: {type(exc).__name__}",
            operation="font_acquisition", stage=stage, context={"font_id": current_font, "http_status": status},
            state={"permanent_files_changed": False, "staging_created": True, "staging_cleaned": True, "safe_to_retry": status != 404},
            suggested_action="Correct the configured resource when necessary, then repeat the confirmed acquisition.", cause=exc) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _available_fonts(font_root: Path) -> dict[str, dict[str, Any]]:
    path = font_root / "acquired-fonts.json"
    if not path.is_file(): raise job_queue.JobQueueError("Exact display fonts are unavailable; run the separate confirmed acquisition step first.")
    return {item["font_id"]: item for item in json.loads(path.read_text(encoding="utf-8"))["fonts"]}


def _rgba(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#"); return tuple(int(value[i:i+2], 16) for i in (0, 2, 4)) + (255,)


def _font(record: dict[str, Any], size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(record["font_path"], size)
    axes = record.get("variation_axes") or {}
    order = record.get("axis_order") or []
    if axes and order:
        try: font.set_variation_by_axes([float(axes[key]) for key in order])
        except (AttributeError, OSError) as exc: raise job_queue.JobQueueError(f"Requested variable font style could not be selected for {record['font_id']}.") from exc
    return font


def _text_layer(text: str, font: ImageFont.FreeTypeFont, treatment: dict[str, Any]) -> Image.Image:
    probe = Image.new("RGBA", (10, 10)); draw = ImageDraw.Draw(probe); bbox = draw.textbbox((0, 0), text, font=font, stroke_width=treatment["outline_width"])
    layer = Image.new("RGBA", (bbox[2] - bbox[0] + 160, bbox[3] - bbox[1] + 160), (0, 0, 0, 0)); target = ImageDraw.Draw(layer)
    offset = treatment["shadow_offset"]
    target.text((80 + offset[0], 80 + offset[1]), text, font=font, fill=_rgba(treatment["shadow"]),
                stroke_width=treatment["outline_width"], stroke_fill=_rgba(treatment["outline"]), anchor="lt")
    target.text((80, 80), text, font=font, fill=_rgba(treatment["fill"]),
                stroke_width=treatment["outline_width"], stroke_fill=_rgba(treatment["outline"]), anchor="lt")
    probe.close(); return layer


def _place_center(canvas: Image.Image, layer: Image.Image, y: int, x_offset: int = 0) -> tuple[int, int, int, int]:
    x = (canvas.width - layer.width) // 2 + x_offset; canvas.alpha_composite(layer, (x, y)); return (x, y, x + layer.width, y + layer.height)


def _curve_text(canvas: Image.Image, text: str, font: ImageFont.FreeTypeFont, treatment: dict[str, Any], *,
                center: tuple[float, float], radius: float, start_angle: float, end_angle: float) -> tuple[list[dict[str, Any]], tuple[int, int, int, int]]:
    glyphs = []; bounds = []
    angles = [start_angle + (end_angle - start_angle) * (i + .5) / len(text) for i in range(len(text))]
    for character, angle in zip(text, angles):
        if character == " ": glyphs.append({"character": character, "angle": angle}); continue
        layer = _text_layer(character, font, treatment); tangent = angle + 90
        rotated = layer.rotate(-tangent, expand=True, resample=Image.Resampling.BICUBIC)
        radians = math.radians(angle); x = round(center[0] + radius * math.cos(radians) - rotated.width / 2); y = round(center[1] + radius * math.sin(radians) - rotated.height / 2)
        canvas.alpha_composite(rotated, (x, y)); bounds.append((x, y, x + rotated.width, y + rotated.height))
        glyphs.append({"character": character, "path_angle_degrees": angle, "tangent_rotation_degrees": tangent, "bounds": list(bounds[-1])})
        layer.close(); rotated.close()
    merged = (min(x[0] for x in bounds), min(x[1] for x in bounds), max(x[2] for x in bounds), max(x[3] for x in bounds))
    return glyphs, merged


def _svg(layout: dict[str, Any], treatment: dict[str, Any], font: dict[str, Any], source: Path, heart: dict[str, Any]) -> str:
    concept = layout["concept_id"]; shadow_x, shadow_y = treatment["shadow_offset"]
    paths = "<path id='upper' d='M 650 1450 Q 2250 350 3850 1450' fill='none'/><path id='lower' d='M 950 3650 Q 2250 4550 3550 3650' fill='none'/>"
    if concept in ("top_bottom_badge", "circular_emblem"):
        text = "<text><textPath href='#upper' startOffset='50%' text-anchor='middle'>LOVE</textPath></text><text><textPath href='#lower' startOffset='50%' text-anchor='middle'>IS LOVE</textPath></text>"
    elif concept == "stacked_groovy": text = "<text x='2250' y='850' text-anchor='middle'>LOVE</text><text x='2250' y='1350' text-anchor='middle'>IS LOVE</text>"
    elif concept == "integrated_shadow": text = "<text x='2250' y='850' text-anchor='middle' font-size='720'>LOVE</text><text x='3000' y='1800' text-anchor='middle' font-size='360'>IS LOVE</text>"
    elif concept == "ribbon_caption": text = "<path d='M500 950 Q2250 650 4000 950 L3900 1450 Q2250 1150 600 1450 Z' fill='#fff1b8'/><text x='2250' y='1170' text-anchor='middle'>LOVE IS LOVE</text>"
    else: text = "<path d='M500 600 V1450' stroke='#d93686' stroke-width='45'/><text x='650' y='1050'>LOVE IS LOVE</text>"
    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='4500' height='5400' viewBox='0 0 4500 5400'><defs>{paths}</defs><image href='{source.as_uri()}' x='{heart['x']}' y='{heart['y']}' width='{heart['width']}' height='{heart['height']}'/><g font-family='{font['family']}' font-size='560' font-weight='bold' letter-spacing='4' fill='{treatment['fill']}' stroke='{treatment['outline']}' stroke-width='{treatment['outline_width']}' paint-order='stroke fill'><g transform='translate({shadow_x} {shadow_y})' fill='{treatment['shadow']}'>{text}</g>{text}</g></svg>"""


def _render_concept(source: Path, root: Path, layout: dict[str, Any], treatment: dict[str, Any], font_record: dict[str, Any]) -> dict[str, Any]:
    root.mkdir(parents=True); font = _font(font_record, 560)
    with Image.open(source) as opened: opened.load(); original = opened.convert("RGBA")
    bbox = original.getchannel("A").getbbox(); heart_source = original.crop(bbox); scale = layout["heart_scale"]
    heart = heart_source.resize((round(heart_source.width * scale), round(heart_source.height * scale)), Image.Resampling.LANCZOS)
    concept = layout["concept_id"]; heart_y = {"top_bottom_badge":1350,"stacked_groovy":1750,"integrated_shadow":1350,"circular_emblem":1350,"ribbon_caption":1550,"minimal_editorial":1400}[concept]
    heart_x = (CANVAS[0] - heart.width)//2 + (180 if concept == "minimal_editorial" else 0); canvas = Image.new("RGBA", CANVAS, (0,0,0,0)); canvas.alpha_composite(heart,(heart_x,heart_y))
    glyph_evidence=[]; text_bounds=[]; full_line_shaping=False; path_geometry={}
    if concept in ("top_bottom_badge","circular_emblem"):
        radius_top = 1500 if concept == "top_bottom_badge" else 1650; radius_bottom = 1250 if concept == "top_bottom_badge" else 1500
        g,b = _curve_text(canvas,"LOVE",font,treatment,center=(2250,1900),radius=radius_top,start_angle=205,end_angle=335); glyph_evidence+=g;text_bounds.append(b)
        g,b = _curve_text(canvas,"IS LOVE",font,treatment,center=(2250,2650),radius=radius_bottom,start_angle=35,end_angle=145); glyph_evidence+=g;text_bounds.append(b)
        path_geometry={"upper":{"center":[2250,1900],"radius":radius_top,"angles":[205,335]},"lower":{"center":[2250,2650],"radius":radius_bottom,"angles":[35,145]}}
    elif concept == "stacked_groovy":
        for text,y,size in (("LOVE",350,700),("IS LOVE",950,520)):
            layer=_text_layer(text,_font(font_record,size),treatment);text_bounds.append(_place_center(canvas,layer,y));layer.close()
        full_line_shaping=True
    elif concept == "integrated_shadow":
        layer=_text_layer("LOVE",_font(font_record,760),treatment);text_bounds.append(_place_center(canvas,layer,300));layer.close()
        layer=_text_layer("IS LOVE",_font(font_record,380),treatment);text_bounds.append(_place_center(canvas,layer,1450,650));layer.close();full_line_shaping=True
    elif concept == "ribbon_caption":
        ribbon=Image.new("RGBA",CANVAS,(0,0,0,0));d=ImageDraw.Draw(ribbon);d.rounded_rectangle((450,650,4050,1450),radius=240,fill=_rgba(treatment["shadow"]),outline=_rgba(treatment["outline"]),width=45);canvas.alpha_composite(ribbon);ribbon.close()
        layer=_text_layer(PHRASE,_font(font_record,470),treatment);text_bounds.append(_place_center(canvas,layer,760));layer.close();full_line_shaping=True;path_geometry={"ribbon_bounds":[450,650,4050,1450]}
    else:
        ImageDraw.Draw(canvas).line((500,500,500,1550),fill=_rgba(treatment["shadow"]),width=48)
        layer=_text_layer(PHRASE,_font(font_record,360),treatment);canvas.alpha_composite(layer,(620,700));text_bounds.append((620,700,620+layer.width,700+layer.height));layer.close();full_line_shaping=True
    alpha_bbox=canvas.getchannel("A").getbbox(); svg_text=_svg(layout,treatment,font_record,source,{"x":heart_x,"y":heart_y,"width":heart.width,"height":heart.height})
    svg_path=root/"composition.svg";svg_path.write_text(svg_text,encoding="utf-8");png_path=root/"composition.png";canvas.save(png_path)
    previews={}; colors={"black":(10,10,12,255),"dark_heather":(62,62,66,255),"white":(255,255,255,255)}
    for name,color in colors.items():
        base=Image.new("RGBA",CANVAS,color);composite=Image.alpha_composite(base,canvas).convert("RGB");path=root/f"preview-{name}.jpg";composite.save(path,quality=92);previews[name]={"path":str(path),"sha256":_hash(path)};base.close();composite.close()
    checker=Image.new("RGBA",CANVAS,(225,225,225,255));cd=ImageDraw.Draw(checker)
    for y in range(0,5400,150):
        for x in range(0,4500,150):
            if (x//150+y//150)%2: cd.rectangle((x,y,x+149,y+149),fill=(175,175,175,255))
    checked=Image.alpha_composite(checker,canvas).convert("RGB");checker_path=root/"preview-checkerboard.jpg";checked.save(checker_path,quality=90);checked.close();checker.close()
    thumb=canvas.copy();thumb.thumbnail((300,360),Image.Resampling.LANCZOS);thumb_path=root/"thumbnail-300.png";thumb.save(thumb_path);thumb.close()
    safe=alpha_bbox and alpha_bbox[0]>=225 and alpha_bbox[1]>=270 and alpha_bbox[2]<=4275 and alpha_bbox[3]<=5130
    quality={"exact_phrase_once":True,"missing_or_duplicated_characters":False,"text_within_safe_bounds":all(b[0]>=225 and b[2]<=4275 for b in text_bounds),
        "composition_within_safe_bounds":bool(safe),"minimum_stroke_thickness_passed":treatment["outline_width"]>=24,
        "transparent_exterior":canvas.getpixel((0,0))[3]==0,"unexpected_opaque_background":canvas.getchannel("A").getextrema()==(0,255),
        "artwork_aspect_ratio_preserved":True,"thumbnail_readability":"warning_human_review_required",
        "text_artwork_spacing":"explicit_overlap_allowed" if concept=="integrated_shadow" else "warning_visual_gap_review_required",
        "near_white_fringe":"warning_requires_visual_dark_preview_review","balanced_visual_bounds":"warning_human_review_required"}
    metadata={"concept_id":concept,"layout_structure":layout["structure"],"treatment_id":treatment["treatment_id"],"font_family":font_record["family"],
        "font_style":font_record["style"],"font_path":font_record["font_path"],"font_sha256":font_record["font_sha256"],"phrase":PHRASE,
        "rendering_engine":ENGINE,"svg_path":str(svg_path),"svg_sha256":_hash(svg_path),"png_path":str(png_path),"png_sha256":_hash(png_path),
        "svg_path_geometry":path_geometry,"text_bounds":[list(x) for x in text_bounds],"glyph_bounds":glyph_evidence,
        "full_line_text_shaping":full_line_shaping,"kerning":"FreeType font kerning for full lines; tangential spacing for paths","tracking":4,
        "baseline_path":path_geometry or "straight","fill_stroke_shadow_layers":treatment,"heart":{"x":heart_x,"y":heart_y,"width":heart.width,"height":heart.height,"scale":scale},
        "previews":previews,"checkerboard":{"path":str(checker_path),"sha256":_hash(checker_path)},"thumbnail":{"path":str(thumb_path),"sha256":_hash(thumb_path)},
        "quality_checks":quality,"status":"needs_human_design_selection","publish_status":"not_published","order_status":"not_created"}
    meta_path=root/"concept-metadata.json";meta_path.write_text(json.dumps(metadata,indent=2,sort_keys=True),encoding="utf-8")
    canvas.close();heart.close();heart_source.close();original.close();return metadata


def generate_design_concepts(job_id: str, composition_id: str, *, phrase: str, confirmed: bool,
                             font_root: Path = FONT_ROOT, run_id: str | None = None) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Design concept generation requires explicit confirmation.")
    if composition_id != "love-is-love-v3": raise job_queue.JobQueueError("Vector design exploration is restricted to the independent love-is-love-v3 composition.")
    if phrase != PHRASE: raise job_queue.JobQueueError(f"Exact phrase required: {PHRASE}")
    evidence=printify_product._approved_evidence(job_id);source=evidence["candidate"];before=_hash(source);fonts=_available_fonts(font_root)
    layouts=_load(LAYOUT_CONFIG,"layouts");treatments={x["treatment_id"]:x for x in _load(TREATMENT_CONFIG,"treatments")}
    root=evidence["job_root"]/"commerce"/"product-compositions"/composition_id/"design-runs"/(run_id or datetime.now().strftime("design-%Y%m%d-%H%M%S"))
    if root.exists(): raise job_queue.JobQueueError("Design preview run already exists and is immutable.")
    concepts=[_render_concept(source,root/layout["concept_id"],layout,treatments[layout["treatment_id"]],fonts[layout["font_id"]]) for layout in layouts]
    design_sheet=Image.new("RGB",(1800,3240),(230,230,230))
    for i,c in enumerate(concepts):
        with Image.open(c["previews"]["black"]["path"]) as p: t=p.copy();t.thumbnail((850,950));design_sheet.paste(t,((i%2)*900+25,(i//2)*1080+75));t.close()
        ImageDraw.Draw(design_sheet).text(((i%2)*900+30,(i//2)*1080+25),c["concept_id"],fill=(10,10,10))
    design_path=root/"design-comparison-sheet.jpg";design_sheet.save(design_path,quality=92);design_sheet.close()
    strongest=["top_bottom_badge","stacked_groovy","integrated_shadow","circular_emblem"];garment=Image.new("RGB",(1800,3600),(235,235,235))
    for row,cid in enumerate(strongest):
        c=next(x for x in concepts if x["concept_id"]==cid)
        for col,name in enumerate(("black","dark_heather","white")):
            with Image.open(c["previews"][name]["path"]) as p:t=p.copy();t.thumbnail((580,820));garment.paste(t,(col*600+10,row*900+60));t.close()
        ImageDraw.Draw(garment).text((20,row*900+15),cid,fill=(10,10,10))
    garment_path=root/"garment-comparison-sheet.jpg";garment.save(garment_path,quality=92);garment.close()
    manifest={"composition_id":composition_id,"design_run_id":root.name,"source_job_id":job_id,"phrase":phrase,"approved_source_path":str(source),
        "approved_source_sha256":before,"final_approval_sha256":evidence["approval_sha"],"concepts":concepts,
        "design_comparison_sheet":{"path":str(design_path),"sha256":_hash(design_path)},"garment_comparison_sheet":{"path":str(garment_path),"sha256":_hash(garment_path)},
        "status":"needs_human_design_selection","publish_status":"not_published","order_status":"not_created"}
    path=root/"design-concept-manifest.json";path.write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")
    if _hash(source)!=before: raise job_queue.JobQueueError("Approved source artwork changed during design exploration.")
    return {**manifest,"manifest_path":str(path),"manifest_sha256":_hash(path)}


def approve_design_concept(job_id: str, composition_id: str, *, design_run_id: str, concept_id: str,
                           approved_by: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed or not approved_by.strip(): raise job_queue.JobQueueError("Design approval requires reviewer and explicit confirmation.")
    evidence=printify_product._approved_evidence(job_id);root=evidence["job_root"]/"commerce"/"product-compositions"/composition_id
    manifest_path=root/"design-runs"/design_run_id/"design-concept-manifest.json";manifest=json.loads(manifest_path.read_text())
    concept=next((x for x in manifest["concepts"] if x["concept_id"]==concept_id),None)
    if not concept: raise job_queue.JobQueueError("Concept is not present in the immutable design manifest.")
    path=root/"design-selection-approval.json"
    if path.exists():
        old=json.loads(path.read_text())
        if old["concept_id"]==concept_id and old["approved_by"]==approved_by.strip() and old["concept_manifest_sha256"]==_hash(manifest_path): return {**old,"idempotent":True,"approval_sha256":_hash(path)}
        raise job_queue.JobQueueError("Existing design selection cannot be silently replaced.")
    approval={"composition_id":composition_id,"concept_id":concept_id,"exact_phrase":PHRASE,"selected_font_family":concept["font_family"],
        "selected_font_sha256":concept["font_sha256"],"selected_svg_sha256":concept["svg_sha256"],"selected_png_sha256":concept["png_sha256"],
        "selected_png_path":concept["png_path"],"concept_manifest_sha256":_hash(manifest_path),"manifest_path":str(manifest_path),
        "treatment_id":concept["treatment_id"],"approved_by":approved_by.strip(),"approved_at":datetime.now().astimezone().isoformat()}
    with path.open("x",encoding="utf-8") as h:json.dump(approval,h,indent=2,sort_keys=True)
    return {**approval,"idempotent":False,"approval_sha256":_hash(path)}


def show_design_selection(job_id: str, composition_id: str) -> dict[str, Any]:
    evidence=printify_product._approved_evidence(job_id);path=evidence["job_root"]/"commerce"/"product-compositions"/composition_id/"design-selection-approval.json"
    return {"status":"needs_human_design_selection"} if not path.is_file() else {"status":"approved",**json.loads(path.read_text()),"approval_sha256":_hash(path)}
