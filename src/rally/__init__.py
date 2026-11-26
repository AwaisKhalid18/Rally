"""Rally — one top-level package for the whole modular monolith.

`rally.core`    — P Platform: pipeline, clock, response shapers, wiring, web.
`rally.modules` — the capability modules M1…M8, each reachable only through its `api`.

See AGENTS.md §3 for the module map and §3.1 for why Platform is `rally.core` and not
`rally.platform`.
"""
