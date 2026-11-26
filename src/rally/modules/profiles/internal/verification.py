"""M2's one read of M1 — the published view and nothing else.

AGENTS.md §3 permits exactly `profile -> identity (reads v_verified_account only)`. M2
therefore never imports M1 and never touches M1's tables: it queries the published view,
which carries an account id and a verification flag and no contact field (rule 1, rule 6,
ADR-002). import-linter enforces the absence of the import.
"""
from __future__ import annotations

from django.db import connection

VERIFIED_ACCOUNT_VIEW = "v_verified_account"


def account_is_verified(account_id: int) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT is_verified FROM {VERIFIED_ACCOUNT_VIEW} WHERE account_id = %s",
            [account_id],
        )
        row = cursor.fetchone()
    return bool(row and row[0])
