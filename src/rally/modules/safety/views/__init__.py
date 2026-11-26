"""M6's published database read view.

`v_block_pairs(blocker_account_id, blocked_account_id)` — one row per directed block.

This is the whole point of M6: the rule lives in one place and its consumers apply it.
Permitted consumers: `search` (M4) and `collections` (M8); M5 reads it through M6's
facade. Reading it in **both directions** is the caller's job, because "blocked" hides
the pair from each other (PRD §12.5, ASR-10).
"""

BLOCK_PAIRS = "v_block_pairs"
BLOCK_PAIRS_COLUMNS = ("blocker_account_id", "blocked_account_id")

__all__ = ["BLOCK_PAIRS", "BLOCK_PAIRS_COLUMNS"]
