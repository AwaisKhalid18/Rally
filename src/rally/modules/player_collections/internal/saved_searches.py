"""Saved searches: save, list, edit, delete, and resolving the day (FR-18, ADR-006).

M8 stores the criteria. **It never runs them.** Reusing a saved search is composed in
Platform: fetch the criteria here, then call `M4.search()` — the same entry point a
typed search uses, so every rule in ASR-02 and ASR-10 applies identically. M8 does not
call M4 and M4 does not read M8 (rule 12, architecture §16.6, §16.8).

**G-05, the one real decision here.** FR-18 says a saved search stores a date, but an
absolute date goes stale the day after it passes, which makes a "reusable" search
unusable. The resolution (AGENTS.md §5, R-14) is that a saved search carries **either**
a fixed date **or** a day rule that resolves at reuse time. A past fixed date is
reported as needing a new date and is **not** run — never silently shifted to today,
which would run a search the player did not ask for.

Nothing here stores a coordinate (ASR-03): the location is an area reference, and the
centroid is resolved from M2 at execution time.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction

from rally.core import clock
from rally.core.localtime import to_local
from rally.core.logging import log_operation
from rally.modules.player_collections.internal.models import (
    NAME_MAX_LENGTH,
    DayRule,
    SavedSearch,
)

DEFAULT_MAX_SAVED_SEARCHES = 20

NAME_REQUIRED = "Give this search a name."
NAME_TOO_LONG = f"Keep the name under {NAME_MAX_LENGTH} characters."
NAME_TAKEN = "You already have a saved search with that name."
DAY_REQUIRED = "Choose a date, or a day this search should mean."
DAY_AMBIGUOUS = "Choose either a date or a day rule, not both."
DAY_RULE_UNKNOWN = "Choose one of the days offered."
TIMES_REQUIRED = "Enter both times."
END_BEFORE_START = "The end time must be after the start time."
AREA_REQUIRED = "Choose an area."
NOT_FOUND = "No such saved search."

# Rule 13: a past fixed date is reported, not quietly replaced.
NEEDS_A_NEW_DATE = "This search is for a date that has passed. Give it a new date to run it."

_WEEKDAYS = {
    DayRule.MONDAY: 0,
    DayRule.TUESDAY: 1,
    DayRule.WEDNESDAY: 2,
    DayRule.THURSDAY: 3,
    DayRule.FRIDAY: 4,
    DayRule.SATURDAY: 5,
    DayRule.SUNDAY: 6,
}

DAY_RULE_CHOICES = tuple(DayRule.choices)


def max_saved_searches() -> int:
    return int(getattr(settings, "RALLY_MAX_SAVED_SEARCHES", DEFAULT_MAX_SAVED_SEARCHES))


def cap_reached_message() -> str:
    return (
        f"You have the most saved searches Rally keeps, {max_saved_searches()}. "
        "Delete one before saving another."
    )


@dataclass(frozen=True)
class SavedSearchRecord:
    saved_search_id: int
    name: str
    fixed_date: _dt.date | None
    day_rule: str
    day_rule_label: str
    start_time: _dt.time
    end_time: _dt.time
    area_code: str
    playing_level: str
    max_distance_km: int | None
    updated_at: _dt.datetime
    # The date this search would run for, resolved against the server clock — or None
    # with a reason, when a fixed date has passed (G-05).
    resolved_date: _dt.date | None
    cannot_run_reason: str | None

    @property
    def can_run(self) -> bool:
        return self.resolved_date is not None


@dataclass(frozen=True)
class SaveResult:
    saved_search_id: int | None = None
    errors: dict[str, str] | None = None

    @property
    def ok(self) -> bool:
        return self.saved_search_id is not None


def today_locally() -> _dt.date:
    """The current date in the one configured display time zone (AGENTS.md §5).

    Not `clock.now().date()`: that is UTC, and at 02:00 in Karachi it would resolve
    "today" to yesterday. Players type and read local dates; the clock stays injectable
    so a frozen test clock still governs (rule 8).
    """
    return to_local(clock.now()).date()


def resolve_date(fixed_date, day_rule: str, today: _dt.date):
    """The day this search is for. `(date, reason)` — exactly one is set.

    A fixed date in the past is refused rather than nudged forward: running it for a
    different day would be running a search the player never asked for.
    """
    if fixed_date is not None:
        if fixed_date < today:
            return None, NEEDS_A_NEW_DATE
        return fixed_date, None
    if day_rule == DayRule.TODAY:
        return today, None
    if day_rule == DayRule.TOMORROW:
        return today + _dt.timedelta(days=1), None
    weekday = _WEEKDAYS.get(day_rule)
    if weekday is None:
        return None, DAY_RULE_UNKNOWN
    # "Next occurrence": today counts when it is that weekday, so a Saturday search is
    # usable on Saturday morning rather than jumping a week.
    ahead = (weekday - today.weekday()) % 7
    return today + _dt.timedelta(days=ahead), None


def _record(row: SavedSearch, today: _dt.date) -> SavedSearchRecord:
    resolved, reason = resolve_date(row.fixed_date, row.day_rule, today)
    return SavedSearchRecord(
        saved_search_id=row.pk,
        name=row.name,
        fixed_date=row.fixed_date,
        day_rule=row.day_rule,
        day_rule_label=dict(DayRule.choices).get(row.day_rule, ""),
        start_time=row.start_time,
        end_time=row.end_time,
        area_code=row.area_code,
        playing_level=row.playing_level,
        max_distance_km=row.max_distance_km,
        updated_at=row.updated_at,
        resolved_date=resolved,
        cannot_run_reason=reason,
    )


def _validate(name, fixed_date, day_rule, start_time, end_time, area_code) -> dict:
    errors: dict[str, str] = {}

    name = (name or "").strip()
    if not name:
        errors["name"] = NAME_REQUIRED
    elif len(name) > NAME_MAX_LENGTH:
        errors["name"] = NAME_TOO_LONG

    if fixed_date is not None and day_rule:
        errors["day"] = DAY_AMBIGUOUS
    elif fixed_date is None and not day_rule:
        errors["day"] = DAY_REQUIRED
    elif day_rule and day_rule not in DayRule.values:
        errors["day"] = DAY_RULE_UNKNOWN

    if start_time is None or end_time is None:
        errors["times"] = TIMES_REQUIRED
    elif end_time <= start_time:
        errors["times"] = END_BEFORE_START

    if not (area_code or "").strip():
        errors["area_code"] = AREA_REQUIRED

    return errors


def save(
    owner_account_id: int,
    name: str,
    start_time,
    end_time,
    area_code: str,
    fixed_date=None,
    day_rule: str = "",
    playing_level: str = "",
    max_distance_km=None,
) -> SaveResult:
    """Save a new named search (FR-18).

    A *past* fixed date is accepted here: the player may be saving today what they will
    date properly later, and refusing it would lose their other criteria. It is the
    *running* of it that is refused, with a reason (G-05).
    """
    errors = _validate(name, fixed_date, day_rule, start_time, end_time, area_code)
    if errors:
        return SaveResult(errors=errors)

    if count_for_owner(owner_account_id) >= max_saved_searches():
        return SaveResult(errors={"name": cap_reached_message()})

    now = clock.now()
    try:
        with transaction.atomic():  # a savepoint, so a clash leaves the caller usable
            row = SavedSearch.objects.create(
                owner_account_id=owner_account_id,
                name=name.strip(),
                fixed_date=fixed_date,
                day_rule=day_rule,
                start_time=start_time,
                end_time=end_time,
                area_code=area_code,
                playing_level=playing_level or "",
                max_distance_km=max_distance_km,
                created_at=now,
                updated_at=now,
            )
    except IntegrityError:
        return SaveResult(errors={"name": NAME_TAKEN})

    log_operation("saved_search.save", "saved", account_id=owner_account_id)
    return SaveResult(saved_search_id=row.pk)


def update(
    saved_search_id: int,
    owner_account_id: int,
    name: str,
    start_time,
    end_time,
    area_code: str,
    fixed_date=None,
    day_rule: str = "",
    playing_level: str = "",
    max_distance_km=None,
) -> SaveResult:
    """Edit your own saved search. Editing never runs a search (§16.8)."""
    errors = _validate(name, fixed_date, day_rule, start_time, end_time, area_code)
    if errors:
        return SaveResult(errors=errors)

    owned = SavedSearch.objects.filter(pk=saved_search_id, owner_account_id=owner_account_id)
    if not owned.exists():
        # Somebody else's and one that does not exist get the same answer (ASR-05).
        return SaveResult(errors={"name": NOT_FOUND})

    try:
        with transaction.atomic():
            owned.update(
                name=name.strip(),
                fixed_date=fixed_date,
                day_rule=day_rule,
                start_time=start_time,
                end_time=end_time,
                area_code=area_code,
                playing_level=playing_level or "",
                max_distance_km=max_distance_km,
                updated_at=clock.now(),
            )
    except IntegrityError:
        return SaveResult(errors={"name": NAME_TAKEN})

    log_operation("saved_search.update", "updated", account_id=owner_account_id)
    return SaveResult(saved_search_id=saved_search_id)


def delete(saved_search_id: int, owner_account_id: int) -> bool:
    removed, _ = SavedSearch.objects.filter(
        pk=saved_search_id, owner_account_id=owner_account_id
    ).delete()
    if removed:
        log_operation("saved_search.delete", "deleted", account_id=owner_account_id)
    return bool(removed)


def count_for_owner(owner_account_id: int) -> int:
    return SavedSearch.objects.filter(owner_account_id=owner_account_id).count()


def list_for_owner(owner_account_id: int) -> list[SavedSearchRecord]:
    """Your own saved searches, most recently changed first (ASR-05)."""
    today = today_locally()
    return [
        _record(row, today)
        for row in SavedSearch.objects.filter(owner_account_id=owner_account_id).order_by(
            "-updated_at", "-id"
        )
    ]


def get_for_owner(saved_search_id: int, owner_account_id: int) -> SavedSearchRecord | None:
    """One saved search, for its owner only. `None` for anybody else (ASR-05)."""
    row = SavedSearch.objects.filter(
        pk=saved_search_id, owner_account_id=owner_account_id
    ).first()
    if row is None:
        return None
    return _record(row, today_locally())
