"""E2E: Draft status banners on character sheet and homepage badges."""

from tests.e2e.helpers import select_school, apply_changes, create_and_apply, start_new_character
import pytest

pytestmark = [pytest.mark.banners, pytest.mark.homepage]

def test_draft_banner_for_new_character(page, live_server_url):
    """Never-applied character shows 'Draft' banner."""

    page.goto(live_server_url)
    start_new_character(page)
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
    """Homepage shows 'Draft' badge for never-applied character, placed at
    the bottom-right of the card so the full name has the entire top row."""
    # Distinct from the long name in test_homepage_draft_changes_badge_does_not_truncate_name
    # so the session-scoped live-server DB doesn't end up with two cards
    # the locator can't disambiguate.
    long_name = "Bayushi Hikari of the Western Marches"
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', long_name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(live_server_url)

    card = page.locator('a', has=page.locator(f'text="{long_name}"'))
    name_h2 = card.locator('h2').first
    badge = card.locator('text="Draft"').first
    assert badge.is_visible()

    # 1) Badge must sit BELOW the name row (not on the same horizontal line).
    name_box = name_h2.bounding_box()
    badge_box = badge.bounding_box()
    assert badge_box["y"] >= name_box["y"] + name_box["height"] - 2, (
        f"badge y={badge_box['y']} should be below name bottom "
        f"y={name_box['y'] + name_box['height']}"
    )

    # 2) Badge must be on the right side of the card (right-aligned).
    card_box = card.bounding_box()
    badge_right = badge_box["x"] + badge_box["width"]
    card_right = card_box["x"] + card_box["width"]
    assert card_right - badge_right < 30, (
        f"badge right edge ({badge_right}) should be near card right edge "
        f"({card_right}); badge appears to be left-aligned"
    )

    # 3) The h2 must take the full width of its parent flex row - no
    #    sibling badge competing for horizontal space.
    h2_width = name_h2.evaluate("el => el.clientWidth")
    parent_width = name_h2.evaluate("el => el.parentElement.clientWidth")
    assert parent_width - h2_width < 5, (
        f"h2 clientWidth ({h2_width}) should fill its parent "
        f"({parent_width}); something is still occupying the row"
    )


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


def test_homepage_draft_changes_badge_does_not_truncate_name(page, live_server_url):
    """The 'Draft changes' badge must not crowd out the character name.

    Regression: when the badge sat on the same row as the <h2>, longer
    character names got truncated with an ellipsis. The badge belongs at
    the bottom-right of the card so the name has the full row width.
    """
    long_name = "Akodo Tetsuko of the Eastern Provinces"
    create_and_apply(page, live_server_url, "Akodo Tetsuko Initial")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    # Edit the name to a long one so the modified badge appears AND the
    # row width pressure on the homepage card is realistic.
    page.fill('input[name="name"]', long_name)
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(live_server_url)

    card = page.locator('a', has=page.locator(f'text="{long_name}"'))
    name_h2 = card.locator('h2').first
    badge = card.locator('text="Draft changes"')
    assert badge.is_visible()

    # 1) Badge must sit BELOW the name row (not on the same horizontal line).
    name_box = name_h2.bounding_box()
    badge_box = badge.bounding_box()
    assert badge_box["y"] >= name_box["y"] + name_box["height"] - 2, (
        f"badge y={badge_box['y']} should be below name bottom "
        f"y={name_box['y'] + name_box['height']}"
    )

    # 2) Badge must be on the right side of the card (right-aligned).
    card_box = card.bounding_box()
    badge_right = badge_box["x"] + badge_box["width"]
    card_right = card_box["x"] + card_box["width"]
    # Badge right edge should be near (within ~30px of) card right edge.
    assert card_right - badge_right < 30, (
        f"badge right edge ({badge_right}) should be near card right edge "
        f"({card_right}); badge appears to be left-aligned"
    )

    # 3) The h2 must take the full width of its parent flex row - i.e. it
    #    is no longer competing with the badge for horizontal space. The
    #    name may still ellipsize if it's longer than the entire card body
    #    (a separate, intrinsic limit), but moving the badge MUST reclaim
    #    every pixel the badge previously consumed.
    h2_width = name_h2.evaluate("el => el.clientWidth")
    parent_width = name_h2.evaluate("el => el.parentElement.clientWidth")
    # Within a few px of parent width (no sibling badge eating space).
    assert parent_width - h2_width < 5, (
        f"h2 clientWidth ({h2_width}) should fill its parent "
        f"({parent_width}); something is still occupying the row"
    )


def test_character_card_links_to_sheet(page, live_server_url):
    """Character card on homepage links to correct character sheet."""
    create_and_apply(page, live_server_url, "Card Link Test")
    page.goto(live_server_url)
    page.locator('a', has=page.locator('text="Card Link Test"')).click()
    page.wait_for_selector("h1")
    assert "Card Link Test" in page.text_content("h1")
