#!/usr/bin/env python3
"""DNS lookups for homelab hosts. Pass hostnames as args, or runs defaults."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import dns.resolver
import dns.reversename
from lib.hosts import KNOWN_HOSTS
from lib.utils import console, make_table


def reverse_lookup(ip: str) -> str:
    try:
        rev = dns.reversename.from_address(ip)
        return str(dns.resolver.resolve(rev, "PTR")[0])
    except Exception:
        return "-"


def forward_lookup(name: str) -> str:
    try:
        return str(dns.resolver.resolve(name, "A")[0])
    except Exception:
        return "-"


def main():
    targets = sys.argv[1:] or list(KNOWN_HOSTS.keys())

    table = make_table("Input", "Forward / Reverse Result")
    for t in targets:
        # Detect if IP or hostname
        if t[0].isdigit():
            result = reverse_lookup(t)
        else:
            result = forward_lookup(t)
        table.add_row(t, result)

    console.print(table)


if __name__ == "__main__":
    main()
