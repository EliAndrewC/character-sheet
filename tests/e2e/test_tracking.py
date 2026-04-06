"""E2E: Live tracking of wounds, void points, and per-adventure abilities."""

from tests.e2e.helpers import select_school


def _create_published_character(page, live_server_url, name="Track Test", school="akodo_bushi"):
    """Create, publish, and navigate to character sheet."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('text="Publish Changes"')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('button:text("Publish Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)


def test_wound_tracking_persists(page, live_server_url):
    """Clicking +/- on wounds persists across page reload."""
    _create_published_character(page, live_server_url, "Wound Tracker")

    # Add 2 light wounds
    plus_btn = page.locator('text="Light Wounds"').locator('..').locator('button:text("+")')
    plus_btn.click()
    plus_btn.click()
    page.wait_for_timeout(500)

    # Verify display shows 2
    wound_display = page.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert wound_display.text_content().strip() == "2"

    # Reload and verify persistence
    page.reload()
    page.wait_for_selector('text="Light Wounds"')
    wound_display = page.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert wound_display.text_content().strip() == "2"


def test_void_points_tracking(page, live_server_url):
    """Void points can be incremented and decremented."""
    _create_published_character(page, live_server_url, "Void Tracker")

    # Add a void point
    void_section = page.locator('text="Void Points"').locator('..')
    void_section.locator('button', has_text="+").click()
    page.wait_for_timeout(500)

    void_display = void_section.locator('span.text-2xl')
    assert int(void_display.text_content().strip()) == 1

    # Remove it
    void_section.locator('button', has_text="-").click()
    page.wait_for_timeout(500)
    assert int(void_display.text_content().strip()) == 0
