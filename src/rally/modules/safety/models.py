"""Django model-registration shim for M6. Not a public interface (see M1's shim)."""
from rally.modules.safety.internal.models import Block  # noqa: F401

__all__ = ["Block"]
