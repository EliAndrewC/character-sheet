# Character Art - unit-test fixtures

Fixtures for the non-browser code paths of the character-art feature. Two subtrees:

## Face-detect fixtures (this directory)

Images exercised by `tests/test_art_face_detect.py`:

- `portrait_clear_face.jpg` - detects a face; used to assert the bbox is within tolerance of the expected value.
- `abstract_no_face.png` - nothing to detect; used to assert the fallback (centered 3:4 rectangle) kicks in.
- `very_small_face.jpg` - detected face too small for the target aspect ratio to fit inside the image bounds; used to assert the fallback kicks in.

Each fixture may be paired with a sibling `<case>.expected.json` file of the form:

```json
{
  "bbox": [x, y, w, h],
  "tolerance_px": 20
}
```

Tests read the expected bbox plus tolerance and assert the detector's output falls within that box. Leave `expected.json` absent for cases where the assertion is "no face detected" / "fallback used".

Sources should be CC0 / Creative Commons; keep each image under 100 KB.

## `stub_outputs/`

Canned PNGs returned by the Phase 8 Gemini generation stub when `ART_GEN_USE_TEST_STUB=1` is set. The stub picks one based on keywords in the assembled prompt:

- `wasp.png` - returned when the prompt mentions Wasp clan / black and gold
- `scorpion.png` - returned when the prompt mentions Scorpion clan / black and dark red
- `fallback.png` - returned for any other prompt

Each stub output must itself pass the Phase 2 `validate_upload` checks (format, size, aspect ratio) because the generation pipeline runs generated images through the same validator as uploads.

---

This directory is for **unit-test fixtures only**. Sample upload files for Playwright clicktests live in `tests/e2e/art/` instead.
