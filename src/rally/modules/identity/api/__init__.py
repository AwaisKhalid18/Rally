"""M1's published interface. Everything outside M1 enters here and nowhere else."""
from rally.modules.identity.api import facade  # noqa: F401

__all__ = ["facade"]
