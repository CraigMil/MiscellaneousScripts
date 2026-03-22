#!/usr/bin/env python3
"""
Push local dashboards from grafana/dashboards/ to Grafana.

Compares local version against Grafana before pushing.
If Grafana is ahead, warns and asks for confirmation to avoid overwriting
changes made directly in Grafana.

Usage:
  python3 grafana/push_dashboards.py                     # push all, prompt on conflicts
  python3 grafana/push_dashboards.py --uid <uid>         # push a single dashboard
  python3 grafana/push_dashboards.py --force             # push all without prompting

Requires .env with:
  GRAFANA_URL, GRAFANA_USER, GRAFANA_PASSWORD
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import json
import argparse
from grafana.grafana_client import (
    fetch_dashboard, push_dashboard, local_dashboards, GRAFANA_URL
)


def push_one(path, force=False) -> bool:
    local_dashboard = json.loads(path.read_text())
    uid             = local_dashboard.get("uid")
    title           = local_dashboard.get("title", path.stem)
    local_version   = local_dashboard.get("version", 0)

    # Check what's currently in Grafana
    try:
        remote_dashboard = fetch_dashboard(uid)
        remote_version   = remote_dashboard.get("version", 0)
    except Exception:
        remote_version = None  # dashboard doesn't exist in Grafana yet

    if remote_version is not None and remote_version > local_version:
        print(f"  CONFLICT:    {path.name}  (local v{local_version}, grafana v{remote_version} — Grafana is ahead)")
        if not force:
            answer = input("               Push local version anyway and overwrite Grafana? [y/N] ").strip().lower()
            if answer != "y":
                print("               Skipped.")
                return False

    result = push_dashboard(local_dashboard, message=f"Pushed from git (v{local_version})")
    print(f"  pushed:      {path.name}  → {GRAFANA_URL}{result['url']}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid",   help="Push only the dashboard with this uid")
    parser.add_argument("--force", action="store_true", help="Push without prompting on conflicts")
    args = parser.parse_args()

    local = local_dashboards()  # {uid: path}
    if not local:
        print("No local dashboards found.")
        return

    if args.uid:
        if args.uid not in local:
            print(f"No local dashboard found with uid={args.uid}")
            sys.exit(1)
        targets = {args.uid: local[args.uid]}
    else:
        targets = local

    print(f"Pushing {len(targets)} dashboard(s).\n")
    pushed = skipped = 0
    for uid, path in targets.items():
        if push_one(path, force=args.force):
            pushed += 1
        else:
            skipped += 1

    print(f"\nDone. {pushed} pushed, {skipped} skipped.")


if __name__ == "__main__":
    main()
