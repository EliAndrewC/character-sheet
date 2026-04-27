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
    "suzume_overseer",       # court, no 4th Dan technique, shares Doji+Merchant flags
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


def test_sheet_no_js_errors_for_priest_3rd_dan_with_pool(page, live_server_url):
    """A 3rd Dan priest with a populated precepts pool renders all the
    Phase 0-5 pool markup (section, dice icons, swap dropdowns across four
    roll modals) without throwing JavaScript errors. This exercises the
    Phase 4/5 Alpine expressions with a real non-empty pool."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "PriestPoolJSCheck")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 2)  # 1 -> 3 Dan
    click_plus(page, "skill_precepts", 3)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Priest 3rd Dan with pool")
    sheet_url = page.url

    # Seed a pool so every pool-render path fires on reload.
    page.evaluate("""
        window._trackingBridge.preceptsPool = [
            {value: 9}, {value: 6}, {value: 2}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)

    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.{msg.type}: {msg.text}")
        if msg.type == "error"
        else None,
    )

    page.goto(sheet_url)
    page.wait_for_selector('[data-testid="precepts-pool-section"]')
    page.wait_for_timeout(500)

    assert errors == [], (
        "JavaScript errors on a 3rd Dan priest's sheet with a pool:\n"
        + "\n".join(errors)
    )
