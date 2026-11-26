"""Publish M2's read view (ADR-002, ADR-006).

`v_searchable_profile` is the single place the search path learns what a player looks
like. It folds in profile completeness and M1's verification state, so M4 never has to
reimplement the ASR-06 gate.

It carries no contact field (rule 6) and no player location: `centroid_lat/lon` are the
centre of the chosen general area (rule 7, ASR-03).
"""
from django.db import migrations

CREATE = """
CREATE OR REPLACE VIEW v_searchable_profile AS
SELECT p.account_id        AS account_id,
       p.display_name      AS display_name,
       p.playing_level     AS playing_level,
       CASE p.playing_level
            WHEN 'beginner'     THEN 1
            WHEN 'intermediate' THEN 2
            WHEN 'advanced'     THEN 3
       END                  AS level_rank,
       a.code               AS area_code,
       a.name               AS area_name,
       a.centroid_lat       AS centroid_lat,
       a.centroid_lon       AS centroid_lon,
       COALESCE(v.is_verified, FALSE) AS searchable
FROM profile p
JOIN area a ON a.id = p.area_id
LEFT JOIN v_verified_account v ON v.account_id = p.account_id;
"""

DROP = "DROP VIEW IF EXISTS v_searchable_profile;"


class Migration(migrations.Migration):
    dependencies = [
        ("profiles", "0001_initial"),
        # The view reads M1's published view, so M1's must exist first. This is the one
        # permitted cross-module read (AGENTS.md rule 1, allowlist: profile -> identity).
        ("identity", "0002_v_verified_account"),
    ]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
