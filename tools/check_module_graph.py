#!/usr/bin/env python3
"""Check Rally's declared module dependency graph against AGENTS.md section 3.

Usage:
    python tools/check_module_graph.py
    python tools/check_module_graph.py --drop safety:invitations   # a what-if

Rules checked (AGENTS.md section 3 "Permitted dependencies", section 4 rules 1, 9, 11, 12;
architecture.md 6.1.3 to 6.1.6):

  1. Every edge names two declared modules.
  2. The graph is acyclic.
  3. identity and safety depend on nothing.
  4. Nothing depends on search, notification or collections.
  5. search owns no tables (it is read-only).
  6. Only search, collections and profile consume a published read view.
  7. A module marked built has its package on disk; one that is not, does not.

Exit code 0 on PASS, 1 on FAIL. No third-party dependency: this runs in CI before
anything is installed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = Path(__file__).resolve().parent / "module-graph.json"
SRC = ROOT / "src"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def find_cycle(ids: set[str], edges: list[tuple[str, str]]) -> list[str] | None:
    adjacency: dict[str, list[str]] = {name: [] for name in ids}
    for source, target in edges:
        adjacency[source].append(target)

    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(ids, WHITE)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for neighbour in adjacency[node]:
            if colour[neighbour] == GREY:
                return stack[stack.index(neighbour):] + [neighbour]
            if colour[neighbour] == WHITE:
                found = visit(neighbour)
                if found:
                    return found
        stack.pop()
        colour[node] = BLACK
        return None

    for node in sorted(ids):
        if colour[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Check the declared Rally module graph.",
    )
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        metavar="FROM:TO",
        help="remove an edge before checking (a what-if, not a decision)",
    )
    args = parser.parse_args(argv)

    graph = load(GRAPH)
    modules = {module["id"]: module for module in graph["modules"]}
    constraints = graph["constraints"]

    dropped = set()
    for item in args.drop:
        source, _, target = item.partition(":")
        dropped.add((source, target))

    edges: list[tuple[str, str]] = []
    kinds: dict[tuple[str, str], str] = {}
    violations: list[str] = []

    for edge in graph["edges"]:
        pair = (edge["from"], edge["to"])
        if pair in dropped:
            continue
        for end in pair:
            if end not in modules:
                violations.append(
                    "edge {} -> {} names unknown module {!r}".format(pair[0], pair[1], end)
                )
        edges.append(pair)
        kinds[pair] = edge.get("kind", "facade")

    if not violations:
        cycle = find_cycle(set(modules), edges)
        if cycle:
            violations.append("CYCLE: " + " -> ".join(cycle) + "   (6.1.6 no cycles)")

        for module_id in constraints["no_outgoing"]:
            for source, target in edges:
                if source == module_id:
                    violations.append(
                        "{0} must depend on nothing, found {0} -> {1}".format(module_id, target)
                    )

        for module_id in constraints["no_incoming"]:
            for source, target in edges:
                if target == module_id:
                    violations.append(
                        "nothing may depend on {0}, found {1} -> {0}".format(module_id, source)
                    )

        for module_id in constraints["owns_no_tables"]:
            owned = modules[module_id].get("owns") or []
            if owned:
                violations.append(
                    "{} is read-only and must own no table, found {}".format(module_id, owned)
                )

        allowed_consumers = set(constraints["read_view_consumers"])
        for (source, target), kind in kinds.items():
            if kind == "read_view" and source not in allowed_consumers:
                violations.append(
                    "{0} may not consume a published read view ({0} -> {1})".format(source, target)
                )

    for module in graph["modules"]:
        package = SRC / module["package"]
        exists = (package / "__init__.py").exists()
        if module["built"] and not exists:
            violations.append(
                "{} is declared built but {} is missing".format(module["id"], module["package"])
            )
        if not module["built"] and exists:
            violations.append(
                "{} exists on disk but is not declared built - update module-graph.json".format(
                    module["id"]
                )
            )

    summary = "modules: {}   edges: {}".format(len(modules), len(edges))
    if dropped:
        summary += "   dropped: {}".format(len(dropped))
    print(summary)

    if violations:
        print()
        print("FAIL - {} violation(s):".format(len(violations)))
        for violation in violations:
            print("  x " + violation)
        return 1

    print("PASS - graph is acyclic and satisfies the AGENTS.md section 3 rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
