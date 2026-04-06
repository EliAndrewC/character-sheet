"""E2E: Live tracking of wounds, void points, and per-adventure abilities."""

from tests.e2e.helpers import select_school, apply_changes
import pytest

pytestmark = pytest.mark.tracking

def _create_published_character(page, live_server_url, name="Track Test", school="akodo_bushi"):
    """Create, publish, and navigate to character sheet."""

    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")


def test_tracking_renders_with_per_adventure_abilities(page, live_server_url):
    """Tracking section renders correctly even with per-adventure JSON data."""
    # Use a school that doesn't have per-adventure abilities but add Lucky
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Lucky Tracker")
    select_school(page, "akodo_bushi")
    page.check('input[name="adv_lucky"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")

    # The tracking section should render with Lucky toggle
    page.wait_for_selector('text="Tracking"')
    page.wait_for_timeout(500)

    # Numbers should be visible
    light = page.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert light.text_content().strip() == "0"

    # Lucky toggle should be visible
    assert page.locator('text="Lucky (re-roll)"').is_visible()


def test_tracking_shows_initial_values(page, live_server_url):
    """The tracking section should show 0 for all counters on a fresh character."""
    _create_published_character(page, live_server_url, "Initial Values")

    # Wait for Alpine to initialize
    page.wait_for_selector('text="Tracking"')
    page.wait_for_timeout(500)

    # Check that the numbers are visible and show 0
    light = page.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert light.text_content().strip() == "0", f"Light wounds showed: {light.text_content()!r}"

    serious = page.locator('text="Serious Wounds"').locator('..').locator('span.text-2xl')
    assert serious.text_content().strip() == "0", f"Serious wounds showed: {serious.text_content()!r}"

    void = page.locator('text="Void Points"').locator('..').locator('span.text-2xl')
    assert void.text_content().strip() == "0", f"Void points showed: {void.text_content()!r}"


def test_wound_tracking_persists(page, live_server_url):
    """Adding light wounds via modal persists across page reload."""
    _create_published_character(page, live_server_url, "Wound Tracker")

    # Click + to open modal, use "Add to current total"
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('text="Add to current total"', timeout=3000)
    page.locator('input[placeholder="Amount"]').fill("5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_timeout(500)

    wound_display = page.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert wound_display.text_content().strip() == "5"

    # Reload and verify persistence
    page.reload()
    page.wait_for_selector('text="Light Wounds"')
    page.wait_for_timeout(500)
    wound_display = page.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert wound_display.text_content().strip() == "5"


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
