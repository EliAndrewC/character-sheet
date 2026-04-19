# Character Art Implementation Plan

Add character art (uploaded or AI-generated) with a headshot selector, display on the character list and sheet pages, and S3-backed persistence.

Because this is a big feature, the plan is broken into small phases that can each ship and be tested on their own. Each phase has its own unit-test bar and its own clicktests. Every phase ends with a green `pytest -m <marks>` before moving on.

**Clicktest scope during this effort:** run only the targeted clicktests for the phase being worked on - the specific new tests added in that phase plus any directly related existing tests (e.g. the school-selection suite for Phase 1, the `school_abilities` mark for later phases). Do NOT run the full e2e suite between phases. The full suite is deferred until Phase 11 (post-deploy), per `CLAUDE.md` step 8.


---

## Goals & scope

- Users can upload a PNG / JPG / WEBP image as character art (max 1 per character, overwrites replace the prior art).
- Users can alternatively generate art with a Gemini image model using a mad-libs prompt builder.
- Users select a headshot crop from the art; we store the cropped headshot as a separate image so the list page shows all characters at identical pixel dimensions.
- The list page shows the small headshot next to each character.
- The View Sheet page floats the full art next to the school section; responsive rules push the art to the next row when the screen is too narrow.
- Art files live in S3 (next to the database backups). The latest art-per-character is kept; orphaned art keys are deleted.
- All new frontend flows have clicktests; Gemini image calls are stubbed in tests.

Non-goals for this pass:
- More than one piece of art per character (deferred).
- Public sharing of art URLs outside the app.
- Art moderation / NSFW filtering.
- Editing a previously-saved headshot crop without re-running the whole flow.

---

## Phase 1 - Planning artifacts & scaffolding

**Goal:** land everything we need *before* writing feature code so that missing pieces are visible as we go.

1. Add a new `## Character Art` section to `tests/e2e/COVERAGE.md` populated with the full clicktest checklist below (all `[ ]`). Every subsequent phase flips its own boxes to `[x]`. The checklist is in Appendix A of this document; copy it verbatim.
2. Add a new pytest mark `character_art` in `pytest.ini` with a one-line description (matches the existing pattern for other marks in that file).
3. Create two fixture directories, each with a `README.md` that states its purpose and naming convention:
   - **`tests/e2e/art/`** - sample image files that Playwright uploads during the Phase 4 clicktests (e.g. `small_valid.png`, `valid.jpg`, `valid.webp`, `too_large.png`, `wrong_ratio_banner.jpg`, `not_an_image.txt`). Naming: `<case>.<ext>` where `<case>` describes the scenario the test exercises. These are real bytes, committed to the repo, kept under 100 KB each so the repo doesn't bloat.
   - **`tests/import_fixtures/art/`** - unit-test fixtures for the non-browser code paths. Two subtrees:
     - face-detect fixtures (`portrait_clear_face.jpg`, `abstract_no_face.png`, `very_small_face.jpg`) with optional sibling `<case>.expected.json` files carrying the expected bbox plus tolerance.
     - `stub_outputs/` - canned PNGs returned by the Phase 8 generation stub, keyed by prompt-keyword (`wasp.png`, `scorpion.png`, `fallback.png`).
   The READMEs exist so future maintainers know which directory to drop a new fixture in without rereading this plan.

**Tests:** none yet (this phase only adds empty directories, two READMEs, one `pytest.ini` line, and one section to `COVERAGE.md`).

---

## Phase 2 - Data model & S3 storage primitives

**Goal:** a `Character` that can *carry* art metadata and a storage layer that can put/get/delete art in S3. No UI yet.

1. Add columns to `Character` in `app/models.py`:
   - `art_s3_key: str | None` - full-size art (e.g., `character_art/<char_id>/full-<timestamp>.webp`).
   - `headshot_s3_key: str | None` - cropped headshot (e.g., `character_art/<char_id>/head-<timestamp>.webp`).
   - `art_updated_at: datetime | None` - used for cache-busting and orphan cleanup.
   - `art_source: str | None` - `"upload"` or `"generated"`, for Import Notes-style provenance.
   - `art_prompt: str | None` - the final Gemini prompt (null for uploads).
2. Add matching `ALTER TABLE` entries to `database.py::_migrate_add_columns` so the Fly volume DB picks them up on next deploy. Mark the ALTER branches with `# pragma: no cover` (same convention as existing migration paths).
3. Create `app/services/art_storage.py`:
   - `upload_art(char_id, full_bytes, headshot_bytes) -> (full_key, head_key)` - writes both, returns S3 keys.
   - `delete_art(*keys)` - deletes by key.
   - `presigned_url(key, ttl_seconds=900) -> str` - for `<img src>` display.
   - `list_orphaned_keys(known_keys: set[str]) -> list[str]` - listed under the art prefix but not in the known set.
   - Reuses the existing `S3_BACKUP_BUCKET` with a new `S3_CHARACTER_ART_PREFIX` env var (default `character_art/`). No new bucket.
   - Objects are uploaded with `ACL=public-read` (or the bucket is configured so presigned URLs are not required) so the art is viewable by anyone - logged-in or not. See Phase 5/6 notes on the image-URL strategy.
4. Create `app/services/art_image.py`:
   - `validate_upload(data: bytes, content_type: str) -> ValidatedImage` - checks magic bytes, decodes with Pillow, enforces size/ratio constraints (see "Image constraints" below).
   - `encode_for_storage(img: PIL.Image, kind: Literal["full", "headshot"]) -> bytes` - re-encodes to WebP at a known quality (removes EXIF + embedded thumbnails).
   - `build_headshot(img: PIL.Image, crop_box: tuple[int, int, int, int]) -> bytes` - crops and resizes to the fixed headshot dimensions.
5. Constants (in `app/services/art_image.py`):
   - `MAX_UPLOAD_BYTES = 5 * 1024 * 1024` (5 MB).
   - `MIN_DIMENSION_PX = 256` (shortest side).
   - `MAX_DIMENSION_PX = 4096` (longest side).
   - `MIN_ASPECT_RATIO = 0.5` (1:2 tall) and `MAX_ASPECT_RATIO = 2.0` (2:1 wide). Conservative defaults - the common-on-the-web range is about 1:2 to 2:1 (Instagram is 4:5 to 1.91:1, Twitter header is 3:1 which we exclude deliberately).
   - `HEADSHOT_SIZE = (180, 240)` - 3:4 portrait rectangle (width:height). This matches how faces sit in a photo better than a square.
   - `HEADSHOT_ASPECT_RATIO = 3 / 4` - used by the face-detect and cropper to lock the crop box.
   - `FULL_ART_MAX_EDGE = 1024` - we downscale for display.
6. Unit tests (`tests/test_art_image.py`, `tests/test_art_storage.py`):
   - Accepts PNG, JPG, WEBP bytes with the right magic bytes; rejects GIF / BMP / SVG / HTML.
   - Rejects too-small, too-large, too-tall, too-wide images with specific error codes.
   - Decodes EXIF-rotated JPEGs upright (Pillow's `ImageOps.exif_transpose`).
   - `build_headshot` produces exactly `HEADSHOT_SIZE` regardless of input size.
   - `art_storage.upload_art` / `delete_art` / `list_orphaned_keys` mocked via `botocore.stub.Stubber`, same pattern as existing `tests/test_backup.py`.

---

## Phase 3 - Face detection

**Goal:** a service that takes image bytes and returns a default face bbox, with a hard-coded fallback when nothing is detected.

Approach: **OpenCV Haar cascades** running locally on CPU.
- No extra API calls, no new credentials.
- OpenCV headless (`opencv-python-headless`) is ~35 MB and loads lazily - acceptable on a 512 MB Fly machine if we import inside the function like the backup module does with boto3.
- Accuracy is good enough for "seed the cropper default"; the user always has the final say.

1. Create `app/services/art_face_detect.py`:
   - Lazy-imports `cv2` inside `detect_face()` so the cold start of unrelated routes isn't hit.
   - Loads the OpenCV-bundled Haar cascade XML once at first call and caches it.
   - `detect_face(img: PIL.Image, aspect_ratio: float = HEADSHOT_ASPECT_RATIO) -> tuple[int, int, int, int]`:
     - Runs the cascade, picks the highest-confidence face.
     - Expands the returned bbox to match the target aspect ratio (3:4 portrait for headshots), keeping the face centered horizontally and biased slightly upward vertically so the forehead isn't chopped off.
     - If no face found or the expanded bbox would exceed image bounds, returns a fallback bbox (the largest centered 3:4 rectangle capped at image size).
2. Add `opencv-python-headless` to `requirements.txt`.
3. Unit tests (`tests/test_art_face_detect.py`):
   - Fixture images in `tests/import_fixtures/art/`:
     - `portrait_clear_face.jpg` - detects a face; expected bbox in `.expected.json` with a generous tolerance (+/- 20 px).
     - `abstract_no_face.png` - no detection; fallback centered 3:4 rectangle is returned.
     - `very_small_face.jpg` - detected but expanded bbox would exceed bounds; fallback fires.
   - Test that aspect-ratio coercion produces exactly 3:4 within 1 px tolerance.

**Decision on fixtures:** we will commit small (<100 KB) Creative-Commons / CC0 photos. If we can't find suitable ones the user has offered to share real campaign art; ask in the thread when we get here.

---

## Phase 4 - Upload flow (no AI yet)

**Goal:** end-to-end upload + crop + save, ignoring AI generation. This is the foundation that Phase 7/8 will reuse.

**Drafts-vs-Published note:** character art is metadata, not stats. Saving / replacing / deleting art updates the published Character row directly and **never** puts the character into Draft status. If a character has an active Draft for stats changes, editing the art leaves the Draft untouched and applies only to the published row. This is enforced at the route layer: the art endpoints write to the published Character regardless of Draft state, and they do not check or branch on `is_published`.

1. Add `Cropper.js` (`cropperjs`) to `/static/vendor/cropperjs/` (self-hosted per our CDN rule). MIT-licensed, ~40 KB gzipped.
2. Route: `GET /characters/{id}/art` - landing page that shows the current art (if any) plus "Upload new art" and "Generate with AI" buttons.
3. Route: `POST /characters/{id}/art/upload` - multipart file, runs `validate_upload`, stashes the decoded bytes in a short-lived server-side session slot keyed by `art_staging_id` (UUID, 15 min TTL; same in-memory registry pattern as `import_jobs.py`). Redirects to the crop page.
4. Route: `GET /characters/{id}/art/crop/{staging_id}` - Cropper.js UI. Renders the staged full image, seeds the crop box with `detect_face()`'s bbox, locks the aspect ratio to 3:4 portrait, minimum crop size enforced. "Save" and "Cancel" buttons.
5. Route: `POST /characters/{id}/art/crop/{staging_id}` - receives `{x, y, w, h}`, runs `build_headshot`, then `upload_art`. Deletes the previous `art_s3_key` + `headshot_s3_key` if set. Updates the published Character row (not any Draft). Redirects back to the edit page with a success banner (query param, same pattern as Google Sheets export).
6. Route: `POST /characters/{id}/art/delete` - deletes both S3 keys, nulls the columns on the published Character. Protected by a confirmation modal.
7. Overwrite warning: when the user clicks "Upload new art" and the character already has art, open a confirm modal with a thumbnail of the current headshot and text: "This will replace the current art, which cannot be undone." Only proceed after confirm.
8. Permissions: reuse the existing edit-permission check (`app/services/auth.py::require_edit_access`). Only users who can edit the character can change its art.
9. Unit tests: route tests for all five endpoints, including 403 for unauthorized users, 413 for oversized uploads, and 422 for wrong aspect ratios. Add a test proving an art change does NOT flip `is_published` and does NOT create a Draft. Coverage must stay 100%.
10. Clicktests (in `tests/e2e/test_character_art_upload.py`, marked `character_art`):
    - See Appendix A items 1-12.

---

## Phase 5 - Display on index (list) page

**Goal:** characters that have a headshot show one; characters that don't show a neutral placeholder.

1. Modify `app/templates/index.html` character cards to include `<img src="{{ headshot_url(char) }}" class="w-[60px] h-20 rounded-md object-cover">` (3:4 portrait at 60x80 px) on the left of the text block. Characters with no headshot get a CSS-only silhouette placeholder at the same dimensions.
2. Template helper `headshot_url(char)` in `app/main.py` (registered as a Jinja global) returns the public S3 URL, cached per-request. Because the art bucket objects are public-read, no signing is required and the URL can be cached indefinitely (cache-busted by `art_updated_at`).
3. **Public visibility:** art URLs work for everyone, logged-in or not. Do not gate the `<img>` rendering on authentication. This matches the overall policy that character art is public.
4. Responsive check: at `sm:` the card is full-width with the headshot still visible; at the smallest mobile widths the card remains legible. Add to `test_responsive.py`.
5. Clicktest: see Appendix A items 13-15.

---

## Phase 6 - Display on View Sheet page

**Goal:** full art floats right of the school section on wide screens; stacks below on narrow ones.

1. Modify the top section in `app/templates/character/sheet.html`. Wrap the school/techniques block and the art in a `lg:grid lg:grid-cols-2 lg:gap-6` container (art on the right, school/techniques on the left). On widths below `lg`, the grid collapses to a single column and **the art appears above the school block** (the art is visually heavier and reads as the primary element on mobile).
2. If the character has no art, the column collapses and the school block reverts to full width.
3. Add a responsive sanity test in `tests/e2e/test_responsive.py`: no horizontal overflow at 375 px (phone), 768 px (tablet), 1280 px (desktop).
4. Clicktest: see Appendix A items 16-18.

---

## Phase 7 - Mad-libs prompt builder UI

**Goal:** the multi-step wizard that produces a Gemini prompt. No real Gemini call yet - the final step just shows the assembled prompt.

### UI flow (per Eli's spec)

**Step 1: gender.** Radio buttons Male / Female. "Continue" navigates to step 2. The gender choice drives all the `He` / `She` substitutions on the next page.

**Step 2: mad-libs layout.** The whole prompt is *laid out* on the page. The top and bottom are **fixed, non-editable text blocks**; the middle is a stack of checkbox rows where ticking a checkbox adds that sentence to the prompt.

Clan selector: a dropdown of every `CLAN_COLORS` key sits above the fixed prefix. Defaults to **Wasp** (this is the Wasp campaign, and a Wasp-clan character often trained at another clan's school, so auto-detecting from the character's school would be wrong more often than right). The prefix text reflects the current selection live via Alpine.

Fixed prefix (non-editable display text):
> **A portrait of a {clan} clan noble wearing {clan_colors}.**

Middle rows (each is a checkbox + template sentence):
- **`[x]` {He/She} is approximately `<age>` years old.** Mandatory. The checkbox is pre-checked and disabled so it can't be unchecked. The age input is a number field, **min 15, max 55, default 20**.
- **`[ ]` {He/She} is holding `<text>`.** Optional. The text input is disabled when the checkbox is unchecked; when checked, the input is enabled and **required** (the form won't submit with an empty holding text).
- **`[ ]` {He/She} has a `<text>` expression.** Same required-when-checked rule as above.
- **`[ ]` {He/She} `<dropdown>` `<optional text>`.** The dropdown has exactly **two** choices: `"is not wearing armor and has on a kimono"` and `"is wearing samurai armor"`. The trailing text is a free-form modifier that may be left blank (e.g. "ornate", "muted").

Fixed suffix (non-editable display text):
> **Make a colored, photo-realistic portrait painting in the style of a traditional Japanese period portrait. Natural lighting, neutral background, full face visible. No text, no watermark, no signature.**

For **female** characters, the assembled prompt always appends the fixed sentence **"Completely unstyled hair and no makeup."** after the suffix. This is not surfaced in the UI - it's enforced server-side - because exposing it as a toggle invites the "geisha problem" where the model over-stylises female faces with heavy makeup and styled hair.

"Create Prompt" button at the bottom of the page submits the form.

**Step 3: review + generate.** Single view with the assembled prompt in an editable `<textarea>` plus a "Generate Art" button. Clicking Generate Art locks the textarea (`:disabled` via Alpine) while Phase 8's job runs; on success the generated image appears **in the same view** alongside a Cropper.js widget and a "Save" button. On failure the textarea unlocks so the user can tweak the prompt and retry. (See Phase 8 for the generation + in-place crop wiring.)

### Routes

1. `GET  /characters/{id}/art/generate`                            - step 1 (gender radio)
2. `GET  /characters/{id}/art/generate/options?gender=…`           - step 2 (mad-libs)
3. `POST /characters/{id}/art/generate/assemble`                   - step 2 → step 3; builds prompt, stages it, redirects
4. `GET  /characters/{id}/art/generate/review/{staging_id}`        - step 3 (textarea + generate)
5. `POST /characters/{id}/art/generate/submit/{staging_id}`        - kicks off the Phase 8 job (501 stub in Phase 7)

### Clan colors map

Add a `CLAN_COLORS` dict to `app/game_data.py`:

```python
CLAN_COLORS = {
    'Crab': 'dark blue and light gray',
    'Crane': 'light blue and white / silver',
    'Dragon': 'gold and dark green',
    'Lion': 'yellow and brown',
    'Phoenix': 'red and orange',
    'Scorpion': 'black and dark red',
    'Unicorn': 'purple and white with gold trim',
    'Imperial': 'dark green with gold trim and fine chrysanthemum embroidery',
    'Sparrow': 'dun brown and black',
    'Fox': 'green and silver',
    'Wasp': 'black and gold',
    'Dragonfly': 'blue, brown, and gold',
    'Hare': 'red and white',
}
```

Order in the dropdown matches the order of this dict. The selector default is `'Wasp'`.

### Access + tests

**Access:** any user with edit access on a character can open the "Generate with AI" flow. There is no admin-only gate (the rate limit in Phase 8 is the cost-control mechanism).

**Clicktests:** Appendix A items 19-27. The test stub (Phase 8) must be in place to exercise step 4+, but steps 1-3 can be tested without any real API.

---

## Phase 8 - Gemini image generation

**Goal:** real Gemini call; stubbed in tests.

1. Create `app/services/art_generate.py`:
   - Direct `httpx` POST to the Imagen image-generation endpoint (same pattern as `import_llm.py`). Model configurable via `GEMINI_ART_MODEL` env var, **default `imagen-4.0-generate-001`** (the model Eli has had good results with using these prompts on other projects). Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict`.
   - Timeout, retry-once on 5xx/429, typed exceptions `ImageGenerationError` / `ImageRateLimitError` / `ImageTransportError`.
   - Returns raw PNG bytes; we pipe them through `validate_upload` (same validator as uploads) so generated images inherit the same ratio/size checks.
2. Add an async job registry similar to `import_jobs.py` (can be a trimmed-down copy, or extract a small shared helper - my lean is to copy rather than abstract, since jobs-for-art and jobs-for-import have different payloads).
3. **Same-page generation + crop flow** (per Eli's spec): the review page stays on screen during generation. The "Generate Art" submit locks the `<textarea>` via Alpine, kicks off the job, and begins polling `/art/generate/status/{job_id}` every ~1.5 s.
   - While the job is running: textarea is disabled, a "Generating..." indicator is shown next to the button, the Generate button is disabled.
   - On success: the page loads the generated image into a Cropper.js widget **in the same view**. A "Save Headshot" button (reusing Phase 4's crop-save endpoint semantics) commits the crop and writes to the Character row.
   - On failure: the textarea unlocks, an error banner appears with the error code (rate-limit / transport / API / invalid), and the Generate button re-enables so the user can tweak and retry. The staged prompt is preserved across retries.
4. The crop endpoint that the "Save Headshot" button hits is `POST /characters/{id}/art/crop/{staging_id}` (the same one Phase 4 already has). The Phase 8 worker fills the bytes into the same staging slot via `update_staged_bytes`, so the crop flow never sees whether the bytes came from an upload or a generation.
6. Test stub: `ART_GEN_USE_TEST_STUB=1` env var. When set, `art_generate.py` skips the HTTP call and returns one of three canned images from `tests/import_fixtures/art/stub_outputs/` based on keywords in the prompt ("wasp" -> black-and-gold, "scorpion" -> red-and-black, fallback -> neutral portrait). E2E conftest sets this env var in the uvicorn subprocess the same way it sets `IMPORT_USE_TEST_STUB`.
7. Rate limit: **25 generations per user per 24 hours** (same counting method as the importer's rate limiter, tuned higher per Eli's direction). Implemented in a thin wrapper that counts recent `art_source="generated"` updates per user. Kill switch: `ART_GEN_ENABLED` env var.
8. Unit tests:
   - Mocked `httpx` responses for success / 429 / 500 / malformed-JSON.
   - Stub mode returns the expected canned image per prompt keyword.
   - Rate limit blocks the 26th call.
9. Clicktests: Appendix A items 22-27 (from Phase 7, actually exercised end-to-end now that the stub is live).

---

## Phase 9 - S3 backup integration & orphan cleanup

**Goal:** art is in S3; deleted / overwritten art is pruned; a full backup restore gets every user's current art.

1. The `upload_art` / `delete_art` primitives from Phase 2 already live in S3. That gives us per-write backup "for free."
2. Add `app/services/art_backup.py::cleanup_orphans()`:
   - Lists all keys under the art prefix.
   - Loads every `Character.art_s3_key` and `headshot_s3_key` from the DB.
   - Deletes S3 keys not referenced by any character.
3. Wire into the existing startup-backup thread in `app/main.py::_check_and_backup()`: after the DB snapshot, call `cleanup_orphans()`. The whole thing runs in the same backgrounded thread with the existing ~30 s startup delay (mirrors the DB backup pattern - avoids memory pressure during Fly.io health checks). Failures are logged and surfaced through the same admin-only banner as backup failures.
4. When a character is hard-deleted (the existing delete route), also call `delete_art` for its keys. Because art lives on the published Character row (not Drafts), there is no separate "discard draft art" path to worry about - see Phase 4's Drafts-vs-Published note.
5. Unit tests for `cleanup_orphans` using `botocore.stub.Stubber` + a mocked DB.

---

## Phase 10 - Character-art clicktests

**Goal:** bring the `character_art` mark from empty to fully exercising the feature end-to-end in a real browser. Phases 4-9 deferred every e2e test, annotating each COVERAGE.md item with its unit-test reference - that unit coverage keeps the server honest but doesn't catch the class of bugs clicktests exist for (AJAX handlers returning the wrong content type, Alpine state divergence, redirects landing on the wrong URL, interactive overlay timing).

**Pragmatism:** we do NOT write one clicktest per checklist line. Where the difference between items is one the unit tests already nail (PNG vs JPG vs WEBP format; every individual clan; every specific aspect-ratio rejection), one golden-path clicktest suffices. Where a checklist item is inherently not browser-visible (S3 key lifecycle), it gets marked `[-]` with a reason rather than pretending it's pending.

### Implementation steps

1. **E2E harness env vars.** Update `tests/e2e/conftest.py` to set `ART_GEN_ENABLED=true` and `ART_GEN_USE_TEST_STUB=1` in the uvicorn subprocess, mirroring the `IMPORT_USE_TEST_STUB` pattern. This lets the generation clicktests drive the real wizard without touching Imagen.
2. **Edit-page kill-switch gate.** The "Generate with AI" link must render as a disabled-with-tooltip entry when `ART_GEN_ENABLED=false` (Appendix A item 32). Currently it's always a live link. Plumb `art_gen_enabled` as a Jinja global and update `character/edit.html` accordingly.
3. **`tests/e2e/test_character_art_upload.py`** (mark: `character_art`). Covers:
   - "Character Art" dropdown visible on edit page, Upload link goes to landing
   - Upload landing rejects wrong-format file and rejects wrong aspect ratio (one rejection test, not one per error - unit tests cover the per-error copy)
   - Happy path: upload a valid PNG, land on crop page, assert Cropper initialised with the detected bbox, save, land on edit page with success banner
   - Delete art via the dropdown modal, return to edit page with the deleted banner
   - Overwrite modal appears when uploading a replacement
4. **`tests/e2e/test_character_art_display.py`** (mark: `character_art`). Covers:
   - List page: a character with art shows the img; one without shows the placeholder (two characters on the same page)
   - Sheet page at `lg` width: the art grid is present when the character has art
   - Sheet page when character has no art: no grid, school section full-width
5. **`tests/e2e/test_character_art_generate.py`** (mark: `character_art`). Covers:
   - Click "Generate with AI" from edit dropdown -> step 1 page
   - Step 1 -> step 2 carries the selected gender; Alpine `subject` pronoun is "He" or "She"
   - Age checkbox is visually disabled (cannot be unchecked in the UI)
   - Checking an optional row enables its text input; unchecking disables it
   - Click "Create Prompt" -> step 3 shows the assembled prompt in a textarea
   - Click "Generate Art" -> textarea locks, status indicator shows; stub returns image; Cropper appears in-place; Save button commits to character
   - Force a failure by setting the rate-limit to 0: banner appears, textarea re-enables, button label becomes "Try Again"
   - Kill-switch: with `ART_GEN_ENABLED=false`, the dropdown entry renders disabled
6. **Re-mark COVERAGE.md.** Replace `[ ]` with `[x] -> <test_file>::<test_fn>` for items a clicktest now covers; use `[-]` with a short reason for items the plan decided unit-tests-only.
7. **Run `pytest -m character_art` until green.** Don't run the full suite - that's Phase 11.

### Out of scope for Phase 10

- JS-error regression tests for the art pages (moved to Phase 11)
- Phase-10-level responsive assertions beyond what's already in `test_responsive.py`
- Deploy + background full-suite kickoff (Phase 11)

---

## Phase 11 - Polish, deploy, background clicktest run

**Goal:** ship it.

1. Add JS-error tests to `test_sheet_js_errors.py` and `test_editor_controls.py` for the new art-related Alpine state (image `null` branches, missing crop box, etc.).
2. Deploy to Fly.io (UI change).
3. Kick off the full clicktest suite in the background; report done without blocking on the result (per CLAUDE.md workflow step 8).

---

## Image constraints - summary

These are the numbers a reviewer will ask about. Gathered in one place:

| Constraint | Value | Why |
|---|---|---|
| Accepted formats | PNG, JPG, WEBP | Common web formats; others aren't worth the fuss |
| Max upload size | 5 MB | Character art isn't phone-camera-raw; 5 MB fits detailed 1024x1024 PNGs with headroom |
| Min dimension | 256 px (shortest side) | Smaller than this looks bad as a headshot |
| Max dimension | 4096 px (longest side) | Keeps Pillow memory bounded on 512 MB Fly |
| Min aspect ratio | 0.5 (1:2) | Rejects pathological tall strips |
| Max aspect ratio | 2.0 (2:1) | Rejects pathological wide banners |
| Headshot size | 180x240 px (3:4 portrait) | Fixed so the list page is uniform; 3:4 matches where faces sit in a photo better than a square |
| Full-art display max edge | 1024 px | Re-encoded at upload time; saves bandwidth |
| Stored format | WEBP, quality 85 | Smaller than JPEG at comparable quality; Pillow handles it natively |
| Per-user generation rate | 25 / 24 h | Higher than importer; set per Eli's direction |

---

## Appendix A - Clicktest checklist

The full checklist lives in **`tests/e2e/COVERAGE.md`** under the `## Character Art` section - that is the living source of truth, updated as each phase lands. Phase 1 seeded it from this appendix; subsequent phases flipped its boxes to `[x]` (real clicktest landed) or `[-]` (explicitly unit-tested-only, with a reason) as work completed.

The original 33-item template used to live here verbatim; it was removed once the live doc diverged (a few row wordings were updated in Phase 7/8 to match Eli's "same-page generation + crop" spec) to avoid two sources drifting apart. Consult `tests/e2e/COVERAGE.md` for current status.
