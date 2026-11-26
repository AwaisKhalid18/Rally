"""Django model-registration shim for M7. Not a public interface (see M1's shim)."""
from rally.modules.notification.internal.models import Notification, Outbox  # noqa: F401

__all__ = ["Notification", "Outbox"]
