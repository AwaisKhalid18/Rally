"""Django model-registration shim for M1.

Django discovers an application's models at `<app package>.models`. The models themselves
live in `internal/`, which nothing outside M1 may import (rule 2). This file exists only
so the app registry and the migration autodetector can find them; it is **not** a public
interface. Use `rally.modules.identity.api.facade`.
"""
from rally.modules.identity.internal.models import Account  # noqa: F401

__all__ = ["Account"]
