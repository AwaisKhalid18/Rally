"""Template context processors."""
from __future__ import annotations


def viewer(request) -> dict:
    """Expose only the public viewer view model to templates (FE-1)."""
    return {"viewer": getattr(request, "viewer", None)}
