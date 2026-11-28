"""Django model-registration shim for M9. Not a public interface (see M1's shim)."""
from rally.modules.messaging.internal.models import (  # noqa: F401
    Conversation,
    Message,
)

__all__ = ["Conversation", "Message"]
