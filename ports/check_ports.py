#!/usr/bin/env python3
"""Check that expected service ports are open on known hosts."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import socket
from lib.hosts import GRAFANA_HOST, HOME_ASSISTANT, FRIGATE_HOST
from lib.utils import console, make_table, status_icon

# (host, port, description)
EXPECTED_PORTS = [
    (GRAFANA_HOST,   3000, "Grafana"),
    (GRAFANA_HOST,   3100, "Loki"),
    (GRAFANA_HOST,   9090, "Prometheus"),
    (HOME_ASSISTANT, 8123, "Home Assistant"),
    (FRIGATE_HOST,   5000, "Frigate"),
]


def tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def main():
    table = make_table("Service", "Host", "Port", "Open")
    for host, port, desc in EXPECTED_PORTS:
        ok = tcp_open(host, port)
        table.add_row(desc, host, str(port), status_icon(ok))
    console.print(table)


if __name__ == "__main__":
    main()
