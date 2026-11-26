"""M1 Identity — accounts, credentials, sessions, email-verification state.

Owns  : `account`, `session` (Django's session table, AGENTS.md §3.1)
Serves: FR-01, FR-14; ASR-04, ASR-05, ASR-06
Never : holds profile content; knows anything about search, invitations or games.
Depends on: nothing.
"""
default_app_config = None
