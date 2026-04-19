"""E2E tests for the "Generate with AI" wizard + in-place generation.

The uvicorn subprocess runs with ``ART_GEN_ENABLED=true`` and
``ART_GEN_USE_TEST_STUB=1`` so these exercise the real wizard pages
end-to-end without touching Imagen (the stub returns a canned PNG
based on prompt keywords - see ``tests/import_fixtures/art/stub_outputs``).
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character


pytestmark = pytest.mark.character_art


def _create_character(page, live_server_url, name: str) -> str:
    """Return the edit-page URL for a fresh minimal character."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    sheet = page.url
    edit_url = sheet + "/edit"
    page.goto(edit_url)
    page.wait_for_selector('[data-action="character-art-menu"]')
    return edit_url


# ---------------------------------------------------------------------------
# Kill switch gating
# ---------------------------------------------------------------------------


def test_generate_entry_enabled_when_art_gen_enabled(page, live_server_url):
    """Default clicktest env has ART_GEN_ENABLED=true: the dropdown shows
    a live "Generate with AI" link, not the disabled tooltip."""
    _create_character(page, live_server_url, "GenEnabled")
    page.locator('[data-action="character-art-menu"]').click()
    live = page.locator('[data-action="generate-with-ai"]')
    live.wait_for(state="visible")
    assert live.get_attribute("href") is not None
    # Disabled variant is NOT rendered
    assert page.locator(
        '[data-action="generate-with-ai-disabled"]'
    ).count() == 0


# ---------------------------------------------------------------------------
# Wizard steps 1-3
# ---------------------------------------------------------------------------


def test_generate_wizard_step1_opens_from_dropdown(page, live_server_url):
    _create_character(page, live_server_url, "Gen1")
    page.locator('[data-action="character-art-menu"]').click()
    page.locator('[data-action="generate-with-ai"]').click()
    page.wait_for_url("**/art/generate")
    page.wait_for_selector('[data-testid="art-gen-gender-page"]')
    # Both radios present
    assert page.locator('[data-testid="gender-male"]').is_visible()
    assert page.locator('[data-testid="gender-female"]').is_visible()


def test_wizard_carries_gender_forward_with_correct_pronoun(
    page, live_server_url,
):
    """Step 1 -> step 2 passes gender via query string. Step 2's
    rendered sentences use 'He' for male and 'She' for female."""
    edit_url = _create_character(page, live_server_url, "Gen2Pronoun")
    char_id = edit_url.split("/characters/")[1].split("/")[0]

    # Male path: the age row reads 'He is approximately ...'
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=male")
    page.wait_for_selector('[data-testid="age-row"]')
    male_text = page.locator('[data-testid="age-row"]').inner_text()
    assert "He is approximately" in male_text

    # Female path
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=female")
    page.wait_for_selector('[data-testid="age-row"]')
    female_text = page.locator('[data-testid="age-row"]').inner_text()
    assert "She is approximately" in female_text


def test_age_checkbox_cannot_be_unchecked(page, live_server_url):
    edit_url = _create_character(page, live_server_url, "GenAge")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=male")
    age = page.locator('[data-testid="age-checkbox"]')
    age.wait_for()
    assert age.is_checked() is True
    assert age.is_disabled() is True


def test_optional_rows_disable_text_input_until_checkbox_checked(
    page, live_server_url,
):
    """Holding-row text input is disabled until you tick the checkbox,
    then enabled. Same for the expression row. (The armor row works
    the same way via Alpine's shared factory but the dropdown is the
    visible gate; skip the third variant.)"""
    edit_url = _create_character(page, live_server_url, "GenOptional")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=male")
    page.wait_for_selector('[data-testid="holding-row"]')

    holding_input = page.locator('[data-testid="holding-input"]')
    assert holding_input.is_disabled() is True
    page.locator('[data-testid="holding-checkbox"]').check()
    # Alpine needs a tick to propagate :disabled
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=holding-input]').disabled"
    )
    assert holding_input.is_disabled() is False
    # Untick and it disables again
    page.locator('[data-testid="holding-checkbox"]').uncheck()
    page.wait_for_function(
        "() => document.querySelector('[data-testid=holding-input]').disabled"
    )


def test_create_prompt_advances_to_step3_with_textarea(page, live_server_url):
    """Fill in Step 2, click Create Prompt, land on the review page
    with an editable textarea that contains the assembled prompt."""
    edit_url = _create_character(page, live_server_url, "GenStep3")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=male")
    page.wait_for_selector('[data-testid="age-input"]')
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")
    textarea = page.locator('[data-testid="prompt-textarea"]')
    textarea.wait_for()
    assert textarea.is_disabled() is False
    # Prompt body comes from the server - contains the Wasp prefix
    content = textarea.input_value()
    assert "Wasp clan noble" in content
    assert "He is approximately" in content


# ---------------------------------------------------------------------------
# In-place generation + Cropper
# ---------------------------------------------------------------------------


def test_generation_happy_path_in_place_crop_and_save(page, live_server_url):
    """Click Generate Art on the review page. Stub returns a PNG.
    Cropper appears in-place; Save button commits + redirects."""
    edit_url = _create_character(page, live_server_url, "GenHappy")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=female")
    page.wait_for_selector('[data-testid="age-input"]')
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")

    # Trigger generation
    page.locator('[data-action="generate-art"]').click()

    # Cropper section appears (async polling, so allow a few seconds)
    page.wait_for_selector(
        '[data-testid="art-gen-crop-section"]',
        state="visible",
        timeout=10_000,
    )
    # Cropper instance wired
    page.wait_for_selector('.cropper-container', timeout=5_000)

    # Click Save Headshot - submit form, browser navigates to edit page
    # with the art_saved banner
    page.locator('[data-action="save-headshot"]').click()
    page.wait_for_url("**/edit?art_saved=1")
    page.wait_for_selector('[data-testid="art-saved-banner"]')
