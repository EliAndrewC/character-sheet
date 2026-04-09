"""E2E: Draft status banners on character sheet and homepage badges."""

from tests.e2e.helpers import select_school, apply_changes, create_and_apply
import pytest

pytestmark = [pytest.mark.banners, pytest.mark.homepage]

def test_draft_banner_for_new_character(page, live_server_url):
    """Never-applied character shows 'Draft' banner."""

    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Draft Banner Test")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    # Navigate to the view sheet
    page.locator('button:text("View Sheet")').click()
    page.wait_for_selector("h1")
    assert page.locator('text="Draft"').first.is_visible()
    assert "no versions" in page.text_content("body").lower()


def test_no_banner_after_apply(page, live_server_url):
    """No banner after applying changes."""
    create_and_apply(page, live_server_url, "No Banner After Apply")
    body = page.text_content("body")
    assert "Draft changes" not in body
    assert "no versions" not in body


def test_draft_changes_banner_after_edit(page, live_server_url):
    """Banner shows 'Draft changes' after editing an applied character."""
    create_and_apply(page, live_server_url, "Banner After Edit")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Modified Name")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('button:text("View Sheet")').click()
    page.wait_for_selector("h1")
    assert "Draft changes" in page.text_content("body")


def test_homepage_draft_badge(page, live_server_url):
    """Homepage shows 'Draft' badge for never-applied character."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Homepage Draft Badge")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(live_server_url)
    card = page.locator('text="Homepage Draft Badge"').locator('..')
    assert card.locator('text="Draft"').is_visible()


def test_homepage_no_badge_after_apply(page, live_server_url):
    """Homepage shows no badge for cleanly applied character."""
    create_and_apply(page, live_server_url, "Clean Character")
    page.goto(live_server_url)
    card = page.locator('a', has=page.locator('text="Clean Character"'))
    assert not card.locator('text="Draft changes"').is_visible()


def test_homepage_draft_changes_badge(page, live_server_url):
    """Homepage shows 'Draft changes' badge for modified character."""
    create_and_apply(page, live_server_url, "Will Modify Badge")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Modified Badge")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(live_server_url)
    # Find the card for our specific character
    card = page.locator('a', has=page.locator('text="Modified Badge"'))
    assert card.locator('text="Draft changes"').is_visible()


def test_character_card_links_to_sheet(page, live_server_url):
    """Character card on homepage links to correct character sheet."""
    create_and_apply(page, live_server_url, "Card Link Test")
    page.goto(live_server_url)
    page.locator('a', has=page.locator('text="Card Link Test"')).click()
    page.wait_for_selector("h1")
    assert "Card Link Test" in page.text_content("h1")
