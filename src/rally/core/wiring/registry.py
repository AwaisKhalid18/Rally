"""Port registry.

A call that would invert a dependency goes through a port declared by the called-from
module (or Platform) and registered here at startup (AGENTS.md rule 15).

Registered:
  `OutboxAppender`                (S2)   declared by Platform, implemented by M7
                                         (rule 3, ADR-005).
  `PendingInvitationCanceller`    (S12)  declared by M6, implemented by M5
                                         (rule 15, ADR-007 R-02).

Both exist so that a call can cross a dependency edge the wrong way at run time without
any module importing the other. Nothing else may be registered without an ADR.
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
    from rally.modules.invitations.api import pending_canceller
    from rally.modules.notification.api import outbox_appender
    from rally.modules.safety.api.ports import PENDING_INVITATION_CANCELLER

    register("OutboxAppender", outbox_appender.appender())
    register(PENDING_INVITATION_CANCELLER, pending_canceller.canceller())
