"""E2E: roll statistics - the per-player average badges and the statistics
modal (probability-design/design.md)."""
import os

import pytest
from playwright.sync_api import expect

from tests.e2e.helpers import (
    apply_changes, click_plus, save_tracking, select_profession, select_school, start_new_character,
)

pytestmark = pytest.mark.roll_stats

SHOTS = os.environ.get("ROLL_STATS_SHOTS")  # a directory: save screenshots there


def _shot(page, name):
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=False)


def _set_stats_pref(page, live_server_url, on=True):
    page.goto(f"{live_server_url}/profile")
    box = page.locator('[data-testid="roll-stats-pref"]')
    box.check() if on else box.uncheck()
    page.locator('button:text("Save Changes")').click()
    page.wait_for_url("**/profile")


def _make(page, live_server_url, name, school, knacks=None, skills=None):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    for knack, rank in (knacks or {}).items():
        click_plus(page, f"knack_{knack}", rank - 1)
    for skill, rank in (skills or {}).items():
        click_plus(page, f"skill_{skill}", rank)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    page.wait_for_selector('[data-roll-key="attack"]')


def _open(page, key):
    page.locator(f'[data-roll-avg="{key}"]').click()
    modal = page.locator('[data-testid="roll-stats-modal"] [role="dialog"]')
    modal.wait_for(state="visible")
    page.locator('[data-testid="roll-stats-mean"]').wait_for(state="visible")
    return modal


def _mean(page):
    return float(page.locator('[data-testid="roll-stats-mean"]').text_content())


def test_off_by_default_no_badges(page, live_server_url):
    """Nobody sees averages until they opt in on their profile."""
    _make(page, live_server_url, "StatsOff", "akodo_bushi")
    assert page.locator("[data-roll-avg]").count() == 0
    assert page.locator('[data-testid="roll-stats-modal"]').count() == 0


def test_badges_open_the_modal_with_void_and_keep_better(page, live_server_url):
    """With the setting on: every roll row shows an average; clicking one
    opens the chart (not the roll menu); the void stepper and the
    keep-the-better toggle change the numbers; a bar explains itself."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsOn", "akodo_bushi", skills={"etiquette": 2})
    for key in ("attack", "parry", "wound_check", "ring:Fire", "skill:etiquette", "knack:feint"):
        assert page.locator(f'[data-roll-avg="{key}"]').count() == 1, key
    badge_text = page.locator('[data-roll-avg="attack"] span').text_content()
    assert badge_text.isdigit()  # whole numbers
    badge_avg = float(badge_text)
    # In the skills list the average comes before the dice: "avg 17 4k2".
    roll_text = page.locator('[data-roll-key="skill:etiquette"] .skill-row__roll').inner_text().strip()
    assert roll_text.startswith("avg"), roll_text

    _open(page, "attack")
    # The roll menu did not open underneath.
    assert not page.locator('[data-roll-menu="root"]').is_visible()
    assert _mean(page) == badge_avg
    dice0 = page.locator('[data-testid="roll-stats-dice"]').text_content()
    _shot(page, "attack-0-void")

    page.locator('[data-testid="roll-stats-void-plus"]').click()
    assert page.locator('[data-testid="roll-stats-void"]').text_content() == "1"
    assert _mean(page) > badge_avg
    assert page.locator('[data-testid="roll-stats-dice"]').text_content() != dice0
    one_void = _mean(page)

    assert page.locator('label:has([data-testid="roll-stats-better"])').inner_text().strip() == (
        "When keeping the better of two rolls")
    page.locator('[data-testid="roll-stats-better"]').check()
    assert _mean(page) > one_void
    assert "keeping the higher" in page.locator('[data-testid="roll-stats-assumptions"]').text_content()

    bar = page.locator('[data-testid="roll-stats-chart"] [data-bin]').nth(3)
    bar.hover()
    detail = page.locator('[data-testid="roll-stats-detail"]').text_content()
    assert "of rolls" in detail and "or more" in detail
    # No ability whose share varies by bar, so no dice / bonus split.
    assert not page.locator('[data-testid="roll-stats-split"]').is_visible()
    assert not page.locator('[data-testid="roll-stats-one-die-note"]').is_visible()  # 5k3
    _shot(page, "attack-1-void-better-hover")

    # Escape closes it; reopening starts from no void.
    page.keyboard.press("Escape")
    expect(page.locator('[data-testid="roll-stats-modal"] [role="dialog"]')).to_be_hidden()
    _open(page, "attack")
    assert page.locator('[data-testid="roll-stats-void"]').text_content() == "0"

    # The picker reaches any other roll.
    page.locator('[data-testid="roll-stats-key"]').select_option("skill:etiquette")
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"roll-stats-dice\"]')?.textContent.includes('Rolling')")
    # The void level carries over to the next roll, as far as it allows.
    assert page.locator('[data-testid="roll-stats-void"]').text_content() in ("0", "1")

    page.locator('[data-testid="roll-stats-modal"] [aria-label="Close"]').click()
    expect(page.locator('[data-testid="roll-stats-modal"] [role="dialog"]')).to_be_hidden()
    _set_stats_pref(page, live_server_url, False)


def test_post_roll_bonuses_are_notes_not_chart(page, live_server_url):
    """A 3rd Dan free raise is listed under the chart, not added to it."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsNotes", "courtier",
          knacks={"discern_honor": 3, "oppose_social": 3, "worldliness": 3}, skills={"tact": 2})
    _open(page, "attack")
    notes = page.locator('[data-testid="roll-stats-notes"]')
    assert notes.is_visible()
    assert "3rd Dan free raises after the roll: +5 each, up to 2" in notes.text_content()
    _set_stats_pref(page, live_server_url, False)


def test_shosuro_5th_dan_breakdown(page, live_server_url):
    """A shape-changing ability is its own part of the average and of each bar."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsShosuro", "shosuro_actor",
          knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5}, skills={"bragging": 2})
    _open(page, "skill:bragging")
    assert "5th Dan (lowest three dice)" in page.locator('[data-testid="roll-stats-parts"]').text_content()
    page.locator('[data-testid="roll-stats-chart"] [data-bin]').nth(2).hover()
    split = page.locator('[data-testid="roll-stats-split"]')
    assert split.is_visible() and "lowest three dice" in split.text_content()
    _shot(page, "shosuro-bragging")
    _set_stats_pref(page, live_server_url, False)


def test_averages_follow_impaired(page, live_server_url):
    """Becoming Impaired stops skill 10s rerolling, so the badge drops."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsImpaired", "akodo_bushi", skills={"etiquette": 3})
    badge = page.locator('[data-roll-avg="skill:etiquette"] span')
    before = float(badge.text_content())
    # Earth 2: two serious wounds impair. Take them through the sheet.
    for _ in range(2):
        page.locator('[data-action="sw-plus"]').click()
        page.wait_for_timeout(300)
    page.wait_for_function(
        f"() => parseFloat(document.querySelector('[data-roll-avg=\"skill:etiquette\"] span').textContent) < {before}",
        timeout=5000)
    _set_stats_pref(page, live_server_url, False)


@pytest.mark.parametrize("width", [375])
def test_modal_fits_a_phone(page, live_server_url, width):
    """No horizontal overflow at phone width with the modal open; tapping a
    bar shows its detail."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsPhone", "akodo_bushi")
    page.set_viewport_size({"width": width, "height": 800})
    page.reload()
    page.wait_for_selector('[data-roll-avg="attack"]')
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    _shot(page, "phone-sheet")
    # The 72px ring circles have no room for an average; the picker has them.
    assert not page.locator('[data-roll-avg="ring:Fire"]').is_visible()
    _open(page, "attack")
    assert "ring:Fire" in page.locator('[data-testid="roll-stats-key"] option').evaluate_all(
        "os => os.map(o => o.value)")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.locator('[data-testid="roll-stats-chart"] [data-bin]').nth(2).click()
    assert "of rolls" in page.locator('[data-testid="roll-stats-detail"]').text_content()
    _shot(page, "phone-modal")
    _set_stats_pref(page, live_server_url, False)


@pytest.mark.parametrize("school", ["kitsune_warden", "profession"])
def test_no_javascript_errors_with_stats_on(page, live_server_url, school):
    """Badges and the modal, stepped through every roll the character has,
    throw nothing - including for a profession character, who has no
    school for any school-derived expression to read."""
    _set_stats_pref(page, live_server_url, True)
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', f"StatsJS {school}")
    if school == "profession":
        select_profession(page)
    else:
        select_school(page, school)
    page.wait_for_timeout(300)
    ring = page.locator('select[x-model="schoolRingChoice"]')
    if ring.count() and ring.is_visible():
        ring.select_option(index=1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    sheet_url = page.url

    errors = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda msg: errors.append(f"console.error: {msg.text}") if msg.type == "error" else None)
    page.goto(sheet_url)
    page.wait_for_selector('[data-roll-avg="wound_check"]')
    _open(page, "wound_check")
    keys = page.locator('[data-testid="roll-stats-key"] option').evaluate_all("os => os.map(o => o.value)")
    assert len(keys) > 10
    for key in keys:
        page.locator('[data-testid="roll-stats-key"]').select_option(key)
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"roll-stats-modal\"]')._x_dataStack?.[0]?.loading")
        page.locator('[data-testid="roll-stats-chart"] [data-bin]').first.hover()
    assert errors == [], "\n".join(errors)
    _set_stats_pref(page, live_server_url, False)


def test_void_stepper_ignores_the_points_held(page, live_server_url):
    """Out of void points, the stepper still goes to the per-roll limit:
    the modal shows what the character can do, not this moment's pool."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsBroke", "akodo_bushi")
    save_tracking(page, voidPoints=0, tempVoidPoints=0)
    page.reload()
    page.wait_for_selector('[data-roll-avg="attack"]')
    _open(page, "attack")
    plus = page.locator('[data-testid="roll-stats-void-plus"]')
    assert plus.is_visible() and plus.is_enabled()
    plus.click()
    plus.click()
    assert page.locator('[data-testid="roll-stats-void"]').text_content() == "2"
    assert plus.is_disabled()  # lowest ring 2
    _set_stats_pref(page, live_server_url, False)


def test_isawa_ishi_3rd_dan_xk1_has_an_average(page, live_server_url):
    """The 'Spend 1 VP to add Xk1' button carries a badge; its modal shows
    the void row with the reason no more void can go on it."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "StatsIshi", "isawa_ishi",
          knacks={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3}, skills={"precepts": 3})
    badge = page.locator('[data-roll-avg="spend_vp_xk1"]')
    assert badge.is_visible()
    _open(page, "spend_vp_xk1")
    assert page.locator('[data-testid="roll-stats-dice"]').text_content() == "Rolling 3k1"
    assert page.locator('[data-testid="roll-stats-void"]').is_visible()
    assert page.locator('[data-testid="roll-stats-void-plus"]').is_disabled()
    assert "price" in page.locator('[data-testid="roll-stats-void-reason"]').text_content()
    _set_stats_pref(page, live_server_url, False)
