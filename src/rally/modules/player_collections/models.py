"""Django model-registration shim for M8. Not a public interface (see M1's shim)."""
from rally.modules.player_collections.internal.models import Favorite  # noqa: F401

__all__ = ["Favorite"]
