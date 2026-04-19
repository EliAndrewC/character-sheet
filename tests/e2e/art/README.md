# Character Art - e2e upload fixtures

Sample image files that Playwright clicktests upload through the `/characters/{id}/art/upload` flow.

## Naming convention

`<case>.<ext>` where `<case>` describes the scenario the test exercises:

- `small_valid.png`, `valid.jpg`, `valid.webp` - happy-path uploads for each accepted format
- `too_large.png` - oversized file used to exercise the 5 MB rejection path
- `wrong_ratio_banner.jpg` - aspect ratio outside `[0.5, 2.0]`; exercises the ratio rejection
- `not_an_image.txt` - wrong magic bytes; exercises the content-type rejection

## Constraints

- Keep each fixture **under 100 KB** (except `too_large.png`, whose whole point is exceeding 5 MB; that one is generated inside the test setup rather than committed - do NOT commit a 5 MB file).
- Real image bytes, not stubs. These files are uploaded to a live uvicorn subprocess and must pass or fail validation for the reason the test asserts.

This directory is for **Playwright upload inputs only**. Unit-test fixtures for face detection and for the generation stub live in `tests/import_fixtures/art/` instead.
