"""M4's published interface. Only Platform calls it (rule 9)."""
from rally.modules.search.api import facade  # noqa: F401

__all__ = ["facade"]
