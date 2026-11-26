"""M4 Search & Matching — the filter predicate, the ranking, result composition.

Owns  : **no tables.** It is a read-only module (AGENTS.md §3, rule 9).
Serves: FR-02, FR-03, FR-05, FR-07, FR-13; ASR-01, ASR-02, ASR-10, ASR-13
Never : writes any data; sends invitations; is called by another module.
Depends on: the published read views of M2, M3 and M6 — and nothing else.

There is no `migrations/` folder here and this package is not a Django app, because M4
owns nothing to migrate. That absence is the point.
"""
