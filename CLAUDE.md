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

## Environment Variables

A `.env` file (gitignored) holds credentials for deployment and external services:

- `FLY_API_TOKEN` — Fly.io API token for deployments
- `TEST_LOGIN_TOKENS` — UUID-to-discord-id mapping for test user login (format: `uuid:discord_id,uuid:discord_id`)

Values with spaces or special characters must be quoted (e.g. `KEY="value with spaces"`). Load before deploying: `set -a && source .env && set +a`

The following are stored as **Fly secrets** (not in `.env`):

- `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` — Discord OAuth credentials
- `DISCORD_WHITELIST_IDS` — comma-separated Discord IDs allowed to log in
- `ADMIN_DISCORD_IDS` — comma-separated Discord IDs with GM/admin privileges
- `TEST_LOGIN_TOKENS` — also set as a Fly secret (same value as in `.env`)

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

### E2E clicktests (slower, run selectively by feature area)

```bash
python3 -m pytest tests/e2e/ -v --browser chromium                    # run ALL clicktests (~5 min)
python3 -m pytest tests/e2e/ -v --browser chromium -m tracking        # run by feature mark (~15 sec)
python3 -m pytest tests/e2e/ -v --browser chromium -m advantages      # another mark example
python3 -m pytest tests/e2e/ -v --browser chromium -m "skills or rings"  # combine marks
```

Clicktests start a live uvicorn server on a random port with a temp database, then drive headless Chromium via Playwright. Tests are tagged with `pytest.mark` by feature area. **When developing a feature, run only the relevant mark(s)** — not the full suite.

Available marks, which features they cover, and which test files they map to are all documented in `tests/e2e/COVERAGE.md` (the "Pytest Marks" section). Marks are defined in `pytest.ini`.

### Coverage Policy

We target 100% branch coverage for all code that is actually exercised in tests. The only accepted exception is `database.py:get_db()`, which is overridden by the test fixture with an in-memory database — testing the real `get_db` would just test SQLAlchemy's session lifecycle, not our code.

If a function is called at all during tests, every branch in that function must be covered. When adding new code, write tests that exercise all branches including error/edge cases (e.g. invalid inputs, boundary values, unknown IDs). Do not leave defensive branches untested.

## Development Workflow

New features follow this cycle:

1. **Write failing unit tests (TDD red).** Define the expected behavior in `tests/` before writing any implementation.
2. **Implement the feature.** Write the code to make the tests pass.
3. **Iterate until unit tests pass (TDD green).** Check coverage to ensure all new branches are covered.
4. **Update the clicktest coverage checklist.** Before writing code, add new lines to `tests/e2e/COVERAGE.md` for each interactive behavior the feature introduces (buttons, fields, toggles, conditional visibility, AJAX calls). Mark them `[ ]`. This makes missing coverage visible.
5. **Write clicktests for frontend changes (REQUIRED).** Any feature that touches templates, client-side JS, HTMX interactions, or user-facing workflows MUST have corresponding e2e tests in `tests/e2e/`. Clicktests validate that the full user flow works end-to-end in a real browser — things like AJAX handlers returning JSON instead of rendering a page, redirects landing on the right URL, and interactive UI state (overlays, disabled buttons, tooltips) behaving correctly. These catch bugs that unit tests cannot. Tag new tests with the appropriate `pytest.mark` for the feature area. After writing tests, mark the corresponding lines in `COVERAGE.md` as `[x]` with the test reference.
6. **Run relevant clicktests by mark.** Use `pytest -m <mark>` to run only the tests for the feature area you changed — not the full suite. Example: `pytest tests/e2e/ -m advantages --browser chromium`. Iterate until they pass.

The key distinction: unit tests use TDD (tests first), clicktests are written after the feature works. Clicktests are run selectively, not as part of every iteration loop. **Do not skip clicktests** — if a feature changes frontend behavior, it needs a clicktest. The coverage checklist in `tests/e2e/COVERAGE.md` is the source of truth for what's tested.

7. **Deploy after UI changes.** Any change that touches the frontend (templates, CSS, client-side JS) should be deployed to Fly.io after tests pass so the live site stays current.
8. **Background full clicktest suite.** Immediately after deploying, kick off the full e2e suite in the background (`run_in_background`). Report "done" to the user without waiting. If the background run fails, investigate and notify the user immediately.

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
- **New model columns require a migration entry.** When adding a column to any SQLAlchemy model, you MUST also add it to `_migrate_add_columns()` in `database.py`. The production SQLite database on Fly.io persists across deploys — `create_all` only creates new tables, it does not add columns to existing ones. Tests won't catch this because they use a fresh in-memory database each run.

## Deployment

The Fly CLI is not pre-installed in the sandbox container. Install it and authenticate before deploying:

```bash
curl -L https://fly.io/install.sh | sh
export PATH="$HOME/.fly/bin:$PATH"
fly auth login                          # interactive login (requires browser or token)
fly deploy
```

Requires a persistent volume named `l7r_data` mounted at `/data`. The `DATABASE_URL` env var is set to `/data/l7r.db` in fly.toml.

## Test Users

Two non-admin test users ("Test User 1" and "Test User 2") are pre-seeded on startup for testing the site as a regular player. Log in via secret URLs:

```
https://l7r-character-sheet.fly.dev/auth/test-login/<uuid>
```

The UUIDs are stored in the `TEST_LOGIN_TOKENS` Fly secret and in `.env`. The route pattern is public; only the UUID tokens are secret. Test users are NOT admins — use them to test granting edit access, viewing as a non-GM, etc.
