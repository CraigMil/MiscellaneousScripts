#!/usr/bin/env python3
"""
Pull a debug-cropped image and its sidecar from the Frame TV VM for local review.

Usage:
  frame_debug_pull.py 42          # pulls 42.jpg + 42.json to ~/Desktop
  frame_debug_pull.py 42 --out /tmp/debug
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

VM        = "craigmil@192.168.1.48"
REMOTE_DIR = "/home/craigmil/frame-tv-images"


def scp(remote: str, local: Path) -> bool:
    result = subprocess.run(["scp", remote, str(local)], capture_output=True)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Pull a debug crop image + sidecar from Frame TV VM")
    parser.add_argument("number", type=int, help="Image number as seen on TV")
    parser.add_argument("--out", type=Path, default=Path.home() / "Desktop",
                        help="Local destination directory (default: ~/Desktop)")
    args = parser.parse_args()

    n = args.number
    args.out.mkdir(parents=True, exist_ok=True)

    # Find the image — try common extensions
    local_img = None
    for ext in (".jpg", ".JPG", ".jpeg", ".png"):
        dest = args.out / f"{n}{ext}"
        if scp(f"{VM}:{REMOTE_DIR}/{n}{ext}", dest):
            local_img = dest
            break

    if local_img is None:
        print(f"error: no image found for #{n} on VM ({REMOTE_DIR}/{n}.*)", file=sys.stderr)
        sys.exit(1)

    print(f"image  → {local_img}")

    # Pull sidecar
    local_json = args.out / f"{n}.json"
    if scp(f"{VM}:{REMOTE_DIR}/{n}.json", local_json):
        print(f"sidecar → {local_json}\n")
        print(json.dumps(json.loads(local_json.read_text()), indent=2))
    else:
        print("(no sidecar found)")

    # Open image
    subprocess.run(["open", str(local_img)])


if __name__ == "__main__":
    main()
