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
