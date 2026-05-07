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


def test_age_field_is_bidirectional_between_sheet_and_art_form(page, live_server_url):
    """Age set on the Edit Sheet pre-fills the art-generation form, AND
    changing it on the art form propagates back to the sheet."""
    edit_url = _create_character(page, live_server_url, "AgeSync")
    char_id = edit_url.split("/characters/")[1].split("/")[0]

    # 1. Set Age=33 on the Edit Sheet.
    page.goto(edit_url)
    page.fill('input[name="age"]', "33")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.wait_for_timeout(200)

    # 2. Open the art generation form -> the Age input is pre-filled to 33.
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=male")
    page.wait_for_selector('[data-testid="age-input"]')
    age_input = page.locator('[data-testid="age-input"]')
    assert age_input.input_value() == "33"

    # 3. Change Age to 41 on the art form and submit.
    age_input.fill("41")
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")

    # 4. Back on the Edit Sheet, the Age field reflects the new value.
    page.goto(edit_url)
    page.wait_for_selector('input[name="age"]')
    assert page.locator('input[name="age"]').input_value() == "41"

    # 5. The age change must NOT count as an unapplied stat change.
    page.wait_for_timeout(200)
    assert not page.locator('[data-action="apply-changes"]').is_visible()
    assert not page.locator('[data-action="discard-changes"]').is_visible()


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


def test_download_screenshot_button_serves_the_generated_image(page, live_server_url):
    """The Download Screenshot button on the review page lets the player
    save the generated image locally without committing it as the
    headshot. This is the iterate-on-prompt workflow: generate, download
    a candidate, regenerate with a tweaked prompt, repeat until happy."""
    edit_url = _create_character(page, live_server_url, "GenDownload")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=female")
    page.wait_for_selector('[data-testid="age-input"]')
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")

    page.locator('[data-action="generate-art"]').click()
    page.wait_for_selector(
        '[data-testid="art-gen-crop-section"]', state="visible", timeout=10_000,
    )

    download_link = page.locator('[data-action="download-screenshot"]')
    assert download_link.is_visible()
    # Has an HTML download attribute so the browser saves rather than
    # navigates - filename includes the character id for sanity.
    suggested = download_link.get_attribute("download")
    assert suggested and char_id in suggested
    assert suggested.endswith(".png")
    # Clicking starts a download (Playwright helper).
    with page.expect_download() as info:
        download_link.click()
    download = info.value
    assert download.suggested_filename.endswith(".png")
    # Save Headshot button is still visible after a download (download
    # doesn't commit the headshot).
    assert page.locator('[data-action="save-headshot"]').is_visible()


def test_repeated_regenerations_do_not_accumulate_cropper_containers(page, live_server_url):
    """Players doing multiple back-to-back regenerations must always end
    up with exactly one Cropper wrapper in the DOM.

    Regression: the load-event listener attached in _initCropper had no
    {once: true}, so every regeneration where the image wasn't already
    preloaded left a stale listener. On the next image load all stale
    listeners fired together, each constructing a new Cropper - producing
    "two pictures stacked" or "transparent rectangle with no picture
    inside" once Cropper.js got confused by being layered on its own
    previous wrapper. The fix is once-fire listeners + a defensive
    cropper-destroy at the top of _initCropper."""
    edit_url = _create_character(page, live_server_url, "RegenStress")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=female")
    page.wait_for_selector('[data-testid="age-input"]')
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")

    textarea = page.locator('[data-testid="prompt-textarea"]')

    def run_one_generation():
        prev_src = page.locator('#art-gen-crop-target').get_attribute('src') or ''
        page.locator('[data-action="generate-art"]').click()
        # Wait until state lands back at 'succeeded' AND a fresh src is in
        # place AND Cropper has actually wired up (its ``.cropper-container``
        # wrapper is the signal). Without the cropper wait, this helper
        # races the $nextTick + image-load chain and can return before
        # _initCropper has finished, producing a flaky 0-vs-1 mismatch.
        import json
        prev_json = json.dumps(prev_src)
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector('[data-testid="art-gen-review-page"]');
                const data = window.Alpine && window.Alpine.$data(el);
                if (!data || data.state !== 'succeeded') return false;
                const cur = document.querySelector('#art-gen-crop-target')?.getAttribute('src');
                if (!cur || cur === {prev_json}) return false;
                return document.querySelectorAll('.cropper-container').length >= 1;
            }}""",
            timeout=15_000,
        )

    # 1st generation - default Wasp prompt.
    run_one_generation()
    assert page.locator('.cropper-container').count() == 1

    # Now do four more generations, alternating the keyword between Wasp
    # and Scorpion so the stub returns different bytes and the cache-buster
    # flips. After EACH regeneration, exactly one Cropper container must
    # exist - not 2, not "0 + a transparent overlay".
    for i, keyword in enumerate(("Scorpion", "Wasp", "Scorpion", "Wasp")):
        current = textarea.input_value()
        # Replace whichever keyword is currently in the prompt.
        edited = current.replace("Wasp", keyword).replace("wasp", keyword.lower())
        textarea.fill(edited)
        run_one_generation()
        cropper_count = page.locator('.cropper-container').count()
        assert cropper_count == 1, (
            f"after {i + 2} generations, expected exactly one .cropper-container, "
            f"got {cropper_count}"
        )


def test_re_generation_after_prompt_edit_loads_new_image(page, live_server_url):
    """After a successful first generation, editing the prompt textarea
    and clicking Generate again must load the freshly generated image.

    Regression for the bug where the staging_id-keyed image URL is
    reused across regenerations: without a cache-buster the <img> src
    string is identical to the prior render so the browser keeps the
    previous bytes and the user thinks their prompt edits were ignored.
    """
    edit_url = _create_character(page, live_server_url, "RegenEdit")
    char_id = edit_url.split("/characters/")[1].split("/")[0]
    page.goto(f"{live_server_url}/characters/{char_id}/art/generate/options?gender=female")
    page.wait_for_selector('[data-testid="age-input"]')
    page.locator('[data-action="create-prompt"]').click()
    page.wait_for_url("**/art/generate/review/**")

    # Default mad-libs prompt has "Wasp" in it - first gen returns wasp.png.
    page.locator('[data-action="generate-art"]').click()
    page.wait_for_selector(
        '[data-testid="art-gen-crop-section"]', state="visible", timeout=10_000,
    )
    page.wait_for_selector('.cropper-container', timeout=5_000)
    first_src = page.locator('#art-gen-crop-target').get_attribute('src')
    assert first_src, "first generation should set img.src"

    # Swap the clan in the prompt so the stub returns scorpion.png second time.
    textarea = page.locator('[data-testid="prompt-textarea"]')
    edited = textarea.input_value().replace("Wasp", "Scorpion").replace("wasp", "scorpion")
    assert "scorpion" in edited.lower() and "wasp" not in edited.lower(), (
        f"edit must remove all 'wasp' tokens to flip the stub keyword; got: {edited!r}"
    )
    textarea.fill(edited)

    page.locator('[data-action="generate-art"]').click()
    # Wait for the second generation cycle to land back at state='succeeded'
    # AND for the img.src to become a different non-empty string than before.
    import json
    first_src_json = json.dumps(first_src)
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-testid="art-gen-review-page"]');
            const data = window.Alpine && window.Alpine.$data(el);
            if (!data || data.state !== 'succeeded') return false;
            const img = document.querySelector('#art-gen-crop-target');
            const cur = img && img.getAttribute('src');
            return cur && cur !== {first_src_json};
        }}""",
        timeout=15_000,
    )

    second_src = page.locator('#art-gen-crop-target').get_attribute('src')
    assert second_src != first_src, (
        "second-generation img.src must differ from the first to force the "
        f"browser to fetch the new bytes; got both: {first_src!r}"
    )

    # Old Cropper instance must be torn down before the new one is created -
    # otherwise the user sees two cropper-container DIVs stacked on top of
    # each other (the old one anchored to the previous image bytes).
    assert page.locator('.cropper-container').count() == 1, (
        "expected exactly one .cropper-container after re-generation; "
        f"found {page.locator('.cropper-container').count()}"
    )
