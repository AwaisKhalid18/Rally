"""No player may hold two overlapping confirmed games (FR-15, ASR-08, ADR-004).

Enforced twice. `internal/responding.py` checks first so the player gets a sentence;
this constraint is what actually holds under concurrency, because the application check
alone is check-then-act and loses a race.

It is keyed on `game_participant`, one row per player, for the reason recorded as AV-05
in the agent validation: a `confirmed_game` row carries *both* players, and an exclusion
constraint compares rows, so keyed there it could only ever protect one of them.

The range is half-open, `[start, end)`, so **back-to-back games do not conflict**
(PRD §12.4). Cancelled participations are excluded, so cancelling a game frees the time
at once (G-10).

`btree_gist` is the same standard extension M3's slot constraint already needs (S4).
"""
from django.db import migrations

CREATE = """
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE game_participant
    ADD CONSTRAINT game_participant_no_overlap
    EXCLUDE USING gist (
        account_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&
    )
    WHERE (cancelled_at IS NULL);
"""

DROP = "ALTER TABLE game_participant DROP CONSTRAINT IF EXISTS game_participant_no_overlap;"


class Migration(migrations.Migration):
    dependencies = [("invitations", "0002_confirmedgame_gameparticipant")]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
