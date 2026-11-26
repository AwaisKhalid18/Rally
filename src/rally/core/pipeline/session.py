"""Session mechanism (Platform).

M1 Identity is the authority for credentials and verification state; Platform only binds
an already-authenticated account id to the request session and takes it away again
(ADR-003: authentication is enforced in the pipeline, authorisation belongs to the owning
module).

Only the account id is stored. No contact data, no profile field, nothing private
(rule 6). The session rows themselves are Django's session table, which AGENTS.md §3.1
treats as M1's `session`.
"""
from __future__ import annotations

ACCOUNT_ID_KEY = "account_id"


def start_session(request, account_id: int) -> None:
    """Bind an authenticated account to this session, rotating the key first."""
    request.session.cycle_key()  # session-fixation defence
    request.session[ACCOUNT_ID_KEY] = int(account_id)


def end_session(request) -> None:
    request.session.flush()


def current_account_id(request) -> int | None:
    value = request.session.get(ACCOUNT_ID_KEY)
    return int(value) if value is not None else None
