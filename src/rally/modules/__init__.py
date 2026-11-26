"""The capability modules M1…M8.

Each module owns its tables and is reachable only through its `api` package. Nothing
outside a module may import its `internal` package or its `models` shim (AGENTS.md
rules 1 and 2). The permitted dependency edges are listed in AGENTS.md §3 and checked by
`tools/check_module_graph.py` and `import-linter`.
"""
