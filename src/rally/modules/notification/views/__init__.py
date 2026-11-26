"""M7 publishes no database read view.

`outbox` and `notification` are M7's own working tables; nothing else reads them
(AGENTS.md §3: nothing depends on notification).
"""
