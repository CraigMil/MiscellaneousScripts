#!/usr/bin/env python3
"""Scan the local network and identify active hosts."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import nmap
from lib.hosts import NETWORK, KNOWN_HOSTS
from lib.utils import console, make_table

def main():
    console.print(f"[bold]Scanning {NETWORK}...[/bold]")
    nm = nmap.PortScanner()
    nm.scan(hosts=NETWORK, arguments="-sn")  # ping scan, no port scan

    table = make_table("IP", "Hostname", "Known As", "State")
    for host in nm.all_hosts():
        info = nm[host]
        state = info.state()
        hostname = info.hostname() or "-"
        known = KNOWN_HOSTS.get(host, "")
        table.add_row(host, hostname, known, state)

    console.print(table)
    console.print(f"\n[dim]{len(nm.all_hosts())} hosts found[/dim]")


if __name__ == "__main__":
    main()
