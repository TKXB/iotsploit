"""Shared helpers for printing command results to the shell.

Command results — lists, details, confirmations — are written with cmd2's
``poutput``/``perror`` so they carry no log prefix, can be redirected and
piped, and are not silenced by the log level. The logger stays for events
(a backend starting, a plugin's own log lines), not for answers.
"""

from cmd2 import ansi
from cmd2.table_creator import Column, SimpleTable


def fit(columns, rows, minimums=None, maximums=None):
    """Size each column to its widest cell, floored at the header width.

    Width is measured ignoring ANSI colour codes, so a styled cell lines up
    with a plain one. A column with a maximum is capped there, and SimpleTable
    wraps cells that are longer.
    """
    for index, column in enumerate(columns):
        widest = max((ansi.style_aware_wcswidth(str(row[index])) for row in rows), default=0)
        floor = minimums[index] if minimums else 0
        width = max(widest, len(column.header), floor)
        cap = maximums[index] if maximums else None
        column.width = min(width, cap) if cap else width


def table(headers, rows, minimums=None, maximums=None):
    """Render ``rows`` under ``headers`` as an aligned table, sized to fit."""
    columns = [Column(header) for header in headers]
    cells = [[str(cell) for cell in row] for row in rows]
    fit(columns, cells, minimums, maximums)
    return SimpleTable(columns).generate_table(cells, row_spacing=0)


def available_mark(available, reason=None):
    """A yes/no availability cell, green or yellow, with the reason when off."""
    if available:
        return ansi.style("yes", fg=ansi.Fg.GREEN)
    text = "no" if not reason else f"no — {reason}"
    return ansi.style(text, fg=ansi.Fg.YELLOW)
