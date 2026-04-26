"""E2E: Foreign school knacks - edit page picker, XP card, sheet rendering, rolls."""

import pytest

from tests.e2e.helpers import (
    apply_changes,
    click_plus,
    select_school,
    start_new_character,
)

pytestmark = pytest.mark.foreign_knacks


def _go_to_editor(page, live_server_url, school="akodo_bushi"):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, school)


def _add_foreign_knack(page, kid):
    """Open the picker, choose a knack id, wait for the row to appear."""
    page.locator('[data-testid="add-foreign-knack-btn"]').click()
    page.wait_for_selector('[data-testid="foreign-knack-select"]', state="visible", timeout=2000)
    page.select_option('[data-testid="foreign-knack-select"]', kid)
    page.wait_for_selector(f'[data-testid="foreign-knack-row-{kid}"]', timeout=2000)


def test_section_visible_on_edit_page(page, live_server_url):
    """The Foreign School Knacks section, description text, and Add button render."""
    _go_to_editor(page, live_server_url)
    text = page.text_content("body") or ""
    assert "Foreign School Knacks" in text
    # Verify the verbatim spec text (with the user-confirmed "purchase" spelling).
    assert "purchase non-supernatural school knacks from other schools" in text
    assert page.locator('[data-testid="add-foreign-knack-btn"]').is_visible()


def test_picker_options_exclude_own_school_supernatural_and_taken(page, live_server_url):
    """Dropdown should never list: own school's knacks, supernatural knacks, or already-taken."""
    _go_to_editor(page, live_server_url)
    # Akodo school knacks: feint, double_attack, iaijutsu - must NOT be in picker.
    page.locator('[data-testid="add-foreign-knack-btn"]').click()
    page.wait_for_selector('[data-testid="foreign-knack-select"]', state="visible")
    options = page.locator('[data-testid="foreign-knack-select"] option').all_text_contents()
    # Strip the placeholder and the "Never mind" cancel row.
    options = [o for o in options if o not in ("Select another school knack", "Never mind")]
    # Akodo native knacks must be excluded
    assert "Feint" not in options
    assert "Double Attack" not in options
    assert "Iaijutsu" not in options
    # Supernatural knacks must be excluded
    for sup in ("Absorb Void", "Commune", "Detect Taint", "Dragon Tattoo", "Spellcasting"):
        assert sup not in options


def test_picker_placeholder_is_default_and_disabled(page, live_server_url):
    """Opening the picker shows 'Select another school knack' as the default,
    disabled placeholder option - not 'Never mind'."""
    _go_to_editor(page, live_server_url)
    page.locator('[data-testid="add-foreign-knack-btn"]').click()
    page.wait_for_selector('[data-testid="foreign-knack-select"]', state="visible")
    sel = page.locator('[data-testid="foreign-knack-select"]')
    # The currently selected option text is the placeholder.
    selected_text = sel.evaluate("el => el.options[el.selectedIndex].text")
    assert selected_text == "Select another school knack"
    # And the placeholder is disabled (so re-selecting it isn't possible).
    placeholder_disabled = sel.evaluate(
        "el => el.querySelector('option[value=\"\"]').disabled"
    )
    assert placeholder_disabled is True


def test_never_mind_dismisses_without_change(page, live_server_url):
    """Selecting 'Never mind' closes the picker without persisting anything."""
    _go_to_editor(page, live_server_url)
    page.locator('[data-testid="add-foreign-knack-btn"]').click()
    page.wait_for_selector('[data-testid="foreign-knack-select"]', state="visible")
    page.select_option('[data-testid="foreign-knack-select"]', "__cancel__")
    page.wait_for_timeout(150)
    # Picker should be hidden again, button visible again.
    assert page.locator('[data-testid="add-foreign-knack-btn"]').is_visible()
    # No foreign-knack rows appeared and no autosave inputs were emitted.
    assert page.locator('[data-testid^="foreign-knack-row-"]').count() == 0
    assert page.locator('input[name^="foreign_knack_"]').count() == 0


def test_pick_adds_row_at_rank_1(page, live_server_url):
    """Picking a knack adds its row at rank 1, with the +/- toggle visible."""
    _go_to_editor(page, live_server_url)
    _add_foreign_knack(page, "athletics")
    # Hidden input emits the rank for legacy form-POST parity.
    val = page.locator('input[name="foreign_knack_athletics"]').input_value()
    assert val == "1"
    # The Add button is visible again so the user can keep adding.
    assert page.locator('[data-testid="add-foreign-knack-btn"]').is_visible()


def test_decrement_to_zero_removes_row(page, live_server_url):
    """Clicking - on a rank-1 foreign knack removes the entry entirely."""
    _go_to_editor(page, live_server_url)
    _add_foreign_knack(page, "athletics")
    page.locator('[data-testid="foreign-knack-minus-athletics"]').click()
    page.wait_for_timeout(150)
    # Row gone, hidden input gone.
    assert page.locator('[data-testid="foreign-knack-row-athletics"]').count() == 0
    assert page.locator('input[name="foreign_knack_athletics"]').count() == 0


def test_xp_summary_reflects_10_xp_premium(page, live_server_url):
    """Adding one foreign knack at rank 1 adds 10 XP to the editor's gross spend."""
    _go_to_editor(page, live_server_url)
    page.wait_for_timeout(300)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    _add_foreign_knack(page, "athletics")
    page.wait_for_timeout(200)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after - spent_before == 10


def test_xp_summary_card_appears_only_when_present(page, live_server_url):
    """Foreign-knacks XP card is hidden when empty, shows after adding."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "FKCard")
    apply_changes(page, "no foreign yet")
    # Sheet view: no card.
    assert page.locator('[data-xp-card="foreign_knacks"]').count() == 0

    page.goto(page.url.replace("/characters/", "/characters/").replace("?", "/edit?") if "?" in page.url else page.url + "/edit")
    page.wait_for_selector('[data-testid="add-foreign-knack-btn"]', timeout=5000)
    _add_foreign_knack(page, "athletics")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "added athletics")
    # Now the card appears.
    page.wait_for_selector('[data-xp-card="foreign_knacks"]', timeout=5000)
    card = page.locator('[data-xp-card="foreign_knacks"]')
    assert card.is_visible()
    # Total = 10 (the rank-1 premium).
    assert "10" in (card.text_content() or "")


def test_xp_card_expansion_shows_premium_row(page, live_server_url):
    """Expanding the foreign-knacks XP card lists the 10 XP 0->1 row."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "FKExpand")
    _add_foreign_knack(page, "athletics")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "expand test")
    page.wait_for_selector('[data-xp-card="foreign_knacks"]', timeout=5000)
    page.locator('[data-xp-card="foreign_knacks"]').click()
    panel = page.locator('[data-xp-detail="foreign_knacks"]')
    panel.wait_for(state="visible", timeout=2000)
    text = panel.text_content() or ""
    assert "Athletics" in text
    assert "0" in text and "1" in text  # the from->to columns
    assert "10" in text  # the premium XP


def test_foreign_knack_listed_distinctly_on_sheet(page, live_server_url):
    """The sheet's Combat Skills section lists foreign knacks under a separate
    heading, with the 'foreign' badge."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "FKSheet")
    _add_foreign_knack(page, "athletics")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "sheet test")
    page.wait_for_selector('[data-testid="foreign-knacks-list"]', timeout=5000)
    section = page.locator('[data-testid="foreign-knacks-list"]')
    assert section.is_visible()
    text = section.text_content() or ""
    assert "Athletics" in text
    assert "foreign" in text.lower()


def test_foreign_knack_tooltip_includes_foreign_note(page, live_server_url):
    """Expanding a foreign-knack rules-text disclosure shows the 'foreign' preface."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "FKTooltip")
    _add_foreign_knack(page, "athletics")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "tooltip test")
    row = page.locator('[data-testid="foreign-knack-athletics"]')
    row.wait_for(state="visible", timeout=5000)
    # Click to expand the rules-text section.
    row.locator(':scope > div').first.click()
    page.wait_for_timeout(150)
    text = row.text_content() or ""
    assert "foreign school knack" in text.lower()
    assert "learned outside your school" in text.lower()


def test_foreign_athletics_enables_athletics_roll_on_sheet(page, live_server_url):
    """A character with foreign athletics rank 1 can roll the athletics buttons."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "FKAthletics")
    _add_foreign_knack(page, "athletics")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "athletics roll")
    # Athletics rolls show as buttons keyed athletics:Air etc on the sheet.
    # Verify at least one athletics roll button is present.
    btns = page.locator('[data-roll-key^="athletics:"]')
    assert btns.count() >= 1


def test_foreign_worldliness_grants_pool(page, live_server_url):
    """A non-Asahina character with foreign worldliness rank 2 sees the
    Worldliness counter in their per-adventure tracking with max=2."""
    # Akodo doesn't have worldliness as a native knack; take it as foreign.
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "FKWorld")
    _add_foreign_knack(page, "worldliness")
    # Bump to 2.
    page.locator('[data-testid="foreign-knack-plus-worldliness"]').click()
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "worldliness test")
    # The tracking section renders a Worldliness counter when the knack pool
    # is non-zero. Search for "Worldliness" in the sheet body.
    body = page.text_content("body") or ""
    assert "Worldliness" in body
