# Art Mode on Samsung TV with My Images

## Overview

Script: `api/frame_rotate.py`
TV: Samsung The Frame — `192.168.1.51`
Image source: `/Volumes/FastDrive/SamsungTVImageStore` (UGreen NAS, mounted via SMB) — overridable via `FRAME_IMAGE_DIR` env var
Library: [`samsungtvws`](https://github.com/xchwarze/samsung-tv-ws-api) v3.x

---

## How It Works

1. Connects to the TV's WebSocket art API on port 8002
2. Uploads images directly to the TV's internal "My Photos" storage
3. Calls `select_image` to display a given image in Art Mode
4. Tracks rotation state (which image is next) in `api/frame_state.json`

Images are uploaded with **no matte** (`matte="none", portrait_matte="none"`) so they display full-bleed with no frame or shadow box.

---

## One-Time Setup (Pairing)

The first connection prompts a PIN on the TV screen. Accept it. The token is saved to `api/frame_token.txt` and reused automatically on all future runs. Never delete this file unless you want to re-pair.

---

## Commands

```bash
# Upload any new images from the NAS folder (skips already-uploaded ones)
.venv/bin/python3 api/frame_rotate.py --upload

# Display the next image in rotation
.venv/bin/python3 api/frame_rotate.py --next

# Auto-rotate every N seconds (default 300 = 5 minutes)
.venv/bin/python3 api/frame_rotate.py --daemon 300

# Delete all uploaded images from TV and re-upload fresh (e.g. to fix matte settings)
.venv/bin/python3 api/frame_rotate.py --reupload

# Show current rotation state (how many uploaded, which is next)
.venv/bin/python3 api/frame_rotate.py --status
```

---

## Prerequisites

- TV must be **on** and in **Art Mode** — the API is unavailable when the TV is in standby or regular TV mode
- NAS share must be mounted at `/Volumes/FastDrive/` before running

---

## State Files

| File | Purpose |
|------|---------|
| `api/frame_token.txt` | Auth token from TV pairing (keep this) |
| `api/frame_state.json` | Tracks uploaded images + rotation index |

Both are gitignored (or should be — add them to `.gitignore` if not already).

---

## Known Quirks

### TV sends unsolicited `image_selected` on connect
When the art WebSocket opens, the TV immediately pushes an `image_selected` event. The library mistakes this for the upload response and raises `ConnectionFailure`. The script retries once automatically when it detects this event — this is normal.

### Matte must be set at upload time
The `change_matte` API works for landscape orientation but returns error `-7` when trying to set `portrait_matte_id` after the fact. Always upload with `matte="none", portrait_matte="none"` baked in. If images were already uploaded with the wrong matte, use `--reupload` to delete and re-upload cleanly.

### `v2` filename variants
The NAS folder contains pairs like `photo.jpg` / `photov2.jpg` — likely the same image at different resolutions or crops. Both get uploaded and rotated through. Prune the folder to curate the rotation.

---

## Adding More Images

1. Drop images (`.jpg`, `.jpeg`, `.png`) into `/Volumes/FastDrive/dump/sample-tv-images`
2. Run `--upload` — only new files are uploaded, existing ones are skipped

---

## Available Matte Types (for reference)

If you ever want to use a matte, valid types on this TV:

`none` · `modernthin` · `modern` · `modernwide` · `flexible` · `shadowbox` · `panoramic` · `triptych` · `mix` · `squares`

Colors: `black` · `neutral` · `antique` · `warm` · `polar` · `sand` · `seafoam` · `sage` · `burgandy` · `navy` · `apricot` · `byzantine` · `lavender` · `redorange` · `skyblue` · `turquoise`
