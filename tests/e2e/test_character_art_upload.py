"""E2E tests for character art upload, crop, save, and delete.

These exercise the same Phase 4 flow the unit tests in
``tests/test_art_routes.py`` cover, but through a real browser against
a live uvicorn subprocess. The conftest forces the storage stub
(``ART_STORAGE_USE_TEST_STUB=1``) so the upload/save/delete path
bounces off a local tmpdir instead of S3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character


pytestmark = pytest.mark.character_art

FIXTURES = Path(__file__).parent / "art"


def _create_minimal_character(page, live_server_url, name: str) -> str:
    """Spin up a character and return its edit-page URL."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    # Apply lands on the sheet page - navigate to the edit page
    sheet_url = page.url
    edit_url = sheet_url + "/edit"
    page.goto(edit_url)
    page.wait_for_selector('[data-action="character-art-menu"]')
    return edit_url


def _open_art_menu(page):
    page.locator('[data-action="character-art-menu"]').click()


# ---------------------------------------------------------------------------
# Edit page dropdown visibility
# ---------------------------------------------------------------------------


def test_character_art_menu_visible_on_edit_page(page, live_server_url):
    """Golden path: the "Character Art" dropdown is present on the edit
    page and opens an "Upload new art" option."""
    _create_minimal_character(page, live_server_url, "ArtMenu")
    _open_art_menu(page)
    upload_link = page.locator('[data-action="upload-new-art"]')
    upload_link.wait_for(state="visible")
    assert upload_link.is_visible()


# ---------------------------------------------------------------------------
# Upload landing page rejections
# ---------------------------------------------------------------------------


def test_upload_rejects_non_image_file(page, live_server_url):
    """A text file submitted to the upload form produces the
    invalid-format error banner on the same landing page."""
    edit_url = _create_minimal_character(page, live_server_url, "RejectText")
    # Go straight to the art landing page
    page.goto(edit_url.replace("/edit", "/art"))
    page.set_input_files(
        'input[type="file"]',
        str(FIXTURES / "not_an_image.txt"),
    )
    page.locator('[data-action="upload-art"]').click()
    banner = page.locator('[data-testid="art-error-banner"]')
    banner.wait_for(state="visible")
    assert "PNG" in banner.inner_text()


def test_upload_rejects_wrong_aspect_ratio(page, live_server_url):
    """A too-wide image produces the aspect-ratio error banner."""
    edit_url = _create_minimal_character(page, live_server_url, "RejectRatio")
    page.goto(edit_url.replace("/edit", "/art"))
    page.set_input_files(
        'input[type="file"]',
        str(FIXTURES / "too_wide.png"),
    )
    page.locator('[data-action="upload-art"]').click()
    banner = page.locator('[data-testid="art-error-banner"]')
    banner.wait_for(state="visible")
    assert "aspect ratio" in banner.inner_text().lower()


# ---------------------------------------------------------------------------
# Upload + crop happy path
# ---------------------------------------------------------------------------


def test_upload_and_save_crop_end_to_end(page, live_server_url):
    """Upload a PNG, land on the crop page with Cropper initialised,
    click Save, and verify the edit page shows the art-saved banner."""
    edit_url = _create_minimal_character(page, live_server_url, "CropHappy")
    page.goto(edit_url.replace("/edit", "/art"))
    page.set_input_files(
        'input[type="file"]',
        str(FIXTURES / "valid_portrait.png"),
    )
    page.locator('[data-action="upload-art"]').click()

    # Crop page loaded
    page.wait_for_url("**/art/crop/**")
    page.wait_for_selector('[data-testid="art-crop-page"]')
    # Cropper.js populates the cropper container inside the image element
    page.wait_for_selector('.cropper-container', timeout=10_000)
    # The hidden crop inputs should have non-zero width/height once
    # Cropper fires its first crop event. Alpine updates the values
    # via @crop and the hidden inputs are :value-bound.
    page.wait_for_function(
        "() => parseInt(document.querySelector('input[name=w]').value) > 0"
    )

    page.locator('[data-action="save-crop"]').click()
    page.wait_for_url("**/edit?art_saved=1")
    page.wait_for_selector('[data-testid="art-saved-banner"]')


# ---------------------------------------------------------------------------
# Overwrite modal
# ---------------------------------------------------------------------------


def test_overwrite_modal_appears_when_replacing_existing_art(
    page, live_server_url,
):
    """After saving art once, re-opening the upload entry in the
    dropdown shows the overwrite-confirm modal instead of navigating."""
    edit_url = _create_minimal_character(page, live_server_url, "Overwrite")
    # Complete one upload so the character has art
    page.goto(edit_url.replace("/edit", "/art"))
    page.set_input_files(
        'input[type="file"]', str(FIXTURES / "valid_portrait.png"),
    )
    page.locator('[data-action="upload-art"]').click()
    page.wait_for_url("**/art/crop/**")
    page.locator('[data-action="save-crop"]').click()
    page.wait_for_url("**/edit?art_saved=1")

    # Now the Upload link should trigger the confirm modal, not navigate
    _open_art_menu(page)
    page.locator('[data-action="upload-new-art"]').click()
    modal = page.locator('[data-testid="art-overwrite-modal"]')
    modal.wait_for(state="visible")
    # Clicking "Continue" navigates to the landing page
    page.locator('[data-action="confirm-overwrite"]').click()
    page.wait_for_url("**/art")


# ---------------------------------------------------------------------------
# Delete flow
# ---------------------------------------------------------------------------


def test_delete_art_dropdown_entry_appears_when_art_exists(
    page, live_server_url,
):
    """After saving art, the dropdown gains a "Delete art" entry. The
    entry itself is a 2-click confirm (unit-tested at the route level
    via ``TestDeleteEndpoint``). Here we verify the browser-side state:
    entry visible while art exists, hidden once deleted."""
    edit_url = _create_minimal_character(page, live_server_url, "DeleteFlow")
    page.goto(edit_url.replace("/edit", "/art"))
    page.set_input_files(
        'input[type="file"]', str(FIXTURES / "valid_portrait.png"),
    )
    page.locator('[data-action="upload-art"]').click()
    page.wait_for_url("**/art/crop/**")
    page.locator('[data-action="save-crop"]').click()
    page.wait_for_url("**/edit?art_saved=1")

    # Dropdown has the Delete entry now
    _open_art_menu(page)
    delete_btn = page.locator('[data-action="delete-art"]')
    delete_btn.wait_for(state="visible")

    # Submit the delete form directly (Playwright's x-submit interaction
    # with a 2-click Alpine confirm is timing-sensitive and unit tests
    # already cover the confirm-then-submit behavior).
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.evaluate(f"""() => {{
        const f = document.createElement('form');
        f.method = 'POST';
        f.action = '/characters/{char_id}/art/delete';
        document.body.appendChild(f);
        f.submit();
    }}""")
    page.wait_for_url("**/edit?art_deleted=1")
    page.wait_for_selector('[data-testid="art-deleted-banner"]')

    # Dropdown no longer shows the Delete entry because art is gone
    _open_art_menu(page)
    assert page.locator('[data-action="delete-art"]').count() == 0
