"""Port registry.

A call that would invert a dependency goes through a port declared by the called-from
module (or Platform) and registered here at startup (AGENTS.md rule 15).

Registered in slice S2:
  `OutboxAppender`  declared by Platform, implemented by M7 (rule 3, ADR-005).

Still to come:
  `PendingInvitationCanceller`  declared by M6, implemented by M5, arriving with S12.
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
        raise LookupError(
            f"port {name!r} is not registered; wire it in rally.core.wiring.registry"
        ) from None


def registered() -> frozenset[str]:
    return frozenset(_ports)


def wire() -> None:
    """Bind every port. Called once from CoreConfig.ready().

    Platform imports a module's `api` package here and nowhere deeper (rule 2).
    """
    from rally.modules.notification.api import outbox_appender

    register("OutboxAppender", outbox_appender.appender())
