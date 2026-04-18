"""E2E: Live tracking of wounds, void points, and per-adventure abilities."""

from tests.e2e.helpers import select_school, apply_changes, start_new_character
import pytest

pytestmark = pytest.mark.tracking

def _create_published_character(page, live_server_url, name="Track Test", school="akodo_bushi"):
    """Create, publish, and navigate to character sheet."""

    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")


def test_tracking_renders_with_per_adventure_abilities(page, live_server_url):
    """Tracking section renders correctly even with per-adventure JSON data."""
    # Use a school that doesn't have per-adventure abilities but add Lucky
    page.goto(live_server_url)
    start_new_character(page)
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
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"

    # Lucky toggle should be visible
    assert page.locator('text="Lucky (re-roll)"').is_visible()


def test_tracking_shows_initial_values(page, live_server_url):
    """The tracking section shows correct initial values on a fresh character."""
    _create_published_character(page, live_server_url, "Initial Values")

    # Wait for Alpine to initialize
    page.wait_for_selector('text="Tracking"')
    page.wait_for_timeout(500)

    # Wounds start at 0, void points start at max (min ring = 2)
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "0"
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "2"


def test_wound_tracking_persists(page, live_server_url):
    """Adding light wounds via modal persists across page reload."""
    _create_published_character(page, live_server_url, "Wound Tracker")

    # Click + to open modal, use "Add to current total"
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('text="Add to current total"', timeout=3000)
    page.locator('input[placeholder="Amount"]').fill("5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_timeout(500)

    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "5"

    # Reload and verify persistence
    page.reload()
    page.wait_for_selector('text="Light Wounds"')
    page.wait_for_timeout(500)
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "5"


def test_void_points_tracking(page, live_server_url):
    """Void points can be decremented and incremented."""
    _create_published_character(page, live_server_url, "Void Tracker")

    # VP starts at 2 (full, min ring = 2). Decrement first.
    void_row = page.locator('text="Void Points"').locator('..')
    void_row.locator('button', has_text="-").click()
    page.wait_for_timeout(500)
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "1"

    # Increment back
    void_row.locator('button', has_text="+").click()
    page.wait_for_timeout(500)
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "2"
