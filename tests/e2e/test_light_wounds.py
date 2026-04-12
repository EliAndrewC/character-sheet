"""E2E: Light wounds modal — add, set total, take serious, minus dropdown."""

import pytest
from tests.e2e.helpers import select_school, apply_changes

pytestmark = pytest.mark.tracking


def _create_char(page, live_server_url):
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    page.wait_for_selector('text="Light Wounds"')
    page.wait_for_timeout(500)


def _get_lw(page):
    return page.locator('[x-text="lightWounds"]').text_content().strip()


def _get_sw(page):
    return page.locator('[x-text="seriousWounds"]').text_content().strip()


def _add_light_wounds(page, amount):
    """Use the + modal to add light wounds."""
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', str(amount))
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_timeout(500)


def test_plus_opens_modal(page, live_server_url):
    """Clicking + on light wounds opens the modal."""
    _create_char(page, live_server_url)
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('text="Add to current total"', timeout=3000)
    assert page.locator('text="Take serious wounds & reset light to 0"').is_visible()
    assert page.locator('text="Set total to"').is_visible()


def test_modal_add_to_total(page, live_server_url):
    """Modal: add amount to current light wound total."""
    _create_char(page, live_server_url)
    _add_light_wounds(page, 12)
    assert _get_lw(page) == "12"


def test_modal_set_total(page, live_server_url):
    """Modal: set light wound total directly."""
    _create_char(page, live_server_url)
    _add_light_wounds(page, 10)
    assert _get_lw(page) == "10"

    # Now set to a different value
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="New total"]', timeout=3000)
    page.fill('input[placeholder="New total"]', "3")
    page.locator('input[placeholder="New total"]').locator('..').locator('button', has_text="Set").click()
    page.wait_for_timeout(500)
    assert _get_lw(page) == "3"


def test_modal_take_serious_and_reset(page, live_server_url):
    """Modal: take serious wounds and reset light wounds to 0."""
    _create_char(page, live_server_url)
    _add_light_wounds(page, 20)
    assert _get_lw(page) == "20"

    # Take 2 serious wounds and reset light to 0
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('text="Take serious wounds & reset light to 0"', timeout=3000)
    # Increment the serious count to 2 (the + inside the modal's first section)
    modal = page.locator('div.fixed div.bg-white')
    serious_section = modal.locator('div.border-b').first
    serious_section.locator('button', has_text="+").click()
    page.wait_for_timeout(200)
    # Click the submit button for this section
    serious_section.locator('button.bg-red-700').click()
    page.wait_for_timeout(500)
    assert _get_lw(page) == "0"
    assert _get_sw(page) == "2"


def test_minus_dropdown_reset(page, live_server_url):
    """Minus dropdown: reset to 0."""
    _create_char(page, live_server_url)
    _add_light_wounds(page, 8)
    assert _get_lw(page) == "8"

    page.locator('[data-action="lw-minus"]').click()
    page.wait_for_selector('text="Reset to 0"', timeout=3000)
    page.locator('button:text("Reset to 0")').click()
    page.wait_for_timeout(500)
    assert _get_lw(page) == "0"


def test_minus_dropdown_enter_new_total(page, live_server_url):
    """Minus dropdown: enter new total via modal."""
    _create_char(page, live_server_url)
    _add_light_wounds(page, 15)

    page.locator('[data-action="lw-minus"]').click()
    page.wait_for_selector('text="Enter new total..."', timeout=3000)
    page.locator('button:text("Enter new total...")').click()
    page.wait_for_selector('h3:text("Set Light Wounds")', timeout=3000)
    set_modal = page.locator('div.fixed', has=page.locator('h3:text("Set Light Wounds")'))
    set_modal.locator('input[type="number"]').fill("7")
    set_modal.locator('button:text("Set")').click()
    page.wait_for_timeout(500)
    assert _get_lw(page) == "7"


def test_minus_disabled_at_zero(page, live_server_url):
    """Minus button disabled when light wounds is 0."""
    _create_char(page, live_server_url)
    assert page.locator('[data-action="lw-minus"]').is_disabled()
