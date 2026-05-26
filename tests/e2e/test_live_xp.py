"""E2E: the editor's live XP display is server-computed (app/services/xp.py
::editor_xp_view) and fetched via POST /characters/{id}/xp on each change.
These verify the footer (Spent/Total/Unspent) updates to the right values
after the debounced refresh."""

from tests.e2e.helpers import select_school, click_plus, start_new_character
import pytest

pytestmark = [pytest.mark.rings, pytest.mark.skills, pytest.mark.knacks, pytest.mark.combat_skills, pytest.mark.advantages, pytest.mark.honor_rank_recognition]


def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def _wait_text(page, selector, expected, timeout=6000):
    """Wait until ``selector``'s trimmed text equals ``expected`` (the XP fetch
    is debounced + async, so the footer updates a beat after the edit)."""
    page.wait_for_function(
        """([sel, exp]) => {
            const el = document.querySelector(sel);
            return el && el.textContent.trim() === exp;
        }""",
        arg=[selector, expected],
        timeout=timeout,
    )


SPENT = '[x-text="xp.spent"]'
BUDGET = '[x-text="xp.budget"]'
REMAINING = '[x-text="xp.remaining"]'


def test_xp_updates_on_ring_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    _wait_text(page, SPENT, "0")
    click_plus(page, "ring_fire", 1)  # 2->3 = 15 XP
    _wait_text(page, SPENT, "15")


def test_xp_updates_on_skill_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_precepts", 3)  # basic: 2+2+3 = 7
    _wait_text(page, SPENT, "7")


def test_xp_updates_on_advantage_toggle(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    page.check('input[name="adv_lucky"]')
    _wait_text(page, SPENT, "5")
    page.uncheck('input[name="adv_lucky"]')
    _wait_text(page, SPENT, "0")


def test_xp_updates_on_disadvantage_toggle(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_discordant"]')
    _wait_text(page, SPENT, "0")
    _wait_text(page, BUDGET, "162")  # 150 + 12 disadvantage gain


def test_remaining_goes_negative_on_overspend(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    for ring in ["air", "fire", "earth", "void"]:
        click_plus(page, f"ring_{ring}", 3)
    click_plus(page, "ring_water", 2)

    # Wait for the refresh to land a negative remaining, then check the styling.
    page.wait_for_function(
        """() => {
            const el = document.querySelector('[x-text="xp.remaining"]');
            return el && parseInt(el.textContent.trim()) < 0;
        }""",
        timeout=6000,
    )
    parent = page.locator(REMAINING).locator("..")
    assert "text-red-600" in (parent.get_attribute("class") or "")


def test_xp_honor_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    click_plus(page, "honor", 4)  # 1.0 -> 3.0 = 4 XP
    _wait_text(page, SPENT, "4")


def test_xp_updates_on_knack_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    click_plus(page, "knack_feint", 1)  # 1->2 = 4 XP
    _wait_text(page, SPENT, "4")


def test_xp_updates_on_combat_skill_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")
    click_plus(page, "attack", 1)  # 1->2 = 4 XP
    _wait_text(page, SPENT, "4")
