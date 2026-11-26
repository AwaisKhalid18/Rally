"""P Platform.

Request pipeline, authentication enforcement, response shaping, the server clock (UTC),
the unit-of-work mechanism, startup wiring, read-only composition, the worker host and
structured logging.

Platform contains **no business rule** (AGENTS.md §3, rule 14). It may wire, mechanise
transactions and orchestrate read-only facade calls; it never starts a transaction for a
business module and never branches on business data.
"""
