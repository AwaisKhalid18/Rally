# Rally

Rally helps recreational badminton players find a suitable playing partner when their
usual friends are unavailable. A player searches by date, time window and area, sees
ranked players whose availability, approximate distance and playing level fit, sends an
invitation, and the recipient accepts or declines — acceptance creates a confirmed game
that can never overlap another confirmed game for either player.

Private contact data and exact location are never exposed.

## Read this first

`AGENTS.md` in the repository root is the operational contract for everyone working here,
human or AI. It holds the module map, the permitted dependency edges and binding rules
1–15. Read it before changing anything.

Authority order: `docs/context/PRD.md` → `docs/context/architecture.md` → `docs/adr/` →
process evidence → `AGENTS.md`.

## Architecture in one paragraph

A modular monolith: one deployable Django web app plus one background worker built from the
same codebase, over one PostgreSQL database, organised by business capability. Each module
owns its tables and is reachable only through its facade. One external service: an email
provider, reached only by the worker.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3 + Django (modular monolith) |
| Database | PostgreSQL |
| Frontend | Django templates, server-rendered (HTMX vendored when a slice needs it) |
| Worker | Django management command polling the outbox |
| Boundary tests | `import-linter` + `tools/check_module_graph.py` |

## Layout

    src/rally/core/          Platform (P): pipeline, clock, shapers, wiring, web
    src/rally/modules/<m>/   capability modules, each api/ internal/ views/ migrations/ tests/
    tools/                   module-graph.json + check_module_graph.py
    docs/context/            PRD, architecture, process evidence
    docs/adr/                ADR-001 … ADR-008
    ops/                     seed data, environment definitions

`src/rally/core` is the Platform layer and `profile` / `collections` are physically named
`profiles` / `player_collections`, because `platform`, `profile` and `collections` are
Python standard-library module names (AGENTS.md §3.1).

## Running it locally

Prerequisites: Python 3.12+ and Docker (for PostgreSQL).

    docker compose up -d                      # PostgreSQL on localhost:5432
    py -m venv .venv                          # Windows:  .venv\Scripts\activate
    .venv/bin/pip install -r requirements.txt #           .venv\Scripts\pip install -r requirements.txt
    cp .env.example .env                      # then edit if needed
    python manage.py migrate
    python manage.py runserver

Open http://127.0.0.1:8000/ .

## Checks

    python tools/check_module_graph.py        # declared dependency graph
    lint-imports                              # import-linter contracts
    python manage.py test                     # Django tests

All three run in CI on every push and pull request.

## Status

Built slice by slice against `plan.md`. Each slice is a vertical, user-visible capability.
Slice S1 (register, sign in, sign out, plus the minimal skeleton) is the first.
