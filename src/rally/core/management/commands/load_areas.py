"""Load the fixed general-area list from `ops/seed/areas.csv` (PRD §12.1, R-11).

    python manage.py load_areas

Platform parses the file and hands rows to M2, which owns `area`. The file is data; the
schema is M2's. Replacing the list for a different pilot city is a data change, not an
architecture change (G-02: no geocoding service enters the system).
"""
from __future__ import annotations

import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rally.modules.profiles.api import facade as profiles

DEFAULT_PATH = Path(settings.BASE_DIR) / "ops" / "seed" / "areas.csv"


class Command(BaseCommand):
    help = "Load or refresh the fixed general-area list."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--path", default=str(DEFAULT_PATH))

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"no area file at {path}")

        rows = []
        with path.open(encoding="utf-8", newline="") as handle:
            # Comment lines document where the list came from; they are not data.
            lines = [line for line in handle if not line.lstrip().startswith("#")]
        for row in csv.DictReader(lines):
            rows.append(
                {
                    "code": row["code"].strip(),
                    "name": row["name"].strip(),
                    "centroid_lat": row["centroid_lat"].strip(),
                    "centroid_lon": row["centroid_lon"].strip(),
                }
            )

        loaded = profiles.replace_areas(rows)
        self.stdout.write(f"loaded {loaded} areas from {path.name}")
