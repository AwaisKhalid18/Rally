"""Seed synthetic players for the NFR-01 workload (CON-03, plan.md S5 AC7, S16 AC1).

    python manage.py load_areas
    python manage.py seed_players --count 10000

CON-03 makes a reproducible 10,000-profile dataset an architectural requirement, so
`--seed` fixes the pseudo-random choices: two runs on two machines build the same data.

Platform orchestrates and decides nothing (rule 14). Each module writes its own tables
through its own facade — this command touches no model and no table directly (rules 1
and 2).
"""
from __future__ import annotations

import datetime as _dt
import random

from django.core.management.base import BaseCommand, CommandError

from rally.core import clock
from rally.modules.availability.api import facade as availability
from rally.modules.identity.api import facade as identity
from rally.modules.profiles.api import facade as profiles

SEED_EMAIL_DOMAIN = "seed.invalid"
LEVELS = ("beginner", "intermediate", "advanced")
HOURS = (7, 9, 17, 18, 19, 20)


class Command(BaseCommand):
    help = "Create synthetic verified players with profiles and availability slots."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--count", type=int, default=10_000)
        parser.add_argument("--seed", type=int, default=20261127)
        parser.add_argument("--slots", type=int, default=2, help="slots per player")
        parser.add_argument("--days", type=int, default=14, help="spread slots over this many days")
        parser.add_argument("--offset", type=int, default=0, help="first seed number, to top up")

    def handle(self, *args, **options) -> None:
        count = options["count"]
        days = options["days"]
        slots_each = min(options["slots"], days)
        offset = options["offset"]
        rng = random.Random(options["seed"])

        area_codes = profiles.area_codes()
        if not area_codes:
            raise CommandError("no areas loaded - run `manage.py load_areas` first")

        now = clock.now().replace(minute=0, second=0, microsecond=0)
        self.stdout.write(f"seeding {count} players across {len(area_codes)} areas...")

        account_ids = identity.seed_verified_accounts(
            [f"seed{offset + i}@{SEED_EMAIL_DOMAIN}" for i in range(count)], now=now
        )

        profiles.seed_profiles(
            [
                {
                    "account_id": account_id,
                    "display_name": f"Seed Player {offset + i}",
                    "playing_level": rng.choice(LEVELS),
                    "area_code": rng.choice(area_codes),
                }
                for i, account_id in enumerate(account_ids)
            ]
        )

        slots = []
        for account_id in account_ids:
            # One player's slots may not overlap (M3's exclusion constraint), so they go
            # on distinct days.
            for day in rng.sample(range(1, days + 1), k=slots_each):
                starts_at = now + _dt.timedelta(days=day, hours=rng.choice(HOURS) - now.hour)
                slots.append(
                    {
                        "account_id": account_id,
                        "starts_at": starts_at,
                        "ends_at": starts_at + _dt.timedelta(hours=2),
                    }
                )
        availability.seed_slots(slots)

        self.stdout.write(f"seeded {len(account_ids)} players and {len(slots)} slots")
