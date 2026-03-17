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
import json
import os
import re
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import os
import torch
os.environ.setdefault("TORCH_CPP_LOG_LEVEL", "ERROR")  # suppress NNPACK/hardware warnings
torch.backends.mkldnn.enabled = False  # KVM VMs often lack AVX2; disable oneDNN

from ultralytics import YOLO
from lib.utils import console

# YOLO subject detector — person (0) and dog (16) classes
# Model is stored alongside the repo root; absolute path avoids working-dir issues in systemd
_MODEL_PATH = Path(__file__).parent.parent / "yolov8n.pt"
_YOLO = YOLO(str(_MODEL_PATH))
_YOLO_SUBJECTS = {0, 16}  # COCO: 0=person, 16=dog

# Camera/auto-generated prefixes to strip from the start of a filename stem.
# After stripping, whatever meaningful text remains becomes the caption.
_CAMERA_PREFIX_RE = re.compile(
    r"^("
    r"_?dsc[fn]?\d+"       # _DSC2397, DSC0001, DSCF001, DSCN001
    r"|(img|vid)-\d{8}-wa\d+"  # IMG-20231111-WA0008, VID-20231111-WA0008 (WhatsApp)
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
    # Restore possessives encoded as _s_ or _s at end (e.g. Quito_s_adventure → Quito's adventure)
    stem = re.sub(r"_s(?=_|$)", "'s", stem)
    text = re.sub(r"[-_]+", " ", stem).strip()
    # Require at least 2 meaningful words (2+ letters, not image-processing noise)
    _NOISE_WORDS = {"crop", "cropped", "edit", "edited", "resize", "resized",
                    "copy", "final", "draft", "temp", "tmp", "new", "old", "v2", "v3"}
    words = [w for w in text.split()
             if re.search(r"[a-z]{2,}", w, re.IGNORECASE) and w.lower() not in _NOISE_WORDS]
    if len(words) < 2:
        return None
    return " ".join(w.capitalize() for w in words)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _burn_text_overlay(img: Image.Image, text: str, x: int, y: int) -> Image.Image:
    """Burn a text label at (x, y) onto img using a dark backing box."""
    font_size = max(24, int(_CAPTION_FONT_SIZE * img.width / TV_W))
    font = _load_font(font_size)
    pad = font_size // 2

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    draw.rectangle(
        [x - pad // 2, y - pad // 2, x + tw + pad // 2, y + th + pad // 2],
        fill=(0, 0, 0, 140),
    )
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 230))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _burn_caption(img: Image.Image, text: str) -> Image.Image:
    """Burn caption into bottom-left of image."""
    font_size = max(24, int(_CAPTION_FONT_SIZE * img.width / TV_W))
    font = _load_font(font_size)
    pad = font_size // 2
    bbox = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    return _burn_text_overlay(img, text, x=pad, y=img.height - th - pad * 2)


def _burn_debug_label(img: Image.Image, text: str) -> Image.Image:
    """Burn a debug label into the top-right of image."""
    font_size = max(24, int(_CAPTION_FONT_SIZE * img.width / TV_W))
    font = _load_font(font_size)
    pad = font_size // 2
    bbox = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    return _burn_text_overlay(img, text, x=img.width - tw - pad, y=pad)

SOURCE_DIR     = Path(os.environ.get("FRAME_SOURCE_DIR", "/Volumes/FastDrive/SamsungTVImageStore"))
OUTPUT_DIR     = Path(os.environ.get("FRAME_IMAGE_DIR",  "/Volumes/FastDrive/SamsungTVImageStore"))
CROP_SUFFIX    = "_cropped"
TV_W, TV_H     = 3840, 2160  # 4K landscape
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png"}

def is_cropped(path: Path) -> bool:
    return CROP_SUFFIX in path.stem


def output_path(src: Path) -> Path:
    return OUTPUT_DIR / (src.stem + CROP_SUFFIX + src.suffix)


_YOLO_CLASS_NAMES = {0: "person", 16: "dog"}


def detect_focal_point(img_cv) -> tuple[int, int, tuple | None, list]:
    """Return (cx, cy, subject_box, detections).

    subject_box: (x1,y1,x2,y2) union of all detected subjects, or None.
    detections: list of dicts with keys class, conf, box — empty if none found.

    Priority:
      1. YOLO subject detection (person + dog) — weighted centroid of all hits
      2. Entropy fallback with centre bias for landscapes/abstract images
    """
    h, w = img_cv.shape[:2]

    # 1. YOLO subject detection
    results = _YOLO(img_cv, verbose=False)[0]
    subjects = [
        box for box in results.boxes
        if int(box.cls) in _YOLO_SUBJECTS and float(box.conf) > 0.4
    ]
    if subjects:
        total_w, cx_sum, cy_sum = 0.0, 0.0, 0.0
        ux1, uy1, ux2, uy2 = w, h, 0.0, 0.0
        detections = []
        for box in subjects:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            area = (x2 - x1) * (y2 - y1)
            cx_sum += ((x1 + x2) / 2) * area
            cy_sum += ((y1 + y2) / 2) * area
            total_w += area
            ux1, uy1 = min(ux1, x1), min(uy1, y1)
            ux2, uy2 = max(ux2, x2), max(uy2, y2)
            detections.append({
                "class": _YOLO_CLASS_NAMES.get(int(box.cls), str(int(box.cls))),
                "conf": round(float(box.conf), 3),
                "box": [round(v) for v in (x1, y1, x2, y2)],
            })
        return int(cx_sum / total_w), int(cy_sum / total_w), (ux1, uy1, ux2, uy2), detections

    # 2. Entropy fallback with centre bias
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    block = 64
    max_dist = ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5
    best_val, best_cx, best_cy = -1, w // 2, h // 2
    for row in range(0, h - block, block // 2):
        for col in range(0, w - block, block // 2):
            patch = gray[row:row + block, col:col + block]
            hist = cv2.calcHist([patch], [0], None, [256], [0, 256])
            hist /= hist.sum()
            entropy = -np.sum(hist * np.log2(hist + 1e-10))
            cx, cy = col + block // 2, row + block // 2
            dist = ((cx - w / 2) ** 2 + (cy - h / 2) ** 2) ** 0.5
            weighted = entropy * (1 - 0.25 * dist / max_dist)
            if weighted > best_val:
                best_val = weighted
                best_cx, best_cy = cx, cy
    return best_cx, best_cy, None, []


def crop_to_4k(src: Path, *, out_path: Path = None, debug_label: str = None) -> Path | None:
    """Crop src image to 4K centred on focal point. Returns output path or None on skip.

    out_path: override the default output filename (used by debug mode).
    debug_label: if set, burned into the top-right corner (debug mode only).
    """
    if is_cropped(src):
        return None
    if "nocrop" in src.stem.lower():
        console.print(f"[dim]skipping (nocrop):[/dim] {src.name}")
        return None

    out = out_path or output_path(src)
    if out.exists():
        return None  # already processed

    raw = Image.open(src)
    img_pil = ImageOps.exif_transpose(raw).convert("RGB")
    exif_rotated = raw.size != img_pil.size  # True if transpose swapped width/height
    iw, ih = img_pil.size

    if exif_rotated:
        console.print(f"[cyan]EXIF rotation applied:[/cyan] {src.name} ({raw.size[0]}x{raw.size[1]} → {iw}x{ih})")

    caption = caption_for(src)

    # If already 4K or smaller in both dims, save the (exif-corrected) image directly.
    # shutil.copy2 would carry the original EXIF rotation tag which some displays mishandle.
    if iw <= TV_W and ih <= TV_H:
        if caption:
            img_pil = _burn_caption(img_pil, caption)
        if debug_label:
            img_pil = _burn_debug_label(img_pil, debug_label)
        img_pil.save(out, quality=95)
        console.print(f"[dim]small, {'captioned' if caption else 'copying as-is'}:[/dim] {src.name}")
        return out

    # Scale to fill (shorter side matches 4K) then detect subject
    fill_scale = max(TV_W / iw, TV_H / ih)
    fit_scale  = min(TV_W / iw, TV_H / ih)
    new_w, new_h = int(iw * fill_scale), int(ih * fill_scale)
    img_scaled = img_pil.resize((new_w, new_h), Image.LANCZOS)

    img_cv = cv2.cvtColor(np.array(img_scaled), cv2.COLOR_RGB2BGR)
    cx, cy, subject_box, detections = detect_focal_point(img_cv)

    # When no subject detected (entropy fallback), the focal point is uncertain.
    # Back off 75% toward fit scale to avoid aggressively cropping the wrong area.
    if not detections:
        scale = fit_scale + 0.25 * (fill_scale - fit_scale)
        new_w, new_h = int(iw * scale), int(ih * scale)
        img_scaled = img_pil.resize((new_w, new_h), Image.LANCZOS)
        cx = int(cx * scale / fill_scale)
        cy = int(cy * scale / fill_scale)
    else:
        scale = fill_scale

    # If the subject fills the frame (larger than the crop window in either dimension),
    # fit the original into 4K with black padding instead of cropping — avoids cutting
    # off subjects that span the whole image.
    if subject_box is not None:
        sx1, sy1, sx2, sy2 = subject_box
        subject_too_large = (sx2 - sx1) > TV_W or (sy2 - sy1) > TV_H
    else:
        subject_too_large = False

    if subject_too_large:
        fit_scale = min(TV_W / iw, TV_H / ih)
        fit_w, fit_h = int(iw * fit_scale), int(ih * fit_scale)
        img_fit = img_pil.resize((fit_w, fit_h), Image.LANCZOS)
        canvas = Image.new("RGB", (TV_W, TV_H), (0, 0, 0))
        canvas.paste(img_fit, ((TV_W - fit_w) // 2, (TV_H - fit_h) // 2))
        cropped = canvas
        console.print(f"[blue]fit (subject fills frame):[/blue] {src.name}")
    else:
        # Crop box centred on focal point; pad with black if it would go out of bounds
        # rather than shifting the box (which pushes the subject toward the frame edge)
        left = cx - TV_W // 2
        top  = cy - TV_H // 2
        if left >= 0 and top >= 0 and left + TV_W <= new_w and top + TV_H <= new_h:
            cropped = img_scaled.crop((left, top, left + TV_W, top + TV_H))
        else:
            canvas = Image.new("RGB", (TV_W, TV_H), (0, 0, 0))
            src_l, src_t = max(0, left), max(0, top)
            src_r, src_b = min(new_w, left + TV_W), min(new_h, top + TV_H)
            excerpt = img_scaled.crop((src_l, src_t, src_r, src_b))
            exc_w, exc_h = excerpt.size
            canvas.paste(excerpt, ((TV_W - exc_w) // 2, (TV_H - exc_h) // 2))
            cropped = canvas
    if caption:
        cropped = _burn_caption(cropped, caption)
    if debug_label:
        cropped = _burn_debug_label(cropped, debug_label)

    try:
        cropped.save(out, quality=95)
    except PermissionError:
        console.print(f"[red]permission denied writing:[/red] {out} — check NAS write access for the mount user")
        return None

    # Write JSON sidecar with full detection debug info
    sidecar = out.with_suffix(".json")
    sidecar.write_text(json.dumps({
        "source": src.name,
        "original_size": [iw, ih],
        "exif_rotated": exif_rotated,
        "scaled_size": [new_w, new_h],
        "scale": round(scale, 4),
        "method": "fit" if subject_too_large else ("crop-soft" if not detections else "crop"),
        "focal": [cx, cy],
        "subject_box": [round(v) for v in subject_box] if subject_box else None,
        "detections": detections,
        "caption": caption,
    }, indent=2))

    if not subject_too_large:
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


def process_all_debug():
    """Debug mode: crop all images numbered 1..N with filename overlay top-right."""
    images = sorted(p for p in SOURCE_DIR.iterdir()
                    if p.suffix.lower() in SUPPORTED_EXTS and not is_cropped(p))
    if not images:
        console.print("[yellow]No images found.[/yellow]")
        return
    console.print(f"[bold]Debug crop:[/bold] {len(images)} images → 1–{len(images)}.jpg")
    for n, src in enumerate(images, 1):
        out = OUTPUT_DIR / f"{n}.jpg"
        crop_to_4k(src, out_path=out, debug_label=f"#{n}  {src.name}")


def watch():
    console.print(f"[bold]Watching[/bold] {SOURCE_DIR} → {OUTPUT_DIR}")
    process_all()  # catch up on any backlog before entering the watch loop
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
    group.add_argument("--debug", action="store_true",
                       help="Crop all files numbered 1..N with filename overlay (for sidecar review)")
    args = parser.parse_args()

    if args.watch:
        watch()
    elif args.file:
        crop_to_4k(args.file)
    elif args.all:
        process_all()
    elif args.debug:
        process_all_debug()


if __name__ == "__main__":
    main()
