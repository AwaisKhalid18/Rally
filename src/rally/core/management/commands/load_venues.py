"""Load the places to play from `ops/seed/venues.csv` (PRD §12.3).

    python manage.py load_venues

Platform parses the file and hands rows to M2, which owns `venue` beside `area`. The
file is data; the schema is M2's. Replacing the list for a different pilot city is a
data change, not an architecture change — the same footing `load_areas` is on.

Areas must be loaded first: a venue names the area it sits in, and one that names an
area that does not exist is refused rather than silently dropped.
"""
from __future__ import annotations

import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rally.modules.profiles.api import facade as profiles

DEFAULT_PATH = Path(settings.BASE_DIR) / "ops" / "seed" / "venues.csv"


class Command(BaseCommand):
    help = "Load or refresh the fixed list of places to play."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--path", default=str(DEFAULT_PATH))

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"no venue file at {path}")

        rows = []
        with path.open(encoding="utf-8", newline="") as handle:
            # Comment lines document where the list came from; they are not data.
            lines = [line for line in handle if not line.lstrip().startswith("#")]
        for row in csv.DictReader(lines):
            rows.append(
                {
                    "code": row["code"].strip(),
                    "area_code": row["area_code"].strip(),
                    "name": row["name"].strip(),
                }
            )

        if not rows:
            raise CommandError(f"{path.name} holds no venues")

        try:
            loaded = profiles.replace_venues(rows)
        except ValueError as refused:
            raise CommandError(f"{refused}. Run `manage.py load_areas` first.") from None

        self.stdout.write(f"loaded {loaded} places to play from {path.name}")
