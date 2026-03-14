#!/usr/bin/env python3
"""
Rotate images from a local folder onto Samsung The Frame TV art mode.

Usage:
  frame_rotate.py --upload          # upload any new images from IMAGE_DIR to TV
  frame_rotate.py --next            # advance to the next image in rotation
  frame_rotate.py --daemon 300      # auto-advance every N seconds (default 300)
  frame_rotate.py --status          # show current state

First run will prompt for a PIN on the TV screen (one-time pairing).
Token is saved to api/frame_token.txt afterwards.
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import argparse
import json
import os
import random
import signal
import time
from pathlib import Path

from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure
from lib.utils import console

# ── Config ────────────────────────────────────────────────────────────────────
TV_IP      = "192.168.1.51"
TV_PORT    = 8002
_DEFAULT_IMAGE_DIR = "/Volumes/FastDrive/SamsungTVImageStore"
IMAGE_DIR  = Path(os.environ.get("FRAME_IMAGE_DIR", _DEFAULT_IMAGE_DIR))
TV_TIMEOUT        = float(os.environ.get("FRAME_TV_TIMEOUT", "10"))
UPLOAD_TIMEOUT    = int(os.environ.get("FRAME_UPLOAD_TIMEOUT", "60"))
STATE_FILE = Path(__file__).parent / "frame_state.json"
TOKEN_FILE = Path(__file__).parent / "frame_token.txt"
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png"}
# ──────────────────────────────────────────────────────────────────────────────


def connect() -> SamsungTVWS:
    return SamsungTVWS(host=TV_IP, port=TV_PORT, token_file=str(TOKEN_FILE), timeout=TV_TIMEOUT)


def require_artmode(tv: SamsungTVWS):
    """Raise ConnectionFailure if the TV is not actively displaying Art Mode.

    Raises instead of sys.exit so the daemon loop can skip the cycle gracefully.
    Only sys.exit on permanent hardware failure (art mode not supported at all).

    The Samsung Frame TV art WebSocket is always running in the background and
    get_artmode_status returns the ambient *preference* ("on"/"off"), not the
    current display state — so it returns "on" even when the user is watching TV.

    The reliable signal: immediately after the WebSocket handshake the TV
    spontaneously sends an `image_selected` D2D event with `is_shown="Yes"` when
    art is on-screen, or `is_shown="No"` when the TV is in regular viewing mode.
    We read that event before sending any request.
    """
    try:
        art = tv.art()
        if not art.supported():
            console.print("[red]Art mode not supported on this TV.[/red]")
            sys.exit(1)

        if not art.get_artmode():
            raise ConnectionFailure("TV is not in Art Mode — skipping")

    except ConnectionFailure:
        raise
    except Exception as e:
        raise ConnectionFailure(f"Art mode check failed: {e}") from e


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"index": 0, "uploaded": {}}  # {filename: content_id}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def local_images() -> list[Path]:
    if not IMAGE_DIR.exists():
        console.print(f"[red]Image dir not found:[/red] {IMAGE_DIR}")
        sys.exit(1)
    images = sorted(p for p in IMAGE_DIR.iterdir() if p.suffix.lower() in SUPPORTED_EXTS)
    return images


def _upload_one(art, data: bytes) -> str:
    """Upload image bytes, retrying once if the TV sends an unsolicited event first.
    Raises ConnectionFailure if the upload hangs beyond UPLOAD_TIMEOUT seconds."""
    def _timeout_handler(signum, frame):
        raise ConnectionFailure(f"upload timed out after {UPLOAD_TIMEOUT}s")

    for attempt in range(2):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(UPLOAD_TIMEOUT)
        try:
            result = art.upload(data, matte="none", portrait_matte="none")
            signal.alarm(0)
            return result
        except ConnectionFailure as e:
            signal.alarm(0)
            msg = str(e)
            # TV sends image_selected on connect as an unsolicited event; retry once.
            if attempt == 0 and "image_selected" in msg:
                continue
            raise
        finally:
            signal.signal(signal.SIGALRM, old_handler)
            signal.alarm(0)


def upload_new(tv: SamsungTVWS, state: dict) -> int:
    art = tv.art()
    images = local_images()
    uploaded = state["uploaded"]
    new_count = 0

    for img in images:
        if img.name in uploaded:
            console.print(f"[dim]skip (already uploaded):[/dim] {img.name}")
            continue
        console.print(f"[cyan]uploading:[/cyan] {img.name} ...", end=" ")
        data = img.read_bytes()
        try:
            content_id = _upload_one(art, data)
        except ConnectionFailure as e:
            console.print(f"\n[red]Upload interrupted:[/red] {e}")
            break
        uploaded[img.name] = content_id
        save_state(state)
        console.print(f"[green]done[/green] ({content_id})")
        new_count += 1

    return new_count


def show_image(tv: SamsungTVWS, state: dict):
    uploaded = state["uploaded"]

    available = list(uploaded.keys())
    if not available:
        console.print("[yellow]No uploaded images to show. Run --upload first.[/yellow]")
        return

    # Shuffled queue: work through all images in random order before repeating
    queue = state.get("queue", [])
    # Rebuild queue if empty or it contains filenames no longer uploaded
    if not queue or not all(f in uploaded for f in queue):
        queue = available[:]
        random.shuffle(queue)

    filename = queue.pop(0)
    state["queue"] = queue
    content_id = uploaded[filename]

    art = tv.art()
    art.select_image(content_id)
    remaining = len(queue)
    console.print(f"[green]Showing[/green] {filename} ({content_id}) — {remaining} remaining in shuffle")

    save_state(state)


def cmd_upload():
    state = load_state()
    tv = connect()
    n = upload_new(tv, state)
    console.print(f"\n[bold]{n} new image(s) uploaded.[/bold]")


def cmd_reupload():
    """Delete all previously uploaded images from TV and re-upload with correct matte settings."""
    state = load_state()
    uploaded = state["uploaded"]
    if not uploaded:
        console.print("[yellow]Nothing to re-upload.[/yellow]")
        return

    tv = connect()
    require_artmode(tv)
    art = tv.art()

    content_ids = list(uploaded.values())
    console.print(f"[cyan]Deleting {len(content_ids)} images from TV...[/cyan]")
    art.delete_list(content_ids)

    state["uploaded"] = {}
    state["index"] = 0
    save_state(state)
    console.print("[green]Deleted.[/green] Re-uploading with full-bleed matte settings...\n")

    n = upload_new(tv, state)
    console.print(f"\n[bold]{n} image(s) re-uploaded.[/bold]")


def cmd_next():
    state = load_state()
    tv = connect()
    show_image(tv, state)


def sync_deleted(tv: SamsungTVWS, state: dict):
    """Remove images from state (and TV) whose source files no longer exist in IMAGE_DIR."""
    uploaded = state["uploaded"]
    missing = [name for name in list(uploaded) if not (IMAGE_DIR / name).exists()]
    if not missing:
        return
    art = tv.art()
    art.delete_list([uploaded[name] for name in missing])
    for name in missing:
        console.print(f"[yellow]removed:[/yellow] {name} (source deleted)")
        del uploaded[name]
    # Drop any queued entries for deleted files
    state["queue"] = [f for f in state.get("queue", []) if f not in missing]
    save_state(state)


_LOOP_TIMEOUT = int(os.environ.get("FRAME_LOOP_TIMEOUT", "60"))


def cmd_daemon(interval: int):
    console.print(f"[bold]Daemon mode:[/bold] rotating every {interval}s. Ctrl-C to stop.")

    def _timeout_handler(signum, frame):
        raise ConnectionFailure(f"TV operation timed out after {_LOOP_TIMEOUT}s")

    while True:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_LOOP_TIMEOUT)
        try:
            state = load_state()
            tv = connect()
            require_artmode(tv)   # single fast check — skip the whole cycle if not in art mode
            sync_deleted(tv, state)
            upload_new(tv, state)
            show_image(tv, state)
        except ConnectionFailure as e:
            console.print(f"[red]TV error (skipping):[/red] {e}")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        time.sleep(interval)


def cmd_status():
    state = load_state()
    images = local_images()
    uploaded = state["uploaded"]
    available = [img for img in images if img.name in uploaded]
    idx = state["index"] % max(len(available), 1)

    console.print(f"[bold]Image dir:[/bold] {IMAGE_DIR}")
    console.print(f"[bold]Local images:[/bold] {len(images)}")
    console.print(f"[bold]Uploaded:[/bold] {len(uploaded)}")
    console.print(f"[bold]Next index:[/bold] {idx} / {len(available)}")
    if available:
        current = available[(idx - 1) % len(available)]
        console.print(f"[bold]Last shown:[/bold] {current.name}")


def main():
    parser = argparse.ArgumentParser(description="Samsung Frame TV image rotator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--upload", action="store_true", help="Upload new images from folder")
    group.add_argument("--next",   action="store_true", help="Advance to next image")
    group.add_argument("--daemon", type=int, nargs="?", const=300, metavar="SECONDS",
                       help="Auto-rotate every N seconds (default 300)")
    group.add_argument("--reupload", action="store_true", help="Delete all from TV and re-upload with full-bleed matte")
    group.add_argument("--status", action="store_true", help="Show current rotation state")
    args = parser.parse_args()

    if args.upload:
        cmd_upload()
    elif args.next:
        cmd_next()
    elif args.daemon is not None:
        cmd_daemon(args.daemon)
    elif args.reupload:
        cmd_reupload()
    elif args.status:
        cmd_status()


if __name__ == "__main__":
    main()
