"""Django model-registration shim for M3. Not a public interface (see M1's shim)."""
from rally.modules.availability.internal.models import AvailabilitySlot  # noqa: F401

__all__ = ["AvailabilitySlot"]
