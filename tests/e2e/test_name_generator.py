"""E2E: name generator icon + modal on the edit page.

Covers the icon visibility, modal open/close, reroll, gender switch, and
the three name-replacement paths: default placeholder, single word, and
multi-word ("<family> <personal>" or "<family> no <house> <personal>").
"""

import pytest

from tests.e2e.helpers import start_new_character

pytestmark = [pytest.mark.name_generator]


def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def _open_name_modal(page):
    page.locator('[data-action="open-name-modal"]').click()
    page.wait_for_selector('[data-modal="name"]', state="visible", timeout=3000)
    # Wait until the first name has actually loaded (text stops being "...").
    page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-field="name-result"]');
            return el && el.textContent && el.textContent.trim() && el.textContent.trim() !== '...';
        }""",
        timeout=5000,
    )


def _current_name_in_modal(page):
    return page.locator('[data-field="name-result"]').inner_text().strip()


# ---------------------------------------------------------------------------
# Icon + modal basics
# ---------------------------------------------------------------------------


def test_generator_icon_visible(page, live_server_url):
    _go_to_editor(page, live_server_url)
    icon = page.locator('[data-action="open-name-modal"]')
    assert icon.is_visible()


def test_modal_opens_with_a_name_and_explanation(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_name_modal(page)
    name = _current_name_in_modal(page)
    explanation = page.locator('[data-field="name-explanation"]').inner_text().strip()
    assert name
    assert explanation
    # Default gender is male
    assert page.locator('[data-field="name-gender"]').input_value() == "male"


def test_modal_closes_on_cancel(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_name_modal(page)
    page.locator('[data-action="cancel-name"]').click()
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)


def test_modal_closes_on_escape(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_name_modal(page)
    page.keyboard.press("Escape")
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)


def test_reroll_changes_the_name(page, live_server_url):
    """Clicking reroll repeatedly should land on at least one different
    name within a few tries. With ~100 options in the pool, two rolls
    colliding 20 times in a row is essentially impossible."""
    _go_to_editor(page, live_server_url)
    _open_name_modal(page)
    first = _current_name_in_modal(page)
    for _ in range(20):
        page.locator('[data-action="reroll-name"]').click()
        page.wait_for_function(
            """(prev) => {
                const el = document.querySelector('[data-field="name-result"]');
                const t = el && el.textContent && el.textContent.trim();
                return t && t !== '...' && t !== prev;
            }""",
            arg=first,
            timeout=5000,
        )
        if _current_name_in_modal(page) != first:
            return
    assert False, "reroll never produced a different name"


def test_switching_to_female_refetches_from_female_endpoint(page, live_server_url):
    """Selecting female should trigger a fetch to the female endpoint and
    display a non-empty name once it lands."""
    _go_to_editor(page, live_server_url)
    _open_name_modal(page)
    # Watch for the next /api/names/random request and confirm it carries
    # gender=female.
    with page.expect_response(
        lambda r: "/api/names/random" in r.url and "gender=female" in r.url,
        timeout=5000,
    ) as resp_info:
        page.locator('[data-field="name-gender"]').select_option("female")
    resp = resp_info.value
    assert resp.status == 200
    assert resp.json()["gender"] == "female"
    # And the modal eventually shows the name from that response.
    page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-field="name-result"]');
            return el && el.textContent && el.textContent.trim() && el.textContent.trim() !== '...';
        }""",
        timeout=5000,
    )
    assert _current_name_in_modal(page)


# ---------------------------------------------------------------------------
# Apply: name replacement logic
# ---------------------------------------------------------------------------


def test_apply_replaces_default_placeholder_entirely(page, live_server_url):
    """The new-character placeholder "New Character" is treated as default."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "New Character")
    _open_name_modal(page)
    chosen = _current_name_in_modal(page)
    page.locator('[data-action="apply-name"]').click()
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)
    assert page.locator('input[name="name"]').input_value() == chosen


def test_apply_replaces_single_word_entirely(page, live_server_url):
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Kenshiro")
    _open_name_modal(page)
    chosen = _current_name_in_modal(page)
    page.locator('[data-action="apply-name"]').click()
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)
    assert page.locator('input[name="name"]').input_value() == chosen


def test_apply_replaces_only_personal_name_for_two_word_name(page, live_server_url):
    """Family name first, personal name last: 'Mirumoto Daini' -> 'Mirumoto <new>'."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Mirumoto Daini")
    _open_name_modal(page)
    chosen = _current_name_in_modal(page)
    page.locator('[data-action="apply-name"]').click()
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)
    assert page.locator('input[name="name"]').input_value() == f"Mirumoto {chosen}"


def test_apply_replaces_only_personal_name_for_no_house_form(page, live_server_url):
    """'Mirumoto no Ryusei Yasunobu' -> 'Mirumoto no Ryusei <new>'."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Mirumoto no Ryusei Yasunobu")
    _open_name_modal(page)
    chosen = _current_name_in_modal(page)
    page.locator('[data-action="apply-name"]').click()
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)
    assert page.locator('input[name="name"]').input_value() == f"Mirumoto no Ryusei {chosen}"


def test_apply_replaces_empty_field_entirely(page, live_server_url):
    """A blank name field is treated the same as the default placeholder."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "")
    _open_name_modal(page)
    chosen = _current_name_in_modal(page)
    page.locator('[data-action="apply-name"]').click()
    # The generator modal closes but the explanation modal opens right after.
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)
    assert page.locator('input[name="name"]').input_value() == chosen


# ---------------------------------------------------------------------------
# Apply also opens the explanation modal pre-populated
# ---------------------------------------------------------------------------


def test_apply_auto_opens_explanation_modal(page, live_server_url):
    """After "Use this name", the explanation modal should pop open with
    the generated explanation pre-filled into the textarea."""
    _go_to_editor(page, live_server_url)
    _open_name_modal(page)
    explanation_shown = page.locator('[data-field="name-explanation"]').inner_text().strip()
    page.locator('[data-action="apply-name"]').click()
    # Generator modal goes away, explanation modal comes up.
    page.wait_for_selector('[data-modal="name"]', state="hidden", timeout=3000)
    page.wait_for_selector('[data-modal="name-explanation"]', state="visible", timeout=3000)
    textarea_value = page.locator('[data-field="name-explanation-text"]').input_value().strip()
    assert textarea_value == explanation_shown

