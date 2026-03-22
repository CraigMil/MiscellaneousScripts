"""Shared Grafana API helpers."""

import json
import os
import re
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GRAFANA_URL  = os.environ["GRAFANA_URL"].rstrip("/")
AUTH = HTTPBasicAuth(os.environ["GRAFANA_USER"], os.environ["GRAFANA_PASSWORD"])
DASHBOARDS_DIR = Path(__file__).parent / "dashboards"


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def list_dashboards() -> list[dict]:
    resp = requests.get(f"{GRAFANA_URL}/api/search", params={"type": "dash-db"}, auth=AUTH, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_dashboard(uid: str) -> dict:
    resp = requests.get(f"{GRAFANA_URL}/api/dashboards/uid/{uid}", auth=AUTH, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    dashboard = data["dashboard"]
    dashboard.pop("id", None)
    return dashboard


def push_dashboard(dashboard: dict, message: str = "") -> dict:
    payload = {"dashboard": dashboard, "overwrite": True, "message": message}
    resp = requests.post(f"{GRAFANA_URL}/api/dashboards/db", auth=AUTH, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def local_dashboards() -> dict[str, Path]:
    """Return {uid: path} for all local dashboard JSON files."""
    result = {}
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            uid = data.get("uid")
            if uid:
                result[uid] = path
        except (json.JSONDecodeError, KeyError):
            pass
    return result
