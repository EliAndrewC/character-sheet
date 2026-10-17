"""E2E: the generic probability charts page (/probabilities) and the links to
it from roll modals, roll history, the footer and the statistics modal
(probability-design/design.md)."""
from playwright.sync_api import expect
import pytest

from tests.e2e.test_roll_stats import _make, _open, _set_stats_pref

pytestmark = pytest.mark.roll_stats


def _cell(page, dice):
    return page.locator(f'[data-dice="{dice}"]')


def test_average_table_toggles_reroll_and_opens_a_chart(page_anon, live_server_url):
    """Anyone can use it: averages for 1k1..10k10 (3k7 is blank); unticking
    'Reroll 10s' changes them and the URL; a cell opens that roll's chart."""
    page = page_anon
    page.goto(f"{live_server_url}/probabilities")
    assert _cell(page, "10k10").is_visible() and _cell(page, "3k7").count() == 0
    assert _cell(page, "1k1").text_content() == "6"
    page.locator('[data-testid="pc-reroll"]').uncheck()
    expect(_cell(page, "1k1")).to_have_text("5")
    assert "reroll=0" in page.url

    _cell(page, "8k3").click()
    expect(page.locator('[data-testid="pc-modal-title"]')).to_have_text("8k3, not rerolling 10s")
    mean = int(page.locator('[data-testid="roll-stats-mean"]').text_content())
    page.locator('[data-testid="pc-modal"] [data-testid="roll-stats-better"]').check()
    assert int(page.locator('[data-testid="roll-stats-mean"]').text_content()) > mean
    page.locator('[data-testid="roll-stats-chart"] [data-bin]').nth(2).hover()
    assert "of rolls" in page.locator('[data-testid="roll-stats-detail"]').text_content()
    page.keyboard.press("Escape")
    expect(page.locator('[data-testid="pc-modal"]')).to_be_hidden()


def test_one_kept_die_explains_the_dip(page_anon, live_server_url):
    """Only one kept die with 10s rerolled gets the footnote; no bar on this
    page gets a dice / bonus split, since there are no bonuses."""
    page = page_anon
    page.goto(f"{live_server_url}/probabilities")
    note = page.locator('[data-testid="pc-modal"] [data-testid="roll-stats-one-die-note"]')
    _cell(page, "4k1").click()
    expect(note).to_be_visible()
    expect(note).to_contain_text("never total exactly 10")
    page.locator('[data-testid="roll-stats-chart"] [data-bin]').nth(1).hover()
    assert not page.locator('[data-testid="pc-modal"] [data-testid="roll-stats-split"]').is_visible()
    page.keyboard.press("Escape")
    _cell(page, "4k2").click()
    expect(page.locator('[data-testid="pc-modal-title"]')).to_have_text("4k2, rerolling 10s")
    expect(note).to_be_hidden()
    page.keyboard.press("Escape")
    page.locator('[data-testid="pc-reroll"]').uncheck()
    _cell(page, "4k1").click()
    expect(page.locator('[data-testid="pc-modal-title"]')).to_have_text("4k1, not rerolling 10s")
    expect(note).to_be_hidden()


def test_tn_table_rows_open_the_chart(page_anon, live_server_url):
    """The TN table: 1k1 reaches 10 one time in ten; without rerolls it
    never reaches 15; a row opens its chart; ?chart=tn opens on this table."""
    page = page_anon
    page.goto(f"{live_server_url}/probabilities")
    page.locator('[data-testid="pc-tab-tn"]').click()
    assert "chart=tn" in page.url
    row = page.locator('[data-row="1k1"]')
    assert row.locator("td").nth(1).text_content() == "10%"
    page.locator('[data-testid="pc-reroll"]').uncheck()
    expect(row.locator("td").nth(2)).to_have_text("0%")

    page.locator('[data-row="5k3"]').click()
    expect(page.locator('[data-testid="pc-modal-title"]')).to_have_text("5k3, not rerolling 10s")
    page.locator('[data-testid="pc-modal"] [aria-label="Close"]').click()

    page.goto(f"{live_server_url}/probabilities?chart=tn")
    assert page.locator('[data-testid="pc-tn-table"]').is_visible()
    assert not page.locator('[data-testid="pc-dice-table"]').is_visible()


def test_settings_link_lands_on_the_checkbox(page, live_server_url):
    page.goto(f"{live_server_url}/probabilities")
    page.locator('[data-testid="pc-settings-link"]').click()
    page.wait_for_url("**/profile#roll-statistics")
    assert page.evaluate("document.querySelector(':target')?.id") == "roll-statistics"
    assert page.locator('[data-testid="roll-stats-pref"]').is_visible()


def test_page_fits_a_phone(page_anon, live_server_url):
    """The wide TN table scrolls inside its own box, not the page."""
    page = page_anon
    page.set_viewport_size({"width": 375, "height": 800})
    for chart in ("dice", "tn"):
        page.goto(f"{live_server_url}/probabilities?chart={chart}")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), chart


def _chart_link_in_kebab(page, modal):
    page.locator(f'[data-modal="{modal}"] [data-action="pcp-menu"]').click()
    link = page.locator(f'[data-modal="{modal}"] [data-action="probability-chart"]')
    expect(link).to_be_visible()
    assert link.get_attribute("href") == "/probabilities" and link.get_attribute("target") == "_blank"


def test_roll_modals_link_to_the_chart(page, live_server_url):
    """Every roll modal's menu offers the chart, before and after the roll;
    so do the roll history page, the footer and the statistics modal."""
    _set_stats_pref(page, live_server_url, True)
    _make(page, live_server_url, "ChartLinks", "akodo_bushi", skills={"etiquette": 1})
    sheet = page.url
    assert page.locator('footer a[href="/probabilities"]').is_visible()

    # Before a roll: the attack and parry modals.
    page.evaluate("window._diceRoller.openAttackModal('attack')")
    _chart_link_in_kebab(page, "attack")
    page.keyboard.press("Escape")
    page.evaluate("window._diceRoller.atkModalOpen = false; window._diceRoller.openParryModal('parry')")
    _chart_link_in_kebab(page, "parry")
    page.evaluate("window._diceRoller.parryModalOpen = false")

    # After a roll: the result modal.
    page.evaluate("window._diceRoller.executeRoll('skill:etiquette', 0, null)")
    page.locator('[data-modal="dice-roller"]').wait_for(state="visible")
    page.wait_for_function("window._diceRoller.phase === 'done'", timeout=10000)
    _chart_link_in_kebab(page, "dice-roller")

    # The statistics modal and the roll history page.
    page.goto(sheet)
    _open(page, "attack")
    assert page.locator('[data-testid="roll-stats-chart-link"]').get_attribute("href") == "/probabilities"
    page.goto(sheet.rstrip("/") + "/roll-history")
    assert page.locator('[data-testid="rh-probability-link"]').is_visible()
    _set_stats_pref(page, live_server_url, False)
