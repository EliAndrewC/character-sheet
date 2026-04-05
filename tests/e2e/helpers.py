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
