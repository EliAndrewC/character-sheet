"""E2E: Advantage detail fields (text, skill selection) appear and auto-save."""

from tests.e2e.helpers import select_school, apply_changes, start_new_character
import pytest

pytestmark = pytest.mark.advantage_details

def test_higher_purpose_shows_detail_fields(page, live_server_url):
    """Checking Higher Purpose reveals text field and skill checkboxes."""

    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Purpose Test")
    select_school(page, "akodo_bushi")

    # Check Higher Purpose
    page.check('input[name="adv_higher_purpose"]')

    # Detail fields should appear
    page.wait_for_selector('input[placeholder="What is your cause?"]', timeout=3000)
    page.fill('input[placeholder="What is your cause?"]', "oppose the Shadowlands")

    # Wait for auto-save
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Reload and verify persistence
    page.reload()
    page.wait_for_selector('input[name="name"]')
    assert page.input_value('input[placeholder="What is your cause?"]') == "oppose the Shadowlands"


def test_virtue_shows_text_field(page, live_server_url):
    """Checking Virtue reveals a text field for the specific virtue."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Virtue Test")
    select_school(page, "akodo_bushi")

    page.check('input[name="adv_virtue"]')
    page.wait_for_selector('input[placeholder="Which virtue?"]', timeout=3000)
    page.fill('input[placeholder="Which virtue?"]', "Courage")
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Publish and verify on sheet
    apply_changes(page, "Added virtue")
    body = page.text_content("body")
    assert "Virtue" in body
    assert "Courage" in body


def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")


def test_higher_purpose_skill_checkboxes(page, live_server_url):
    """Higher Purpose shows skill checkboxes when checked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="adv_higher_purpose"]')
    page.wait_for_timeout(300)
    # Walk up to the editor-row wrapper (ancestor of the label, chevron,
    # and the conditional skill-checkbox detail panel) and count its
    # nested skill checkboxes. Should have at least the skill multi-select.
    row = page.locator('input[name="adv_higher_purpose"]').locator(
        'xpath=ancestor::div[contains(@class, "editor-row")][1]'
    )
    assert row.locator('input[type="checkbox"]').count() > 1


def test_specialization_full_lifecycle_multiple_rows_view_sheet_roll_modal(
    page, live_server_url,
):
    """End-to-end multi-Specialization workflow:
    1. Open editor, add two Specializations targeting different skills.
    2. Apply changes; both rows appear in the View Sheet's advantages list.
    3. Roll one of the matching skills; the modal shows the +10 alternative
       carrying that spec's text. The other spec's skill is independent.
    """
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "MultiSpec Lifecycle")
    select_school(page, "akodo_bushi")
    # Make sure both target skills have at least rank 1 so they're rollable
    # and don't trigger unskilled penalties that would mask our assertions.
    from tests.e2e.helpers import click_plus
    click_plus(page, "skill_etiquette", 1)
    click_plus(page, "skill_culture", 1)

    # Add two Specializations.
    add = page.locator('[data-testid="add-specialization"]')
    add.click()
    add.click()
    page.wait_for_timeout(150)

    row0 = page.locator('[data-testid="specialization-row-0"]')
    row0.locator('input[type="text"]').fill("Court Etiquette")
    row0.locator('select').select_option(value="etiquette")
    row1 = page.locator('[data-testid="specialization-row-1"]')
    row1.locator('input[type="text"]').fill("Tea Ceremony")
    row1.locator('select').select_option(value="culture")
    page.wait_for_timeout(150)

    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Two specs")

    # View Sheet renders one row per spec.
    body = page.text_content("body")
    assert "Court Etiquette" in body
    assert "Tea Ceremony" in body
    # Both rows labelled "Specialization" in the advantages list.
    section_start = body.index("Advantages & Disadvantages")
    section_end = body.index("XP Summary", section_start)
    section = body[section_start:section_end]
    assert section.count("Specialization") >= 2

    # Roll the Etiquette skill; the +10 alternative carries the spec text.
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="skill:etiquette"]').click()
    page.wait_for_function("""() => {
        const d = window._diceRoller;
        return d && d.phase === 'done';
    }""", timeout=10_000)
    modal = page.locator('[data-modal="dice-roller"]').text_content()
    assert "Alternative totals" in modal
    assert "Court Etiquette" in modal
    # The other spec doesn't apply on this skill.
    assert "Tea Ceremony" not in modal


def test_specialization_sub_section_lets_you_add_multiple_rows(page, live_server_url):
    """Specialization is the only advantage that may be taken multiple times.
    The editor has a dedicated sub-section with a + Add Specialization
    button; each row is a text + single-skill dropdown that costs 2 XP."""
    _go_to_editor(page, live_server_url)
    section = page.locator('[data-testid="specializations-section"]')
    assert section.is_visible()
    # No rows initially.
    assert section.locator('[data-testid^="specialization-row-"]').count() == 0
    # The Specialization checkbox in the regular advantages grid is gone.
    assert page.locator('input[name="adv_specialization"]').count() == 0

    # Add two rows.
    add_btn = page.locator('[data-testid="add-specialization"]')
    add_btn.click()
    add_btn.click()
    page.wait_for_timeout(150)
    assert section.locator('[data-testid^="specialization-row-"]').count() == 2

    row0 = section.locator('[data-testid="specialization-row-0"]')
    row0.locator('input[type="text"]').fill("Court Etiquette")
    row0.locator('select').select_option(value="etiquette")
    row1 = section.locator('[data-testid="specialization-row-1"]')
    row1.locator('input[type="text"]').fill("Loyalty Speeches")
    row1.locator('select').select_option(value="bragging")
    page.wait_for_timeout(150)

    # Each spec costs 2 XP.
    grossSpent = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert grossSpent >= 4

    # Remove the first row; XP drops by 2.
    row0.locator('[data-testid="remove-specialization-0"]').click()
    page.wait_for_timeout(150)
    assert section.locator('[data-testid^="specialization-row-"]').count() == 1
    grossSpent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert grossSpent_after == grossSpent - 2


def test_attack_specialization_checkboxes_on_attack_modal(page, live_server_url):
    """Specialization on Attack surfaces one checkbox per spec on the
    attack-modal pre-roll panel. Each checked box adds +10 to the roll
    and to the hit-chance probability table, and a labeled line shows
    in the post-roll breakdown."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "AttackSpecModal")
    select_school(page, "akodo_bushi")

    # Add two attack specs.
    add = page.locator('[data-testid="add-specialization"]')
    add.click()
    add.click()
    page.wait_for_timeout(150)
    row0 = page.locator('[data-testid="specialization-row-0"]')
    row0.locator('input[type="text"]').fill("katana")
    row0.locator('select').select_option(value="attack")
    row1 = page.locator('[data-testid="specialization-row-1"]')
    row1.locator('input[type="text"]').fill("vs cavalry")
    row1.locator('select').select_option(value="attack")
    page.wait_for_timeout(150)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Two attack specs")

    # Open the attack modal.
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)

    section = page.locator('[data-testid="attack-spec-section"]')
    assert section.is_visible()
    cb0 = page.locator('[data-testid="attack-spec-checkbox-0"]')
    cb1 = page.locator('[data-testid="attack-spec-checkbox-1"]')
    assert cb0.is_visible()
    assert cb1.is_visible()
    # Labels include the per-row sub-domain text.
    assert "katana" in section.text_content()
    assert "vs cavalry" in section.text_content()

    # Probability table climbs as each box is ticked.
    base = page.evaluate("window._diceRoller.atkHitChance(0)")
    cb0.check()
    boosted_one = page.evaluate("window._diceRoller.atkHitChance(0)")
    cb1.check()
    boosted_two = page.evaluate("window._diceRoller.atkHitChance(0)")
    assert boosted_one >= base
    assert boosted_two >= boosted_one
    # Helper returns +20 with both ticked.
    assert page.evaluate("window._diceRoller._attackSpecBonus()") == 20

    # Roll. Both spec bonuses are stamped onto the formula and the
    # post-roll breakdown surfaces the labeled +20 entry.
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.atkPhase === 'result'",
        timeout=10000,
    )
    result = page.evaluate("""() => ({
        bonus: window._diceRoller.formula?.attack_spec_bonus || 0,
        texts: window._diceRoller.formula?.attack_spec_applied_texts || [],
    })""")
    assert result["bonus"] == 20
    assert "katana" in result["texts"]
    assert "vs cavalry" in result["texts"]
    breakdown = page.locator('[data-testid="attack-spec-breakdown"]')
    assert breakdown.is_visible()
    assert "+20" in breakdown.text_content()


def test_attack_specialization_section_hidden_without_attack_spec(page, live_server_url):
    """No Specialization on Attack → the attack-modal section never renders.
    A spec on a non-combat skill should NOT surface the checkbox."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "NoAtkSpec")
    select_school(page, "akodo_bushi")

    add = page.locator('[data-testid="add-specialization"]')
    add.click()
    page.wait_for_timeout(150)
    row0 = page.locator('[data-testid="specialization-row-0"]')
    row0.locator('input[type="text"]').fill("Court")
    row0.locator('select').select_option(value="etiquette")
    page.wait_for_timeout(150)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Non-combat spec only")

    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    section = page.locator('[data-testid="attack-spec-section"]')
    assert not section.is_visible()


def test_attack_specialization_checkbox_visible_on_other_attack_variants(page, live_server_url):
    """The checkbox is gated on ``is_attack_type``, so it must appear on
    every attack-modal variant - here we verify it on double_attack,
    an attack-type knack that opens the attack modal."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "AtkSpecDA")
    select_school(page, "akodo_bushi")
    # Akodo's school knacks include double_attack; rank 1 is free, so the
    # knack:double_attack roll key is available without extra ranks.

    add = page.locator('[data-testid="add-specialization"]')
    add.click()
    page.wait_for_timeout(150)
    row0 = page.locator('[data-testid="specialization-row-0"]')
    row0.locator('input[type="text"]').fill("katana")
    row0.locator('select').select_option(value="attack")
    page.wait_for_timeout(150)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Attack spec + double_attack")

    page.locator('[data-roll-key="knack:double_attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert page.locator('[data-testid="attack-spec-section"]').is_visible()
    assert page.locator('[data-testid="attack-spec-checkbox-0"]').is_visible()


def test_specialization_dropdown_includes_attack_and_parry(page, live_server_url):
    """Specialization may target the Attack / Parry combat skills, not
    just the regular skill list. Pick one and verify it persists on the
    sheet's advantages list with the chosen combat skill labelled."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "AttackSpec")

    add_btn = page.locator('[data-testid="add-specialization"]')
    add_btn.click()
    page.wait_for_timeout(150)
    row = page.locator('[data-testid="specialization-row-0"]')

    # The dropdown carries options for the combat skills.
    select_handle = row.locator('select')
    option_values = select_handle.evaluate(
        "el => Array.from(el.options).map(o => o.value)"
    )
    assert "attack" in option_values
    assert "parry" in option_values

    row.locator('input[type="text"]').fill("Katana")
    select_handle.select_option(value="attack")
    page.wait_for_timeout(150)
    page.wait_for_selector('text="Saved"', timeout=5000)

    apply_changes(page, "Combat spec")
    body = page.text_content("body")
    # The sheet's advantages list shows the spec text and the combat-skill
    # name in parens (same shape as a regular skill spec).
    section_start = body.index("Advantages & Disadvantages")
    section_end = body.index("XP Summary", section_start)
    section = body[section_start:section_end]
    assert "Specialization" in section
    assert "Katana" in section
    assert "Attack" in section


def test_dark_secret_shows_fields(page, live_server_url):
    """Dark Secret shows text field and player dropdown."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="dis_dark_secret"]')
    page.wait_for_selector('input[placeholder="What is your secret?"]', timeout=3000)
    assert page.locator('input[placeholder="What is your secret?"]').is_visible()
    assert page.locator('select', has=page.locator('option:text("Select player who knows...")')).is_visible()


def test_jealousy_shows_text(page, live_server_url):
    """Jealousy shows text field when checked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="dis_jealousy"]')
    page.wait_for_selector('input[placeholder="Which skill do you measure yourself by?"]', timeout=3000)


def test_good_reputation_shows_text(page, live_server_url):
    """Good Reputation shows text field when checked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="adv_good_reputation"]')
    page.wait_for_selector('input[placeholder="What are you known for?"]', timeout=3000)


def test_bad_reputation_shows_text(page, live_server_url):
    """Bad Reputation (disadvantage) shows text field when checked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="dis_bad_reputation"]')
    # The second "What are you known for?" field (first is for good_reputation advantage)
    page.wait_for_timeout(300)
    fields = page.locator('input[placeholder="What are you known for?"]')
    assert fields.last.is_visible()


def test_unconventional_shows_text(page, live_server_url):
    """Unconventional shows text field when checked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="dis_unconventional"]')
    page.wait_for_selector('input[placeholder="What aspect of bushido?"]', timeout=3000)


def test_detail_hidden_when_unchecked(page, live_server_url):
    """Detail fields hidden when advantage is unchecked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="adv_virtue"]')
    page.wait_for_selector('input[placeholder="Which virtue?"]', timeout=3000)
    page.uncheck('input[name="adv_virtue"]')
    page.wait_for_timeout(300)
    assert not page.locator('input[placeholder="Which virtue?"]').is_visible()
