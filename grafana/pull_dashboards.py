#!/usr/bin/env python3
"""
Pull Grafana dashboards to grafana/dashboards/ as JSON files.

Compares the version in Grafana against the local file before overwriting.
If Grafana is ahead, shows a warning and asks for confirmation.

Usage:
  python3 grafana/pull_dashboards.py           # interactive (prompts on divergence)
  python3 grafana/pull_dashboards.py --force   # overwrite all without prompting

Requires .env with:
  GRAFANA_URL, GRAFANA_USER, GRAFANA_PASSWORD
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import json
import argparse
from pathlib import Path
from grafana.grafana_client import (
    list_dashboards, fetch_dashboard, slugify, DASHBOARDS_DIR, local_dashboards
)

DASHBOARDS_DIR.mkdir(exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite local files without prompting")
    args = parser.parse_args()

    remote = list_dashboards()
    if not remote:
        print("No dashboards found.")
        return

    local = local_dashboards()  # {uid: path}

    print(f"Found {len(remote)} dashboard(s) in Grafana.\n")

    for item in remote:
        uid   = item["uid"]
        title = item["title"]
        filename = f"{slugify(title)}.json"
        path = DASHBOARDS_DIR / filename

        remote_dashboard = fetch_dashboard(uid)
        remote_version   = remote_dashboard.get("version", 0)

        # Check local version if file exists
        if path.exists():
            local_dashboard  = json.loads(path.read_text())
            local_version    = local_dashboard.get("version", 0)

            if remote_version == local_version:
                print(f"  up to date:  {filename}  (v{remote_version})")
                continue
            elif remote_version > local_version:
                print(f"  DIVERGED:    {filename}  (local v{local_version} → grafana v{remote_version})")
                if not args.force:
                    answer = input("               Overwrite local with Grafana version? [y/N] ").strip().lower()
                    if answer != "y":
                        print("               Skipped.")
                        continue
            else:
                # local is ahead — local edits not yet pushed
                print(f"  local ahead: {filename}  (local v{local_version}, grafana v{remote_version}) — skipping")
                continue

        path.write_text(json.dumps(remote_dashboard, indent=2) + "\n")
        print(f"  saved:       {filename}  (v{remote_version})")

    print("\nDone.")


if __name__ == "__main__":
    main()
