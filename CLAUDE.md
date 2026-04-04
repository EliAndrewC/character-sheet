# L7R Character Builder

A character sheet and character builder web app for L7R, a Legend of the Five Rings homebrew tabletop RPG system.

## Tech Stack

- **Backend:** Python / FastAPI
- **Database:** SQLite via SQLAlchemy (persistent volume on Fly.io)
- **Frontend:** Jinja2 templates + HTMX (server interactions) + Alpine.js (client-side reactivity) + Tailwind CSS (CDN)
- **Testing:** pytest (unit), Playwright + headless Chromium (e2e clicktests)
- **Deployment:** Fly.io with Docker

## Setup

The dev environment is the `docker.io/docker/sandbox-templates:claude-code` container. To install dependencies:

```bash
pip install --break-system-packages -r requirements.txt
playwright install chromium
playwright install-deps chromium
```

## Running the App

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

The app auto-creates the SQLite database (`l7r.db` by default) on first startup. Set the `DATABASE_URL` env var to change the path (file path only, the app prepends `sqlite:///`).

## Running Tests

### Unit tests (fast, run constantly during development)

```bash
python3 -m pytest tests/ --ignore=tests/e2e -v                        # run unit tests
python3 -m pytest tests/ --ignore=tests/e2e --cov=app --cov-report=term-missing  # with coverage
```

Unit tests use an in-memory SQLite database and FastAPI's TestClient (via httpx). No external services needed.

### E2E clicktests (slower, run selectively)

```bash
python3 -m pytest tests/e2e/ -v --browser chromium                    # run all clicktests
python3 -m pytest tests/e2e/test_live_xp.py -v --browser chromium     # run one file
python3 -m pytest tests/e2e/ -v --browser chromium -k "school"        # run by keyword
```

Clicktests start a live uvicorn server on a random port with a temp database, then drive headless Chromium via Playwright. They are organized by workflow:

- `test_smoke.py` — basic infrastructure check
- `test_create_character.py` — full character creation flow
- `test_edit_character.py` — editing and cancel workflows
- `test_live_xp.py` — client-side Alpine.js XP calculation (rings, skills, advantages, disadvantages, honor, overspend)
- `test_school_selection.py` — HTMX school details loading, knack selectors, techniques

### Coverage Policy

We target 100% branch coverage for all code that is actually exercised in tests. The only accepted exception is `database.py:get_db()`, which is overridden by the test fixture with an in-memory database — testing the real `get_db` would just test SQLAlchemy's session lifecycle, not our code.

If a function is called at all during tests, every branch in that function must be covered. When adding new code, write tests that exercise all branches including error/edge cases (e.g. invalid inputs, boundary values, unknown IDs). Do not leave defensive branches untested.

## Development Workflow

New features follow this cycle:

1. **Write failing unit tests (TDD red).** Define the expected behavior in `tests/` before writing any implementation.
2. **Implement the feature.** Write the code to make the tests pass.
3. **Iterate until unit tests pass (TDD green).** Check coverage to ensure all new branches are covered.
4. **Write clicktests for frontend changes.** If the feature touches the frontend, add e2e tests in `tests/e2e/` that exercise the workflow in a real browser.
5. **Run relevant clicktests.** Only run the specific clicktest file(s) related to this change — not the entire e2e suite. Iterate until they pass.

The key distinction: unit tests use TDD (tests first), clicktests are written after the feature works. Clicktests are run selectively, not as part of every iteration loop.

## Project Structure

```
app/
  main.py              — FastAPI app entry point, template + static config
  game_data.py         — All L7R rules as Python dataclasses (schools, skills, knacks, etc.)
  database.py          — SQLAlchemy engine, session, Base, get_db dependency
  models.py            — Character SQLAlchemy model
  services/xp.py       — XP calculation engine
  routes/pages.py      — Full HTML page routes (index, create, view, edit)
  routes/characters.py — Character CRUD + HTMX partial endpoints
  templates/           — Jinja2 templates
tests/                 — Unit test suite (pytest)
tests/e2e/             — E2E clicktests (Playwright)
```

## L7R Rules

The canonical rules live at: https://github.com/EliAndrewC/l7r/tree/master/rules

`app/game_data.py` encodes these rules as Python data structures. When rules change upstream, this file needs to be updated to match. The same is true for any campaign-specific supplemental rules, which will also live in public GitHub repos.

## Key Architectural Decisions

- **XP calculation is implemented both client-side (Alpine.js) and server-side (services/xp.py).** The client-side version provides instant feedback during editing; the server-side version is authoritative for validation and display on the character sheet. These must stay in sync.
- **TemplateResponse uses keyword arguments** (`request=`, `name=`, `context=`) — required by the installed Starlette version.
- **School selection uses `htmx.ajax()` called from Alpine.js** — not HTMX attributes on the select element. This is because the URL is dynamic (includes the school ID) and HTMX attribute-based triggers don't reliably fire from Alpine-managed elements.
- **School ring choice is stored explicitly** because some schools let the player choose their school ring (e.g. "any non-Void"). The `school_ring_choice` field records which ring was actually selected.
- **Knacks start at rank 1 for free** (given by the school). XP cost for knacks only applies for ranks above 1.
- **Dan = minimum school knack rank.** A character's Dan level equals the lowest rank among their three school knacks.

## Deployment

```bash
fly deploy
```

Requires a persistent volume named `l7r_data` mounted at `/data`. The `DATABASE_URL` env var is set to `/data/l7r.db` in fly.toml.
