"""Shared utilities."""

import subprocess
import sys
from rich.console import Console
from rich.table import Table

console = Console(width=300)  # prevent line-wrapping in systemd/log shipping


def ping(host: str, count: int = 1, timeout: float = 1.0) -> bool:
    """Return True if host responds to ping."""
    result = subprocess.run(
        ["ping", "-c", str(count), "-W", str(int(timeout * 1000)), host],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def make_table(*columns: str) -> Table:
    """Create a styled Rich table with the given column headers."""
    table = Table(show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    return table


def status_icon(ok: bool) -> str:
    return "[green]✓[/green]" if ok else "[red]✗[/red]"
