# Art Mode on Samsung TV with My Images

## Overview

| Component | Detail |
|-----------|--------|
| TV | Samsung The Frame — `192.168.1.51` |
| Image source | `/mnt/FastDrive/SamsungTVImageStore` (UGreen NAS, `192.168.1.3`) |
| Run host | `192.168.1.48` (Grafana/Prometheus/Loki VM) |
| NAS mount | `/etc/fstab` SMB entry, mounts at `/mnt/FastDrive` |
| TV library | `samsungtvws` v3.x |
| Image path env var | `FRAME_IMAGE_DIR` (overrides default) |

---

## Full Pipeline

```
Drop image into NAS folder
        ↓
frame-crop.service detects new file (inotify-style polling, 5s)
        ↓
Crops to 4K (3840×2160), centred on face or highest-entropy region
Saves as filename_cropped.jpg alongside original
        ↓
Cron (every 3 min, 192.168.1.48): frame_rotate.py --next
  → uploads any new _cropped images to TV (skips already-uploaded)
  → advances shuffle queue, displays next image in Art Mode
        ↓
Alloy ships frame_rotate.log → Loki (queryable in Grafana)
```

---

## Scripts

### `api/frame_rotate.py` — Upload & rotate images on the TV

```bash
# Upload any new images from NAS folder (skips already-uploaded)
FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore .venv/bin/python3 api/frame_rotate.py --upload

# Display next image in shuffle rotation
FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore .venv/bin/python3 api/frame_rotate.py --next

# Delete all from TV and re-upload fresh (e.g. to fix matte settings)
FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore .venv/bin/python3 api/frame_rotate.py --reupload

# Show current rotation state
FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore .venv/bin/python3 api/frame_rotate.py --status
```

**Rotation order:** randomised shuffle — cycles through all images before repeating.
**Matte:** full-bleed, no frame (`matte="none"`, `portrait_matte="none"` set at upload time).
**State files:** `api/frame_state.json` (shuffle queue + uploaded map), `api/frame_token.txt` (TV pairing token — do not delete).

### `api/crop_for_tv.py` — Auto-crop images to 4K

```bash
# Watch folder for new files (run as systemd service, see below)
FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore .venv/bin/python3 api/crop_for_tv.py --watch

# Crop a single file
.venv/bin/python3 api/crop_for_tv.py --file /path/to/image.jpg

# Crop all uncropped files in folder
FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore .venv/bin/python3 api/crop_for_tv.py --all
```

**Focal point detection:** tries face detection (OpenCV Haar cascade) first; falls back to entropy-based region if no face found.
**Output:** saves `filename_cropped.jpg` alongside the original. Only `_cropped` files are picked up by `frame_rotate.py`.

---

## Services on 192.168.1.48

### frame-crop (systemd)

Watches the NAS folder and auto-crops new images.

```bash
sudo systemctl status frame-crop
sudo systemctl restart frame-crop
journalctl -u frame-crop -f          # live logs
```

Service file: `/etc/systemd/system/frame-crop.service`

### Cron — frame rotation (every 3 minutes)

```
*/3 * * * * FRAME_IMAGE_DIR=/mnt/FastDrive/SamsungTVImageStore /home/craigmil/MiscellaneousScripts/.venv/bin/python3 /home/craigmil/MiscellaneousScripts/api/frame_rotate.py --next >> /home/craigmil/MiscellaneousScripts/api/frame_rotate.log 2>&1
```

Edit with: `crontab -e` on `192.168.1.48`

### Alloy (systemd) — log shipping

Ships `frame_rotate.log` to Loki. Config lives at `/etc/alloy/config.alloy`.

```bash
sudo systemctl status alloy
journalctl -u alloy -f
```

Query logs in Grafana with: `{job="frame_rotate"}`

---

## NAS Mount (192.168.1.48)

```
//192.168.1.3/FastDrive → /mnt/FastDrive
SMB credentials: /etc/samba/credentials/nas (user: NetworkScriptPerms)
fstab options: cifs, vers=3.0, uid=1000, gid=1000, _netdev
```

---

## One-Time TV Pairing

The first connection prompts a PIN on the TV screen. Accept it. Token saved to `api/frame_token.txt` — tracked in git, do not delete.

---

## Prerequisites

- TV must be **on and in Art Mode** — API unavailable in standby or regular TV mode
- NAS must be mounted: `sudo mount /mnt/FastDrive`
- The `frame-crop` service must be running to auto-process new images

---

## Adding Images

1. Drop any `.jpg`/`.jpeg`/`.png` into `/Volumes/FastDrive/SamsungTVImageStore` from Mac (or any SMB client)
2. `frame-crop.service` detects it within ~5 seconds, crops to 4K, saves `_cropped` version
3. Next cron tick uploads the cropped file to the TV and adds it to the shuffle

---

## Known Quirks

**TV sends unsolicited `image_selected` on connect** — normal behaviour; script retries once automatically.

**Matte must be set at upload time** — `change_matte` returns error `-7` for `portrait_matte_id` after the fact. Use `--reupload` if images were uploaded with wrong matte.

**TV must be on** — cron will log an error and exit cleanly if TV is in standby; resumes normally next tick.

---

## Available Matte Types (reference)

Types: `none` · `modernthin` · `modern` · `modernwide` · `flexible` · `shadowbox` · `panoramic` · `triptych` · `mix` · `squares`

Colors: `black` · `neutral` · `antique` · `warm` · `polar` · `sand` · `seafoam` · `sage` · `burgandy` · `navy` · `apricot` · `byzantine` · `lavender` · `redorange` · `skyblue` · `turquoise`
