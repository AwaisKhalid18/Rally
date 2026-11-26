"""Publish M3's read view (ADR-002).

Future slots only. The filter uses the database clock, so the view is correct the moment
a slot ends, independently of the worker sweep.

No contact field and no location may ever be added here (rules 6 and 7).
"""
from django.db import migrations

CREATE = """
CREATE OR REPLACE VIEW v_active_availability AS
SELECT s.id         AS slot_id,
       s.account_id AS account_id,
       s.starts_at  AS starts_at,
       s.ends_at    AS ends_at
FROM availability_slot s
WHERE s.ends_at > now();
"""

DROP = "DROP VIEW IF EXISTS v_active_availability;"


class Migration(migrations.Migration):
    dependencies = [("availability", "0002_no_overlap")]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
