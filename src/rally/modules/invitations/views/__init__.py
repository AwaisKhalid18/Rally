"""M5 publishes no database read view.

Nothing reads M5's tables: a participant asks the facade, and the in-app invitation
record is the source of truth for state (architecture §6.6, ASR-11).
"""
