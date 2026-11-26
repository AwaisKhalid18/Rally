"""M2's published interface. Everything outside M2 enters here and nowhere else."""
from rally.modules.profiles.api import facade  # noqa: F401

__all__ = ["facade"]
