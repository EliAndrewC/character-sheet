"""E2E: School selection via HTMX and its effects on the form."""

from tests.e2e.helpers import select_school


def test_school_selection_loads_details(page, live_server_url):
    """Selecting a school should load its details via HTMX."""
    page.goto(f"{live_server_url}/characters/new")

    details = page.text_content("#school-details")
    assert "Special Ability" not in details

    select_school(page, "hida_bushi")

    details = page.text_content("#school-details")
    assert "Water" in details
    assert "counterattack" in details.lower()


def test_switching_schools_updates_details(page, live_server_url):
    """Changing the school should replace the details panel."""
    page.goto(f"{live_server_url}/characters/new")

    select_school(page, "akodo_bushi")
    assert "feint" in page.text_content("#school-details").lower()

    page.locator('select[name="school"]').select_option("kakita_duelist")
    page.locator('select[name="school"]').dispatch_event("change")
    page.wait_for_selector("#school-details :text('Phase 0')", timeout=10000)
    details = page.text_content("#school-details")
    assert "Fire" in details
    assert "lunge" in details.lower()


def test_school_knack_controls_appear(page, live_server_url):
    """School selection should show knack +/- controls managed by Alpine."""
    page.goto(f"{live_server_url}/characters/new")

    select_school(page, "mirumoto_bushi")

    assert page.locator('input[name="knack_counterattack"]').count() > 0
    assert page.locator('input[name="knack_double_attack"]').count() > 0
    assert page.locator('input[name="knack_iaijutsu"]').count() > 0


def test_school_techniques_shown(page, live_server_url):
    """School details should show all 5 Dan techniques."""
    page.goto(f"{live_server_url}/characters/new")

    select_school(page, "courtier")

    details = page.text_content("#school-details")
    assert "1st Dan" in details
    assert "2nd Dan" in details
    assert "3rd Dan" in details
    assert "4th Dan" in details
    assert "5th Dan" in details
