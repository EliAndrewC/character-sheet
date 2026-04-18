# Character Art Implementation Plan

Add character art (uploaded or AI-generated) with a headshot selector, display on the character list and sheet pages, and S3-backed persistence.

Because this is a big feature, the plan is broken into small phases that can each ship and be tested on their own. Each phase has its own unit-test bar and its own clicktests. Every phase ends with a green `pytest -m <marks>` before moving on.

Open questions for the user live at the bottom in "Open Questions" - please answer those before we begin Phase 2 (some answers change the design of later phases).

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
2. Add a new pytest mark `character_art` in `pytest.ini`.
3. Add `art/` subdirectory under `tests/e2e/` and a matching `tests/import_fixtures/art/` directory (the latter for unit-test fixtures). Add a short `README.md` explaining the fixture naming convention (`<case>.png` / `<case>.jpg`, optional `<case>.expected.json` with detected-face bbox).
4. Add a `school-features/` note? No - this doesn't belong there; it's not school-specific.

**Tests:** none yet (this phase only adds empty files and one section to COVERAGE.md).

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
   - Reuses the same bucket as backups via a new `S3_CHARACTER_ART_PREFIX` env var (default `character_art/`). No new bucket needed unless the user wants one (see Open Questions).
4. Create `app/services/art_image.py`:
   - `validate_upload(data: bytes, content_type: str) -> ValidatedImage` - checks magic bytes, decodes with Pillow, enforces size/ratio constraints (see "Image constraints" below).
   - `encode_for_storage(img: PIL.Image, kind: Literal["full", "headshot"]) -> bytes` - re-encodes to WebP at a known quality (removes EXIF + embedded thumbnails).
   - `build_headshot(img: PIL.Image, crop_box: tuple[int, int, int, int]) -> bytes` - crops and resizes to the fixed headshot dimensions.
5. Constants (in `app/services/art_image.py`):
   - `MAX_UPLOAD_BYTES = 5 * 1024 * 1024` (5 MB).
   - `MIN_DIMENSION_PX = 256` (shortest side).
   - `MAX_DIMENSION_PX = 4096` (longest side).
   - `MIN_ASPECT_RATIO = 0.5` (1:2 tall) and `MAX_ASPECT_RATIO = 2.0` (2:1 wide). Conservative defaults - the common-on-the-web range is about 1:2 to 2:1 (Instagram is 4:5 to 1.91:1, Twitter header is 3:1 which we exclude deliberately).
   - `HEADSHOT_SIZE = (200, 200)` - square. See Open Questions about whether to match a portrait ratio instead.
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

We have two reasonable options. Flagged as an Open Question, but my recommendation is to start with **OpenCV Haar cascades** because:
- It runs locally on CPU, no extra API calls, no new credentials.
- OpenCV headless (`opencv-python-headless`) is ~35 MB and loads lazily - acceptable on a 512 MB Fly machine if we import inside the function like the backup module does with boto3.
- Accuracy is good enough for "seed the cropper default"; the user always has the final say.

The alternative is calling Gemini Vision with a bbox-return prompt. That saves the dependency but adds a second API hop per upload and ties face detection to our Gemini budget.

1. Create `app/services/art_face_detect.py`:
   - Lazy-imports `cv2` inside `detect_face()` so the cold start of unrelated routes isn't hit.
   - Loads the OpenCV-bundled Haar cascade XML once at first call and caches it.
   - `detect_face(img: PIL.Image, aspect_ratio: float) -> tuple[int, int, int, int]`:
     - Runs the cascade, picks the highest-confidence face.
     - Expands the returned bbox to match the target aspect ratio (typically 1:1 for headshots), keeping the face centered.
     - If no face found or the expanded bbox would exceed image bounds, returns a fallback bbox (the largest centered square capped at image size).
2. Add `opencv-python-headless` to `requirements.txt`.
3. Unit tests (`tests/test_art_face_detect.py`):
   - Fixture images in `tests/import_fixtures/art/`:
     - `portrait_clear_face.jpg` - detects a face; expected bbox in `.expected.json` with a generous tolerance (+/- 20 px).
     - `abstract_no_face.png` - no detection; fallback centered-square is returned.
     - `very_small_face.jpg` - detected but expanded bbox would exceed bounds; fallback fires.
   - Test that aspect-ratio coercion produces the exact target ratio within 1 px tolerance.

**Decision on fixtures:** we will commit small (<100 KB) Creative-Commons / CC0 photos. If we can't find suitable ones the user has offered to share real campaign art; ask in the thread when we get here.

---

## Phase 4 - Upload flow (no AI yet)

**Goal:** end-to-end upload + crop + save, ignoring AI generation. This is the foundation that Phase 7/8 will reuse.

1. Add `Cropper.js` (`cropperjs`) to `/static/vendor/cropperjs/` (self-hosted per our CDN rule). MIT-licensed, ~40 KB gzipped.
2. Route: `GET /characters/{id}/art` - landing page that shows the current art (if any) plus "Upload new art" and "Generate with AI" buttons.
3. Route: `POST /characters/{id}/art/upload` - multipart file, runs `validate_upload`, stashes the decoded bytes in a short-lived server-side session slot keyed by `art_staging_id` (UUID, 15 min TTL; same in-memory registry pattern as `import_jobs.py`). Redirects to the crop page.
4. Route: `GET /characters/{id}/art/crop/{staging_id}` - Cropper.js UI. Renders the staged full image, seeds the crop box with `detect_face()`'s bbox, locks the aspect ratio to the headshot ratio, minimum crop size enforced. "Save" and "Cancel" buttons.
5. Route: `POST /characters/{id}/art/crop/{staging_id}` - receives `{x, y, w, h}`, runs `build_headshot`, then `upload_art`. Deletes the previous `art_s3_key` + `headshot_s3_key` if set. Updates the Character row. Redirects back to the edit page with a success banner (query param, same pattern as Google Sheets export).
6. Route: `POST /characters/{id}/art/delete` - deletes both S3 keys, nulls the columns. Protected by a confirmation modal.
7. Overwrite warning: when the user clicks "Upload new art" and the character already has art, open a confirm modal with a thumbnail of the current headshot and text: "This will replace the current art, which cannot be undone." Only proceed after confirm.
8. Permissions: reuse the existing edit-permission check (`app/services/auth.py::require_edit_access`). Only users who can edit the character can change its art.
9. Unit tests: route tests for all five endpoints, including 403 for unauthorized users, 413 for oversized uploads, and 422 for wrong aspect ratios. Coverage must stay 100%.
10. Clicktests (in `tests/e2e/test_character_art_upload.py`, marked `character_art`):
    - See Appendix A items 1-12.

---

## Phase 5 - Display on index (list) page

**Goal:** characters that have a headshot show one; characters that don't show a neutral placeholder.

1. Modify `app/templates/index.html` character cards to include `<img src="{{ headshot_url(char) }}" class="w-16 h-16 rounded-md object-cover">` on the left of the text block. Characters with no headshot get a CSS-only silhouette placeholder.
2. Template helper `headshot_url(char)` in `app/main.py` (registered as a Jinja global) returns the presigned URL, cached per-request.
3. Responsive check: at `sm:` the card is full-width with the headshot still visible; at the smallest mobile widths the card remains legible. Add to `test_responsive.py`.
4. Clicktest: see Appendix A items 13-15.

---

## Phase 6 - Display on View Sheet page

**Goal:** full art floats right of the school section on wide screens; stacks below on narrow ones.

1. Modify the top section in `app/templates/character/sheet.html`. Wrap the school/techniques block and the art in a `lg:grid lg:grid-cols-2 lg:gap-6` container (art on the right, school/techniques on the left). On widths below `lg`, the grid collapses to a single column and the art appears above the school block (or below - TBD, see Open Questions).
2. If the character has no art, the column collapses and the school block reverts to full width.
3. Add a responsive sanity test in `tests/e2e/test_responsive.py`: no horizontal overflow at 375 px (phone), 768 px (tablet), 1280 px (desktop).
4. Clicktest: see Appendix A items 16-18.

---

## Phase 7 - Mad-libs prompt builder UI

**Goal:** the multi-step wizard that produces a Gemini prompt. No real Gemini call yet - the final step just shows the assembled prompt.

1. Route: `GET /characters/{id}/art/generate` - step 1, gender selection (radio: Male / Female; controls the pronoun).
2. Route: `GET /characters/{id}/art/generate/options` - step 2, mad-libs form (Alpine-driven, no HTMX):
   - Mandatory age checkbox (pre-checked, cannot be unchecked), numeric input min=15 max=55, default 30.
   - Optional "is holding" text input.
   - Optional "expression" text input.
   - Optional "armor/kimono" dropdown + free-text modifier.
   - Fixed prefix: "A portrait of a <clan/school> <noble>. <He/She> is wearing their <clan colors>." - we pre-fill clan colors from `game_data.py` if the school has them; otherwise the user can edit the prefix in step 3.
   - Fixed suffix: the "Make a colored, photo-realistic..." block from the user's instructions.
   - For female characters we always append "completely unstyled hair and no makeup" to the suffix. This is not user-editable to avoid regenerating the geisha problem by accident.
3. Route: `POST /characters/{id}/art/generate/assemble` - takes the form, produces the final prompt, stores it in the staging slot, redirects to step 3.
4. Route: `GET /characters/{id}/art/generate/review` - step 3, textarea pre-filled with the assembled prompt + "Generate Art" button + a "Back" button. Textarea editable.
5. Route: `POST /characters/{id}/art/generate/submit` - kicks off the generation job (Phase 8) and redirects to the generation-progress page.
6. Clicktests: Appendix A items 19-27. The test stub (Phase 8) must be in place to exercise step 4+, but step 1-3 can be tested without any real API.

**Tech note:** prefix pre-fill reads the character's school + clan from `game_data.py`. If a school doesn't have canonical "clan colors", we skip that clause and leave the prefix generic. This lookup is pure-Python, no new state.

---

## Phase 8 - Gemini image generation

**Goal:** real Gemini call; stubbed in tests.

1. Create `app/services/art_generate.py`:
   - Direct `httpx` POST to the Gemini image endpoint (same pattern as `import_llm.py`). Model configurable via `GEMINI_ART_MODEL` env var, default `gemini-2.5-flash-image-preview` (Google's current multimodal image output model). If the user's API key uses Imagen instead, we can swap the endpoint - this is an Open Question.
   - Timeout, retry-once on 5xx/429, typed exceptions `ImageGenerationError` / `ImageRateLimitError` / `ImageTransportError`.
   - Returns raw PNG bytes; we pipe them through `validate_upload` (same validator as uploads) so generated images inherit the same ratio/size checks.
2. Add an async job registry similar to `import_jobs.py` (can be a trimmed-down copy, or extract a small shared helper - my lean is to copy rather than abstract, since jobs-for-art and jobs-for-import have different payloads).
3. Kickoff route from Phase 7 step 5 creates a job, returns the job ID, redirects to `GET /characters/{id}/art/generate/progress/{job_id}`.
4. Progress page polls `/characters/{id}/art/generate/status/{job_id}` every 1.5 s. On success it redirects to the crop page (reusing Phase 4's Cropper.js view, with a bit of adjusted copy because the user may also want to re-generate rather than save).
5. On failure the progress page shows the error and a "Try again" link that goes back to step 3 with the prompt preserved.
6. Test stub: `ART_GEN_USE_TEST_STUB=1` env var. When set, `art_generate.py` skips the HTTP call and returns one of three canned images from `tests/import_fixtures/art/stub_outputs/` based on keywords in the prompt ("wasp" -> black-and-gold, "scorpion" -> red-and-black, fallback -> neutral portrait). E2E conftest sets this env var in the uvicorn subprocess the same way it sets `IMPORT_USE_TEST_STUB`.
7. Rate limit: 10 generations per user per 24 hours (same limit and same counting method as the importer's rate limiter). Implemented in a thin wrapper that counts recent `art_source="generated"` updates per user. Kill switch: `ART_GEN_ENABLED` env var.
8. Unit tests:
   - Mocked `httpx` responses for success / 429 / 500 / malformed-JSON.
   - Stub mode returns the expected canned image per prompt keyword.
   - Rate limit blocks the 11th call.
9. Clicktests: Appendix A items 22-27 (from Phase 7, actually exercised end-to-end now that the stub is live).

---

## Phase 9 - S3 backup integration & orphan cleanup

**Goal:** art is in S3; deleted / overwritten art is pruned; a full backup restore gets every user's current art.

1. The `upload_art` / `delete_art` primitives from Phase 2 already live in S3. That gives us per-write backup "for free."
2. Add `app/services/art_backup.py::cleanup_orphans()`:
   - Lists all keys under the art prefix.
   - Loads every `Character.art_s3_key` and `headshot_s3_key` from the DB.
   - Deletes S3 keys not referenced by any character.
3. Wire into the existing startup-backup thread in `app/main.py::_check_and_backup()`: after the DB snapshot, call `cleanup_orphans()`. Failures are logged and surfaced through the same admin-only banner as backup failures.
4. When a character is hard-deleted (the existing delete route), also call `delete_art` for its keys. Drafts that are discarded via Apply Changes should keep their art since the art stays tied to the published character.
5. Unit tests for `cleanup_orphans` using `botocore.stub.Stubber` + a mocked DB.

---

## Phase 10 - Polish, deploy, background clicktest run

**Goal:** ship it.

1. Add JS-error tests to `test_sheet_js_errors.py` and `test_editor_controls.py` for the new art-related Alpine state (image `null` branches, missing crop box, etc.).
2. Add responsive sanity assertions to `test_responsive.py` covering both the list-page headshots and the sheet-page art float.
3. Deploy to Fly.io (UI change).
4. Kick off the full clicktest suite in the background; report done without blocking on the result (per CLAUDE.md workflow step 8).

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
| Headshot size | 200x200 px square | Fixed so the list page is uniform. See Open Questions |
| Full-art display max edge | 1024 px | Re-encoded at upload time; saves bandwidth |
| Stored format | WEBP, quality 85 | Smaller than JPEG at comparable quality; Pillow handles it natively |
| Per-user generation rate | 10 / 24 h | Mirrors importer |

---

## Open Questions (please answer before Phase 2)

1. **S3 bucket/prefix:** OK to reuse the existing `S3_BACKUP_BUCKET` with a `character_art/` prefix, or do you want a dedicated bucket (e.g., `l7r-character-art`)? Separate buckets are cleaner but more infra to manage.

Eli's answer: same S3 bucket is fine

2. **Face detection approach:** OpenCV Haar cascades locally, or a Gemini Vision bbox call? OpenCV adds ~35 MB to the image; Gemini adds per-upload latency + API cost.

OpenCV Haar sounds fine

3. **Headshot aspect ratio:** 1:1 square (my default in this plan), or a portrait ratio like 4:5 or 3:4 that better matches where a face sits in a photo?



4. **Narrow-screen stack order on View Sheet:** when the layout collapses, should the full art appear *above* the school section or *below* it? I'm defaulting to above (it's visually heavier and reads as "primary"), but "below" keeps the important mechanics at the top.
5. **Public visibility:** the index page shows characters to logged-in users. Are those characters (and therefore their art) visible to *any* logged-in user, or scoped to campaign/group membership? That affects whether we need per-character presigned URLs vs a single signed-cookie trick.
6. **Gemini image model choice:** `gemini-2.5-flash-image-preview` is the default in this plan. If your key uses Imagen 3 / Imagen 4 instead, the endpoint and request shape differ - please confirm which model you'd like and we'll lock that in.
7. **Clan colors table:** the prefix "wearing their <clan colors>" is only automated if we map school/clan -> color pair. Do you want us to hand-enter those colors in a new table in `game_data.py`, or always leave the prefix's color clause for the user to fill in on step 3?
8. **Age default:** should the age number-input pre-fill with anything (e.g., 30), or start blank requiring the user to type a value?
9. **Rate-limit parity:** 10 AI generations per user per 24 hours (matching the importer) - is that the right cap, or do you want tighter/looser?
10. **Who sees the "Generate with AI" button:** everyone with edit access, or only admins/GMs? This is a cost-control question, not a feature-access one.
11. **When to cleanup orphans:** every startup (current plan), only on a dedicated cron, or after every art change? Startup is the simplest and matches the DB backup cadence.
12. **Keeping a Drafts-vs-Published art distinction:** when a user clicks Apply Changes and a new version is published, does the art carry over to the published version (yes, I think), and does editing the art in a Draft leave the published art untouched until Apply (also yes, I think)? Confirm so we can implement this correctly the first time.

---

## Appendix A - Full clicktest checklist (copy to COVERAGE.md in Phase 1)

Add a new `## Character Art` section to `tests/e2e/COVERAGE.md` with these lines, all `[ ]`. Mark them as tests land.

```
## Character Art

- [ ] "Upload new art" button visible on edit page for users with edit access
- [ ] "Upload new art" button hidden for users without edit access
- [ ] Upload rejects non-image file with clear error banner
- [ ] Upload rejects oversized file (> 5 MB) with clear error banner
- [ ] Upload rejects image outside allowed aspect ratio with clear error banner
- [ ] Upload of valid PNG redirects to crop page
- [ ] Upload of valid JPG redirects to crop page
- [ ] Upload of valid WEBP redirects to crop page
- [ ] Crop page seeds the crop box from detected face bbox
- [ ] Crop page falls back to centered-square when no face detected
- [ ] Crop page enforces locked aspect ratio during drag
- [ ] Save-crop writes full + headshot, redirects back to edit page with success banner
- [ ] Overwrite confirm modal appears when replacing existing art
- [ ] Delete-art confirm modal removes art and reverts to placeholder
- [ ] Character list page shows headshot for characters that have art
- [ ] Character list page shows placeholder for characters without art
- [ ] Character list page does not overflow horizontally at 375 px viewport
- [ ] View Sheet floats full art to the right of the school section at >= lg breakpoint
- [ ] View Sheet stacks full art and school section below lg breakpoint
- [ ] View Sheet omits art block for characters without art (no empty column)
- [ ] "Generate with AI" button opens step 1 (gender)
- [ ] Step 1 -> step 2 carries gender forward; pronouns are correct
- [ ] Step 2 age checkbox cannot be unchecked
- [ ] Step 2 optional rows disable their text input until the checkbox is checked
- [ ] Step 2 "Create Prompt" assembles the prompt and advances to step 3
- [ ] Step 3 textarea is editable before "Generate Art" is clicked
- [ ] Step 3 textarea locks while generation is in flight; unlocks on success or failure
- [ ] Successful generation redirects to the crop page with the generated art
- [ ] Failed generation shows a retry link that preserves the prompt
- [ ] Generation stub returns the expected canned image based on prompt keyword (smoke check)
- [ ] Per-user rate limit blocks the 11th generation in 24 h with a clear banner
- [ ] ART_GEN_ENABLED=false disables the "Generate with AI" button with a disabled-state tooltip
- [ ] Deleting the character also removes its S3 art keys (checked via orphan cleanup)
```
