"""Shared helpers for e2e tests."""


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


def click_plus(page, name, times=1):
    """Click the + button for a +/- control."""
    for _ in range(times):
        page.locator(f'input[name="{name}"]').locator('..').locator('button:text("+")').click(force=True)


def click_minus(page, name, times=1):
    """Click the - button for a +/- control."""
    for _ in range(times):
        page.locator(f'input[name="{name}"]').locator('..').locator('button:text("-")').click(force=True)


def create_and_apply(page, live_server_url, name="Test Character", school="akodo_bushi",
                     summary="Initial character creation", **kwargs):
    """Create a character, select a school, optionally set fields, apply changes.

    Returns the character sheet URL after apply.
    """
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
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


def apply_changes(page, summary="Test version"):
    """Click Apply Changes, fill in the modal summary, and confirm.

    Waits for redirect to the character sheet view.
    """
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    page.fill('textarea[placeholder="Describe your changes..."]', summary)
    # Click the modal's confirm button (inside the fixed overlay)
    page.locator('div.fixed button:text("Apply Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)
