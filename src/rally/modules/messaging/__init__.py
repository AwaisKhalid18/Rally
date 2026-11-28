"""M9 Messaging - a conversation between two players who have agreed to play.

Owns  : `conversation`, `message`
Serves: in-app chat
Never : lets a player message someone they have no confirmed game with, lets a message
        carry contact data out of M1, or opens a conversation across a block.
Depends on: M5 (is there a confirmed game between these two?) and M6 (the block rule).

**Status: not in the Final Validated PRD.** PRD 12.5 records in-app chat as formally
excluded from the MVP, and AGENTS.md 7 repeats it. This module was built on an explicit
instruction from the project lead to add it anyway. Until the PRD and the ADR record
that decision, this module is *ahead of* the artefacts, and both need updating - see
the README.

Three rules keep it from undoing the privacy model it was warned about:

1. A conversation exists only where a **confirmed game** does. Players who have merely
   searched for each other cannot message.
2. A **block** closes it in both directions, like everything else (ASR-10).
3. A message that looks like it carries an **email address or a phone number** is
   refused. Rule 6 keeps contact data inside M1, and a free-text box between two players
   is the one place it could leak out by hand.
"""
