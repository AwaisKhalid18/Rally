"""M8 Player Collections - a player's own favorites and named searches.

Owns  : `favorite`, `saved_search`
Serves: FR-16, FR-18 (architecture section 16, ADR-006)
Never : executes a search, calls M4 or is read by M4, copies another player's profile,
        availability or contact data, or stores coordinates (rules 11, 12).
Depends on: the published read views of M2, M3 and M6 - for composing the display only.

M8 is a leaf. Nothing depends on it, and it holds references rather than copies, so a
favorite can never show a playing level or an area the other player has since changed.

**FR-16 and FR-18 are not part of the Final Validated PRD** (architecture section 16.1).
They are real requirements recorded with the same discipline, but they have not been
through the client's validation, and nothing here may be presented as approved.

S13 builds favorites. Saved searches are S15.
"""
