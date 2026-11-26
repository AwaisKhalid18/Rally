"""Django model-registration shim for M2. Not a public interface (see M1's shim)."""
from rally.modules.profiles.internal.models import Area, Profile  # noqa: F401

__all__ = ["Area", "Profile"]
