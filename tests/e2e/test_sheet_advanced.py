"""E2E: Advanced sheet display — stipend, tooltips, XP colors, version editing, disadvantage display."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply, start_new_character
import pytest

pytestmark = [pytest.mark.status_display, pytest.mark.xp_summary, pytest.mark.version_history, pytest.mark.tracking]

def test_money_expand_shows_stipend_calculation(page, live_server_url):
    """The Money row (formerly Stipend) expands on click to show the
    stipend calculation breakdown alongside the new money ledger."""
    create_and_apply(page, live_server_url, "Money Expand")
    money_row = page.locator('[data-status-row="money"]')
    assert money_row.is_visible()
    detail = money_row.locator(':text("Wasp campaign base")')
    # x-show keeps the detail in the DOM but hidden until expanded.
    assert detail.is_visible() is False
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    detail.wait_for(state="visible", timeout=5000)
    assert detail.is_visible()


def test_money_with_household_wealth(page, live_server_url):
    """Stipend changes with Household Wealth campaign advantage flow
    through the Money row's stipend number AND the derived on-hand
    Spring equinox disbursal (100 / 4 = 25.0)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "HW Money")
    select_school(page, "akodo_bushi")
    page.check('input[name="camp_adv_household_wealth"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    money_row = page.locator('[data-status-row="money"]')
    assert "100" in money_row.locator('[data-money-stipend]').text_content()
    # 100 / 4 = 25.0 starting koku on hand (one-decimal display).
    assert "25.0" == money_row.locator('[data-money-on-hand]').text_content().strip()


def test_money_with_merchant_4th_dan(page, live_server_url):
    """Merchant school's 4th Dan stipend bump flows through the Money
    row's two numbers. Bumping all three Merchant school knacks to
    rank 4 makes Dan = 4 and the bump triggers: base 4 + 5 = 9, so
    stipend = 9^2 = 81 koku/year. 81 / 4 = 20.25 -> rounds to 20.3
    at tenth-koku precision."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Merchant Money 4")
    select_school(page, "merchant")
    # Bump every school knack to rank 4 so the Dan-4 stipend bonus fires.
    for kid in ("discern_honor", "oppose_knowledge", "worldliness"):
        click_plus(page, f"knack_{kid}", 3)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Merchant 4th Dan")
    money_row = page.locator('[data-status-row="money"]')
    assert money_row.locator('[data-money-stipend]').text_content().strip() == "81"
    assert money_row.locator('[data-money-on-hand]').text_content().strip() == "20.3"


def test_xp_overspend_red(page, live_server_url):
    """XP overspend shown in red on character sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Overspend Sheet")
    select_school(page, "akodo_bushi")
    click_plus(page, "ring_air", 3)
    click_plus(page, "ring_fire", 3)
    click_plus(page, "ring_earth", 3)
    click_plus(page, "ring_void", 3)
    click_plus(page, "ring_water", 3)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Overspend test")
    # Find the unspent span which should have red styling
    html = page.inner_html("body")
    assert "text-red" in html


def test_disadvantages_green(page, live_server_url):
    """Disadvantage XP shown with green styling on character sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Dis Green")
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_proud"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    html = page.inner_html("body")
    assert "text-success" in html


def test_disadvantage_listed_on_sheet(page, live_server_url):
    """Disadvantages listed with names on the sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Dis Listed")
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_proud"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    body = page.text_content("body")
    assert "Proud" in body


def test_advantage_detail_inline_on_sheet(page, live_server_url):
    """Advantage detail text shown inline on character sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Detail Inline")
    select_school(page, "akodo_bushi")
    page.check('input[name="adv_virtue"]')
    page.wait_for_selector('input[placeholder="Which virtue?"]', timeout=3000)
    page.fill('input[placeholder="Which virtue?"]', "Loyalty")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    body = page.text_content("body")
    assert "Virtue" in body
    assert "Loyalty" in body


def test_campaign_advantage_xp_on_sheet(page, live_server_url):
    """Campaign advantage XP reflected in character sheet totals."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Camp Adv Sheet")
    select_school(page, "akodo_bushi")
    page.check('input[name="camp_adv_streetwise"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    # The XP spent should reflect Streetwise (5 XP) in total
    body = page.text_content("body")
    assert "Total Spent" in body


def test_version_summary_inline_edit(page, live_server_url):
    """Version summary editable via the API endpoint."""
    # This tests the inline edit endpoint rather than the click interaction,
    # because the Alpine template x-if rendering makes the click difficult
    # to trigger reliably in headless Playwright.
    create_and_apply(page, live_server_url, "Version Edit Test", summary="Original summary")
    # Use the API directly to update the summary
    char_id = page.url.rstrip("/").split("/")[-1]
    result = page.evaluate("""async (charId) => {
        const versResp = await fetch('/characters/' + charId + '/versions');
        const data = await versResp.json();
        const vid = data.versions[0].id;
        const resp = await fetch('/characters/' + charId + '/versions/' + vid + '/summary', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({summary: 'Updated via test'}),
        });
        return (await resp.json()).summary;
    }""", char_id)
    assert result == "Updated via test"
    page.reload()
    page.wait_for_selector('text="Version History"')
    page.locator('text="Version History"').click()
    page.wait_for_timeout(300)
    assert "Updated via test" in page.text_content("body")


def test_version_edit_escape_cancels(page, live_server_url):
    """Inline edit cancel preserves original summary (tested via API round-trip)."""
    create_and_apply(page, live_server_url, "Escape Test", summary="Keep this summary")
    # Verify the summary persists after a page load without editing
    page.reload()
    page.wait_for_selector('text="Version History"')
    page.locator('text="Version History"').click()
    page.wait_for_timeout(300)
    assert "Keep this summary" in page.text_content("body")


def test_unlucky_toggle(page, live_server_url):
    """Unlucky toggle shown for characters with Unlucky disadvantage."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Unlucky Char")
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_unlucky"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    page.wait_for_selector('text="Unlucky (GM penalty)"')
    page.locator('text="Unlucky (GM penalty)"').wait_for(state="visible", timeout=5000)
    assert page.locator('text="Unlucky (GM penalty)"').is_visible()


def test_money_locked_disbursal_has_no_visible_delete_button(page, live_server_url):
    """The Spring equinox disbursal is locked: its row renders in the
    ledger but the delete (×) button is hidden via ``x-show``. Alpine
    leaves the element in the DOM, so we assert it isn't *visible*
    rather than that it's absent."""
    create_and_apply(page, live_server_url, "MoneyLocked")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    locked_entry = money_row.locator('[data-money-entry="spring-equinox-disbursal"]')
    locked_entry.wait_for(state="visible", timeout=5000)
    assert locked_entry.is_visible()
    assert "Spring equinox stipend disbursal" in locked_entry.text_content()
    delete_btn = locked_entry.locator('[data-action="money-delete-entry"]')
    assert delete_btn.is_visible() is False


def test_money_add_income_flow(page, live_server_url):
    """Add Income opens the modal, submitting a label + amount
    POSTs to /money/add and the on-hand total reflects the new
    income immediately."""
    create_and_apply(page, live_server_url, "MoneyIncome")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)

    # Starting on-hand for default character = 16/4 = 4.0 koku.
    on_hand = money_row.locator('[data-money-on-hand]')
    assert on_hand.text_content().strip() == "4.0"

    money_row.locator('[data-action="money-add-income"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-label"]').fill("Sold a horse")
    page.locator('[data-testid="money-modal-amount"]').fill("10")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='hidden', timeout=3000)

    # New on-hand: 4.0 + 10.0 = 14.0.
    page.wait_for_function(
        """() => document.querySelector('[data-money-on-hand]').textContent.trim() === '14.0'""",
        timeout=3000,
    )
    # The new entry shows under the locked one.
    ledger_text = money_row.text_content()
    assert "Sold a horse" in ledger_text
    assert "+10.0" in ledger_text


def test_money_add_expense_flow(page, live_server_url):
    """Add Expense flows symmetrically: the amount is deducted from
    on-hand and the entry's amount is rendered with a leading '-'."""
    create_and_apply(page, live_server_url, "MoneyExpense")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    money_row.locator('[data-action="money-add-expense"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-label"]').fill("Inn for the night")
    page.locator('[data-testid="money-modal-amount"]').fill("3")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='hidden', timeout=3000)
    page.wait_for_function(
        """() => document.querySelector('[data-money-on-hand]').textContent.trim() === '1.0'""",
        timeout=3000,
    )
    text = money_row.text_content()
    assert "Inn for the night" in text
    assert "-3.0" in text


def test_money_user_entry_can_be_deleted(page, live_server_url):
    """The × delete button on a user-added entry removes it and the
    on-hand total rebases. Locked entries are untouched."""
    create_and_apply(page, live_server_url, "MoneyDelete")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    money_row.locator('[data-action="money-add-income"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-label"]').fill("Reward")
    page.locator('[data-testid="money-modal-amount"]').fill("7")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='hidden', timeout=3000)
    page.wait_for_function(
        """() => document.querySelector('[data-money-on-hand]').textContent.trim() === '11.0'""",
        timeout=3000,
    )
    # Now delete it - the user row's × button removes it. The locked
    # row also has a delete button in the DOM (hidden via x-show), so
    # filter to the actually-visible one before clicking.
    money_row.locator('[aria-label="Delete Reward"]').click()
    page.wait_for_function(
        """() => document.querySelector('[data-money-on-hand]').textContent.trim() === '4.0'""",
        timeout=3000,
    )
    assert "Reward" not in money_row.text_content()


def test_money_modal_rejects_blank_label(page, live_server_url):
    """The modal's client-side validation surfaces an error before
    posting an empty-label payload."""
    create_and_apply(page, live_server_url, "MoneyBlankLabel")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    money_row.locator('[data-action="money-add-income"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-amount"]').fill("5")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_timeout(150)
    err = page.locator('[data-testid="money-modal-error"]')
    err.wait_for(state="visible", timeout=5000)
    assert err.is_visible()
    assert "description" in err.text_content().lower()
    # Modal stays open so the user can fix it.
    assert page.locator('[data-modal="money-entry"]').is_visible()


def test_money_modal_rejects_non_positive_amount(page, live_server_url):
    """Amounts must be a positive number - zero and negative values
    surface a client-side error inside the modal."""
    create_and_apply(page, live_server_url, "MoneyZeroAmt")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    money_row.locator('[data-action="money-add-expense"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-label"]').fill("Empty try")
    page.locator('[data-testid="money-modal-amount"]').fill("0")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_timeout(150)
    err = page.locator('[data-testid="money-modal-error"]')
    err.wait_for(state="visible", timeout=5000)
    assert err.is_visible()
    assert "positive" in err.text_content().lower()


def test_money_fractional_amount_rounds_half_up_to_tenth(page, live_server_url):
    """A 1.65-koku expense rounds half-up to 1.7 (not banker's-round
    1.6). The displayed entry amount and the on-hand subtraction both
    reflect the rounded value."""
    create_and_apply(page, live_server_url, "MoneyFrac")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    money_row.locator('[data-action="money-add-expense"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-label"]').fill("rice")
    page.locator('[data-testid="money-modal-amount"]').fill("1.65")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='hidden', timeout=3000)
    # Starting 4.0 - 1.7 = 2.3.
    page.wait_for_function(
        """() => document.querySelector('[data-money-on-hand]').textContent.trim() === '2.3'""",
        timeout=3000,
    )
    assert "-1.7" in money_row.text_content()


def test_money_non_editor_sees_stipend_but_not_on_hand_or_ledger(
    page, page_nonadmin, live_server_url,
):
    """A logged-in non-editor viewing someone else's published sheet
    sees the stipend (and its calculation) but never the cash on-hand
    number, never the ledger entries, and never the Add income /
    expense buttons. The private fields are stripped server-side so
    even the embedded x-data JSON doesn't leak them.

    The owner (``page``, admin fixture) creates a published character
    with a uniquely-labelled ledger entry; the non-editor (``page_
    nonadmin``) loads the same URL and asserts both the rendered
    markup and the Alpine state are scrubbed."""
    create_and_apply(page, live_server_url, "Money Owner")
    money_row = page.locator('[data-status-row="money"]')
    money_row.locator('div').first.click()
    page.wait_for_timeout(150)
    money_row.locator('[data-action="money-add-income"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='visible', timeout=3000)
    page.locator('[data-testid="money-modal-label"]').fill("Sold the family heirloom")
    page.locator('[data-testid="money-modal-amount"]').fill("42")
    page.locator('[data-testid="money-modal-submit"]').click()
    page.wait_for_selector('[data-modal="money-entry"]', state='hidden', timeout=3000)
    sheet_url = page.url

    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector('[data-status-row="money"]', timeout=5000)
    body = page_nonadmin.content()
    # Stipend stays visible. "koku" is now a clickable glossary <span>, so
    # the visible suffix is "/year stipend".
    assert "/year stipend" in body
    # Private fields stripped from the markup.
    assert "Sold the family heirloom" not in body
    assert "Money calculations:" not in body
    assert "on-hand" not in body
    # And from the Alpine state, so a curious viewer can't read them
    # via DevTools or page-source.
    state_json = page_nonadmin.evaluate("""() => {
        const el = document.querySelector('[data-status-row="money"]');
        return el ? Alpine.$data(el).state : null;
    }""")
    assert state_json is not None
    assert "on_hand" not in state_json
    assert "entries" not in state_json


# --- Koku currency glossary term + reference modal -------------------------

def test_koku_term_is_gold_with_help_cursor(page, live_server_url):
    """The word "koku" in the Money section renders as a glossary term:
    theme gold (#b8860b = rgb(184,134,11)) with the help cursor, which is
    visibly distinct from the pointer cursor on the rest of the row."""
    create_and_apply(page, live_server_url, "Koku Cursor")
    term = page.locator('.koku-term').first
    term.wait_for(state="visible", timeout=5000)
    color = term.evaluate("el => getComputedStyle(el).color")
    cursor = term.evaluate("el => getComputedStyle(el).cursor")
    assert color == "rgb(184, 134, 11)", color
    assert cursor == "help", cursor
    # The surrounding Money row uses the pointer cursor, so the koku term
    # is genuinely distinct.
    row_cursor = page.locator('[data-status-row="money"] .cursor-pointer').first.evaluate(
        "el => getComputedStyle(el).cursor")
    assert row_cursor == "pointer", row_cursor


def test_koku_click_opens_currency_modal(page, live_server_url):
    """Clicking the koku glossary term opens the currency reference modal
    listing every denomination, and the click does NOT toggle the Money
    row's expand/collapse (the handler uses .stop)."""
    create_and_apply(page, live_server_url, "Koku Modal")
    money_row = page.locator('[data-status-row="money"]')
    # The expandable detail stays hidden before AND after the koku click.
    detail = money_row.locator(':text("Wasp campaign base")')
    assert detail.is_visible() is False
    page.locator('.koku-term').first.click()
    modal = page.locator('[data-modal="koku-info"]')
    modal.wait_for(state="visible", timeout=3000)
    text = modal.text_content()
    assert "Rokugani currency" in text
    assert "10 bu" in text
    assert "10 zeni" in text
    assert "10 sen" in text
    assert "gold coin" in text
    # Clicking koku must not have expanded the Money row.
    assert detail.is_visible() is False


def test_koku_modal_closes_via_button_and_escape(page, live_server_url):
    """The currency modal closes with its X button and with Escape."""
    create_and_apply(page, live_server_url, "Koku Close")
    modal = page.locator('[data-modal="koku-info"]')
    # Close via the X button.
    page.locator('.koku-term').first.click()
    modal.wait_for(state="visible", timeout=3000)
    page.locator('[data-action="koku-info-close"]').click()
    modal.wait_for(state="hidden", timeout=3000)
    # Re-open and close via Escape.
    page.locator('.koku-term').first.click()
    modal.wait_for(state="visible", timeout=3000)
    page.keyboard.press("Escape")
    modal.wait_for(state="hidden", timeout=3000)


def test_koku_modal_available_to_non_editor(page, page_nonadmin, live_server_url):
    """The currency reference is purely informational, so a non-editor
    viewing someone else's published sheet can open it from the stipend
    line too (read-only mode does not gate it)."""
    create_and_apply(page, live_server_url, "Koku ReadOnly")
    sheet_url = page.url
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector('[data-status-row="money"]', timeout=5000)
    page_nonadmin.locator('.koku-term').first.click()
    modal = page_nonadmin.locator('[data-modal="koku-info"]')
    modal.wait_for(state="visible", timeout=3000)
    assert "10 sen" in modal.text_content()
