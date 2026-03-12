#!/usr/bin/env python3
"""Ping all known homelab hosts and report status."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from lib.hosts import KNOWN_HOSTS
from lib.utils import console, make_table, ping, status_icon


def main():
    table = make_table("Host", "IP", "Status")
    for ip, name in KNOWN_HOSTS.items():
        ok = ping(ip)
        table.add_row(name, ip, status_icon(ok))
    console.print(table)


if __name__ == "__main__":
    main()
