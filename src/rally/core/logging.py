"""Structured operation logging (ASR-12, ADR-005).

Rule 6: email and phone appear in no log. This helper takes an account id and a short
outcome, never a contact address, and refuses anything that looks like an email address.
"""
from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger("rally.operation")


def log_operation(operation: str, outcome: str, **fields: Any) -> None:
    """Record one operation with its outcome.

    `fields` carries identifiers and reasons only. A value containing '@' is replaced
    rather than written, so a slip cannot leak a contact address into the log.
    """
    safe: list[str] = [f"operation={operation}", f"outcome={outcome}"]
    for key, value in fields.items():
        text = "" if value is None else str(value)
        if "@" in text:
            text = "<redacted>"
        safe.append(f"{key}={text}")
    _logger.info(" ".join(safe))
