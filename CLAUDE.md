# L7R Character Builder

A character sheet and character builder web app for L7R, a Legend of the Five Rings homebrew tabletop RPG system.

<!-- Dev-container config consumed by launch-container.sh (lives in the sibling gm-assistant repo). Format is HOST:CONTAINER. -->
<!-- Primary = the FastAPI/uvicorn app (container 8080). Secondary (container 8090) is reserved for a future blind-eval webapp; nothing listens there yet. Host ports are unique across the GM's repos so several containers can run at once. -->
<!-- container-ports: 8081:8080 8092:8090 -->
<!-- Mount the parent l7r repo at /host-l7r-repo; its rules/ dir holds the canonical L7R rules this project encodes. -->
<!-- container-mounts: ..:/host-l7r-repo -->
<!-- container-workdir: /character-sheet -->
<!-- (distinct mount path per repo so Claude memory under ~/.claude/projects/ stays separate across sibling repos) -->

## Tech Stack

- **Backend:** Python / FastAPI
- **Database:** SQLite via SQLAlchemy (persistent volume on Fly.io)
- **Frontend:** Jinja2 templates + HTMX (server interactions) + Alpine.js (client-side reactivity) + Tailwind CSS (build-time compiled to `app/static/css/app.css`, see "Styling / CSS build") - all self-hosted in /static/, no CDN
- **Testing:** pytest (unit), Playwright + headless Chromium (e2e clicktests)
- **Deployment:** Fly.io with Docker

## Setup

The dev environment is the `docker.io/docker/sandbox-templates:claude-code` container. To install dependencies:

```bash
sudo apt-get install -y libmagic1 antiword libcairo2  # system deps for the importer + dice-card PNG renderer
pip install --break-system-packages -r requirements.txt
pip install --break-system-packages reportlab         # test-only: used to build PDF fixtures in tests/test_import_llm.py
playwright install chromium
playwright install-deps chromium
```

`libmagic1` is required by `python-magic` (importer format detection) and `antiword` is required by the `.doc` ingest path in `app/services/import_ingest.py`. `libcairo2` is required by `cairocffi`/`CairoSVG`, used by the dice-card PNG renderer; without it `tests/test_dice_card.py` errors out at collection time. All three are missing from `requirements.txt` because they are system packages; without them `app.main` fails to import and large portions of the unit suite never run. `reportlab` is a dev-only dependency (PDF fixtures); it is not imported by `app/` at runtime, so it lives outside `requirements.txt`.

If `apt-get install` can't find the packages, run `sudo apt-get update` first (a fresh container may have a stale package index).

### Newer-than-supported OS quirks (e.g. Ubuntu 26.04 "resolute")

The sandbox container can be a newer Ubuntu release than Playwright supports, which breaks two of the setup steps. Both have simple workarounds:

- **`playwright install chromium` fails** with `Playwright does not support chromium on ubuntu26.04-x64`. This is a host-OS version gate, not a missing binary. Temporarily spoof `/etc/os-release` to the most recent supported LTS, install, then restore it:
  ```bash
  sudo cp /etc/os-release /tmp/os-release.bak
  sudo sed -i 's/26.04/24.04/g; s/VERSION_CODENAME=resolute/VERSION_CODENAME=noble/; s/UBUNTU_CODENAME=resolute/UBUNTU_CODENAME=noble/' /etc/os-release
  playwright install chromium && playwright install-deps chromium
  sudo cp /tmp/os-release.bak /etc/os-release    # restore - the downloaded browser runs fine on the real OS
  ```
- **`node --test tests/js/` errors** with `Cannot find module '/character-sheet/tests/js'` on newer Node (e.g. v22.22). The directory-argument form is unreliable on that version; pass an explicit glob instead: `node --test tests/js/*.test.js`.

## Environment Variables

A `.env` file (gitignored) holds credentials for deployment and external services:

- `FLY_API_TOKEN` - Fly.io API token for deployments
- `MAGIC_LOGIN_TOKENS` - UUID-to-discord-id mapping for backup login URLs (format: `uuid:discord_id,uuid:discord_id`). Covers test users plus any campaign player who needs a Discord-bypass link. The legacy name `TEST_LOGIN_TOKENS` is still read for backward compat.
- `GOOGLE_CLIENT_ID` - Google OAuth 2.0 client ID (for Google Sheets export)
- `GOOGLE_CLIENT_SECRET` - Google OAuth 2.0 client secret

Values with spaces or special characters must be quoted (e.g. `KEY="value with spaces"`). Load before deploying: `set -a && source .env && set +a`

The following are stored as **Fly secrets** (not in `.env`):

- `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` - Discord OAuth credentials
- `DISCORD_WHITELIST_IDS` - comma-separated Discord IDs allowed to log in
- `ADMIN_DISCORD_IDS` - comma-separated Discord IDs with GM/admin privileges
- `MAGIC_LOGIN_TOKENS` - also set as a Fly secret (same value as in `.env`)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - also set as Fly secrets (same values as in `.env`)
- `S3_BACKUP_BUCKET` - S3 bucket name for database backups (e.g. `l7r-character-sheet-backups`)
- `S3_BACKUP_REGION` - AWS region (default: `us-east-1`)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` - IAM credentials for S3 backup (needs PutObject, GetObject, DeleteObject, ListBucket on the bucket)

## Running the App

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

The app auto-creates the SQLite database (`l7r.db` by default) on first startup. Set the `DATABASE_URL` env var to change the path (file path only, the app prepends `sqlite:///`).

## Styling / CSS build

Tailwind is **compiled at build time** into `app/static/css/app.css` (a purged, minified stylesheet, ~50KB) - NOT the in-browser Play CDN runtime (that ~407KB `tailwind.js` was removed). `base.html` links `app.css` and keeps its hand-written rules in the inline `<style>` block.

- **Theme** (custom colors `accent`/`gold`/`success`/`info`, the `display` font family, warm `boxShadow`) lives in `tailwind.config.js` - the single source of truth. Keep it in sync with the `@font-face` / custom CSS in `base.html`.
- **Build:** `scripts/build-css.sh` (uses the standalone Tailwind CLI, no Node; downloads it to gitignored `bin/` on first run). Pass `--watch` during local dev.
- **Committed artifact:** `app/static/css/app.css` is committed so a fresh checkout + `uvicorn` (and the e2e suite) work with zero setup. **After editing templates/classes, rerun `scripts/build-css.sh`** so the committed CSS matches - otherwise new classes won't be styled locally.
- **Deploys** rebuild it automatically: the Dockerfile `cssbuild` stage runs the CLI against the templates and overwrites the committed copy, so `fly deploy` always ships a current, fully-purged stylesheet.
- **Purge caveat:** only classes that appear *literally* in `content` files (`app/templates/**/*.html`, `app/static/js/**/*.js`) survive. A class assembled by string concatenation in JS will be dropped - add such classes to `safelist` in `tailwind.config.js`.
- **Button system:** reusable button colour variants live in an `@layer components` block in `tailwind-input.css`: `.btn-primary` (accent), `.btn-secondary` (ink), `.btn-danger` / `.btn-danger-soft` (red), `.btn-info` (slate), `.btn-gold`, `.btn-ghost`, and `.btn-pip` (the square +/- stepper). Each centralizes only the colour/hover treatment; callers keep their own size/padding utilities (e.g. `class="btn-primary px-4 py-2 rounded text-sm font-medium"`). Use these for new buttons so a restyle stays one-touch. (Dropdown menu-items - `w-full text-left ... hover:bg-parchment` - are a separate pattern, not buttons.)
- **Dark mode** is a per-user opt-in (Profile > Appearance) and works **without per-element `dark:` variants**. The theme colours in `tailwind.config.js` resolve through CSS custom properties (`rgb(var(--color-ink) / <alpha-value>)`, etc.) defined for both `:root` (light) and `.dark` in `tailwind-input.css`. Tailwind is set to `darkMode: 'class'`; toggling the `dark` class on `<html>` flips every `bg-parchment`/`text-ink/60`/`bg-accent` (and opacity variants) at once. Three things the blanket variable-swap can't reach are patched by authored `.dark ...` rules at the bottom of `tailwind-input.css`: (1) **inverted/chrome surfaces** that must stay dark-with-light-text in both themes (the navbar via `.dark nav`, tooltips via `.dark .tooltip-content`, and an opt-in `.dark-surface` class on standalone dark menus/buttons) re-pin `--color-ink`/`--color-parchment` locally; (2) **modal scrims** (`bg-ink/60|80` on `fixed inset-0`) forced dark; (3) **`bg-white` cards** -> an elevated dark surface, plus the standard-Tailwind status palettes (red/amber/orange/rose banners) that don't flow through the theme variables. Hardcoded `rgba(44,24,16,…)` ink colours in `base.html`'s inline `<style>` were switched to `rgb(var(--color-ink) / …)` so they flip too. The `dark` class is server-rendered from `dark_mode_enabled(request)` (a Jinja global in `app/main.py`): the account preference (`User.preferences["dark_mode_enabled"]`, carried on `request.state.user` in a real session) is authoritative, with a `dark_mode` cookie fallback (set by `POST /profile`) for logged-out pages and the header-based test-auth bypass, whose synthetic user dict has no `preferences`. **When adding a new dark "chip"/menu/badge that uses `bg-ink text-parchment`, add the `dark-surface` class; when adding a banner in a non-theme palette, add a matching `.dark` override.**

## Running Tests

### Unit tests (fast, run constantly during development)

```bash
python3 -m pytest tests/ --ignore=tests/e2e -v                        # run unit tests
python3 -m pytest tests/ --ignore=tests/e2e --cov=app --cov-report=term-missing  # with coverage
```

Unit tests use an in-memory SQLite database and FastAPI's TestClient (via httpx). No external services needed.

### E2E clicktests (slower, run selectively by feature area)

```bash
python3 -m pytest tests/e2e/ -v --browser chromium                    # run ALL clicktests (~46 min)
python3 -m pytest tests/e2e/ -v --browser chromium -m tracking        # run by feature mark (~15 sec)
python3 -m pytest tests/e2e/ -v --browser chromium -m advantages      # another mark example
python3 -m pytest tests/e2e/ -v --browser chromium -m "skills or rings"  # combine marks
```

Clicktests start a live uvicorn server on a random port with a temp database, then drive headless Chromium via Playwright. Tests are tagged with `pytest.mark` by feature area. **When developing a feature, run only the relevant mark(s)** - not the full suite.

Available marks, which features they cover, and which test files they map to are all documented in `tests/e2e/COVERAGE.md` (the "Pytest Marks" section). Marks are defined in `pytest.ini`.

### JS unit tests (pure roll-math helpers)

Pure roll/engine math extracted from the sheet's Alpine layer lives in
`app/static/js/roll_math.js` (no DOM/Alpine deps; exposed as `window.L7RRollMath`
for the browser and `module.exports` for Node). It is unit-tested with Node's
built-in runner - no npm install, no framework, ~0.2s:

```bash
node --test tests/js/
```

**This MUST pass before any deploy** (see the Development Workflow / Deployment
sections). When you add or change school roll math, put the pure computation
(inputs -> number, side-effect free) in `roll_math.js` and assert it in
`tests/js/`, rather than inlining it in an Alpine `@click` handler where only a
slow browser clicktest can reach it. The Alpine layer keeps the *interaction*
(when to apply, accumulate, undo, optimistic display); the *arithmetic* lives in
`roll_math.js`. See `akodoBankedBonus` for the pattern.

### Coverage Policy

**Coverage must report 100%.** Either write a real test, or add `# pragma: no cover` with a one-line comment explaining why the line is untestable. The pragma forces the "why not" to be deliberate and visible in the diff, instead of hidden in a policy doc that drifts out of date.

Qualifying reasons for `# pragma: no cover` (look at the existing uses for examples):
- **Framework scaffolding overridden by tests** - e.g. `database.py:get_db()`, which the test fixture replaces with an in-memory engine. Testing the real body would just test SQLAlchemy's session lifecycle.
- **First-run-on-old-schema migration branches** - e.g. the `ALTER TABLE ADD COLUMN` paths in `_migrate_add_columns`. Tests use a fresh in-memory DB where `create_all` covers every column, so these branches never fire. Exercising them requires staging a pre-migration schema snapshot, which doesn't catch real bugs.
- **Import-time guards** that raise on malformed static data (e.g. the `SCHOOL_RING_OPTIONS` fallback in `game_data.py`). These fire only if someone mistypes the data at dev time.
- **Defensive `except: pass` blocks** where the failure is non-critical and the trigger is a contrived DB/service injection that doesn't model a real failure mode.

Do NOT use `# pragma: no cover` for:
- Error paths you haven't gotten around to testing (write the test).
- Rarely-hit branches that are still reachable (write the test).
- Permission checks, validation, or any code that guards a security/data-integrity invariant (write the test).

When adding new code, write tests that exercise all branches including error/edge cases (invalid inputs, boundary values, unknown IDs, permission denials). Prefer a real test over a pragma every time you have a choice.

## Development Workflow

New features follow this cycle:

1. **Write failing unit tests (TDD red).** Define the expected behavior in `tests/` before writing any implementation.
2. **Implement the feature.** Write the code to make the tests pass.
3. **Iterate until unit tests pass (TDD green).** Check coverage to ensure all new branches are covered.
4. **Update the clicktest coverage checklist.** Before writing code, add new lines to `tests/e2e/COVERAGE.md` for each interactive behavior the feature introduces (buttons, fields, toggles, conditional visibility, AJAX calls). Mark them `[ ]`. This makes missing coverage visible.
5. **Write clicktests for frontend changes (REQUIRED).** Any feature that touches templates, client-side JS, HTMX interactions, or user-facing workflows MUST have corresponding e2e tests in `tests/e2e/`. Clicktests validate that the full user flow works end-to-end in a real browser - things like AJAX handlers returning JSON instead of rendering a page, redirects landing on the right URL, and interactive UI state (overlays, disabled buttons, tooltips) behaving correctly. These catch bugs that unit tests cannot. Tag new tests with the appropriate `pytest.mark` for the feature area. After writing tests, mark the corresponding lines in `COVERAGE.md` as `[x]` with the test reference.
6. **Run relevant clicktests by mark.** Use `pytest -m <mark>` to run only the tests for the feature area you changed - not the full suite. Example: `pytest tests/e2e/ -m advantages --browser chromium`. Iterate until they pass.

The key distinction: unit tests use TDD (tests first), clicktests are written after the feature works. Clicktests are run selectively, not as part of every iteration loop. **Do not skip clicktests** - if a feature changes frontend behavior, it needs a clicktest. The coverage checklist in `tests/e2e/COVERAGE.md` is the source of truth for what's tested. **After writing clicktests, always update `tests/e2e/COVERAGE.md`** with entries for every new test function. This is required, not optional - every test must appear in COVERAGE.md.

7. **Deploy after UI changes.** Any change that touches the frontend (templates, CSS, client-side JS) should be deployed to Fly.io after tests pass so the live site stays current. **Before every deploy, `node --test tests/js/` MUST pass** (the pure roll-math layer, ~0.2s) - alongside the unit suite and the relevant clicktests.

**Do NOT auto-run the full e2e suite.** The full suite takes ~46 minutes on the dev container and is not part of the per-feature loop. Targeted clicktests by `pytest.mark` (step 6) are the only e2e gate before declaring a feature done. Only run the full suite when the user explicitly asks for it.

## Project Structure

```
app/
  main.py              - FastAPI app entry point, template + static config
  game_data.py         - All L7R rules as Python dataclasses (schools, skills, knacks, etc.)
  database.py          - SQLAlchemy engine, session, Base, get_db dependency
  models.py            - Character SQLAlchemy model
  services/xp.py       - XP calculation engine
  services/sheets.py   - Google Sheets spreadsheet building and formatting
  routes/pages.py      - Full HTML page routes (index, create, view, edit)
  routes/characters.py - Character CRUD + HTMX partial endpoints
  routes/google_sheets.py - Google OAuth2 flow + Sheets export
  templates/           - Jinja2 templates
tests/                 - Unit test suite (pytest)
tests/e2e/             - E2E clicktests (Playwright)
```

## L7R Rules

The canonical rules live in the `rules/` directory of the GM's `l7r` repo. When this project runs in its dev container that repo is bind-mounted at `/host-l7r-repo`, so read the rules directly from the local filesystem - e.g. `/host-l7r-repo/rules/04-schools.md` - which is faster and more reliable than fetching them over the network. If that mount is not present (e.g. someone outside the GM's setup cloned this repo), fall back to the public GitHub copy at https://github.com/EliAndrewC/l7r/tree/master/rules.

`app/game_data.py` encodes these rules as Python data structures. When rules change upstream, this file needs to be updated to match. The same is true for any campaign-specific supplemental rules; prefer the local container mount when it is available, with the public GitHub repos as the fallback.

## Key Architectural Decisions

- **XP calculation lives only in `services/xp.py` (single source of truth).** The editor no longer recomputes XP in Alpine; it POSTs its current state to `POST /characters/{id}/xp` (read-only, ~250ms debounced) and renders the returned `editor_xp_view()` payload - the footer figures (`spent`/`budget`/`remaining`), per-control "X XP spent" totals (`costs`), and the +/- tooltip marginal hints (`marginal`). The initial paint is seeded server-side via `xp_initial` in the edit route. The published sheet's XP breakdown is server-rendered separately via `calculate_xp_breakdown()`. Trade-off: live edit feedback lags an edit by the debounce + a tiny round-trip instead of being instant - the deliberate cost of removing the former client/server duplication.
- **TemplateResponse uses keyword arguments** (`request=`, `name=`, `context=`) - required by the installed Starlette version.
- **School selection uses `htmx.ajax()` called from Alpine.js** - not HTMX attributes on the select element. This is because the URL is dynamic (includes the school ID) and HTMX attribute-based triggers don't reliably fire from Alpine-managed elements.
- **School ring choice is stored explicitly** because some schools let the player choose their school ring (e.g. "any non-Void"). The `school_ring_choice` field records which ring was actually selected.
- **Knacks start at rank 1 for free** (given by the school). XP cost for knacks only applies for ranks above 1.
- **Dan = minimum school knack rank.** A character's Dan level equals the lowest rank among their three school knacks.
- **New model columns require a migration entry.** When adding a column to any SQLAlchemy model, you MUST also add it to `_migrate_add_columns()` in `database.py`. The production SQLite database on Fly.io persists across deploys - `create_all` only creates new tables, it does not add columns to existing ones. Tests won't catch this because they use a fresh in-memory database each run.
- **Character visibility (`Character.is_hidden`).** New characters created via POST /characters start with `is_hidden=True` so the creator can iterate before sharing. Hidden characters are filtered out of the index page list, return 404 from `GET /characters/{id}` for non-editors, and are stripped from party-effect data on other players' sheets - all gated by `can_view_drafts(viewer, owner, owner_grants)`. The flag is **bidirectional**: editors flip it back and forth via the visibility chip in the edit page header (POST `/characters/{id}/show` and `/hide`). Apply Changes does **not** auto-clear the flag; the modal renders an explicit "make visible" checkbox **only while the character is hidden**, and `publish_character(make_visible=True)` clears the flag if checked. The hidden-draft banner above Basics is always shipped in the markup (visibility is bidirectional, so server-side gating would be wrong) but Alpine's `isHidden` flag controls whether it actually paints. The visibility filter is asymmetric: a hidden character does not affect other party members' sheets (party-effect data is stripped for non-editor viewers), but other party members still affect the hidden character's own sheet.

- **Read-only Roll Mode design philosophy (non-editors on someone else's sheet).** Anyone with view access to a published character can interactively walk through every roll on that sheet — initiative, attacks, parries, wound checks, school abilities, posture choices, "spend VP for free raise", "use Lucky for a re-roll", consume conviction / worldliness / otherworldliness, etc. The dice roll, the modals advance through their phases, the result panels render with all the bonuses applied, the read-only banner is visible inside each result. The point is to let players test-drive a character — see what their rolls look like, feel out a school's mechanics — without having to be granted edit access first.

  The hard rule: **no action a non-editor takes can mutate the character's persisted state, AND the sheet's displayed counters must stay anchored to the persisted server values throughout the walk-through.** That means both DB persistence (via the `save()` shim) and local Alpine state are off-limits for non-editor mutations to bridge fields. A non-editor who "spends 2 VP for raises" sees the +10 reflected in the roll total but their VP counter on the sheet stays at the server value. A non-editor who "takes 1 serious wound" sees the modal accept the choice and close, but the sheet's LW/SW counts don't move. A non-editor who triggers a Mirumoto parry doesn't get the auto-granted +1 temp VP. A Lucky reroll for a non-editor doesn't flip `lucky_used`. Banked bonuses don't accumulate. Posture history doesn't extend. **Only an editor's actions update the sheet.**

  Implementation: the bridge (`window._trackingBridge`, defined by `trackingData()` in `app/templates/character/sheet.html`) carries `canEdit` from `viewer_can_edit`. The `save()`, `setCount()`, `setToggle()`, and `saveBankedBonuses()` methods on the bridge early-return for non-editors. Direct field mutations (`t.voidPoints--`, `t.tempVoidPoints += 1`, `t.akodoBankedBonuses.push(...)`, etc.) inside roll-modal handlers must be wrapped `if (t.canEdit) { ... }`; the surrounding modal-local state (`wcRollTotal += 5`, `baseTotal -= 5`, `wcPostRollVpSpent++`, etc.) stays unconditional so the modal still computes and displays the spend's effect on the roll. Tracking-section counter buttons (LW -, SW +/-, VP +/-, Temp Void +/-) are mostly hidden via `{% if viewer_can_edit %}`; LW - stays in the DOM but disabled to keep layout stable; LW + remains clickable and dispatches an event-detail `amount` to `openWoundCheckModal()` so the WC roll runs against the entered scenario amount without ever touching `lightWounds`. New code that handles roll/modal flow must follow this pattern; if you're adding a school ability that grants a temp VP on a roll's success, gate the grant on `t.canEdit`. **When in doubt, ask: "if a non-editor clicks this five times, does the sheet's displayed state change?" If yes, gate it.**

## Google Sheets Export

Users with edit access can export a character to a Google Sheet from the edit page. The "Google Sheets" dropdown in the sticky bottom bar has "Export to Google Sheets" and (if previously exported) "View in Google Sheets".

### How it works

The export uses a one-shot Google OAuth2 flow - no refresh tokens are stored. Each export requires the user to sign in with Google:

1. User clicks "Export to Google Sheets" on the edit page
2. `GET /auth/google/export/{char_id}` renders an HTML page that redirects to Google's consent screen (the page also pings `/auth/google/keepalive` every 5 seconds to prevent the Fly machine from auto-stopping)
3. User authorizes on Google's consent screen (scope: `drive.file` only)
4. Google redirects to `GET /auth/google/callback` with an auth code
5. Callback exchanges the code for an access token, loads the character, builds a 5-tab formatted spreadsheet via the Sheets REST API, and redirects back to the edit page with a success banner

### Key constraints

- **No `google-api-python-client` library.** It loads the full API discovery document into memory and OOMs on the 256MB Fly machine. Instead, `app/services/sheets.py` makes direct HTTP calls to `https://sheets.googleapis.com/v4/spreadsheets` using `httpx`.
- **No stored tokens.** The Google OAuth consent screen is in "testing" mode (avoids Google's $4,500+ verification process for restricted scopes). Refresh tokens expire after 7 days in testing mode, so we don't bother storing them - each export is a fresh OAuth round-trip.
- **Test users must be added manually** in the Google Cloud Console under APIs & Services > OAuth consent screen > Test users. Only listed emails can authorize.
- **`drive.file` scope only.** This restricts the app to files it created - it cannot see or modify the user's other Drive files. Do not add the `spreadsheets` scope (it grants access to all of a user's sheets).
- **Keepalive page.** The export entry point renders an HTML page (not a server-side redirect) that pings the server while the user is on Google's consent screen. This prevents Fly's `auto_stop_machines` from killing the machine before the callback arrives.

### Spreadsheet structure (5 tabs)

Each tab has its own column widths. Formatting uses `batchUpdate` with dark red (#8b0000) section headers, alternating row colors, and frozen title rows.

1. **Character Sheet** - identity, rings, derived stats, combat skills, knacks, status, techniques
2. **Skills** - grouped by category (social/knowledge, basic/advanced), with roll formulas
3. **Advantages & Disadvantages** - with detail text, campaign items marked
4. **XP Breakdown** - itemized spending per category with totals
5. **Notes** - rich-text sections stripped to plain text

### Future: update in place

`Character.google_sheet_id` stores the spreadsheet ID of the most recent export. This enables a future feature where re-exporting updates the existing sheet instead of creating a new one. The `drive.file` scope grants access to files the app previously created, so re-authenticating gives access to the old sheet.

## Character Import

Players can import an existing character sheet into the app rather than re-entering it by hand. The importer accepts almost any document format, extracts structured fields with Gemini, and produces a Draft the user reviews before clicking Apply Changes. The full design lives in `import-design/CLAUDE.md` (with an implementation-tracking checklist in `import-design/design.md`); this section is the production summary.

### How it works

1. From any logged-in page, the "New Character" nav dropdown offers "Import a character", which routes to `GET /import`.
2. The user uploads a file or pastes a URL (public Google Doc, public Google Sheet, or arbitrary HTTP(S) URL).
3. `POST /import` validates the request, enforces the per-user rate limit, and dispatches an async job in an in-memory worker (see `app/services/import_jobs.py`). The route redirects to `/import/progress/<id>` immediately.
4. The worker runs the full pipeline:
   - **Ingest** (`import_ingest.py`): libmagic-based format detection, per-format text extraction, PDF multimodal fallback flag.
   - **Fetch** (`import_url.py`): SSRF-hardened URL fetcher with DNS-resolve-and-check, Google Docs/Sheets export rewriting, private-doc redirect detection.
   - **Extract** (`import_llm.py`): Gemini structured-output call with flash-primary / pro-fallback logic, multimodal PDF path via `pypdfium2`.
   - **Resolve** (`import_match.py`, `import_validate.py`): fuzzy-match "as written" strings to canonical IDs, clamp numeric fields, split advantages into base-vs-campaign lists, cross-check school knacks.
   - **Reconcile** (`import_reconcile.py`): recompute XP via the existing engine, compare to source-stated totals, build the Import Notes section.
5. The progress page polls `/import/status/<id>` every 1.5s. On success the browser redirects to the Draft's edit page; on failure the progress page shows the error banner plus a retry link.
6. The edit page for the imported Draft shows an amber "This character was imported" banner that disappears after Apply Changes.

### Key constraints

- **1 MB upload cap.** Enforced before any extraction work. Character sheets are small documents; anything larger is almost certainly not one.
- **Multi-character documents are rejected**, not silently picked-from. The user is told to split the document.
- **Never stored.** The importer does not save a copy of the uploaded file or the fetched URL content anywhere - not on the persistent volume and not in S3 backups.
- **Character art is never imported**, even if embedded or linked in the source. Image handling is reserved for a separate future feature.
- **Public Google Docs / Sheets only.** We do not OAuth for import; the document must be shared "Anyone with the link". Private documents surface a dedicated instructions banner rather than a generic error.
- **XP is recomputed from stats, never trusted from the source.** Source-stated totals are compared and any discrepancy is flagged in Import Notes.
- **Drafts only.** The importer always saves `is_published=False`. The user must click Apply Changes to create the first version.

### Gemini model fallback

The pipeline calls `GEMINI_MODEL_PRIMARY` (default `gemini-2.5-flash`) first. If the extraction result looks too sparse (name and school both empty, OR every ring null, AND the model did not self-report `not_a_character_sheet=true`), the pipeline retries once with `GEMINI_MODEL_FALLBACK` (default `gemini-2.5-pro`). The Import Notes section records which model produced the final result and whether the fallback fired.

Per-field re-extraction (`extract_single_field`) is available as a primitive for future use; the current orchestrator relies on the main call + model-upgrade retry only.

### Rate limit + kill switch

- **Rate limit:** per-user, 10 successful imports per 24 hours. Counted by looking for characters owned by the user whose sections include the Import Notes label and whose `created_at` falls in the last 24 hours. No extra schema.
- **Kill switch:** `IMPORT_ENABLED` gates both the `/import` route (503 "temporarily unavailable" banner when off) AND the navbar's "New Character" dropdown (collapses to a single submit button with no Import option or `/import` link when off). **The default is `false` (fail-closed)** - a missing env var keeps the feature disabled so an incomplete .env or unset Fly secret can't silently re-enable it. Set `IMPORT_ENABLED=true` explicitly to turn it on. The flag is read at request time by both the route and the template, so toggling it doesn't require a restart. Test fixtures opt in: `tests/test_import_routes.py` has an autouse fixture that sets it true, and the clicktest live server in `tests/e2e/conftest.py` also sets it true.

### Env vars and Fly secrets

The pipeline reads these env vars. Production secrets go in Fly:

```bash
fly secrets set GEMINI_API_KEY="AIza..."
# Models are optional; set only if you want to override the defaults.
fly secrets set GEMINI_MODEL_PRIMARY="gemini-2.5-flash"
fly secrets set GEMINI_MODEL_FALLBACK="gemini-2.5-pro"
```

Everything else (`IMPORT_ENABLED`, `IMPORT_RATE_LIMIT_PER_DAY`, `IMPORT_MAX_UPLOAD_MB`, timeouts, PDF caps) has production-safe defaults and does not need to be set explicitly. See `.env.example` for the full list.

For local dev, the same vars go in `.env`. For e2e tests, the harness sets `IMPORT_USE_TEST_STUB=1` in the subprocess env; that short-circuits the real Gemini call in favour of canned responses based on document content markers. Never set that in production.

### Key architectural decisions

- **No `google-generativeai` SDK.** The pipeline makes direct `httpx` calls to `https://generativelanguage.googleapis.com/v1beta` - same pattern as `app/services/sheets.py` and for the same reason (SDK startup cost on a 256MB machine).
- **LLM output is schema-constrained.** Gemini's `responseMimeType: application/json` + `responseSchema` means the model physically cannot emit free-form text, function calls, or tool calls. This is the primary defense against prompt injection in source documents; the sanitizer layer is belt-and-braces.
- **Async worker, in-memory registry.** Jobs live in a process-local dict keyed by UUID, reaped 10 minutes after completion. Good enough for the current single-machine Fly deployment; would need a Redis-backed registry if we scaled past one machine.
- **"As written" strings stay raw through the LLM call.** The LLM returns `"name_as_written"` fields like `"Crane Duelist"`; Python fuzzy-matches against `game_data.py` in Phase 5. This keeps the LLM's context small and catalog drift out of the prompt.
- **No new DB schema.** The Import Notes section stores provenance and the rate-limit counter reads from the `sections` JSON column. A copy of the uploaded document is never persisted.

### Future work

- Per-field re-extraction driver (the primitive exists; no caller yet).
- Image-file direct imports (deferred to a separate workflow).
- `.sxw` (pre-fork OpenOffice) fixture (extractor code path exists; no real sample to test against - see `tests/import_fixtures/happy_path/DEFERRED.md`).
- Cross-machine job registry if we scale beyond one Fly machine.

## Style & Design Preferences

- **No em-dashes or en-dashes.** Use hyphens (`-`) everywhere - in templates, user-facing text, tooltips, and banners. Never use `&mdash;`, `&ndash;`, or the literal Unicode em/en-dash characters.
- **No external CDN dependencies.** All JavaScript and CSS libraries (Tailwind, Alpine, HTMX, Quill) are self-hosted in `/static/`. Do not add `<script>` or `<link>` tags pointing to CDN URLs. This avoids tracker warnings from browser privacy extensions.
- **Responsive design is required.** The site must look good and function correctly on both desktop and mobile. Use Tailwind's responsive prefixes (`sm:`, `md:`, `lg:`) for layout breakpoints. Tooltips use `@media (hover: none)` to show tap-friendly `?` indicators on touch devices. Navigation collapses to a hamburger on narrow screens. Labels use `truncate` to prevent overflow. Add responsive sanity-check tests (no horizontal overflow, no zero-width labels) when making layout changes.
- **JS error tests for both editor and sheet.** The sheet page has a parametrized JS error test across multiple schools (`test_sheet_js_errors.py`). The editor has its own (`test_editor_controls.py`). When adding Alpine expressions, use optional chaining (`?.`) for any property access that could be null during initial render. Use single-quote delimiters on Alpine attributes that contain Jinja `tojson` output (which produces double-quoted strings).
- **Low-effort automated sanity checks.** When making UI changes, look for cheap structural assertions: no horizontal overflow at phone width, no zero-width truncated elements, critical controls visible/hidden at expected breakpoints. Add these to `test_responsive.py`.

## School Features Inventory

The `school-features/` directory contains one .md file per school documenting:
- Implementation status of each ability (special ability, 1st-5th Dan techniques)
- How each ability is implemented in the codebase (which files, which functions)
- Which unit tests and clicktests cover each ability
- What's missing (unimplemented features, untested behaviors)
- Open questions about ambiguous rules

This inventory is the basis for future school-by-school implementation work. When implementing a school feature, update the corresponding .md file to reflect the new status.

## Deployment

**Pre-deploy gate:** `node --test tests/js/` (pure roll-math, ~0.2s) and the unit suite must pass, plus the relevant clicktests for anything you changed.

The Fly CLI is not pre-installed in the sandbox container. Install it and authenticate before deploying:

```bash
curl -L https://fly.io/install.sh | sh
export PATH="$HOME/.fly/bin:$PATH"
fly auth login                          # interactive login (requires browser or token)
fly deploy
```

Requires a persistent volume named `l7r_data` mounted at `/data`. The `DATABASE_URL` env var is set to `/data/l7r.db` in fly.toml. The VM is configured for 512MB RAM (shared CPU) to accommodate boto3 imports for the backup system.

`fly deploy` builds the multi-stage `Dockerfile`: the `cssbuild` stage compiles the purged Tailwind stylesheet (see "Styling / CSS build") and the runtime stage copies it in, so each deploy ships a stylesheet matching that deploy's templates - no manual CSS step. `.dockerignore` keeps `.env`, `.git`, `bin/`, and dev DBs out of the image.

## Database Backups

Automated S3 backups run on app startup via a background thread. The system:

- **Triggers on startup** if >= 20 hours since the last backup (checked via S3 listing)
- **Delays 30 seconds** after startup before importing boto3 to avoid memory pressure during Fly.io health checks
- **Uses SQLite backup API** (`connection.backup()`) for a consistent snapshot even during writes
- **Rolling retention**: 7 most recent (daily), 4 weekly, 12 monthly, yearly forever
- **Graceful failure**: if S3 is unreachable, the app starts normally and shows an admin-only banner

Key files:
- `app/services/backup.py` - S3 upload, retention logic, snapshot creation
- `app/main.py` - `_check_and_backup()` background thread, `backup_status` global, `get_backup_error()` template global
- `app/templates/base.html` - admin-only "backups offline" banner

S3 key format: `backups/l7r-YYYY-MM-DDTHH-MM-SSZ.db`. If `S3_BACKUP_BUCKET` is not set, backups are silently skipped (safe for local dev).

## Magic-Login URLs

Some pre-seeded users have a magic-login URL that bypasses Discord OAuth - the two non-admin test users ("Test User 1" and "Test User 2") and any campaign player who needs a backup login (e.g. someone whose Discord access is broken). Log in via:

```
https://l7r-character-sheet.fly.dev/auth/magic-login/<uuid>
```

(The legacy path `https://l7r-character-sheet.fly.dev/auth/test-login/<uuid>` still works as an alias.) The UUIDs are stored in the `MAGIC_LOGIN_TOKENS` Fly secret and in `.env` (one `<uuid>:<discord_id>` entry per user, comma-separated). The route pattern is public; only the UUID tokens are secret. Magic-login users keep whatever permission level their Discord ID has - test users are NOT admins, but a magic-login UUID for an admin's discord_id signs in WITH admin privileges, so treat the secret accordingly.

To add a new entry: generate a UUID (`python3 -c "import uuid; print(uuid.uuid4())"`), append `<uuid>:<discord_id>` to `MAGIC_LOGIN_TOKENS` in `.env`, and update the Fly secret (`fly secrets set MAGIC_LOGIN_TOKENS="..."`). The discord_id must already exist in the `users` table; pre-seeded campaign players (`CAMPAIGN_PLAYERS` in `app/game_data.py`) qualify automatically.
