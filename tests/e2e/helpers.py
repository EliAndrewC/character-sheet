"""Shared helpers for e2e tests."""


def start_new_character(page):
    """Click "New Character" and route through the dropdown's
    "Create a character" option. Backwards-compatible with the old
    direct-submit button in case an older build is running."""
    page.locator('button:text("New Character")').click()
    create_option = page.locator('[data-testid="new-character-option-create"]')
    # Wait briefly for Alpine to open the dropdown. If it never appears we
    # must be on the older direct-submit build, so proceed without clicking.
    try:
        create_option.wait_for(state="visible", timeout=1000)
        create_option.click()
    except Exception:
        pass


def select_school(page, school_id):
    """Select a school and wait for HTMX to load details.

    Playwright's select_option + dispatch_event doesn't reliably trigger
    Alpine's @change. We use evaluate to set the value and fire the event
    natively, which Alpine picks up.
    """
    page.evaluate(f"""() => {{
        const sel = document.querySelector('select[name="school"]');
        sel.value = '{school_id}';
        sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }}""")
    page.wait_for_selector("#school-details :text('Special Ability')", timeout=10000)


def _click_pm(page, name, sign, times):
    """Shared +/- click helper that verifies the backing input's value
    actually changed after each click. Rapid clicks during Alpine
    re-renders can otherwise be silently dropped under heavy session
    load (the DOM node gets replaced mid-click), so we retry up to a
    few times if the value didn't advance. Works for both integer
    (knacks, skills) and fractional (honor's 0.5 steps) controls.

    If the value refuses to change after a handful of retries we stop
    silently — the button may be disabled at its cap/floor, which is
    valid behavior for tests that probe boundaries."""
    input_el = page.locator(f'input[name="{name}"]')
    for _ in range(times):
        start_val = input_el.input_value() or ""
        for _ in range(10):
            input_el.locator('..').locator(f'button:text("{sign}")').click(force=True)
            if (input_el.input_value() or "") != start_val:
                break


def click_plus(page, name, times=1):
    """Click the + button for a +/- control."""
    _click_pm(page, name, "+", times)


def click_minus(page, name, times=1):
    """Click the - button for a +/- control."""
    _click_pm(page, name, "-", times)


def create_and_apply(page, live_server_url, name="Test Character", school="akodo_bushi",
                     summary="Initial character creation", **kwargs):
    """Create a character, select a school, optionally set fields, apply changes.

    Returns the character sheet URL after apply.
    """
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)

    # Apply any optional interactions
    for adv in kwargs.get("advantages", []):
        page.check(f'input[name="adv_{adv}"]')
    for dis in kwargs.get("disadvantages", []):
        page.check(f'input[name="dis_{dis}"]')

    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, summary)
    return page.url


def dismiss_wc_modal(page):
    """Close the wound-check modal if it is currently open.

    Adding light wounds auto-opens the WC modal. Tests that do not care
    about rolling a wound check call this to dismiss it and get back to
    interacting with the page underneath.
    """
    modal = page.locator('[data-modal="wound-check"]')
    if modal.count() > 0 and modal.is_visible():
        modal.locator('button', has_text="\u00d7").first.click()
        page.wait_for_timeout(100)


def add_light_wounds(page, amount, *, dismiss_wc=True):
    """Add light wounds via the + modal.

    By default also dismisses the auto-opened wound-check modal so that
    callers can continue interacting with the page.
    """
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', str(amount))
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_timeout(300)
    if dismiss_wc:
        dismiss_wc_modal(page)


def apply_changes(page, summary="Test version"):
    """Click Apply Changes, fill in the modal summary, and confirm.

    Waits for redirect to the character sheet view.
    """
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=5000)
    page.fill('textarea[placeholder="Describe your changes..."]', summary)
    # Click the modal's confirm button (inside the fixed overlay)
    page.locator('div.fixed button:text("Apply Changes")').click()
    # Use a generous timeout — under heavy session load the server can be slow
    page.wait_for_url("**/characters/*", timeout=30000)
