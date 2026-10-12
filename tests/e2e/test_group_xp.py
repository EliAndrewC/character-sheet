"""E2E: GM group XP-awards page (mass + individual awards)."""

import uuid

import pytest

from tests.e2e.helpers import create_and_apply

pytestmark = [pytest.mark.groups]


def _make_xp_group(page, live_server_url, names):
    """Create a uniquely-named gaming group, drop ``names`` into it, and
    land on its XP-awards page through the Group Summary's GM link.
    Returns ``(xp_page_url, {name: sheet_url})``."""
    gname = "XP-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    sheets = {}
    for nm in names:
        sheets[nm] = create_and_apply(page, live_server_url, name=nm, school="akodo_bushi")
        page.goto(sheets[nm] + "/edit")
        page.wait_for_selector('select[name="gaming_group_id"]')
        page.locator('select[name="gaming_group_id"]').select_option(label=gname)
        page.wait_for_timeout(400)  # let setGroup() round-trip

    page.goto(live_server_url)
    page.locator('[data-testid="group-link"]', has_text=gname).first.click()
    page.wait_for_url("**/groups/**")
    page.locator('[data-testid="group-xp-link"]').click()
    page.wait_for_url("**/groups/**/xp")
    return page.url, sheets


def _card(page, name):
    return page.locator('[data-group-xp-card]', has_text=name)


def _earned(page, name):
    return int(_card(page, name).locator('[data-testid="earned-xp"]').text_content().strip())


def _total(page, name):
    return int(_card(page, name).locator('[data-testid="total-xp"]').text_content().strip())


def test_mass_award_updates_every_character_inline(page, live_server_url):
    """After a confirm, the same XP lands on every character inline, and
    each sheet then shows it with nothing left to apply."""
    _, sheets = _make_xp_group(page, live_server_url, ["XpAlpha", "XpBravo"])
    assert _earned(page, "XpAlpha") == 0
    page.evaluate("window.__noReload = true")

    dialogs = []
    page.once("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.fill('[data-testid="mass-xp-label"]', "The Haunted Shrine")
    page.fill('[data-testid="mass-xp-amount"]', "15")
    page.locator('[data-testid="mass-xp-award-btn"]').click()
    page.wait_for_selector('[data-testid="mass-xp-ok"]', state="visible", timeout=5000)

    assert dialogs and "15 XP to all 2 characters" in dialogs[0]
    for name in ("XpAlpha", "XpBravo"):
        assert _earned(page, name) == 15
        assert _total(page, name) == 165
    assert page.evaluate("window.__noReload") is True

    page.goto(sheets["XpAlpha"])
    html = page.content()
    assert 'Total: <span class="font-mono">165</span>' in html
    assert "GM awarded 15 XP: The Haunted Shrine" in html   # its own version
    assert "has been edited since the last time" not in html


def test_mass_award_cancelled_at_the_confirm_awards_nothing(page, live_server_url):
    _make_xp_group(page, live_server_url, ["XpCancel"])
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.url.endswith("/xp/award") else None)
    page.once("dialog", lambda d: d.dismiss())
    page.fill('[data-testid="mass-xp-label"]', "Oops")
    page.fill('[data-testid="mass-xp-amount"]', "10")
    page.locator('[data-testid="mass-xp-award-btn"]').click()
    page.wait_for_timeout(500)
    assert posts == []
    page.reload()
    assert _earned(page, "XpCancel") == 0


def test_individual_award_updates_only_that_character(page, live_server_url):
    _make_xp_group(page, live_server_url, ["XpSolo", "XpBystander"])
    card = _card(page, "XpSolo")
    card.locator('[data-testid="row-xp-label"]').fill("Won the duel")
    card.locator('[data-testid="row-xp-amount"]').fill("3")
    card.locator('[data-testid="row-xp-award-btn"]').click()
    card.locator('[data-testid="row-xp-ok"]').wait_for(state="visible", timeout=5000)
    assert _earned(page, "XpSolo") == 3
    assert _earned(page, "XpBystander") == 0
    page.reload()
    assert _earned(page, "XpSolo") == 3


def test_award_validation_refuses_without_posting(page, live_server_url):
    _make_xp_group(page, live_server_url, ["XpValid"])
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.url.endswith("/xp/award") else None)
    page.fill('[data-testid="mass-xp-amount"]', "5")
    page.locator('[data-testid="mass-xp-award-btn"]').click()
    assert page.locator('[data-testid="mass-xp-error"]').inner_text() == "Enter a reason."
    page.fill('[data-testid="mass-xp-label"]', "Half")
    page.fill('[data-testid="mass-xp-amount"]', "2.5")
    page.locator('[data-testid="mass-xp-award-btn"]').click()
    assert "whole number" in page.locator('[data-testid="mass-xp-error"]').inner_text()
    assert posts == []


def test_unapplied_earned_xp_change_is_flagged(page, live_server_url):
    """A player who typed this adventure's XP into a draft would be counted
    twice by a group award; the GM sees it before awarding."""
    xp_url, sheets = _make_xp_group(page, live_server_url, ["XpSelfMarked", "XpClean"])
    page.goto(sheets["XpSelfMarked"] + "/edit")
    page.wait_for_selector('input[name="earned_xp"]')
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as saved:
        page.fill('input[name="earned_xp"]', "15")
    assert saved.value.status == 200

    page.goto(xp_url)
    warning = page.locator('[data-testid="mass-xp-warning"]')
    warning.wait_for(state="visible")
    assert "XpSelfMarked" in warning.inner_text()
    assert "XpClean" not in warning.inner_text()
    assert _card(page, "XpSelfMarked").locator('[data-testid="xp-mismatch"]').is_visible()
    assert not _card(page, "XpClean").locator('[data-testid="xp-mismatch"]').is_visible()


def test_xp_page_is_admin_only(page, page_nonadmin, live_server_url):
    xp_url, _ = _make_xp_group(page, live_server_url, ["XpAdminOnly"])
    summary_url = xp_url.rsplit("/xp", 1)[0]
    page_nonadmin.goto(summary_url)
    assert page_nonadmin.locator('[data-testid="group-xp-link"]').count() == 0
    page_nonadmin.goto(xp_url)
    assert "Admin access required" in page_nonadmin.content()


def test_xp_page_has_no_horizontal_overflow_on_a_phone(page, live_server_url):
    xp_url, _ = _make_xp_group(page, live_server_url, ["XpPhoneWithAFairlyLongName"])
    page.set_viewport_size({"width": 375, "height": 700})
    page.goto(xp_url)
    page.wait_for_selector('[data-group-xp-card]')
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert page.locator('[data-testid="mass-xp-award-btn"]').is_visible()
