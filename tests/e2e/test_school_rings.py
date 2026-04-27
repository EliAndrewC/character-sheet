"""E2E: School ring interactions — fixed ring, multi-ring dropdown, changing schools."""

from tests.e2e.helpers import select_school, start_new_character
import pytest

pytestmark = pytest.mark.school_rings

def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def test_fixed_ring_school_sets_ring(page, live_server_url):
    """School with fixed ring (Akodo Bushi = Water) auto-sets school ring."""

    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    val = page.locator('input[name="school_ring_choice"]').input_value()
    assert val == "Water"


def test_multi_ring_school_shows_dropdown(page, live_server_url):
    """School with 'any non-Void' ring shows ring choice dropdown."""
    _go_to_editor(page, live_server_url)
    select_school(page, "brotherhood_of_shinsei_monk")  # any non-Void
    page.wait_for_timeout(500)
    dropdown = page.locator('text="Choose School Ring"')
    assert dropdown.is_visible()


def test_air_or_water_ring_dropdown(page, live_server_url):
    """School with 'Air or Water' ring shows dropdown."""
    _go_to_editor(page, live_server_url)
    select_school(page, "doji_artisan")  # Air or Water
    page.wait_for_timeout(500)
    assert page.locator('text="Choose School Ring"').is_visible()


def test_selecting_ring_from_dropdown(page, live_server_url):
    """Selecting a ring from the dropdown updates school_ring_choice."""
    _go_to_editor(page, live_server_url)
    select_school(page, "brotherhood_of_shinsei_monk")
    page.wait_for_timeout(500)
    dropdown = page.locator('text="Choose School Ring"').locator('..').locator('select')
    dropdown.select_option("Fire")
    page.wait_for_timeout(300)
    val = page.locator('input[name="school_ring_choice"]').input_value()
    assert val == "Fire"


def test_changing_school_resets_knacks(page, live_server_url):
    """Changing school replaces knack controls with new school's knacks."""
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    page.wait_for_timeout(500)
    assert page.locator('input[name="knack_feint"]').count() > 0
    select_school(page, "courtier")
    page.wait_for_timeout(500)
    assert page.locator('input[name="knack_feint"]').count() == 0
    assert page.locator('input[name="knack_discern_honor"]').count() > 0


def test_changing_multi_to_fixed_hides_dropdown(page, live_server_url):
    """Changing from multi-ring school to fixed-ring hides the ring dropdown."""
    _go_to_editor(page, live_server_url)
    select_school(page, "brotherhood_of_shinsei_monk")  # multi-ring
    page.wait_for_timeout(500)
    assert page.locator('text="Choose School Ring"').is_visible()
    select_school(page, "akodo_bushi")  # fixed ring (Water)
    page.wait_for_timeout(500)
    assert not page.locator('text="Choose School Ring"').is_visible()


def test_suzume_overseer_fixed_water(page, live_server_url):
    """Suzume Overseer has a fixed Water school ring (no dropdown)."""
    _go_to_editor(page, live_server_url)
    select_school(page, "suzume_overseer")
    val = page.locator('input[name="school_ring_choice"]').input_value()
    assert val == "Water"
    assert not page.locator('text="Choose School Ring"').is_visible()


def test_kitsune_warden_any_non_void_dropdown_options(page, live_server_url):
    """Kitsune Warden's 'any non-Void' ring picker offers Air/Fire/Earth/Water,
    not Void, and the choice persists in school_ring_choice."""
    _go_to_editor(page, live_server_url)
    select_school(page, "kitsune_warden")
    page.wait_for_timeout(500)
    dropdown = page.locator('text="Choose School Ring"').locator('..').locator('select')
    options = [o.strip() for o in dropdown.locator('option').all_text_contents()]
    assert "Air" in options
    assert "Fire" in options
    assert "Earth" in options
    assert "Water" in options
    assert "Void" not in options
    dropdown.select_option("Fire")
    page.wait_for_timeout(300)
    val = page.locator('input[name="school_ring_choice"]').input_value()
    assert val == "Fire"
