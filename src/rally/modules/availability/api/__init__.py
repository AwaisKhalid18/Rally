"""M3's published interface. Everything outside M3 enters here and nowhere else."""
from rally.modules.availability.api import facade  # noqa: F401

__all__ = ["facade"]
