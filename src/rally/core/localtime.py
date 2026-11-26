"""Converting between what a player types and what Rally stores.

AGENTS.md §5 [v5]: one configured display time zone for the pilot; every timestamp is
stored as UTC. Players type local dates and times, and Platform converts at the edge.

This is mechanism, not a business rule (rule 14): it decides nothing about whether a time
is acceptable — M3 and M5 do that, against the clock in `rally.core.clock`.
"""
from __future__ import annotations

import datetime as _dt

from django.utils import timezone

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


class LocalTimeInvalid(ValueError):
    """The text was not a date and a time at all. Shape, not policy."""


def parse_local(date_text: str, time_text: str) -> _dt.datetime:
    """Read a typed local date and time and return the instant in UTC."""
    try:
        naive = _dt.datetime.strptime(f"{date_text.strip()} {time_text.strip()}", f"{DATE_FORMAT} {TIME_FORMAT}")
    except (ValueError, AttributeError) as error:
        raise LocalTimeInvalid(str(error)) from error
    local = timezone.make_aware(naive, timezone.get_current_timezone())
    return local.astimezone(_dt.timezone.utc)


def to_local(instant: _dt.datetime) -> _dt.datetime:
    return timezone.localtime(instant)


def local_date_text(instant: _dt.datetime) -> str:
    return to_local(instant).strftime(DATE_FORMAT)


def local_time_text(instant: _dt.datetime) -> str:
    return to_local(instant).strftime(TIME_FORMAT)
