"""E2E: GM group money-awards page (inline individual + mass awards)."""

import uuid
import pytest

from tests.e2e.helpers import create_and_apply

pytestmark = [pytest.mark.groups]


def _make_money_group(page, live_server_url, names):
    """Create a uniquely-named gaming group, drop ``names`` into it, and
    land on its money-awards page. Returns the money-page URL."""
    gname = "Money-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    for nm in names:
        create_and_apply(page, live_server_url, name=nm, school="akodo_bushi")
        page.goto(page.url + "/edit")
        page.wait_for_selector('select[name="gaming_group_id"]')
        page.locator('select[name="gaming_group_id"]').select_option(label=gname)
        page.wait_for_timeout(400)  # let setGroup() round-trip

    # Reach the money page via the group summary's GM link.
    page.goto(live_server_url)
    page.locator('[data-testid="group-link"]', has_text=gname).first.click()
    page.wait_for_url("**/groups/**")
    page.locator('[data-testid="group-money-link"]').click()
    page.wait_for_url("**/groups/**/money")
    return page.url


def _card(page, name):
    return page.locator('[data-group-money-card]', has_text=name)


def _on_hand(page, name):
    txt = _card(page, name).locator('[data-testid="on-hand"]').first.text_content()
    return float(txt.strip())


def test_mass_award_updates_all_characters_inline(page, live_server_url):
    """A mass award adds the same income entry to every character and
    refreshes each on-hand total inline (no page reload)."""
    _make_money_group(page, live_server_url, ["MassAlpha", "MassBravo"])
    before_a = _on_hand(page, "MassAlpha")
    before_b = _on_hand(page, "MassBravo")
    page.evaluate("window.__noReload = true")

    page.fill('[data-testid="mass-label"]', "Winter stipend")
    page.fill('[data-testid="mass-amount"]', "10")
    page.locator('[data-testid="mass-award-btn"]').click()
    page.wait_for_selector('[data-testid="mass-ok"]', state="visible", timeout=5000)

    assert abs(_on_hand(page, "MassAlpha") - (before_a + 10)) < 0.05
    assert abs(_on_hand(page, "MassBravo") - (before_b + 10)) < 0.05
    assert "Winter stipend" in _card(page, "MassAlpha").text_content()
    assert "Winter stipend" in _card(page, "MassBravo").text_content()
    # No full reload happened - the sentinel survives.
    assert page.evaluate("window.__noReload") is True


def test_individual_award_updates_only_that_character_inline(page, live_server_url):
    """An inline individual award updates only the targeted character's
    ledger + on-hand; the others are untouched, and there's no reload."""
    _make_money_group(page, live_server_url, ["SoloPC", "BystanderPC"])
    before_solo = _on_hand(page, "SoloPC")
    before_by = _on_hand(page, "BystanderPC")
    page.evaluate("window.__noReload = true")

    card = _card(page, "SoloPC")
    card.locator('[data-testid="row-label"]').fill("Bounty payout")
    card.locator('[data-testid="row-amount"]').fill("7")
    card.locator('[data-testid="row-award-btn"]').click()
    card.locator('[data-testid="ledger-entry"]', has_text="Bounty payout").wait_for(
        state="visible", timeout=5000)

    assert abs(_on_hand(page, "SoloPC") - (before_solo + 7)) < 0.05
    assert abs(_on_hand(page, "BystanderPC") - before_by) < 0.05
    assert "Bounty payout" not in _card(page, "BystanderPC").text_content()
    assert page.evaluate("window.__noReload") is True


def _award_one(page, name, label, amount):
    """Make an individual award to a named character's card."""
    card = _card(page, name)
    card.locator('[data-testid="row-label"]').fill(label)
    card.locator('[data-testid="row-amount"]').fill(str(amount))
    card.locator('[data-testid="row-award-btn"]').click()
    card.locator('[data-testid="ledger-entry"]', has_text=label).wait_for(
        state="visible", timeout=5000)


def test_edit_existing_award_inline(page, live_server_url):
    """An existing entry can be edited in place; label + amount + on-hand
    update inline with no reload."""
    _make_money_group(page, live_server_url, ["EditMe"])
    _award_one(page, "EditMe", "Initial award", 5)
    before = _on_hand(page, "EditMe")  # includes the +5 just awarded
    page.evaluate("window.__noReload = true")

    row = _card(page, "EditMe").locator(
        '[data-testid="ledger-entry"]', has_text="Initial award")
    row.locator('[data-testid="entry-edit"]').click()
    row.locator('[data-testid="entry-edit-label"]').fill("Corrected award")
    row.locator('[data-testid="entry-edit-amount"]').fill("8")
    row.locator('[data-testid="entry-edit-save"]').click()

    _card(page, "EditMe").locator(
        '[data-testid="ledger-entry"]', has_text="Corrected award").wait_for(
        state="visible", timeout=5000)
    card_text = _card(page, "EditMe").text_content()
    assert "Initial award" not in card_text
    assert "+8" in card_text
    # 5 -> 8 raises on-hand by 3.
    assert abs(_on_hand(page, "EditMe") - (before + 3)) < 0.05
    assert page.evaluate("window.__noReload") is True


def test_delete_existing_award_inline(page, live_server_url):
    """An existing entry can be deleted (with an inline confirm); it
    disappears and on-hand drops, with no reload."""
    _make_money_group(page, live_server_url, ["DeleteMe"])
    _award_one(page, "DeleteMe", "Mistaken award", 6)
    before = _on_hand(page, "DeleteMe")
    page.evaluate("window.__noReload = true")

    row = _card(page, "DeleteMe").locator(
        '[data-testid="ledger-entry"]', has_text="Mistaken award")
    row.locator('[data-testid="entry-delete"]').click()
    row.locator('[data-testid="entry-delete-confirm"]').click()

    _card(page, "DeleteMe").locator(
        '[data-testid="ledger-entry"]', has_text="Mistaken award").wait_for(
        state="detached", timeout=5000)
    assert abs(_on_hand(page, "DeleteMe") - (before - 6)) < 0.05
    assert page.evaluate("window.__noReload") is True


def test_locked_disbursal_has_no_edit_or_delete(page, live_server_url):
    """The computed Spring equinox disbursal row offers no edit/delete."""
    _make_money_group(page, live_server_url, ["LockedOnly"])
    card = _card(page, "LockedOnly")
    # The only entry is the locked disbursal; it has no edit/delete controls.
    assert card.locator('[data-testid="entry-edit"]').count() == 0
    assert card.locator('[data-testid="entry-delete"]').count() == 0


def test_money_page_is_admin_only(page, page_nonadmin, live_server_url):
    """The GM link is hidden from non-admins and the money page itself
    rejects them."""
    money_url = _make_money_group(page, live_server_url, ["AdminOnlyPC"])
    summary_url = money_url.rsplit("/money", 1)[0]

    page_nonadmin.goto(summary_url)
    assert page_nonadmin.locator('[data-testid="group-money-link"]').count() == 0

    page_nonadmin.goto(money_url)
    assert "Admin access required" in page_nonadmin.content()
