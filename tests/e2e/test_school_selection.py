"""E2E: School selection via HTMX and its effects on the form."""

from tests.e2e.helpers import select_school, start_new_character
import pytest

pytestmark = pytest.mark.school

def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def test_school_selection_loads_details(page, live_server_url):
    _go_to_editor(page, live_server_url)

    details = page.text_content("#school-details")
    assert "Special Ability" not in details

    select_school(page, "hida_bushi")

    details = page.text_content("#school-details")
    assert "Water" in details
    assert "counterattack" in details.lower()


def test_switching_schools_updates_details(page, live_server_url):
    _go_to_editor(page, live_server_url)

    select_school(page, "akodo_bushi")
    assert "feint" in page.text_content("#school-details").lower()

    page.evaluate("""() => {

        const sel = document.querySelector('select[name="school"]');
        sel.value = 'kakita_duelist';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_selector("#school-details :text('Phase 0')", timeout=10000)
    details = page.text_content("#school-details")
    assert "Fire" in details
    assert "lunge" in details.lower()


def test_school_knack_controls_appear(page, live_server_url):
    _go_to_editor(page, live_server_url)

    select_school(page, "mirumoto_bushi")

    assert page.locator('input[name="knack_counterattack"]').count() > 0
    assert page.locator('input[name="knack_double_attack"]').count() > 0
    assert page.locator('input[name="knack_iaijutsu"]').count() > 0


def test_school_techniques_shown(page, live_server_url):
    _go_to_editor(page, live_server_url)

    select_school(page, "courtier")

    details = page.text_content("#school-details")
    assert "1st Dan" in details
    assert "2nd Dan" in details
    assert "3rd Dan" in details
    assert "4th Dan" in details
    assert "5th Dan" in details
