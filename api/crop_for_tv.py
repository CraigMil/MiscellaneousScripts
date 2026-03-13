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
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from lib.utils import console

IMAGE_DIR      = Path(os.environ.get("FRAME_IMAGE_DIR", "/Volumes/FastDrive/SamsungTVImageStore"))
CROP_SUFFIX    = "_cropped"
TV_W, TV_H     = 3840, 2160  # 4K landscape
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png"}

# OpenCV face detector
_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def is_cropped(path: Path) -> bool:
    return CROP_SUFFIX in path.stem


def output_path(path: Path) -> Path:
    return path.with_stem(path.stem + CROP_SUFFIX)


def detect_focal_point(img_cv) -> tuple[int, int]:
    """Return (cx, cy) focal point. Uses face detection, falls back to entropy map."""
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) > 0:
        # Centre of the largest face
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]
        return x + w // 2, y + h // 2

    # Entropy fallback: find the most visually complex region
    h, w = gray.shape
    block = 64
    best_val, best_cx, best_cy = -1, w // 2, h // 2
    for row in range(0, h - block, block // 2):
        for col in range(0, w - block, block // 2):
            patch = gray[row:row + block, col:col + block]
            hist = cv2.calcHist([patch], [0], None, [256], [0, 256])
            hist /= hist.sum()
            entropy = -np.sum(hist * np.log2(hist + 1e-10))
            if entropy > best_val:
                best_val = entropy
                best_cx, best_cy = col + block // 2, row + block // 2
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

    # If already 4K or smaller in both dims, just copy
    if iw <= TV_W and ih <= TV_H:
        console.print(f"[dim]small, copying as-is:[/dim] {src.name}")
        shutil.copy2(src, out)
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

    cropped.save(out, quality=95)
    console.print(f"[green]cropped:[/green] {src.name} → {out.name} (focal {cx},{cy})")
    return out


def process_all():
    images = [p for p in IMAGE_DIR.iterdir()
              if p.suffix.lower() in SUPPORTED_EXTS and not is_cropped(p)]
    if not images:
        console.print("[yellow]No uncropped images found.[/yellow]")
        return
    for img in sorted(images):
        crop_to_4k(img)


def watch():
    console.print(f"[bold]Watching[/bold] {IMAGE_DIR} for new images...")
    seen = set(IMAGE_DIR.iterdir())
    while True:
        time.sleep(5)
        current = set(IMAGE_DIR.iterdir())
        new_files = current - seen
        seen = current
        for f in sorted(new_files):
            if f.suffix.lower() in SUPPORTED_EXTS and not is_cropped(f):
                console.print(f"[cyan]new file:[/cyan] {f.name}")
                time.sleep(1)  # wait briefly in case file is still copying
                crop_to_4k(f)


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
