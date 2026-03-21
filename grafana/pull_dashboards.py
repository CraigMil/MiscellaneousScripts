#!/usr/bin/env python3
"""
Pull all Grafana dashboards to grafana/dashboards/ as JSON files.

Usage:
  python3 grafana/pull_dashboards.py

Requires .env with:
  GRAFANA_URL, GRAFANA_USER, GRAFANA_PASSWORD
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import json
import os
import re
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GRAFANA_URL  = os.environ["GRAFANA_URL"].rstrip("/")
GRAFANA_USER = os.environ["GRAFANA_USER"]
GRAFANA_PASS = os.environ["GRAFANA_PASSWORD"]
AUTH = HTTPBasicAuth(GRAFANA_USER, GRAFANA_PASS)

OUT_DIR = Path(__file__).parent / "dashboards"
OUT_DIR.mkdir(exist_ok=True)


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def fetch_all_dashboards():
    resp = requests.get(f"{GRAFANA_URL}/api/search", params={"type": "dash-db"}, auth=AUTH, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_dashboard(uid: str) -> dict:
    resp = requests.get(f"{GRAFANA_URL}/api/dashboards/uid/{uid}", auth=AUTH, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    dashboards = fetch_all_dashboards()
    if not dashboards:
        print("No dashboards found.")
        return

    print(f"Found {len(dashboards)} dashboard(s).")
    for item in dashboards:
        uid   = item["uid"]
        title = item["title"]
        data  = fetch_dashboard(uid)

        # Strip the live 'id' — not portable across Grafana instances
        dashboard_json = data["dashboard"]
        dashboard_json.pop("id", None)

        filename = f"{slugify(title)}.json"
        path = OUT_DIR / filename
        path.write_text(json.dumps(dashboard_json, indent=2) + "\n")
        print(f"  saved: grafana/dashboards/{filename}  (uid={uid})")

    print("Done.")


if __name__ == "__main__":
    main()
