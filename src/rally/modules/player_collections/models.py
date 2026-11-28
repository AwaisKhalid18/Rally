"""Django model-registration shim for M8. Not a public interface (see M1's shim)."""
from rally.modules.player_collections.internal.models import (  # noqa: F401
    Favorite,
    SavedSearch,
)

__all__ = ["Favorite", "SavedSearch"]
