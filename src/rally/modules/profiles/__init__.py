"""M2 Profile — display name, playing level, general area, completeness, searchability.

Owns  : `profile`, `area`
Serves: FR-01, FR-05, FR-06, FR-14; ASR-03, ASR-06, ASR-13
Never : stores contact data, credentials or availability; stores any exact location.
Depends on: M1 Identity, through the published view `v_verified_account` only.

Physically `profiles` because `profile` is a Python standard-library module name
(AGENTS.md §3.1).
"""
