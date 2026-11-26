#!/usr/bin/env python
"""Django management entry point for Rally.

The single top-level package `rally` lives under `src/` (AGENTS.md §3.1: there must be
no top-level package named `platform`, `profile` or `collections`).
"""
import os
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rally.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
