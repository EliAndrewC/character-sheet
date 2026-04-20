"""E2E tests for character-art display on the list and sheet pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character


pytestmark = pytest.mark.character_art

FIXTURES = Path(__file__).parent / "art"


def _create_character(page, live_server_url, name: str) -> str:
    """Create a minimal published character and return its sheet URL."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    return page.url  # sheet URL


def _upload_and_save_art(page, sheet_url: str) -> None:
    """From a sheet URL, upload + crop-save a portrait so the character has art."""
    page.goto(sheet_url + "/edit")
    page.locator('[data-action="character-art-menu"]').wait_for()
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
# List page
# ---------------------------------------------------------------------------


def test_list_page_shows_headshot_for_character_with_art(page, live_server_url):
    """The index page's character card uses the real headshot img once
    art is saved; the placeholder silhouette disappears for that card."""
    # Use unique names so this test's assertions can scope to its own
    # cards even when the index has leftover characters from earlier
    # tests in the same session (the live server uses one DB per session).
    name_with = "HasArtList"
    name_without = "NoArtList"
    sheet_with = _create_character(page, live_server_url, name_with)
    _upload_and_save_art(page, sheet_with)
    _create_character(page, live_server_url, name_without)

    page.goto(live_server_url)
    # Locate the two specific cards by character name (h2 inside the card).
    card_with = page.locator(f'a:has(h2:text-is("{name_with}"))')
    card_without = page.locator(f'a:has(h2:text-is("{name_without}"))')
    assert card_with.count() == 1
    assert card_without.count() == 1
    # The "with art" card has the real img and no placeholder.
    assert card_with.locator('[data-testid="character-headshot"]').count() == 1
    assert card_with.locator('[data-testid="character-headshot-placeholder"]').count() == 0
    # The "no art" card has the placeholder and no real img.
    assert card_without.locator('[data-testid="character-headshot-placeholder"]').count() == 1
    assert card_without.locator('[data-testid="character-headshot"]').count() == 0

    # The rendered img has a non-zero natural size once loaded
    headshot = card_with.locator('[data-testid="character-headshot"]')
    headshot.wait_for()
    page.wait_for_function(
        "el => el.complete && el.naturalWidth > 0",
        arg=headshot.element_handle(),
        timeout=5000,
    )


# ---------------------------------------------------------------------------
# Sheet page
# ---------------------------------------------------------------------------


def test_sheet_page_shows_art_grid_when_character_has_art(
    page, live_server_url,
):
    """When the character has art, the sheet page renders the grid
    wrapper and the character-full-art img. Without art, neither exists."""
    with_art = _create_character(page, live_server_url, "GridArt")
    _upload_and_save_art(page, with_art)

    page.goto(with_art)
    page.wait_for_selector('[data-testid="sheet-art-grid"]')
    page.wait_for_selector('[data-testid="character-full-art"] img')


def test_sheet_page_hides_art_grid_when_character_has_no_art(
    page, live_server_url,
):
    no_art = _create_character(page, live_server_url, "NoGrid")
    page.goto(no_art)
    # School section still rendered
    page.wait_for_selector('h1')
    # Art grid + full-art are absent
    assert page.locator('[data-testid="sheet-art-grid"]').count() == 0
    assert page.locator('[data-testid="character-full-art"]').count() == 0


def test_sheet_art_height_matches_left_column(page, live_server_url):
    """At lg+ widths the art fills the grid cell so its bottom lines up with
    the bottom of the School+Rings stack on the left. Before this layout
    tweak, the art overhung Rings by hundreds of pixels."""
    page.set_viewport_size({"width": 1280, "height": 900})
    with_art = _create_character(page, live_server_url, "ArtHeightAlign")
    _upload_and_save_art(page, with_art)
    page.goto(with_art)
    page.wait_for_selector('[data-testid="sheet-art-grid"]')
    page.wait_for_selector('[data-testid="character-full-art"] img')
    # Wait for the image to load so its rendered height is real.
    page.wait_for_function(
        "() => { const i = document.querySelector('[data-testid=\"character-full-art\"] img');"
        " return i && i.complete && i.naturalWidth > 0; }"
    )
    gap = page.evaluate("""() => {
        const art = document.querySelector('[data-testid="character-full-art"]');
        const grid = document.querySelector('[data-testid="sheet-art-grid"]');
        // The left content column is the non-art direct child of the grid.
        const left = [...grid.children].find(el =>
            el.getAttribute('data-testid') !== 'character-full-art');
        return Math.abs(art.getBoundingClientRect().bottom
                      - left.getBoundingClientRect().bottom);
    }""")
    assert gap <= 4, f"art/left-column bottoms should align within 4px, got {gap}px"
