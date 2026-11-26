"""M3's published database read view.

`v_active_availability` — slot id, account id, start and end, **future slots only**.

The SQL lives in this module's migrations. Permitted consumers: `search` (M4) and
`collections` (M8) — ADR-002, ADR-006. Changing a column is a contract change.

The view filters on the database clock, so a slot whose end time has passed disappears
from it immediately, whether or not the worker's sweep has run. That is what keeps a
stalled worker a freshness problem and never a correctness one (ADR-005).
"""

ACTIVE_AVAILABILITY = "v_active_availability"
ACTIVE_AVAILABILITY_COLUMNS = ("slot_id", "account_id", "starts_at", "ends_at")

__all__ = ["ACTIVE_AVAILABILITY", "ACTIVE_AVAILABILITY_COLUMNS"]
