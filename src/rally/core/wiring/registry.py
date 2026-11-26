"""Port registry.

A call that would invert a dependency goes through a port declared by the called-from
module (or Platform) and registered here at startup (AGENTS.md rule 15).

Slice S1 declares no port. `PendingInvitationCanceller` (M6 → M5) arrives with S12 and
`OutboxAppender` (Platform, written by M1/M5/M6, read by M7) arrives with S2.
"""
from __future__ import annotations

from typing import Any

_ports: dict[str, Any] = {}


def register(name: str, implementation: Any) -> None:
    _ports[name] = implementation


def resolve(name: str) -> Any:
    try:
        return _ports[name]
    except KeyError:
        raise LookupError(f"port {name!r} is not registered; wire it in rally.core.wiring.registry") from None


def registered() -> frozenset[str]:
    return frozenset(_ports)


def wire() -> None:
    """Bind every port. Called once from CoreConfig.ready()."""
    return None
