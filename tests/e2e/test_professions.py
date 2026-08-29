"""E2E: the Wave Man profession - selection, ability steppers, and rolls.

A profession is taken INSTEAD of a school, so these tests exercise a
character shape nothing else in the suite covers: no school, no School
Ring, no school knacks and Dan 0. Ability numbering (W1-W10) follows
rules/09-professions.md; see profession-design/design.md.
"""

import pytest

from tests.e2e.helpers import (
    apply_changes,
    select_profession,
    select_school,
    start_new_character,
    take_profession_ability,
)

pytestmark = pytest.mark.professions


def _mock_dice(page, value):
    """Force every d10 to roll ``value`` (1-10)."""
    page.evaluate(
        f"window._origRandom = Math.random; Math.random = () => {(value - 1) / 10 + 0.01:.3f}"
    )


def _restore_dice(page):
    page.evaluate("if (window._origRandom) Math.random = window._origRandom")


def _editor(page, live_server_url, name="Wave Man"):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    return page


def _make_wave_man(page, live_server_url, name="Ronin", xp=600, abilities=()):
    """Create a published Wave Man and return their sheet URL."""
    _editor(page, live_server_url, name)
    page.fill('input[name="earned_xp"]', str(xp))
    page.locator('input[name="earned_xp"]').dispatch_event("input")
    select_profession(page, "wave_man")
    for ability_id, count in abilities:
        take_profession_ability(page, ability_id, count)
    page.wait_for_selector('text="Saved"', timeout=8000)
    apply_changes(page, "Wave Man")
    return page.url


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

def test_wave_man_is_selectable_and_shows_its_panel(page, live_server_url):
    _editor(page, live_server_url)
    select_profession(page, "wave_man")
    details = page.text_content("#school-details")
    assert "Wave Man" in details
    assert "No School Ring" in details


def test_unimplemented_professions_are_disabled(page, live_server_url):
    _editor(page, live_server_url)
    for pid in ("worker", "merchant", "priest", "ninja"):
        assert page.locator(
            f'select[name="school"] option[value="profession:{pid}"]'
        ).is_disabled()
    assert not page.locator(
        'select[name="school"] option[value="profession:wave_man"]'
    ).is_disabled()


def test_picking_a_profession_hides_the_school_ring_and_knacks(page, live_server_url):
    _editor(page, live_server_url)
    select_school(page, "kitsune_warden")   # a variable-ring school
    assert page.locator('[data-testid="school-ring-choice"]').is_visible()
    select_profession(page, "wave_man")
    assert not page.locator('[data-testid="school-ring-choice"]').is_visible()
    assert page.locator('input[name="knack_hunting"]').count() == 0


def test_all_ten_abilities_render_with_steppers(page, live_server_url):
    _editor(page, live_server_url)
    select_profession(page, "wave_man")
    section = page.locator('[data-testid="profession-abilities"]')
    assert section.locator("[data-ability]").count() == 10


def test_taking_an_ability_twice(page, live_server_url):
    _editor(page, live_server_url, "Twice")
    page.fill('input[name="earned_xp"]', "600")
    page.locator('input[name="earned_xp"]').dispatch_event("input")
    select_profession(page, "wave_man")
    take_profession_ability(page, "wave_man_round_damage", 2)
    assert page.locator('[data-count="wave_man_round_damage"]').text_content().strip() == "2"
    # The per-ability ceiling is 2, so + is now disabled for this one.
    assert page.locator('[data-action="profession-plus-wave_man_round_damage"]').is_disabled()


def test_the_allowance_ceiling_disables_every_plus(page, live_server_url):
    # A fresh character has 150 XP: exactly one pick.
    _editor(page, live_server_url, "OnePick")
    select_profession(page, "wave_man")
    page.wait_for_selector('[data-testid="profession-allowance"]')
    take_profession_ability(page, "wave_man_initiative_die", 1)
    page.wait_for_function(
        """() => document.querySelector(
            '[data-action="profession-plus-wave_man_round_damage"]').disabled""",
        timeout=8000,
    )
    label = page.locator('[data-testid="profession-allowance"]').text_content()
    assert "1 of 1 picks used" in label


def test_the_allowance_grows_with_xp(page, live_server_url):
    _editor(page, live_server_url, "MoreXp")
    select_profession(page, "wave_man")
    page.fill('input[name="earned_xp"]', "30")     # 180 total -> 3 picks
    page.locator('input[name="earned_xp"]').dispatch_event("input")
    page.wait_for_function(
        """() => document.querySelector(
            '[data-testid="profession-allowance"]')?.textContent.includes('of 3 picks')""",
        timeout=8000,
    )


def test_stepping_an_ability_back_down(page, live_server_url):
    _editor(page, live_server_url, "StepDown")
    select_profession(page, "wave_man")
    take_profession_ability(page, "wave_man_initiative_die", 1)
    page.locator('[data-action="profession-minus-wave_man_initiative_die"]').click()
    page.wait_for_function(
        """() => document.querySelector(
            '[data-count="wave_man_initiative_die"]').textContent.trim() === '0'""",
        timeout=5000,
    )
    assert page.locator(
        '[data-action="profession-minus-wave_man_initiative_die"]').is_disabled()


def test_switching_from_a_profession_to_a_school_clears_abilities(page, live_server_url):
    _editor(page, live_server_url, "BackToSchool")
    select_profession(page, "wave_man")
    take_profession_ability(page, "wave_man_initiative_die", 1)
    select_school(page, "hida_bushi")
    assert not page.locator('[data-testid="profession-abilities"]').is_visible()
    assert page.evaluate(
        "() => Object.keys(window._charForm?.professionAbilities || {}).length"
    ) in (0, None)


# ---------------------------------------------------------------------------
# View sheet
# ---------------------------------------------------------------------------

def test_sheet_shows_the_profession_panel(page, live_server_url):
    _make_wave_man(page, live_server_url, "SheetPanel",
                   abilities=[("wave_man_round_damage", 2)])
    body = page.text_content("body")
    assert "Wave Man" in body
    assert "No school selected yet" not in body
    assert page.locator('[data-testid="ability-x2-wave_man_round_damage"]').count() == 1


def test_sheet_flags_a_reference_only_ability(page, live_server_url):
    _make_wave_man(page, live_server_url, "RefOnly",
                   abilities=[("wave_man_parry_tn", 1)])
    assert page.locator(
        '[data-testid="reference-only-wave_man_parry_tn"]').count() == 1


def test_sheet_xp_card_counts_picks_not_xp(page, live_server_url):
    _make_wave_man(page, live_server_url, "XpCard",
                   abilities=[("wave_man_round_damage", 2)])
    card = page.locator('[data-xp-card="professions"]')
    assert card.count() == 1
    assert "2 /" in card.text_content()


# ---------------------------------------------------------------------------
# Rolls
# ---------------------------------------------------------------------------

def test_w6_adds_an_unkept_initiative_die(page, live_server_url):
    _make_wave_man(page, live_server_url, "W6",
                   abilities=[("wave_man_initiative_die", 2)])
    formula = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        return JSON.parse(el.textContent || '{}')['initiative'];
    }""")
    # Void 2 => 3 rolled / 2 kept normally; two copies add two rolled dice.
    assert formula["rolled"] == 5
    assert formula["kept"] == 2


def test_w7_adds_four_unkept_wound_check_dice(page, live_server_url):
    _make_wave_man(page, live_server_url, "W7",
                   abilities=[("wave_man_wound_check_dice", 2)])
    formula = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        return JSON.parse(el.textContent || '{}')['wound_check'];
    }""")
    assert formula["rolled"] == 7   # (Water 2 + 1) + 2x2
    assert formula["kept"] == 2


def _atk_data(page):
    return page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && 'atkPhase' in d) {
                return {
                    phase: d.atkPhase, total: d.atkRollTotal, hit: d.atkHit,
                    excess: d.atkExcess, extraDice: d.atkExtraDice,
                    raises: d.atkWaveManRaises, damage: d.atkDamageTotal,
                    damageRaw: d.atkDamageWaveManRaw,
                    exploded: d.waveManTensExploded,
                };
            }
        }
        return null;
    }""")


def _open_attack(page, tn):
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_timeout(200)
    menu = page.locator('[data-attack-choice-menu]')
    if menu.count() > 0 and menu.is_visible():
        menu.locator('[data-attack-choice="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('[x-data]')) {{
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'pre') {{ d.atkTN = {tn}; return; }}
        }}
    }}""")


def _roll_attack(page):
    page.locator('[data-modal="attack"]').locator(
        '[data-action="roll-attack"]').click()
    page.wait_for_function(
        """() => {
            for (const el of document.querySelectorAll('[x-data]')) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'result') return true;
            }
            return false;
        }""", timeout=10000)


def test_w1_raises_a_missing_attack_into_a_hit(page, live_server_url):
    _make_wave_man(page, live_server_url, "W1Hit",
                   abilities=[("wave_man_miss_raise", 2)])
    # Fire 2 + attack 1 = 3k2 of 1s = 2. Against TN 10 that misses by 8,
    # which two copies (+10) turn into a hit.
    _mock_dice(page, 1)
    _open_attack(page, 10)
    _roll_attack(page)
    _restore_dice(page)
    d = _atk_data(page)
    assert d["hit"] is True
    assert d["raises"] == 2
    assert d["total"] == 12
    # D11: the raise gets you to the TN and no further.
    assert d["extraDice"] == 0
    assert page.locator('[data-testid="wave-man-raise-note"]').is_visible()


def test_w1_uses_only_the_raises_it_needs(page, live_server_url):
    _make_wave_man(page, live_server_url, "W1Min",
                   abilities=[("wave_man_miss_raise", 2)])
    # 3k2 of 1s = 2 vs TN 5 misses by 3: one raise is enough.
    _mock_dice(page, 1)
    _open_attack(page, 5)
    _roll_attack(page)
    _restore_dice(page)
    d = _atk_data(page)
    assert d["hit"] is True
    assert d["raises"] == 1
    assert d["total"] == 7


def test_w1_does_not_fire_on_an_attack_that_already_hits(page, live_server_url):
    _make_wave_man(page, live_server_url, "W1NoOp",
                   abilities=[("wave_man_miss_raise", 2)])
    _mock_dice(page, 7)
    _open_attack(page, 5)
    _roll_attack(page)
    _restore_dice(page)
    d = _atk_data(page)
    assert d["hit"] is True
    assert d["raises"] == 0
    assert not page.locator('[data-testid="wave-man-raise-note"]').is_visible()
    # A roll that hit on its own keeps its excess damage dice.
    assert d["extraDice"] > 0


def test_a_character_without_w1_still_misses(page, live_server_url):
    _make_wave_man(page, live_server_url, "NoW1",
                   abilities=[("wave_man_round_damage", 1)])
    _mock_dice(page, 1)
    _open_attack(page, 10)
    _roll_attack(page)
    _restore_dice(page)
    assert _atk_data(page)["hit"] is False


def test_w2_and_w10_show_a_tell_your_gm_line(page, live_server_url):
    _make_wave_man(page, live_server_url, "RefLine",
                   abilities=[("wave_man_parry_tn", 2),
                              ("wave_man_wound_check_tn", 1)])
    _mock_dice(page, 7)
    _open_attack(page, 5)
    _roll_attack(page)
    _restore_dice(page)
    note = page.locator('[data-testid="wave-man-opponent-note"]')
    assert note.is_visible()
    text = note.text_content()
    assert "+10" in text          # two copies of W2
    assert "+5" in text           # one copy of W10


def test_w3_adds_weapon_dice_below_four(page, live_server_url):
    _make_wave_man(page, live_server_url, "W3",
                   abilities=[("wave_man_weapon_dice", 2)])
    _mock_dice(page, 7)
    _open_attack(page, 5)
    # A non-bushi Wave Man defaults to a 3k2 weapon; drop it to a knife.
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'pre') { d.atkWeaponRolled = 2; return; }
        }
    }""")
    _roll_attack(page)
    _restore_dice(page)
    parts = page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.atkCurrentDamage()?.parts || [];
        }
        return [];
    }""")
    assert any("2k0 weapon dice from Wave Man" in p for p in parts), parts


def test_w4_rounds_the_damage_total_up(page, live_server_url):
    _make_wave_man(page, live_server_url, "W4",
                   abilities=[("wave_man_round_damage", 1)])
    _mock_dice(page, 7)
    _open_attack(page, 5)
    _roll_attack(page)
    page.locator('[data-modal="attack"]').locator(
        'button:text("Make Damage Roll")').click()
    page.wait_for_function(
        """() => {
            for (const el of document.querySelectorAll('[x-data]')) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'damage-result') return true;
            }
            return false;
        }""", timeout=10000)
    _restore_dice(page)
    d = _atk_data(page)
    assert d["damageRaw"] is not None
    assert d["damage"] > d["damageRaw"]
    assert d["damage"] % 5 == 0 or (d["damageRaw"] % 5 == 0
                                    and d["damage"] == d["damageRaw"] + 3)
    assert page.locator('[data-testid="wave-man-rounding"]').is_visible()


def test_w9_toggle_appears_only_with_a_failed_parry(page, live_server_url):
    _make_wave_man(page, live_server_url, "W9",
                   abilities=[("wave_man_failed_parry_dice", 2)])
    _mock_dice(page, 7)
    _open_attack(page, 5)
    _roll_attack(page)
    _restore_dice(page)
    toggle = page.locator('[data-action="wave-man-recover-dice"]')
    assert not toggle.is_visible()
    # Set the flag through Alpine: Playwright's native check() does not
    # reliably fire Alpine's x-model binding here (same reason
    # helpers.select_school drives the dropdown through evaluate).
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') { d.atkFailedParry = true; return; }
        }
    }""")
    page.wait_for_selector('[data-action="wave-man-recover-dice"]',
                           state="visible", timeout=5000)


def test_w9_recovers_damage_dice_the_failed_parry_removed(page, live_server_url):
    _make_wave_man(page, live_server_url, "W9Dice",
                   abilities=[("wave_man_failed_parry_dice", 2)])
    _mock_dice(page, 7)
    _open_attack(page, 5)
    _roll_attack(page)
    _restore_dice(page)
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') {
                d.atkParrySkill = 5; d.atkFailedParry = true; return;
            }
        }
    }""")
    with_recovery = page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.atkCurrentDamage()?.rolled;
        }
    }""")
    without = page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') {
                d.atkWaveManRecover = false;
                return d.atkCurrentDamage()?.rolled;
            }
        }
    }""")
    # Two copies give back 4 dice, and parry skill 5 removed more than that.
    assert with_recovery - without == 4


def _add_foreign_knack(page, knack_id):
    page.locator('[data-testid="add-foreign-knack-btn"]').click()
    page.wait_for_selector('[data-testid="foreign-knack-select"]', state="visible")
    page.evaluate(f"""() => {{
        const sel = document.querySelector('[data-testid="foreign-knack-select"]');
        sel.value = '{knack_id}';
        sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }}""")
    page.wait_for_selector(f'[data-testid="foreign-knack-row-{knack_id}"]', timeout=5000)


def test_a_wave_man_can_buy_foreign_knacks(page, live_server_url):
    # D8: with no school of their own, every knack in the game is foreign.
    _editor(page, live_server_url, "ForeignKnacks")
    page.fill('input[name="earned_xp"]', "600")
    page.locator('input[name="earned_xp"]').dispatch_event("input")
    select_profession(page, "wave_man")
    _add_foreign_knack(page, "iaijutsu")
    assert page.locator('[data-testid="foreign-knack-row-iaijutsu"]').count() == 1


def test_w1_reaches_the_iaijutsu_strike(page, live_server_url):
    """D9: the Wave Man's attack scope is wider than ATTACK_TYPE_KEYS.

    Iaijutsu is deliberately excluded from ATTACK_TYPE_KEYS so a duel's
    strike keeps its own rules for every school; the Wave Man is the one
    exception, so this is the case most likely to be wired into only one
    of the two code paths.
    """
    _editor(page, live_server_url, "W1Iaijutsu")
    page.fill('input[name="earned_xp"]', "600")
    page.locator('input[name="earned_xp"]').dispatch_event("input")
    select_profession(page, "wave_man")
    _add_foreign_knack(page, "iaijutsu")
    take_profession_ability(page, "wave_man_miss_raise", 2)
    page.wait_for_selector('text="Saved"', timeout=8000)
    apply_changes(page, "W1 iaijutsu")
    formulas = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return {
            iaijutsu: data['knack:iaijutsu']?.wave_man_miss_raise || 0,
            attack: data['attack']?.wave_man_miss_raise || 0,
            parry: data['parry']?.wave_man_miss_raise || 0,
            initiative: data['initiative']?.wave_man_miss_raise || 0,
        };
    }""")
    assert formulas["iaijutsu"] == 2
    assert formulas["attack"] == 2
    assert formulas["parry"] == 0
    assert formulas["initiative"] == 0


def test_w5_explodes_a_ten_while_impaired(page, live_server_url):
    """D12/D13: Impaired suppresses the 10s reroll, but W5 frees one die
    per copy, chosen automatically."""
    _make_wave_man(page, live_server_url, "W5",
                   abilities=[("wave_man_impaired_reroll", 1)])
    # Earth 2 => impaired at 2 serious wounds. The roll formulas are
    # server-rendered, so persist the wounds and reload rather than
    # expecting the embedded JSON to follow a client-side counter.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.seriousWounds = 2;
        return t.saveTracking ? t.saveTracking() : t.save();
    }""")
    page.wait_for_timeout(800)
    page.reload()
    page.wait_for_function(
        """() => {
            const el = document.getElementById('roll-formulas');
            const f = JSON.parse(el.textContent || '{}')['attack'];
            return f && f.no_reroll_reason === 'impaired';
        }""", timeout=8000)
    freed = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const f = JSON.parse(el.textContent || '{}')['attack'];
        return { freed: f.wave_man_freed_dice, reroll: f.reroll_tens };
    }""")
    assert freed["freed"] == 1
    # The suppression itself is NOT cleared - only one die is freed.
    assert freed["reroll"] is False


def test_w5_is_absent_when_not_impaired(page, live_server_url):
    _make_wave_man(page, live_server_url, "W5Healthy",
                   abilities=[("wave_man_impaired_reroll", 2)])
    freed = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        return JSON.parse(el.textContent || '{}')['attack']
            ?.wave_man_freed_dice || 0;
    }""")
    assert freed == 0


# ---------------------------------------------------------------------------
# Read-only Roll Mode
# ---------------------------------------------------------------------------

@pytest.mark.readonly_rolls
def test_non_editor_can_walk_a_wave_man_attack_without_moving_the_sheet(
    page, page_nonadmin, live_server_url
):
    """A non-editor test-drives every Wave Man ability on the attack flow
    and the sheet's persisted counters stay exactly where they were.

    None of the Wave Man state is persistent - the raise count, the
    rounding, the recovered dice and the freed 10s are all modal-local -
    so this is really a check that nothing leaked into the tracking
    bridge on the way in.
    """
    sheet_url = _make_wave_man(
        page, live_server_url, "ReadOnlyRonin",
        abilities=[("wave_man_miss_raise", 2), ("wave_man_round_damage", 1),
                   ("wave_man_weapon_dice", 2)],
    )

    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    before = page_nonadmin.evaluate("""() => {
        const t = window._trackingBridge;
        return { vp: t.voidPoints, temp: t.tempVoidPoints,
                 lw: t.lightWounds, sw: t.seriousWounds };
    }""")

    _mock_dice(page_nonadmin, 1)
    _open_attack(page_nonadmin, 10)
    _roll_attack(page_nonadmin)
    _restore_dice(page_nonadmin)

    # The roll itself worked: W1 turned the miss into a hit.
    d = _atk_data(page_nonadmin)
    assert d["hit"] is True
    assert d["raises"] == 2
    banner = page_nonadmin.locator('[data-modal="attack"]').locator(
        '[data-testid="readonly-roll-banner"]')
    assert banner.first.is_visible()

    page_nonadmin.locator('[data-modal="attack"]').locator(
        'button:text("Make Damage Roll")').click()
    page_nonadmin.wait_for_function(
        """() => {
            for (const el of document.querySelectorAll('[x-data]')) {
                const dd = window.Alpine && window.Alpine.$data(el);
                if (dd && dd.atkPhase === 'damage-result') return true;
            }
            return false;
        }""", timeout=10000)

    after = page_nonadmin.evaluate("""() => {
        const t = window._trackingBridge;
        return { vp: t.voidPoints, temp: t.tempVoidPoints,
                 lw: t.lightWounds, sw: t.seriousWounds };
    }""")
    assert after == before

    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    persisted = page_nonadmin.evaluate("""() => {
        const t = window._trackingBridge;
        return { vp: t.voidPoints, temp: t.tempVoidPoints,
                 lw: t.lightWounds, sw: t.seriousWounds };
    }""")
    assert persisted == before


@pytest.mark.readonly_rolls
def test_non_editor_cannot_change_profession_abilities(page, page_nonadmin,
                                                       live_server_url):
    """The abilities live in the editor, which a non-editor cannot reach."""
    sheet_url = _make_wave_man(page, live_server_url, "NoEditRonin",
                               abilities=[("wave_man_round_damage", 1)])
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.locator(
        '[data-testid="profession-abilities"]').count() == 0
    page_nonadmin.goto(sheet_url + "/edit")
    assert page_nonadmin.locator(
        '[data-action="profession-plus-wave_man_round_damage"]').count() == 0
