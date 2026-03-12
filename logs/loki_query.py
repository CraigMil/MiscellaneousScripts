#!/usr/bin/env python3
"""Query Loki for recent log lines. Usage: loki_query.py '{job="varlogs"}' [--limit 50]"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import argparse
import requests
from datetime import datetime, timezone, timedelta
from lib.hosts import LOKI_URL
from lib.utils import console


def query_loki(logql: str, limit: int = 50, lookback_minutes: int = 60) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=lookback_minutes)
    params = {
        "query": logql,
        "limit": limit,
        "start": str(int(start.timestamp() * 1e9)),
        "end":   str(int(now.timestamp() * 1e9)),
        "direction": "backward",
    }
    r = requests.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    results = []
    for stream in data.get("data", {}).get("result", []):
        for ts_ns, line in stream.get("values", []):
            ts = datetime.fromtimestamp(int(ts_ns) / 1e9, tz=timezone.utc)
            results.append({"ts": ts, "line": line, "labels": stream.get("stream", {})})
    return sorted(results, key=lambda x: x["ts"])


def main():
    parser = argparse.ArgumentParser(description="Query Loki logs")
    parser.add_argument("query", help='LogQL query, e.g. \'{job="varlogs"}\'')
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--lookback", type=int, default=60, help="Minutes to look back (default 60)")
    args = parser.parse_args()

    results = query_loki(args.query, limit=args.limit, lookback_minutes=args.lookback)
    if not results:
        console.print("[yellow]No results[/yellow]")
        return
    for entry in results:
        ts_str = entry["ts"].strftime("%Y-%m-%d %H:%M:%S")
        console.print(f"[dim]{ts_str}[/dim]  {entry['line']}")


if __name__ == "__main__":
    main()
