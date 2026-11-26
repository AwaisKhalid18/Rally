"""M1's published database read views.

`v_verified_account` — account id and verification state. **No contact fields.**

The SQL that creates the view lives in this module's migrations, because the view is part
of M1's schema. Changing a column here is a contract change, not an internal refactor
(ADR-002). Permitted consumers: `profile` (M2), per AGENTS.md rule 1.

This folder holds published *database* views, not Django views or templates
(AGENTS.md §10).
"""

VERIFIED_ACCOUNT = "v_verified_account"
VERIFIED_ACCOUNT_COLUMNS = ("account_id", "is_verified")

__all__ = ["VERIFIED_ACCOUNT", "VERIFIED_ACCOUNT_COLUMNS"]
