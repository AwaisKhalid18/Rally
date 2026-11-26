"""Ports declared by Platform.

A port is how a call crosses a boundary that a direct import would invert (rule 15).
Platform declares the port, a module implements it, and `rally.core.wiring.registry`
binds the two at startup.

`OutboxAppender` — a business module appends an outbox record inside its own
transaction without importing M7 (rule 3). M7 implements it and stays the only writer
of the `outbox` table (rule 1).
"""
from rally.core.ports.outbox import OUTBOX_APPENDER, OutboxAppender, append_outbox

__all__ = ["OUTBOX_APPENDER", "OutboxAppender", "append_outbox"]
