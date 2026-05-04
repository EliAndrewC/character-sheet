"""E2E: Combat skills (Attack and Parry) in the editor."""

from tests.e2e.helpers import (
    select_school, click_plus, click_minus, apply_changes,
    start_new_character, create_and_apply,
)
import pytest

pytestmark = pytest.mark.combat_skills

def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def test_combat_skill_xp_live_calculation(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    click_plus(page, "attack", 2)  # 4+6 = 10 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "10"
    click_plus(page, "parry", 1)  # +4 = 14
    assert page.text_content('[x-text="grossSpent()"]').strip() == "14"


def test_parry_cannot_exceed_attack_plus_1(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "parry", 1)  # 1->2, attack still 1
    assert page.locator('input[name="parry"]').input_value() == "2"
    plus_btn = page.locator('input[name="parry"]').locator('..').locator('button:text("+")')
    assert plus_btn.is_disabled()


def test_attack_cannot_lower_below_parry_minus_1(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 1)
    click_plus(page, "parry", 1)

    minus_btn = page.locator('input[name="attack"]').locator('..').locator('button:text("-")')
    assert not minus_btn.is_disabled()
    click_minus(page, "attack", 1)
    assert minus_btn.is_disabled()


def test_create_with_combat_skills_and_publish(page, live_server_url):
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Combat Fighter")
    select_school(page, "akodo_bushi")
    click_plus(page, "attack", 2)
    click_plus(page, "parry", 1)

    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Added combat skills")
    page.wait_for_selector("h1")

    body = page.text_content("body")
    assert "Combat Fighter" in body
    assert "Attack" in body
    assert "Parry" in body


def test_attack_parry_pips_align_with_knack_pips(page, live_server_url):
    """On the read-only sheet, the rank pips on the Attack and Parry rows
    must vertically align (right edge) with the rank pips on each school
    knack row below. The roll formula sits to the LEFT of the pips."""
    create_and_apply(page, live_server_url, name="PipAlign", school="akodo_bushi",
                     summary="Setup")

    def pip_right(row_locator):
        # The pip group is the inner "flex gap-0.5" div holding the 5 circles.
        pip_group = row_locator.locator('div.flex.gap-0\\.5').first
        box = pip_group.bounding_box()
        assert box is not None, "pip group not visible"
        return box['x'] + box['width']

    attack_row = page.locator('[data-roll-key="attack"]')
    parry_row = page.locator('[data-roll-key="parry"]')
    # Akodo's school knacks: feint, double_attack, iaijutsu. Pick one.
    knack_row = page.locator('div.bg-parchment', has_text="Iaijutsu").first

    attack_x = pip_right(attack_row)
    parry_x = pip_right(parry_row)
    knack_x = pip_right(knack_row)

    # Allow a 1px tolerance for sub-pixel rounding.
    assert abs(attack_x - knack_x) <= 1, (
        f"attack pips end at {attack_x}, knack pips end at {knack_x}"
    )
    assert abs(parry_x - knack_x) <= 1, (
        f"parry pips end at {parry_x}, knack pips end at {knack_x}"
    )

    # Roll formula must appear to the LEFT of the pips on attack and parry.
    for row in (attack_row, parry_row):
        pip_group = row.locator('div.flex.gap-0\\.5').first
        roll_span = row.locator('span.text-ink\\/60').first
        pip_box = pip_group.bounding_box()
        roll_box = roll_span.bounding_box()
        assert roll_box['x'] + roll_box['width'] <= pip_box['x'], (
            f"roll text right edge ({roll_box['x'] + roll_box['width']}) "
            f"must be at or before pips left edge ({pip_box['x']})"
        )
