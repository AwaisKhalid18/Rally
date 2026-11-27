"""M6 Safety — block relationships and their cascade; reports.

Owns  : `block`, `report`
Serves: FR-03, FR-08, FR-14, PRD §12.5; ASR-10
Never : applies a block itself. It **publishes** the rule; M4 and M5 apply it. A call
        the other way would invert the dependency and create a cycle (architecture §5.1).
Depends on: nothing.

S5 built a stub: the `block` table and the published view `v_block_pairs`, so M4's
search predicate could honour blocking from its first line. **S12 is the feature**:
the screens, the unblock list, the `report` table, and the cancellation cascade that
crosses back to M5 through the `PendingInvitationCanceller` port M6 declares.
"""
