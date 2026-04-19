"""E2E: JavaScript console-error sweep for every character-art page.

These tests don't assert on any specific behaviour; they navigate to
the art-related pages and fail if anything shows up on ``pageerror``
or ``console.error``. That's the cheap net that catches Alpine state
divergence, Cropper.js init problems, and the "image ``null`` during
initial render" class of bugs the plan called out for Phase 11.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character


pytestmark = pytest.mark.character_art

FIXTURES = Path(__file__).parent / "art"


def _collect_errors(page):
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: (
            errors.append(f"console.{msg.type}: {msg.text}")
            if msg.type == "error" else None
        ),
    )
    return errors


def _assert_no_errors(errors: list[str], page_label: str):
    # Filter out known-harmless network-level errors; we only care about
    # JS exceptions and logic-level console.error calls.
    # (Right now nothing needs filtering, but leave the hook in place.)
    filtered = [e for e in errors if e]
    assert filtered == [], (
        f"JavaScript errors on {page_label}:\n" + "\n".join(filtered)
    )


def _create_minimal_character(page, live_server_url, name: str) -> str:
    """Return the sheet URL for a fresh minimal character."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, f"Setup {name}")
    return page.url  # sheet URL


def _upload_art(page, sheet_url: str) -> None:
    """Upload + save the valid-portrait fixture so the character has art."""
    page.goto(sheet_url + "/art")
    page.set_input_files(
        'input[type="file"]', str(FIXTURES / "valid_portrait.png"),
    )
    page.locator('[data-action="upload-art"]').click()
    page.wait_for_url("**/art/crop/**")
    page.wait_for_function(
        "() => parseInt(document.querySelector('input[name=w]').value) > 0"
    )
    page.locator('[data-action="save-crop"]').click()
    page.wait_for_url("**/edit?art_saved=1")


# ---------------------------------------------------------------------------
# Art-adjacent pages that render even without any uploaded art yet
# ---------------------------------------------------------------------------


def test_art_landing_page_without_art_has_no_js_errors(page, live_server_url):
    sheet_url = _create_minimal_character(page, live_server_url, "LandingJS")
    errors = _collect_errors(page)
    page.goto(sheet_url + "/art")
    page.wait_for_selector('[data-testid="art-landing-page"]')
    page.wait_for_timeout(300)  # Let Alpine settle
    _assert_no_errors(errors, "art landing (no existing art)")


def test_generate_gender_page_has_no_js_errors(page, live_server_url):
    sheet_url = _create_minimal_character(page, live_server_url, "GenderJS")
    errors = _collect_errors(page)
    page.goto(sheet_url + "/art/generate")
    page.wait_for_selector('[data-testid="art-gen-gender-page"]')
    page.wait_for_timeout(300)
    _assert_no_errors(errors, "art generate step 1")


def test_generate_options_page_has_no_js_errors(page, live_server_url):
    sheet_url = _create_minimal_character(page, live_server_url, "OptionsJS")
    char_id = sheet_url.split("/characters/")[1]
    errors = _collect_errors(page)
    page.goto(
        f"{live_server_url}/characters/{char_id}/art/generate/options?gender=female"
    )
    page.wait_for_selector('[data-testid="art-gen-options-page"]')
    # Tick every optional row to force every Alpine binding to evaluate.
    page.locator('[data-testid="holding-checkbox"]').check()
    page.locator('[data-testid="expression-checkbox"]').check()
    page.locator('[data-testid="armor-checkbox"]').check()
    page.wait_for_timeout(300)
    _assert_no_errors(errors, "art generate step 2")


def test_generate_review_and_in_place_crop_have_no_js_errors(
    page, live_server_url,
):
    """Walk through Generate -> review -> generate (stubbed) -> Cropper
    init in place. The success transition changes the Alpine `state`
    from 'generating' to 'succeeded', swaps the DOM to include the
    Cropper wrapper, and wires an image load handler - all error-prone
    if a state guard is off by one."""
    sheet_url = _create_minimal_character(page, live_server_url, "ReviewJS")
    char_id = sheet_url.split("/characters/")[1]
    page.goto(
        f"{live_server_url}/characters/{char_id}/art/generate/options?gender=male"
    )
    page.wait_for_selector('[data-testid="age-input"]')
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")

    errors = _collect_errors(page)
    page.locator('[data-action="generate-art"]').click()
    page.wait_for_selector(
        '[data-testid="art-gen-crop-section"]',
        state="visible",
        timeout=10_000,
    )
    page.wait_for_selector('.cropper-container', timeout=5_000)
    page.wait_for_timeout(300)
    _assert_no_errors(errors, "art generate review + in-place Cropper")


# ---------------------------------------------------------------------------
# Pages that render differently once a character has art
# ---------------------------------------------------------------------------


def test_edit_page_with_art_has_no_js_errors(page, live_server_url):
    """Edit page with art present renders the dropdown, the
    overwrite-confirm modal (initially hidden via x-show), and the
    delete-art form - each with its own nested Alpine scope."""
    sheet_url = _create_minimal_character(page, live_server_url, "EditJS")
    _upload_art(page, sheet_url)
    errors = _collect_errors(page)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('[data-action="character-art-menu"]')
    page.locator('[data-action="character-art-menu"]').click()
    page.locator('[data-action="upload-new-art"]').click()
    # The overwrite modal should open without throwing
    page.wait_for_selector(
        '[data-testid="art-overwrite-modal"]', state="visible",
    )
    page.wait_for_timeout(300)
    _assert_no_errors(errors, "edit page (with art) + overwrite modal")


def test_sheet_page_with_art_has_no_js_errors(page, live_server_url):
    sheet_url = _create_minimal_character(page, live_server_url, "SheetJS")
    _upload_art(page, sheet_url)
    errors = _collect_errors(page)
    page.goto(sheet_url)
    page.wait_for_selector('[data-testid="sheet-art-grid"]')
    page.wait_for_timeout(500)
    _assert_no_errors(errors, "sheet page (with art grid)")


def test_index_page_with_mixed_art_has_no_js_errors(page, live_server_url):
    """Index page renders one card with a real headshot img and one
    with the placeholder. Both code paths must be quiet."""
    with_art = _create_minimal_character(page, live_server_url, "IndexWithArt")
    _upload_art(page, with_art)
    _create_minimal_character(page, live_server_url, "IndexNoArt")
    errors = _collect_errors(page)
    page.goto(live_server_url)
    page.wait_for_selector('[data-testid="character-headshot"]')
    page.wait_for_selector('[data-testid="character-headshot-placeholder"]')
    page.wait_for_timeout(300)
    _assert_no_errors(errors, "index (with + without art)")
