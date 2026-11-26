"""A player's own slots may not overlap (AC2, G-12).

Enforced twice, the same way double-booking is (AGENTS.md §5, ADR-004): an application
check in `internal/rules.py` so the player gets a readable sentence, and this constraint
as the backstop that actually holds under concurrency. The application check alone is
check-then-act.

The range is half-open, `[start, end)`, so back-to-back slots do not conflict.

`btree_gist` is a standard PostgreSQL extension, not a new database or service (rule 10).
Creating it needs a role with the right to do so; S8 needs the same extension for the
`game_participant` exclusion constraint.
"""
from django.db import migrations

CREATE = """
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE availability_slot
    ADD CONSTRAINT availability_slot_no_overlap
    EXCLUDE USING gist (
        account_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&
    );
"""

DROP = "ALTER TABLE availability_slot DROP CONSTRAINT IF EXISTS availability_slot_no_overlap;"


class Migration(migrations.Migration):
    dependencies = [("availability", "0001_initial")]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
