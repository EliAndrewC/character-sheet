"""E2E: Live tracking of wounds, void points, and per-adventure abilities."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character
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
    page.wait_for_selector('text="Add to current total"', timeout=10000)
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


def test_absorb_void_use_regains_one_spent_vp(page, live_server_url):
    """Absorb Void is a per-adventure ability. Each use restores 1 spent VP
    AND decrements the remaining-uses counter. The use button is disabled
    when no VP has been spent (nothing to recover)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "AbsorbVoidUse")
    select_school(page, "isawa_ishi")
    # Bump absorb_void to rank 2 so we have 2 uses to test undo on.
    click_plus(page, "knack_absorb_void", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    page.wait_for_selector('text="Tracking"')
    page.wait_for_timeout(300)

    # Sanity: no dice icon next to Absorb Void in the knacks panel.
    assert page.locator('[data-roll-key="knack:absorb_void"]').count() == 0

    # Snapshot starting VP and counter.
    starting_vp = int(page.locator('[x-text="voidPoints"]').text_content().strip())
    counter_text = page.locator(
        'span[x-text*="getCount(\'absorb_void\')"]'
    ).first.text_content()
    assert "/ 2" in counter_text  # rank 2 -> max 2

    # Use button is disabled at full VP (nothing to regain).
    use_btn = page.locator('[data-action="use-absorb-void"]')
    assert use_btn.is_disabled()

    # Spend a VP via the regular - button on Void Points.
    void_row = page.locator('text="Void Points"').locator('..')
    void_row.locator('button', has_text="-").click()
    page.wait_for_timeout(300)
    assert int(page.locator('[x-text="voidPoints"]').text_content().strip()) == starting_vp - 1

    # Now Use Absorb Void: VP restored, remaining uses drops by 1.
    use_btn.click()
    page.wait_for_timeout(300)
    assert int(page.locator('[x-text="voidPoints"]').text_content().strip()) == starting_vp
    counter_text = page.locator(
        'span[x-text*="getCount(\'absorb_void\')"]'
    ).first.text_content()
    assert "1 / 2" in counter_text  # one used, one remaining

    # Undo: refund the use AND re-spend the VP.
    page.locator('[data-action="undo-absorb-void"]').click()
    page.wait_for_timeout(300)
    assert int(page.locator('[x-text="voidPoints"]').text_content().strip()) == starting_vp - 1
    counter_text = page.locator(
        'span[x-text*="getCount(\'absorb_void\')"]'
    ).first.text_content()
    assert "2 / 2" in counter_text  # back to full uses
