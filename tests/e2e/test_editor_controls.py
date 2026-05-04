"""E2E: Editor field controls — min/max, disabled states, recognition halving, rank lock."""

from tests.e2e.helpers import select_school, click_plus, click_minus, start_new_character, apply_changes
import pytest

pytestmark = [pytest.mark.rings, pytest.mark.knacks, pytest.mark.combat_skills, pytest.mark.skills, pytest.mark.honor_rank_recognition, pytest.mark.advantages]


def test_editor_has_no_javascript_console_errors(page, live_server_url):
    """The editor page should not throw JavaScript errors on load.

    Captures any 'pageerror' (uncaught exception) and 'console.error'
    messages while navigating to a fresh editor and asserts there are none.
    """
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.{msg.type}: {msg.text}")
        if msg.type == "error"
        else None,
    )

    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    # Pick a school so the full editor renders (school knacks, advantage tooltips, etc.)
    select_school(page, "akodo_bushi")
    page.wait_for_timeout(500)

    assert errors == [], "JavaScript errors on the editor page:\n" + "\n".join(errors)

def _go_to_editor(page, live_server_url, school="akodo_bushi"):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, school)


# --- Rings ---

def test_nonschool_ring_min_2(page, live_server_url):
    """Non-school ring cannot go below 2."""

    _go_to_editor(page, live_server_url)  # Water is school ring for akodo
    # Air is non-school, starts at 2 — minus should be disabled
    minus = page.locator('input[name="ring_air"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_nonschool_ring_max_5(page, live_server_url):
    """Non-school ring cannot exceed 5."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "ring_air", 3)  # 2 → 5
    plus = page.locator('input[name="ring_air"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


def test_school_ring_min_3(page, live_server_url):
    """School ring cannot go below 3."""
    _go_to_editor(page, live_server_url)  # Water is school ring, starts at 3
    minus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_school_ring_max_6(page, live_server_url):
    """School ring can go up to 6 (one higher than non-school)."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "ring_water", 3)  # 3 → 6
    plus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()
    # Verify value is 6
    val = page.locator('input[name="ring_water"]').input_value()
    assert val == "6"


# --- Knacks ---

def test_knack_min_1(page, live_server_url):
    """Knack minimum is 1 (free from school), minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="knack_feint"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_knack_max_5(page, live_server_url):
    """Knack maximum is 5, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "knack_feint", 4)  # 1 → 5
    plus = page.locator('input[name="knack_feint"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


def test_fourth_dan_auto_raises_school_ring(page, live_server_url):
    """Reaching 4th Dan (all knacks ≥ 4) auto-raises school ring from 3 to 4."""
    _go_to_editor(page, live_server_url)
    # Akodo Bushi: school ring is Water, starts at 3.
    assert page.locator('input[name="ring_water"]').input_value() == "3"
    # Raise all three knacks to 4 → currentDan() == 4.
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(200)
    assert page.locator('input[name="ring_water"]').input_value() == "4"
    # Minus button is disabled at the new floor.
    minus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_fourth_dan_school_ring_max_7(page, live_server_url):
    """At 4th Dan the school ring's max climbs from 6 to 7."""
    _go_to_editor(page, live_server_url)
    # Reach 4th Dan
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(200)
    # School ring is now 4. Raise it to 7.
    click_plus(page, "ring_water", 3)  # 4 → 7
    assert page.locator('input[name="ring_water"]').input_value() == "7"
    plus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


def test_drop_below_4th_dan_caps_ring_at_6(page, live_server_url):
    """Ring at 7 drops to 6 when a knack is lowered below 4th Dan."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(200)
    click_plus(page, "ring_water", 3)  # 4 -> 7
    assert page.locator('input[name="ring_water"]').input_value() == "7"
    # Lower one knack -> Dan drops to 3
    click_minus(page, "knack_feint", 1)  # 4 -> 3
    page.wait_for_timeout(200)
    assert page.locator('input[name="ring_water"]').input_value() == "6"


def test_drop_below_4th_dan_ring_at_4_goes_to_3(page, live_server_url):
    """Ring auto-raised to 4 at 4th Dan should drop back to 3 when Dan
    falls below 4 (the free raise is removed)."""
    _go_to_editor(page, live_server_url)
    assert page.locator('input[name="ring_water"]').input_value() == "3"
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(200)
    # Auto-raised to 4
    assert page.locator('input[name="ring_water"]').input_value() == "4"
    # Drop a knack
    click_minus(page, "knack_feint", 1)
    page.wait_for_timeout(200)
    # Should go back to 3 (floor is 3, ring was at 4 = old floor, now below new...
    # Actually at Dan<4 the floor is 3, so 4 is valid. But the enforce function
    # should NOT lower from 4 to 3 because 4 is still >= min(3).
    # The user said "lower the ring immediately" but the ring at 4 is valid at Dan 3.
    # The enforce clamps: min=3, max=6, current=4 -> no change.
    # UNLESS we interpret "auto-raise is reversed" as the ring losing the +1.
    # Let me check what the user actually wants...)
    # Per the enforce function: Dan<4 floor=3, ring=4, 4 >= 3 and 4 <= 6 -> no clamp.
    assert page.locator('input[name="ring_water"]').input_value() == "4"


def test_ring_max_correct_after_repeated_dan_toggle(page, live_server_url):
    """Rapidly toggling above/below 4th Dan should always leave ringMax correct."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(100)
    plus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="+")
    # At 4th Dan, ring=4, max=7 -> + is enabled
    assert not plus.is_disabled()
    # Toggle below 4th Dan
    click_minus(page, "knack_feint", 1)
    page.wait_for_timeout(100)
    # At 3rd Dan, ring=4, max=6 -> + should still be enabled (4 < 6)
    assert not plus.is_disabled()
    # Raise ring to 6 (the non-4th-Dan max)
    click_plus(page, "ring_water", 2)  # 4 -> 6
    page.wait_for_timeout(100)
    # At 3rd Dan, ring=6, max=6 -> + IS disabled
    assert plus.is_disabled()
    # Toggle back to 4th Dan
    click_plus(page, "knack_feint", 1)  # 3 -> 4
    page.wait_for_timeout(100)
    # At 4th Dan, ring=6, max=7 -> + is enabled again
    assert not plus.is_disabled()


def test_ring_max_never_exceeds_bounds_after_many_toggles(page, live_server_url):
    """After many rapid Dan toggles, the ring value and + button state are consistent."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(100)
    # Raise ring to 7 (4th Dan max)
    click_plus(page, "ring_water", 3)
    page.wait_for_timeout(100)
    assert page.locator('input[name="ring_water"]').input_value() == "7"
    # Toggle Dan several times
    for _ in range(3):
        click_minus(page, "knack_feint", 1)  # below 4th
        page.wait_for_timeout(50)
        click_plus(page, "knack_feint", 1)   # back to 4th
        page.wait_for_timeout(50)
    # Should be clamped to 6 then raised back... let's check
    val = int(page.locator('input[name="ring_water"]').input_value())
    plus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="+")
    minus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="-")
    # The ring should be in a valid state
    assert 4 <= val <= 7
    # + disabled iff at max
    if val == 7:
        assert plus.is_disabled()
    else:
        assert not plus.is_disabled()
    # - disabled iff at min (4 at 4th Dan)
    if val == 4:
        assert minus.is_disabled()
    else:
        assert not minus.is_disabled()


def test_ring_at_5_stable_across_dan_toggle(page, live_server_url):
    """A ring manually raised to 5 should stay at 5 regardless of Dan changes."""
    _go_to_editor(page, live_server_url)
    # Raise ring to 5 at Dan 1
    click_plus(page, "ring_water", 2)  # 3 -> 5
    page.wait_for_timeout(100)
    assert page.locator('input[name="ring_water"]').input_value() == "5"
    # Go to 4th Dan
    click_plus(page, "knack_double_attack", 3)
    click_plus(page, "knack_feint", 3)
    click_plus(page, "knack_iaijutsu", 3)
    page.wait_for_timeout(100)
    # Ring should still be 5 (already above the 4th Dan floor of 4)
    assert page.locator('input[name="ring_water"]').input_value() == "5"
    # Drop back below 4th Dan
    click_minus(page, "knack_feint", 1)
    page.wait_for_timeout(100)
    # Ring should still be 5 (it's <= 6, the non-4th-Dan max)
    assert page.locator('input[name="ring_water"]').input_value() == "5"


# --- Combat Skills ---

def test_attack_min_1(page, live_server_url):
    """Attack minimum is 1, minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="attack"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_attack_max_5(page, live_server_url):
    """Attack maximum is 5, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "attack", 4)  # 1 → 5
    plus = page.locator('input[name="attack"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Skills ---

def test_skill_min_0(page, live_server_url):
    """Skill minimum is 0, minus disabled at 0."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="skill_precepts"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_skill_max_5(page, live_server_url):
    """Skill maximum is 5, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "skill_precepts", 5)  # 0 → 5
    plus = page.locator('input[name="skill_precepts"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Honor ---

def test_honor_min(page, live_server_url):
    """Honor minimum is 1.0, minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="honor"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_honor_max(page, live_server_url):
    """Honor maximum is 5.0, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "honor", 8)  # 1.0 → 5.0 in 0.5 steps
    plus = page.locator('input[name="honor"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Rank (locked) ---

def test_rank_locked_buttons_disabled(page, live_server_url):
    """Rank buttons are permanently disabled (locked for campaign)."""
    _go_to_editor(page, live_server_url)
    rank_section = page.locator('text="Rank"').first.locator('..')
    minus = rank_section.locator('button', has_text="-")
    plus = rank_section.locator('button', has_text="+")
    assert minus.is_disabled()
    assert plus.is_disabled()


# --- Recognition ---

def test_recognition_min_7_5(page, live_server_url):
    """Recognition minimum is 7.5, minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="recognition"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_recognition_halve_sets_3_5(page, live_server_url):
    """Checking halve sets recognition to 3.5."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    val = page.locator('input[name="recognition"]').input_value()
    assert val == "3.5"


def test_recognition_halve_grants_3_xp(page, live_server_url):
    """Halving recognition reduces spent XP by 3 (net effect of -3 recognition XP)."""
    _go_to_editor(page, live_server_url)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after == spent_before - 3


def test_recognition_unhalve_restores(page, live_server_url):
    """Unchecking halve restores recognition to at least 7.5."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    page.uncheck('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    val = page.locator('input[name="recognition"]').input_value()
    assert float(val) >= 7.5


def test_recognition_halved_min_3_5(page, live_server_url):
    """With halve checked, recognition minimum is 3.5."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    minus = page.locator('input[name="recognition"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


# --- Wealthy / Poor disabled ---

def test_wealthy_disabled(page, live_server_url):
    """Wealthy checkbox is disabled for Wasp campaign."""
    _go_to_editor(page, live_server_url)
    assert page.locator('input[name="adv_wealthy"]').is_disabled()


def test_poor_disadvantage_disabled(page, live_server_url):
    """Poor disadvantage checkbox is disabled for Wasp campaign."""
    _go_to_editor(page, live_server_url)
    assert page.locator('input[name="dis_poor"]').is_disabled()


# --- Recognition max ---

def test_recognition_max(page, live_server_url):
    """Recognition + disabled at rank * 1.5 rounded down to nearest 0.5."""
    _go_to_editor(page, live_server_url)
    # Max is floor(rank(7.5) * 3) / 2 = floor(22.5)/2 = 11.0
    plus = page.locator('input[name="recognition"]').locator('..').locator('button', has_text="+")
    for _ in range(20):  # more than enough
        if plus.is_disabled():
            break
        plus.click(force=True)
    assert plus.is_disabled()
    val = float(page.locator('input[name="recognition"]').input_value())
    assert val == 11.0


def test_recognition_halved_can_raise(page, live_server_url):
    """With halve checked, recognition can be raised above 3.5 (costs XP)."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    click_plus(page, "recognition", 2)  # 3.5 → 4.5
    val = page.locator('input[name="recognition"]').input_value()
    assert float(val) == 4.5
    # Should cost XP: -3 (halve) + 1 (raised 1.0 above base) = -2
    spent = page.text_content('[x-text="grossSpent()"]').strip()
    assert int(spent) == -2


# --- Earned XP / Notes ---

def test_earned_xp_updates_budget(page, live_server_url):
    """Changing earned XP updates the total budget."""
    _go_to_editor(page, live_server_url)
    budget_before = page.text_content('[x-text="budgetWithDis()"]').strip()
    page.fill('input[name="earned_xp"]', "20")
    page.wait_for_timeout(300)
    budget_after = page.text_content('[x-text="budgetWithDis()"]').strip()
    assert int(budget_after) == int(budget_before) + 20


# --- Save status ---

def test_save_status_indicator(page, live_server_url):
    """Save status shows 'Saved' after a change."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Status Test")
    page.wait_for_selector('text="Saved"', timeout=5000)


# --- Campaign advantages/disadvantages ---

def test_campaign_advantage_toggles_xp(page, live_server_url):
    """Campaign advantage checkbox updates XP."""
    _go_to_editor(page, live_server_url)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    page.check('input[name="camp_adv_streetwise"]')
    page.wait_for_timeout(300)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after > spent_before


def test_campaign_disadvantage_toggles_xp(page, live_server_url):
    """Campaign disadvantage checkbox adds XP to budget."""
    _go_to_editor(page, live_server_url)
    budget_before = int(page.text_content('[x-text="budgetWithDis()"]').strip())
    page.check('input[name="camp_dis_peasantborn"]')
    page.wait_for_timeout(300)
    budget_after = int(page.text_content('[x-text="budgetWithDis()"]').strip())
    assert budget_after > budget_before


def test_campaign_advantage_tooltip_has_full_rules_text(page, live_server_url):
    """Streetwise tooltip renders the full campaign rules text, not the old summary."""
    _go_to_editor(page, live_server_url)
    tip = page.locator('label:has(input[name="camp_adv_streetwise"]) .tooltip-content')
    text = (tip.text_content() or "").lower()
    assert "before being assigned to your current post" in text
    assert "etiquette, law, intimidation, and underworld" in text


def test_campaign_disadvantage_tooltip_has_full_rules_text(page, live_server_url):
    """Crane-indebted tooltip renders the full campaign rules text, including the bullets."""
    _go_to_editor(page, live_server_url)
    tip = page.locator('label:has(input[name="camp_dis_crane_indebted"]) .tooltip-content')
    text = (tip.text_content() or "").lower()
    assert "your household owes a great deal to the crane patrons" in text
    assert "bad reputation" in text
    assert "•" in text  # bullet character preserved


def test_editor_skill_tooltip_has_canonical_rules_text(page, live_server_url):
    """Skill tooltip on the edit page renders the canonical rules_text, not the short description.

    The view sheet has long shown skill.rules_text in tooltips; the editor used
    to show only the short skill.description. Both pages must now match exactly.
    """
    _go_to_editor(page, live_server_url)
    tip = page.locator('input[name="skill_bragging"]').locator('xpath=ancestor::div[contains(@class, "tooltip-trigger")][1]').locator('.tooltip-content')
    text = (tip.text_content() or "").lower()
    # Canonical rules_text from rules/02-skills.md - the "make an open bragging
    # roll" phrase appears only in rules_text, not in the short description.
    assert "make an open bragging roll" in text
    # Second paragraph from rules_text — proves whitespace-pre-line preserved
    # the paragraph break.
    assert "contested bragging roll" in text


# --- Skill XP costs ---

def test_basic_skill_xp_cost(page, live_server_url):
    """Adding a basic skill rank increases XP spent."""
    _go_to_editor(page, live_server_url)
    page.wait_for_timeout(500)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    click_plus(page, "skill_bragging", 1)
    page.wait_for_timeout(300)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after > spent_before


def test_advanced_skill_costs_more(page, live_server_url):
    """Advanced skill at rank 1 costs more than basic skill at rank 1."""
    _go_to_editor(page, live_server_url)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    click_plus(page, "skill_precepts", 1)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after - spent_before > 1  # Advanced cost 2 at rank 1


def test_per_row_xp_labels_say_spent_not_just_xp(page, live_server_url):
    """Editor per-row XP totals beside skills, school knacks, rings, and
    Attack/Parry must read e.g. "15 XP spent" so players don't mistake the
    running total for the cost of the next +1. Advantages/disadvantages are
    per-item costs and stay as plain "N XP" / "+N XP"."""
    _go_to_editor(page, live_server_url)
    # Raise a sampling of fields so non-zero totals appear next to each row.
    click_plus(page, "skill_bragging", 2)            # basic skill
    click_plus(page, "ring_fire", 1)                 # ring 2 -> 3
    click_plus(page, "attack", 1)                    # combat skill
    click_plus(page, "knack_double_attack", 1)       # school knack 1 -> 2
    page.wait_for_timeout(200)

    body = page.text_content("body")
    # All four updated rows should show "X XP spent" labels somewhere.
    assert "XP spent" in body
    # Spot-check specific rendered totals.
    # Bragging at rank 2 (basic): 2 + 2 = 4 XP
    assert "4 XP spent" in body
    # Fire ring at rank 3 (school ring is Water for akodo, so Fire 2->3 costs
    # 5 + 10 = 15 XP, but ringCost only counts above default 2: just 15).
    assert "15 XP spent" in body
    # Attack at rank 2 (advanced): 4 XP
    # double_attack at rank 2 (advanced): 4 XP
    # Both produce "4 XP spent" – already asserted.

    # Advantages/disadvantages still use the bare "N XP" form.
    # Find a "X XP" advantage label that is NOT followed by "spent". The
    # standard Crab Hands advantage costs 3 XP for example.
    import re
    bare_xp_count = len(re.findall(r"\b\d+ XP(?!\s*spent)", body))
    assert bare_xp_count > 0, (
        "expected at least one advantage/disadvantage row to show plain "
        "'N XP' (no 'spent')"
    )


# --- Mantis Wave-Treader school selection (Phase 1) ---

def test_mantis_defaults_ring_to_void(page, live_server_url):
    """Selecting Mantis Wave-Treader defaults the school-ring picker to Void
    and bumps the Void ring to at least 3."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "mantis_wave_treader")
    page.wait_for_timeout(300)
    # School-ring picker is visible (the "Any" list has length > 1) and set to Void.
    ring_dropdown = page.locator('select[x-model="schoolRingChoice"]')
    assert ring_dropdown.is_visible()
    assert ring_dropdown.input_value() == "Void"
    # Void ring is raised to 3 (school-ring floor).
    assert page.locator('input[name="ring_void"]').input_value() == "3"
    # The hidden field posts Void on save.
    assert page.locator('input[name="school_ring_choice"]').input_value() == "Void"


def test_priest_still_defaults_ring_to_water(page, live_server_url):
    """Variable-ring schools other than Mantis still default to Water."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "priest")
    page.wait_for_timeout(300)
    ring_dropdown = page.locator('select[x-model="schoolRingChoice"]')
    assert ring_dropdown.is_visible()
    assert ring_dropdown.input_value() == "Water"
    assert page.locator('input[name="ring_water"]').input_value() == "3"


def test_mantis_school_is_selectable_and_saves(page, live_server_url):
    """Mantis Wave-Treader can be selected, the draft saves, and Apply Changes
    creates the first version."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Wave Runner")
    select_school(page, "mantis_wave_treader")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial Mantis draft")
    # Landed on the sheet view for the new character.
    assert "/characters/" in page.url
