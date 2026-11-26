"""Publish M6's read view (ADR-002).

One row per directed block. A consumer checks both directions, because blocking hides
the pair from each other (PRD §12.5, ASR-10).
"""
from django.db import migrations

CREATE = """
CREATE OR REPLACE VIEW v_block_pairs AS
SELECT b.blocker_account_id AS blocker_account_id,
       b.blocked_account_id AS blocked_account_id
FROM block b;
"""

DROP = "DROP VIEW IF EXISTS v_block_pairs;"


class Migration(migrations.Migration):
    dependencies = [("safety", "0001_initial")]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
