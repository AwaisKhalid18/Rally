"""M4 publishes no database read view.

It owns no tables, so there is nothing to publish. M4 **consumes** the views of M2, M3
and M6; see `internal/query.py`.
"""
