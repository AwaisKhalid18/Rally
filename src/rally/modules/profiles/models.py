"""Django model-registration shim for M2. Not a public interface (see M1's shim)."""
from rally.modules.profiles.internal.models import (  # noqa: F401
    Area,
    Profile,
    Venue,
)

__all__ = ["Area", "Profile", "Venue"]
