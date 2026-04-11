"""E2E: Advantage detail fields (text, skill selection) appear and auto-save."""

from tests.e2e.helpers import select_school, apply_changes
import pytest

pytestmark = pytest.mark.advantage_details

def test_higher_purpose_shows_detail_fields(page, live_server_url):
    """Checking Higher Purpose reveals text field and skill checkboxes."""

    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
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
    page.locator('button:text("New Character")').click()
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
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")


def test_higher_purpose_skill_checkboxes(page, live_server_url):
    """Higher Purpose shows skill checkboxes when checked."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="adv_higher_purpose"]')
    page.wait_for_timeout(300)
    # Should see skill checkboxes (at least one)
    assert page.locator('input[name="adv_higher_purpose"]').locator('..').locator('..').locator('input[type="checkbox"]').count() > 1


def test_specialization_shows_dropdown(page, live_server_url):
    """Specialization shows text field and single skill dropdown."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="adv_specialization"]')
    page.wait_for_selector('input[placeholder="What specialization?"]', timeout=3000)
    assert page.locator('input[placeholder="What specialization?"]').is_visible()
    # Should have a select dropdown for skill
    select = page.locator('select', has=page.locator('option:text("Applied to which skill?")'))
    assert select.is_visible()


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
