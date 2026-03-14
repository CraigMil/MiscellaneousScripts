#!/usr/bin/env python3
"""
Create (or update) the Frame TV monitoring dashboard in Grafana.

Usage:
  python3 api/setup_frame_dashboard.py
"""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import json
import os
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GRAFANA_URL  = os.environ["GRAFANA_URL"].rstrip("/")
GRAFANA_USER = os.environ["GRAFANA_USER"]
GRAFANA_PASS = os.environ["GRAFANA_PASSWORD"]
AUTH = HTTPBasicAuth(GRAFANA_USER, GRAFANA_PASS)

# ── helpers ───────────────────────────────────────────────────────────────────

def loki_stat(title, expr, x, y, w=6, h=4, color_mode="value", thresholds=None):
    panel = {
        "type": "stat",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": color_mode, "graphMode": "none"},
        "targets": [{"expr": expr, "datasource": {"type": "loki"}, "legendFormat": "", "instant": True}],
        "fieldConfig": {"defaults": {}},
    }
    if thresholds:
        panel["fieldConfig"]["defaults"]["thresholds"] = thresholds
        panel["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
    return panel


def loki_timeseries(title, targets, x, y, w=16, h=8):
    return {
        "type": "timeseries",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {"tooltip": {"mode": "multi"}, "legend": {"displayMode": "list", "placement": "bottom"}},
        "targets": [
            {"expr": t["expr"], "legendFormat": t.get("legend", ""), "datasource": {"type": "loki"}}
            for t in targets
        ],
        "fieldConfig": {"defaults": {"custom": {"fillOpacity": 20}}},
    }


def loki_table(title, expr, x, y, w=10, h=8):
    return {
        "type": "table",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {"sortBy": [{"displayName": "Value", "desc": True}]},
        "targets": [{"expr": expr, "datasource": {"type": "loki"}, "legendFormat": "{{filename}}",
                     "instant": True}],
        "transformations": [{"id": "sortBy", "options": {"fields": [{"displayName": "Value", "desc": True}]}}],
        "fieldConfig": {"defaults": {}},
    }


def loki_logs(title, expr, x, y, w=12, h=8):
    return {
        "type": "logs",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {"showTime": True, "wrapLogMessage": True, "dedupStrategy": "none",
                    "sortOrder": "Descending"},
        "targets": [{"expr": expr, "datasource": {"type": "loki"}}],
    }


def row_panel(title, y):
    return {"type": "row", "title": title, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False}


# ── panels ────────────────────────────────────────────────────────────────────

panels = [
    # ── Row: Overview stats
    row_panel("Rotation Overview", y=0),

    loki_stat("Images in Rotation",
              r'count(count by (filename) (count_over_time({job="frame_rotate"} |= "Showing " | pattern `Showing <filename> (` | filename != "" [$__range])))',
              x=0, y=1, w=6, h=4),

    loki_stat("Total Shows",
              r'sum(count_over_time({job="frame_rotate"} |= "Showing " [$__range]))',
              x=6, y=1, w=6, h=4),

    loki_stat("Total Uploads",
              r'sum(count_over_time({job="frame_rotate"} |= "uploading:" |= "done (" [$__range]))',
              x=12, y=1, w=6, h=4),

    loki_stat("Upload Errors",
              r'sum(count_over_time({job="frame_rotate"} |= "Upload interrupted:" [$__range]))',
              x=18, y=1, w=6, h=4,
              thresholds={"mode": "absolute", "steps": [
                  {"color": "green", "value": None},
                  {"color": "red", "value": 1},
              ]}),

    # ── Row: Rotation activity
    row_panel("Rotation Activity", y=5),

    loki_timeseries("Rotations Over Time",
                    [{"expr": r'sum(count_over_time({job="frame_rotate"} |= "Showing " [5m]))',
                      "legend": "Shows per 5m"}],
                    x=0, y=6, w=16, h=8),

    loki_logs("Errors & Interruptions",
              r'{job="frame_rotate"} |~ "interrupted|Error|error|standby"',
              x=16, y=6, w=8, h=8),

    # ── Row: Per-image show counts
    row_panel("Per-Image Show Counts", y=14),

    {
        "type": "barchart",
        "title": "Times Each Image Shown",
        "gridPos": {"x": 0, "y": 15, "w": 24, "h": 10},
        "options": {
            "orientation": "horizontal",
            "xTickLabelRotation": 0,
            "legend": {"displayMode": "hidden"},
            "tooltip": {"mode": "single"},
        },
        "targets": [{
            "expr": r'sort_desc(sum by (filename) (count_over_time({job="frame_rotate"} |= "Showing " | pattern `Showing <filename> (` | filename != "" [$__range])))',
            "datasource": {"type": "loki"},
            "legendFormat": "{{filename}}",
            "instant": True,
        }],
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}},
        },
    },

    # ── Row: Crop pipeline
    row_panel("Crop Pipeline", y=25),

    loki_stat("Files Cropped",
              r'sum(count_over_time({job="frame_crop"} |= "cropped:" [$__range]))',
              x=0, y=26, w=6, h=4),

    loki_stat("Copied As-Is (small)",
              r'sum(count_over_time({job="frame_crop"} |= "small, copying as-is:" [$__range]))',
              x=6, y=26, w=6, h=4),

    loki_stat("New Files Detected",
              r'sum(count_over_time({job="frame_crop"} |= "new file:" [$__range]))',
              x=12, y=26, w=6, h=4),

    loki_stat("Files Removed",
              r'sum(count_over_time({job="frame_crop"} |= "removed:" [$__range]))',
              x=18, y=26, w=6, h=4),

    # ── Row: Crop detail
    row_panel("Crop Detail", y=30),

    loki_timeseries("Crop Activity Over Time",
                    [
                        {"expr": r'sum(count_over_time({job="frame_crop"} |= "cropped:" [10m]))', "legend": "Cropped"},
                        {"expr": r'sum(count_over_time({job="frame_crop"} |= "small, copying as-is:" [10m]))', "legend": "Copied as-is"},
                        {"expr": r'sum(count_over_time({job="frame_crop"} |= "small, captioned:" [10m]))', "legend": "Captioned (small)"},
                    ],
                    x=0, y=31, w=14, h=8),

    loki_table("Files Cropped by Source",
               r'sort_desc(sum by (src) (count_over_time({job="frame_crop"} | regexp `cropped: (?P<src>\S+)` | __error__="" [$__range])))',
               x=14, y=31, w=10, h=8),

    # ── Row: Recent logs
    row_panel("Recent Logs", y=39),

    loki_logs("Recent Crop Activity",
              r'{job="frame_crop"} |~ "cropped:|small,|new file:|removed:"',
              x=0, y=40, w=12, h=8),

    loki_logs("Recent Rotation Activity",
              r'{job="frame_rotate"} |~ "Showing |uploading:|Upload interrupted"',
              x=12, y=40, w=12, h=8),
]

# ── dashboard payload ─────────────────────────────────────────────────────────

dashboard = {
    "uid": "frame-tv-monitor",
    "title": "Frame TV Monitor",
    "tags": ["frame-tv"],
    "timezone": "browser",
    "time": {"from": "now-7d", "to": "now"},
    "refresh": "1m",
    "panels": panels,
    "schemaVersion": 36,
}

payload = {"dashboard": dashboard, "folderId": 0, "overwrite": True, "message": "Created by setup_frame_dashboard.py"}

# ── find Loki datasource uid ──────────────────────────────────────────────────

resp = requests.get(f"{GRAFANA_URL}/api/datasources", auth=AUTH, timeout=10)
resp.raise_for_status()
loki_uid = next(
    (ds["uid"] for ds in resp.json() if ds["type"] == "loki"),
    None,
)
if not loki_uid:
    print("ERROR: No Loki datasource found in Grafana.", file=sys.stderr)
    sys.exit(1)

# Inject Loki UID into all targets
def inject_uid(obj, uid):
    if isinstance(obj, dict):
        if obj.get("type") == "loki" and "uid" not in obj:
            obj["uid"] = uid
        for v in obj.values():
            inject_uid(v, uid)
    elif isinstance(obj, list):
        for item in obj:
            inject_uid(item, uid)

inject_uid(dashboard, loki_uid)

# ── push to Grafana ───────────────────────────────────────────────────────────

resp = requests.post(f"{GRAFANA_URL}/api/dashboards/db", auth=AUTH,
                     json=payload, timeout=15)
resp.raise_for_status()
result = resp.json()
print(f"Dashboard created: {GRAFANA_URL}{result['url']}")
