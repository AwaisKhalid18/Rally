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

Prerequisites: **Python 3.12+** and a **PostgreSQL 14+** server. The project uses one
database and one external service (an email provider), and the email provider is off by
default — the console backend prints messages instead, so nothing is ever sent (G-14).

`docker-compose.yml` is there if Docker works for you:

    docker compose up -d                      # PostgreSQL on localhost:5432

Without Docker, create a database and user on a PostgreSQL you already have, then point
the project at it with the environment variables below. Then, from the project root:

    py -m venv .venv
    .venv\Scripts\pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
    copy .env.example .env                              # Linux/macOS: cp
    .venv\Scripts\python manage.py migrate
    .venv\Scripts\python manage.py load_areas          # the pilot city's areas
    .venv\Scripts\python manage.py runserver

Open <http://127.0.0.1:8000/> and register an account. The verification email prints to
the console the server runs in; open the link it contains.

### Pointing it at a database

`.env` is read if present; the same names work as environment variables, which is what
you need when your PostgreSQL is not on the default port:

| Variable | Default |
| --- | --- |
| `RALLY_DB_NAME` · `RALLY_DB_USER` · `RALLY_DB_PASSWORD` | `rally` / `rally` / `rally` |
| `RALLY_DB_HOST` · `RALLY_DB_PORT` | `127.0.0.1` / `5432` |
| `RALLY_TIME_ZONE` | `Asia/Karachi` — one display zone; everything is stored UTC |
| `RALLY_MAX_FAVORITES` · `RALLY_MAX_SAVED_SEARCHES` | `50` / `20` |

In PowerShell, for a server on port 55432:

    $env:RALLY_DB_PORT = "55432"
    .venv\Scripts\python manage.py migrate

### The background worker

Emails and the expiry sweep are the worker's job, not the web request's. Run it in a
second terminal, with the same database variables:

    .venv\Scripts\python manage.py run_worker          # --once for a single pass

Until it runs, notifications sit in the app marked **queued**, which is what the product
honestly says. Nothing is sent unless `RALLY_EMAIL_LIVE=1` and SMTP credentials are
supplied.

### Seeing it work, on a fresh database

    .venv\Scripts\python manage.py load_areas
    .venv\Scripts\python manage.py seed_players --count 10000   # the CON-03 dataset
    .venv\Scripts\python manage.py demo_walk

`demo_walk` registers three players and walks every flow — profile, availability,
search, compare, favorites, saved searches, invitation, acceptance, the confirmed game,
notifications, cancellation, blocking and reporting — printing what the system actually
answered at each step and failing if any step does not do what its slice promised.

Seeded players cannot be signed in as: their passwords are deliberately unusable, since
nobody signs in as a synthetic player. They exist so search has 10,000 profiles to work
against.

## Checks

    python tools/check_module_graph.py        # declared dependency graph
    lint-imports                              # import-linter contracts (set PYTHONPATH=src)
    python manage.py test rally               # the full suite

All three run in CI on every push and pull request. The suite needs the database.

Performance evidence is produced by `ops/load_test.py`, which drives authenticated
searches concurrently and reports p50/p95/p99 and the error rate against whichever
server it is pointed at.

## Status

Built slice by slice against `plan.md`; each slice is a vertical, user-visible
capability. S1–S15 are implemented — the eight modules, the worker, and every screen in
AGENTS.md §11.3. FR-16 to FR-18 (favorites, compare, saved searches) come from an
amendment that is **not** part of the Final Validated PRD and are marked as such
throughout.
