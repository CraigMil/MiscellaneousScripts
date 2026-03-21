#!/usr/bin/env python3
"""HTTP health check for homelab web services."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import requests
from lib.hosts import GRAFANA_URL, HOME_ASSISTANT_URL, FRIGATE_URL, LOKI_URL
from lib.utils import console, make_table, status_icon

SERVICES = {
    "Grafana":       (GRAFANA_URL, "/api/health"),
    "Home Assistant": (HOME_ASSISTANT_URL, "/api/"),
    "Frigate":       (FRIGATE_URL, "/api/version"),
    "Loki":          (LOKI_URL, "/loki/api/v1/labels"),
}


def check(base: str, path: str, timeout: int = 5) -> tuple:
    try:
        r = requests.get(base + path, timeout=timeout)
        return r.status_code < 500, r.status_code
    except requests.RequestException:
        return False, None


def main():
    table = make_table("Service", "URL", "Status", "HTTP")
    for name, (base, path) in SERVICES.items():
        ok, code = check(base, path)
        table.add_row(name, base, status_icon(ok), str(code) if code else "-")
    console.print(table)


if __name__ == "__main__":
    main()
