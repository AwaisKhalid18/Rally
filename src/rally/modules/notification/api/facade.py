"""M7 — facade for the worker.

M7 publishes nothing to business modules (AGENTS.md §3). These operations exist for
Platform's worker host, which polls the outbox and asks M7 to dispatch what is due.
"""
from __future__ import annotations

from rally.modules.notification.internal import adapters, dispatch
from rally.modules.notification.internal.adapters import EmailAdapter
from rally.modules.notification.internal.dispatch import DispatchRun

MAX_ATTEMPTS = dispatch.MAX_ATTEMPTS
RETRY_INTERVAL = dispatch.RETRY_INTERVAL
RETRY_WINDOW = dispatch.RETRY_WINDOW

# The provider seam, published because ADR-005 asks for the provider-outage case to be
# demonstrable: "simulate email-provider outage; invitation operations should still
# succeed". A caller swaps the adapter; it still cannot see M7's internals (rule 2).
RecordingEmailAdapter = adapters.RecordingEmailAdapter
AlwaysFailingEmailAdapter = adapters.AlwaysFailingEmailAdapter


def set_email_adapter(adapter: EmailAdapter | None) -> EmailAdapter | None:
    """Install an email adapter and return the previous one. Tests and the demo only."""
    return adapters.set_adapter(adapter)


def dispatch_due(limit: int = 50) -> DispatchRun:
    """Dispatch every outbox record whose next attempt is due. Never raises on a
    provider failure: a failure is recorded and retried."""
    return dispatch.dispatch_due(limit=limit)
