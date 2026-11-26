"""M6's published interface. Everything outside M6 enters here and nowhere else."""
from rally.modules.safety.api import facade  # noqa: F401

__all__ = ["facade"]
