"""
Image Generator Service - Generates images via fal.ai Flux Pro 2.
Prompt format: {subject}, {outfit}, {pose}, {setting}, {camera style}, {quality suffix}
NSFW handled purely through prompt text. 30% nude (chest-hidden), 70% suggestive.
Generated images are watermarked with CamHours branding.
"""

import os
import re
import json
import random
import hashlib
import httpx
import fal_client
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

from ..config import settings


# Fal.ai config
FAL_MODEL = "fal-ai/flux-pro/v1.1-ultra"
FAL_MODEL_FALLBACK = "fal-ai/flux-realism"
FAL_API_KEY = settings.fal_api_key or os.environ.get("FAL_API_KEY", "")

# Font for watermark
FONT_PATH = None
for fp in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
]:
    if os.path.exists(fp):
        FONT_PATH = fp
        break

# CamHours accent color (pink)
ACCENT_COLOR = (236, 72, 153)

# ─── Prompt Components ───────────────────────────────────────────────────────

SUBJECT_AGES = [
    "21 year old", "22 year old", "23 year old", "24 year old",
    "25 year old", "26 year old", "27 year old", "28 year old", "29 year old",
]
SUBJECT_ETHNICITIES = [
    "caucasian", "latina", "mixed race", "mediterranean",
    "eastern european", "brazilian", "french", "italian", "spanish",
]
SUBJECT_HAIR_COLOR = [
    "blonde", "platinum blonde", "dirty blonde", "brunette",
    "dark brown", "black", "auburn", "red", "strawberry blonde",
]
SUBJECT_HAIR_LENGTH = [
    "short hair", "shoulder-length hair", "long hair", "wavy long hair",
    "straight long hair", "curly hair", "loose waves",
]
SUBJECT_EYES = [
    "blue eyes", "green eyes", "brown eyes", "hazel eyes",
    "grey eyes", "dark eyes", "light brown eyes",
]
SUBJECT_BUILD = [
    "slim build", "athletic build", "petite build", "curvy build",
    "slender build", "toned build",
]

SETTINGS = [
    "luxurious bedroom with silk sheets and warm lamplight",
    "modern bathroom with steam, glass shower and warm overhead lighting",
    "luxury hotel suite with floor-to-ceiling windows, city lights at night",
    "balcony overlooking the ocean at sunset, sheer curtains blowing",
    "spa room with massage table, candles, and warm stone accents",
    "dimly lit boudoir with velvet drapes and golden hour window light",
    "rooftop pool at dusk, city skyline in background, warm ambient light",
    "private beach at golden hour, soft sand, gentle waves",
    "modern penthouse living room, minimalist, floor-to-ceiling windows at night",
    "sunlit bedroom with white linen, morning light through sheer curtains",
    "vintage dressing room with vanity mirror, warm bulb lighting",
    "candlelit studio with dark walls and soft directional lighting",
    "tropical cabana by the pool, palm shadows, golden midday light",
    "rain-streaked window at night, moody ambient light, urban backdrop",
]

# Suggestive outfits (70%)
OUTFITS_SUGGESTIVE = [
    "wearing a see-through negligee",
    "in lace lingerie",
    "wrapped in a towel loosely falling open",
    "wearing a micro bikini",
    "in an open robe revealing bare skin",
    "wearing sheer bodysuit",
    "in strappy lingerie set",
    "wearing a barely-there bikini top and shorts",
    "in a thin white shirt, wet",
    "draped in an open silk kimono",
]

# Nude outfits (30%) — all chest-hidden
OUTFITS_NUDE = [
    "nude with strategically placed bedsheets covering chest",
    "nude, back to camera",
    "water running down bare skin, viewed from behind",
    "nude, silhouetted against city lights",
    "nude, submerged to shoulders in bath",
    "nude, draped in sheer fabric across chest",
    "nude, hair falling forward covering chest",
    "nude, arms raised framing face, side profile",
]

# Suggestive poses (paired with suggestive outfits)
POSES_SUGGESTIVE = [
    "arching back sensually on bed",
    "leaning against wall, confident expression",
    "sitting on edge of bed, legs crossed, looking at camera",
    "standing under shower, eyes closed, head tilted back",
    "reclining on chaise, one leg raised, direct gaze",
    "kneeling on bed, looking over shoulder",
    "lying on stomach, propped on elbows, looking at camera",
    "standing at window, silhouette framed by light",
    "seated at vanity, looking at reflection then camera",
    "lying on side, silk sheets pooled around hips",
]

# Nude poses — chest-hidden only
POSES_NUDE = [
    "lying face down on silk sheets, looking to side",
    "standing under water, back to camera",
    "silhouetted behind steamed glass",
    "relaxing in bathtub, submerged to shoulders",
    "sitting on floor, knees drawn up, arms wrapped around legs",
    "back to camera, looking over shoulder at camera",
    "lying in bed, face down, sheet draped over lower body",
    "standing at window, arms raised, backlit silhouette",
]

# Camera styles
CAMERA_STYLES = [
    "editorial photography, medium shot",
    "cinematic photography, shallow depth of field",
    "film photography aesthetic, slight grain",
    "fashion photography, natural light",
    "boudoir photography, soft focus",
    "portrait photography, 85mm lens, bokeh background",
]

# Always appended
QUALITY_SUFFIX = "photorealistic, high detail, anatomically correct, natural skin texture"

# Nude probability
NUDE_PROBABILITY = 0.30


def _build_subject() -> str:
    age = random.choice(SUBJECT_AGES)
    ethnicity = random.choice(SUBJECT_ETHNICITIES)
    hair_color = random.choice(SUBJECT_HAIR_COLOR)
    hair_length = random.choice(SUBJECT_HAIR_LENGTH)
    eyes = random.choice(SUBJECT_EYES)
    build = random.choice(SUBJECT_BUILD)
    return f"{age} {ethnicity} woman, {hair_color} {hair_length}, {eyes}, {build}"


def _build_prompt(is_nude: bool) -> str:
    """Build a full prompt from randomized components."""
    subject = _build_subject()
    setting = random.choice(SETTINGS)
    camera = random.choice(CAMERA_STYLES)

    if is_nude:
        outfit = random.choice(OUTFITS_NUDE)
        pose = random.choice(POSES_NUDE)
    else:
        outfit = random.choice(OUTFITS_SUGGESTIVE)
        pose = random.choice(POSES_SUGGESTIVE)

    return f"{subject}, {outfit}, {pose}, {setting}, {camera}, {QUALITY_SUFFIX}"


def _add_camhours_watermark(img_bytes: bytes) -> bytes:
    """Add 'CamHours' text watermark: 'Cam' white + 'Hours' pink, semi-transparent pill."""
    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(28, int(w * 0.04))
    font = ImageFont.truetype(FONT_PATH, font_size) if FONT_PATH else ImageFont.load_default()

    full_bbox = draw.textbbox((0, 0), "CamHours", font=font)
    text_w = full_bbox[2] - full_bbox[0]
    text_h = full_bbox[3] - full_bbox[1]
    text_y_offset = full_bbox[1]
    cam_w = draw.textlength("Cam", font=font)

    pad_x, pad_y = 14, 10
    margin = int(w * 0.02)
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    pill_x = w - pill_w - margin
    pill_y = h - pill_h - margin

    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=8,
        fill=(0, 0, 0, 140),
    )

    tx = pill_x + pad_x
    ty = pill_y + pad_y - text_y_offset
    draw.text((tx, ty), "Cam", font=font, fill=(255, 255, 255, 230))
    draw.text((tx + cam_w, ty), "Hours", font=font, fill=(*ACCENT_COLOR, 230))

    result = Image.alpha_composite(img, overlay)
    buf = BytesIO()
    result.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _image_hash(img_bytes: bytes) -> str:
    return hashlib.md5(img_bytes).hexdigest()


def _load_used_hashes(used_file: Path) -> set:
    try:
        if used_file.exists():
            return set(json.loads(used_file.read_text()))
    except Exception:
        pass
    return set()


def _save_used_hashes(used_file: Path, hashes: set) -> None:
    try:
        used_file.parent.mkdir(parents=True, exist_ok=True)
        used_file.write_text(json.dumps(list(hashes)[-1000:]))
    except Exception as e:
        print(f"Warning: couldn't save used image hashes: {e}")


async def _generate_fal_image(prompt: str) -> Optional[bytes]:
    """Call fal.ai — tries flux-pro/v1.1-ultra first, falls back to flux-realism."""
    if not FAL_API_KEY:
        raise ValueError("FAL_API_KEY not configured")

    os.environ["FAL_KEY"] = FAL_API_KEY

    models = [
        (FAL_MODEL, {"aspect_ratio": "16:9", "num_images": 1, "output_format": "jpeg", "safety_tolerance": "5"}),
        (FAL_MODEL_FALLBACK, {"image_size": "landscape_16_9", "num_inference_steps": 28, "guidance_scale": 3.5, "num_images": 1, "output_format": "jpeg"}),
    ]

    for model, args in models:
        try:
            result = await fal_client.run_async(model, arguments={"prompt": prompt, **args})
            images = result.get("images", [])
            if not images:
                print(f"fal.ai {model}: no images returned, trying fallback...")
                continue
            image_url = images[0].get("url")
            if not image_url:
                continue
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                if model != FAL_MODEL:
                    print(f"fal.ai: used fallback model {model}")
                return resp.content
        except Exception as e:
            print(f"fal.ai {model} error: {e}, trying fallback...")
            continue

    return None


async def generate_article_images(
    order_id: str,
    image_descriptions: List[str],
    output_dir: str = None,
) -> List[Dict[str, str]]:
    """
    Generate images via fal.ai Flux Pro 2.
    Prompts built from randomized subject + outfit + pose + setting + camera style.
    70% suggestive, 30% nude (chest-hidden). Watermarked. Deduplicated by hash.

    Args:
        order_id: Order ID for organizing images
        image_descriptions: List of descriptions (used for count; content drives prompt variety)
        output_dir: Optional custom output directory

    Returns:
        List of dicts with: {"description": str, "path": str, "url": str}
    """
    if not FAL_API_KEY:
        raise ValueError("FAL_API_KEY not configured")

    if not image_descriptions:
        return []

    if output_dir is None:
        output_dir = f"data/images/{order_id}"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    used_hashes_file = Path("data/images/_used_hashes.json")
    used_hashes = _load_used_hashes(used_hashes_file)

    results = []

    for idx, description in enumerate(image_descriptions, 1):
        try:
            is_nude = random.random() < NUDE_PROBABILITY
            prompt = _build_prompt(is_nude)

            nude_label = " [nude]" if is_nude else " [suggestive]"
            print(f"Image {idx}{nude_label}: {prompt[:100]}...")

            img_data = None
            for attempt in range(2):
                img_data = await _generate_fal_image(prompt)
                if img_data:
                    break
                print(f"  Attempt {attempt + 1} failed, retrying with new prompt...")
                prompt = _build_prompt(is_nude)

            if not img_data:
                print(f"Image {idx}: generation failed after 2 attempts")
                continue

            # Dedup by hash
            img_hash = _image_hash(img_data)
            if img_hash in used_hashes:
                print(f"Image {idx}: duplicate hash, regenerating...")
                img_data = await _generate_fal_image(_build_prompt(is_nude))
                if not img_data:
                    continue
                img_hash = _image_hash(img_data)

            used_hashes.add(img_hash)

            # Watermark
            watermarked = _add_camhours_watermark(img_data)

            # Save
            filename = f"image_{idx}.jpg"
            filepath = output_path / filename
            with open(filepath, "wb") as f:
                f.write(watermarked)

            results.append({
                "description": description,
                "path": str(filepath),
                "url": f"/api/v1/images/{order_id}/{filename}?t={int(__import__('time').time())}",
                "hash": img_hash,
                "nude": is_nude,
            })

            print(f"Image {idx}: saved {filepath} ({len(watermarked) // 1024}KB)")

        except Exception as e:
            print(f"Error generating image {idx}: {e}")
            continue

    _save_used_hashes(used_hashes_file, used_hashes)
    return results


def extract_image_placeholders(article_content: str) -> List[str]:
    """Extract image descriptions from [IMAGE: description] markers."""
    pattern = r'\[IMAGE:\s*([^\]]+)\]'
    matches = re.findall(pattern, article_content, re.IGNORECASE)
    return [m.strip() for m in matches]


def replace_image_placeholders(
    article_content: str,
    image_results: List[Dict[str, str]]
) -> str:
    """Replace [IMAGE: description] placeholders with markdown image references."""
    result = article_content

    for img in image_results:
        pattern = rf'\[IMAGE:\s*{re.escape(img["description"])}\s*\]'
        alt_text = img["description"][:100]
        markdown_img = f'![{alt_text}]({img["url"]})'
        result = re.sub(pattern, markdown_img, result, count=1, flags=re.IGNORECASE)

    result = re.sub(r'\[IMAGE:[^\]]+\]', '', result, flags=re.IGNORECASE)
    return result
