"""The one server clock. Always UTC (AGENTS.md rule 8, §5 Time zone).

Every state transition reads the time from here. A client-supplied timestamp is never
trusted. The clock is injectable so tests can freeze time.
"""
from __future__ import annotations

import datetime as _dt
from typing import Protocol


class Clock(Protocol):
    def now(self) -> _dt.datetime:
        """Return the current instant, timezone-aware, in UTC."""


class SystemClock:
    def now(self) -> _dt.datetime:
        return _dt.datetime.now(_dt.timezone.utc)


class FrozenClock:
    """Test double. Not used by production code."""

    def __init__(self, instant: _dt.datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FrozenClock needs a timezone-aware instant")
        self._instant = instant.astimezone(_dt.timezone.utc)

    def now(self) -> _dt.datetime:
        return self._instant

    def advance(self, **delta: float) -> None:
        self._instant += _dt.timedelta(**delta)


_clock: Clock = SystemClock()


def now() -> _dt.datetime:
    """The current instant in UTC."""
    return _clock.now()


def set_clock(clock: Clock) -> Clock:
    """Install a clock and return the previous one. For tests only."""
    global _clock
    previous, _clock = _clock, clock
    return previous
