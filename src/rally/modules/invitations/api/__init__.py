"""M5's published interface. Everything outside M5 enters here and nowhere else."""
from rally.modules.invitations.api import facade  # noqa: F401

__all__ = ["facade"]
