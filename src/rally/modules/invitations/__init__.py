"""M5 Invitation & Games — the invitation state machine, acceptance, confirmed games.

Owns  : `invitation` · `confirmed_game` and `game_participant` arrive with S8
Serves: FR-08, FR-09, FR-10, FR-11, FR-15; ASR-07, ASR-08, ASR-09, ASR-10, ASR-11
Never : owns availability or block data; imports M7; lets any other module change an
        invitation's status.
Depends on: M3 Availability, M6 Safety, M2 Profile — and not on M1 (architecture §6.3:
        the sender's verification state is read through M2).
"""
