#!/usr/bin/env python3
"""
Watch SamsungTVImageStore for new images and auto-crop to 4K (3840x2160)
using focal point detection (face detection → entropy fallback).

Usage:
  crop_for_tv.py --watch       # watch folder continuously (blocking)
  crop_for_tv.py --file <path> # crop a single file
  crop_for_tv.py --all         # crop any uncropped files in the folder
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import argparse
import os
import re
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from lib.utils import console

# Camera/auto-generated prefixes to strip from the start of a filename stem.
# After stripping, whatever meaningful text remains becomes the caption.
_CAMERA_PREFIX_RE = re.compile(
    r"^("
    r"_?dsc[fn]?\d+"       # _DSC2397, DSC0001, DSCF001, DSCN001
    r"|img_?\d+"            # IMG_1234, IMG1234
    r"|r\d{7}"              # R0001234 (Ricoh)
    r"|mvc[-_]\d+"          # MVC-001 (old Sony)
    r"|mvi_?\d+"            # MVI_1234 (Canon video)
    r"|vid[-_]?\d+"         # VID_20240101
    r"|photo[-_]\d+"        # PHOTO_001
    r"|pic[-_]\d+"          # PIC_001
    r"|pano[-_]\d+"         # PANO_001
    r"|screenshot[-_\d]*"   # screenshot_2024...
    r"|\d{8}[-_]?\d*"       # 20161012_162701 (date/datetime stamps)
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUID
    r")",
    re.IGNORECASE,
)

# Candidate font paths (tried in order; first found wins)
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",  # macOS fallback
]
_CAPTION_FONT_SIZE = 72   # px at 4K; scales down for smaller images


def caption_for(src: Path) -> str | None:
    """Return a human-readable caption derived from the filename, or None if meaningless."""
    stem = src.stem
    if stem.endswith("_cropped"):
        stem = stem[: -len("_cropped")]
    # Strip leading punctuation then any camera prefix, then trailing noise
    stem = stem.lstrip("_-~")
    stem = _CAMERA_PREFIX_RE.sub("", stem, count=1).lstrip("_-~")
    # Strip trailing version/sync noise like v2, ~1v2, v3
    stem = re.sub(r"[~v]\d+$", "", stem, flags=re.IGNORECASE).rstrip("_-~")
    text = re.sub(r"[-_]+", " ", stem).strip()
    # Require at least 2 words, each with 2+ letters
    words = [w for w in text.split() if re.search(r"[a-z]{2,}", w, re.IGNORECASE)]
    if len(words) < 2:
        return None
    return text.title()


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _burn_caption(img: Image.Image, text: str) -> Image.Image:
    """Burn text caption into bottom-left of image, returning the modified image."""
    draw = ImageDraw.Draw(img, "RGBA")
    # Scale font to image width
    font_size = max(24, int(_CAPTION_FONT_SIZE * img.width / TV_W))
    font = _load_font(font_size)

    pad = font_size // 2
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    x = pad
    y = img.height - th - pad * 2

    # Semi-transparent dark pill behind text
    draw.rectangle(
        [x - pad // 2, y - pad // 2, x + tw + pad // 2, y + th + pad // 2],
        fill=(0, 0, 0, 140),
    )
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 230))
    return img

SOURCE_DIR     = Path(os.environ.get("FRAME_SOURCE_DIR", "/Volumes/FastDrive/SamsungTVImageStore"))
OUTPUT_DIR     = Path(os.environ.get("FRAME_IMAGE_DIR",  "/Volumes/FastDrive/SamsungTVImageStore"))
CROP_SUFFIX    = "_cropped"
TV_W, TV_H     = 3840, 2160  # 4K landscape
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png"}

# OpenCV face detector
_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def is_cropped(path: Path) -> bool:
    return CROP_SUFFIX in path.stem


def output_path(src: Path) -> Path:
    return OUTPUT_DIR / (src.stem + CROP_SUFFIX + src.suffix)


def detect_focal_point(img_cv) -> tuple[int, int]:
    """Return (cx, cy) focal point. Uses face detection, falls back to entropy map."""
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) > 0:
        # Centre of the largest face
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]
        return x + w // 2, y + h // 2

    # Entropy fallback: find the most visually complex region, biased toward centre
    h, w = gray.shape
    block = 64
    max_dist = ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5
    best_val, best_cx, best_cy = -1, w // 2, h // 2
    for row in range(0, h - block, block // 2):
        for col in range(0, w - block, block // 2):
            patch = gray[row:row + block, col:col + block]
            hist = cv2.calcHist([patch], [0], None, [256], [0, 256])
            hist /= hist.sum()
            entropy = -np.sum(hist * np.log2(hist + 1e-10))
            # Apply a gentle centre bias: up to 25% penalty at the image edges
            cx, cy = col + block // 2, row + block // 2
            dist = ((cx - w / 2) ** 2 + (cy - h / 2) ** 2) ** 0.5
            weighted = entropy * (1 - 0.25 * dist / max_dist)
            if weighted > best_val:
                best_val = weighted
                best_cx, best_cy = cx, cy
    return best_cx, best_cy


def crop_to_4k(src: Path) -> Path | None:
    """Crop src image to 4K centred on focal point. Returns output path or None on skip."""
    if is_cropped(src):
        return None

    out = output_path(src)
    if out.exists():
        return None  # already processed

    img_pil = Image.open(src).convert("RGB")
    iw, ih = img_pil.size

    caption = caption_for(src)

    # If already 4K or smaller in both dims, just copy (or caption-only)
    if iw <= TV_W and ih <= TV_H:
        if caption:
            img_pil = _burn_caption(img_pil, caption)
            img_pil.save(out, quality=95)
        else:
            shutil.copy2(src, out)
        console.print(f"[dim]small, {'captioned' if caption else 'copying as-is'}:[/dim] {src.name}")
        return out

    # Scale down so the shorter side matches 4K target
    scale = max(TV_W / iw, TV_H / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    img_pil = img_pil.resize((new_w, new_h), Image.LANCZOS)

    # Detect focal point on scaled image
    img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    cx, cy = detect_focal_point(img_cv)

    # Crop box centred on focal point, clamped to bounds
    left  = max(0, min(cx - TV_W // 2, new_w - TV_W))
    top   = max(0, min(cy - TV_H // 2, new_h - TV_H))
    cropped = img_pil.crop((left, top, left + TV_W, top + TV_H))
    if caption:
        cropped = _burn_caption(cropped, caption)

    try:
        cropped.save(out, quality=95)
    except PermissionError:
        console.print(f"[red]permission denied writing:[/red] {out} — check NAS write access for the mount user")
        return None
    caption_note = f" caption='{caption}'" if caption else ""
    console.print(f"[green]cropped:[/green] {src.name} → {out.name} (focal {cx},{cy}{caption_note})")
    return out


def process_all():
    images = [p for p in SOURCE_DIR.iterdir()
              if p.suffix.lower() in SUPPORTED_EXTS and not is_cropped(p)]
    if not images:
        console.print("[yellow]No uncropped images found.[/yellow]")
        return
    for img in sorted(images):
        crop_to_4k(img)


def watch():
    console.print(f"[bold]Watching[/bold] {SOURCE_DIR} → {OUTPUT_DIR}")
    seen = set(SOURCE_DIR.iterdir())
    while True:
        time.sleep(5)
        current = set(SOURCE_DIR.iterdir())
        new_files     = current - seen
        removed_files = seen - current
        seen = current

        for f in sorted(new_files):
            if f.suffix.lower() in SUPPORTED_EXTS and not is_cropped(f):
                console.print(f"[cyan]new file:[/cyan] {f.name}")
                time.sleep(1)  # wait briefly in case file is still copying
                crop_to_4k(f)

        for f in sorted(removed_files):
            if f.suffix.lower() in SUPPORTED_EXTS and not is_cropped(f):
                out = output_path(f)
                if out.exists():
                    out.unlink()
                    console.print(f"[yellow]removed:[/yellow] {out.name} (source deleted)")
                else:
                    console.print(f"[dim]source deleted (no cropped output to clean up):[/dim] {f.name}")


def main():
    parser = argparse.ArgumentParser(description="Auto-crop images to 4K for Frame TV")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--watch", action="store_true", help="Watch folder for new files")
    group.add_argument("--file",  type=Path, metavar="PATH", help="Crop a single file")
    group.add_argument("--all",   action="store_true", help="Crop all uncropped files in folder")
    args = parser.parse_args()

    if args.watch:
        watch()
    elif args.file:
        crop_to_4k(args.file)
    elif args.all:
        process_all()


if __name__ == "__main__":
    main()
