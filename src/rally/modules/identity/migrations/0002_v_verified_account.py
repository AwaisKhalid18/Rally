"""Publish M1's read view (ADR-002).

`v_verified_account` exposes an account id and a verification state and nothing else.
No contact field may ever be added to it (rule 6).
"""
from django.db import migrations

CREATE = """
CREATE OR REPLACE VIEW v_verified_account AS
SELECT id AS account_id,
       is_verified
FROM account
WHERE is_active = TRUE;
"""

DROP = "DROP VIEW IF EXISTS v_verified_account;"


class Migration(migrations.Migration):
    dependencies = [("identity", "0001_initial")]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
