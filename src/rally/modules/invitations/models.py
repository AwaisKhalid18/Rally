"""Django model-registration shim for M5. Not a public interface (see M1's shim)."""
from rally.modules.invitations.internal.models import Invitation  # noqa: F401

__all__ = ["Invitation"]
