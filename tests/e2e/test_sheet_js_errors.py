"""E2E: JavaScript console error checks on the View Sheet page.

The editor page has its own JS error test in test_editor_controls.py.
This file checks the sheet page for multiple school types, since different
schools render different knacks, techniques, and tracking sections that
can trigger template/Alpine errors.
"""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character

pytestmark = [pytest.mark.rolls, pytest.mark.status_display]

SCHOOLS_TO_TEST = [
    "akodo_bushi",           # standard bushi, feint knack, temp void
    "mirumoto_bushi",        # Void school ring, counterattack knack, temp void
    "courtier",              # non-bushi, court category, temp void at 4th Dan
    "brotherhood_of_shinsei_monk",  # monk, multi-ring school
    "isawa_ishi",            # spellcaster, absorb_void/kharmic_spin knacks
    "kakita_duelist",        # duelist, initiative Phase 0 ability
    "mantis_wave_treader",   # bushi, "Any" ring (all five), worldliness knack
]


def _create_and_view(page, live_server_url, school, name):
    """Create a character with the given school, apply, and stay on the sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    # For multi-ring schools, pick a ring if needed
    page.wait_for_timeout(300)
    ring_dropdown = page.locator('select[x-model="schoolRingChoice"]')
    if ring_dropdown.count() > 0 and ring_dropdown.is_visible():
        ring_dropdown.select_option(index=1)
        page.wait_for_timeout(200)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, f"Setup {school}")


@pytest.mark.parametrize("school", SCHOOLS_TO_TEST)
def test_sheet_has_no_javascript_errors(page, live_server_url, school):
    """The View Sheet page should not throw JavaScript errors for any school.

    Captures 'pageerror' (uncaught exceptions) and 'console.error' messages
    while navigating to the sheet of a freshly-created character.
    """
    # Create the character at the normal page (captures errors during setup
    # aren't relevant — we only care about the sheet page).
    _create_and_view(page, live_server_url, school, f"JSCheck {school}")
    sheet_url = page.url

    # Set up error listeners and RELOAD the sheet page so we only capture
    # errors from the sheet, not from the editor/apply flow above.
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.{msg.type}: {msg.text}")
        if msg.type == "error"
        else None,
    )

    page.goto(sheet_url)
    page.wait_for_timeout(500)

    assert errors == [], (
        f"JavaScript errors on the sheet page for {school}:\n" + "\n".join(errors)
    )
