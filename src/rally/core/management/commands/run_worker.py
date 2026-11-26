"""The background worker (ADR-008 S-08, ADR-005).

A Django management command in the same codebase and the same deployable — no Celery, no
Redis, no broker. It polls the outbox and dispatches what is due; it is the only caller
of the email provider (architecture §7).

    python manage.py run_worker              # poll forever
    python manage.py run_worker --once       # one pass, for tests and the demo

Platform hosts the worker; the work itself belongs to the modules and is reached through
their facades (rule 14). The expiry sweep — `M5.expirePending()` and
`M3.removeExpiredSlots()` — is added by slices S4 and S9; expiry stays authoritative at
commit time, so a stopped worker degrades freshness and never correctness (ADR-005).
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from rally.core.logging import log_operation
from rally.modules.notification.api import facade as notification

DEFAULT_POLL_SECONDS = 10
DEFAULT_BATCH = 50


class Command(BaseCommand):
    help = "Dispatch due outbox records (and, from S4/S9, run the expiry sweep)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true", help="run a single pass and exit")
        parser.add_argument("--interval", type=float, default=DEFAULT_POLL_SECONDS)
        parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)

    def handle(self, *args, **options) -> None:
        once = options["once"]
        interval = options["interval"]
        batch = options["batch"]

        self.stdout.write("worker started" + (" (single pass)" if once else ""))
        while True:
            run = notification.dispatch_due(limit=batch)
            if run.claimed:
                log_operation(
                    "worker.pass",
                    "done",
                    claimed=run.claimed,
                    sent=run.sent,
                    retrying=run.retrying,
                    failed=run.failed,
                )
                self.stdout.write(
                    f"claimed={run.claimed} sent={run.sent} retrying={run.retrying} failed={run.failed}"
                )
            if once:
                return
            time.sleep(interval)
