"""E2E: drill-down "Show changes" panel inside the version-history block.

Each non-first version on the View Sheet exposes a "Show changes" button
that loads an HTMX partial summarising what changed since the prior
version. The partial groups changes by category (Skills, Rings, etc.),
and rich-text section edits are summarised as "section content updated"
rather than dumping the raw HTML.
"""

import pytest
from tests.e2e.helpers import (
    apply_changes, click_plus, select_school, start_new_character,
)

pytestmark = [pytest.mark.version_history]


def _character_with_two_versions(page, live_server_url, name="DiffTest"):
    """Create a character, publish v1, then bump a ring, raise a skill,
    add an advantage, and publish v2. The drill-down on v2 will then
    contain at least Rings, Skills, and Advantages categories - enough
    surface for the grouping tests."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial creation")  # v1
    sheet_url = page.url

    # v2 - several distinct changes so at least three category headers appear.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    click_plus(page, "ring_air", 1)
    click_plus(page, "skill_bragging", 1)
    page.check('input[name="adv_charming"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Bumped Air, learned Bragging, added Charming")

    return sheet_url


def _expand_version_history(page):
    page.locator('text="Version History"').click()
    page.wait_for_timeout(200)


def test_show_changes_button_hidden_on_first_version(page, live_server_url):
    """The chronologically first version has no prior to diff against,
    so its row must not render a Show changes button."""
    _character_with_two_versions(page, live_server_url, "FirstVHidden")
    _expand_version_history(page)

    show_btns = page.locator('[data-action="show-changes"]')
    # Two versions exist; only v2 should show the button.
    assert show_btns.count() == 1


def test_show_changes_loads_diff_partial(page, live_server_url):
    """Clicking the button HTMX-loads the diff partial. After the request
    settles we should see at least one expected change line ('Air: 2 → 3'
    from the +1 Air bump in the seed)."""
    _character_with_two_versions(page, live_server_url, "LoadsDiff")
    _expand_version_history(page)

    page.locator('[data-action="show-changes"]').click()
    # Wait for HTMX to inject content.
    page.wait_for_selector('[data-version-diff]', timeout=3000)

    body = page.locator('[data-version-diff]').inner_text()
    assert "Air" in body and "→" in body
    # The bumped value should appear too.
    assert "2" in body and "3" in body


def test_show_changes_groups_by_category(page, live_server_url):
    """The partial uses category headers (Rings, Skills, Advantages...).
    The seed touches Rings, Skills, and Advantages, so all three header
    blocks must be present."""
    _character_with_two_versions(page, live_server_url, "Categories")
    _expand_version_history(page)

    page.locator('[data-action="show-changes"]').click()
    page.wait_for_selector('[data-version-diff]', timeout=3000)

    # Read the category names from the data attribute (the visible text
    # is uppercased by Tailwind, so comparing inner text would be brittle).
    categories = page.locator('[data-diff-category]').evaluate_all(
        "els => els.map(e => e.dataset.diffCategory)"
    )
    assert "Rings" in categories
    assert "Skills" in categories
    assert "Advantages" in categories


def _flush_autosave(page):
    """Force the debounced autosave (mirrors test_sections.py helper)."""
    page.evaluate(
        "(async () => {"
        "  const root = document.querySelector('[x-data=\"characterForm()\"]');"
        "  const data = window.Alpine.$data(root);"
        "  if (data._saveTimeout) clearTimeout(data._saveTimeout);"
        "  data._dirty = true;"
        "  await data.doSave();"
        "})()"
    )
    page.wait_for_timeout(200)


def test_show_changes_section_edit_renders_as_content_updated(page, live_server_url):
    """Editing a rich-text section between two versions must show as
    'section content updated' in the diff, not as a dumped HTML blob.
    Rich-text edits are too noisy to render verbatim."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "SectionEdit")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Add a section with content, publish v1.
    page.locator('#add-section-btn').click()
    page.wait_for_function(
        "document.querySelectorAll('#sections-container > div').length === 1"
    )
    card = page.locator('#sections-container > div').first
    card.locator('input.section-label').fill("Backstory")
    card.locator('.ql-editor').click()
    card.locator('.ql-editor').fill("Born in winter.")
    _flush_autosave(page)
    apply_changes(page, "Initial with Backstory")

    # Edit the section's body, publish v2.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('#add-section-btn')
    card = page.locator('#sections-container > div').first
    card.locator('.ql-editor').click()
    card.locator('.ql-editor').fill("Adopted by Akodo.")
    _flush_autosave(page)
    apply_changes(page, "Updated Backstory")

    _expand_version_history(page)
    page.locator('[data-action="show-changes"]').click()
    page.wait_for_selector('[data-version-diff]', timeout=3000)

    body = page.locator('[data-version-diff]').inner_text()
    assert "Backstory" in body
    assert "section content updated" in body
    # Crucially, neither the old nor the new prose appears.
    assert "Born in winter" not in body
    assert "Adopted by Akodo" not in body


def test_show_changes_collapses_on_second_click(page, live_server_url):
    """The toggle should collapse the panel on a second click. Alpine
    drives visibility; HTMX only fetched once but the cached HTML stays
    in the DOM."""
    _character_with_two_versions(page, live_server_url, "Toggle")
    _expand_version_history(page)

    btn = page.locator('[data-action="show-changes"]')
    btn.click()
    page.wait_for_selector('[data-version-diff]', timeout=3000)
    assert page.locator('[data-version-diff]').is_visible()

    btn.click()
    page.wait_for_timeout(200)
    assert not page.locator('[data-version-diff]').is_visible()


def test_diff_endpoint_returns_403_for_non_editor(
    page, page_nonadmin, live_server_url
):
    """The diff endpoint duplicates the editor permission gate (the
    version-history block on the sheet is already hidden for
    non-editors, but a direct fetch must also 403)."""
    sheet_url = _character_with_two_versions(page, live_server_url, "PermGate")
    char_id = sheet_url.rstrip("/").split("/")[-1]

    # Find a version_id we can hit. Versions endpoint returns DESC by
    # version_number, so the first entry is the latest (v2).
    api_resp = page.evaluate(
        f"() => fetch('/characters/{char_id}/versions').then(r => r.json())"
    )
    v2_id = api_resp["versions"][0]["id"]
    assert api_resp["versions"][0]["version_number"] == 2

    # Navigate the nonadmin page to the live origin first so its fetch
    # picks up the X-Test-User context header set by the fixture.
    page_nonadmin.goto(live_server_url)
    status = page_nonadmin.evaluate(
        f"() => fetch('/characters/{char_id}/versions/{v2_id}/diff')"
        f"  .then(r => r.status)"
    )
    assert status == 403


def test_draft_diff_hidden_when_no_unpublished_changes(page, live_server_url):
    """A character with no draft changes (just-published, no edits) must
    not render the Draft changes preview block."""
    _character_with_two_versions(page, live_server_url, "NoDraft")
    # We're already on the sheet right after Apply Changes - no draft
    # changes pending.
    _expand_version_history(page)
    assert page.locator('[data-draft-diff]').count() == 0


def test_draft_diff_visible_after_editing_without_apply(page, live_server_url):
    """Editing the character (without Applying) should reveal a Draft
    changes block at the top of version history with the expected
    category headers and a representative diff line."""
    _character_with_two_versions(page, live_server_url, "DraftPreview")
    sheet_url = page.url

    # Edit the character WITHOUT applying.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    click_plus(page, "ring_water", 1)
    click_plus(page, "skill_etiquette", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Back to the sheet without going through Apply Changes.
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")

    # Version-history block auto-expands when there are draft changes -
    # no manual click required.
    block = page.locator('[data-draft-diff]')
    block.wait_for(state="visible")
    body = block.inner_text()
    assert "Draft changes" in body
    assert "→" in body
    # Category attribute is the canonical name (template uppercases the
    # visible text).
    cats = block.locator('[data-draft-diff-category]').evaluate_all(
        "els => els.map(e => e.dataset.draftDiffCategory)"
    )
    assert "Rings" in cats
    assert "Skills" in cats


def test_draft_diff_has_distinct_visual_styling(page, live_server_url):
    """The draft block must read as 'in flight' - distinct background
    from the white v# rows. We assert via class list rather than a
    pixel-level comparison so the test stays useful through theming."""
    _character_with_two_versions(page, live_server_url, "DraftStyle")
    sheet_url = page.url
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    click_plus(page, "ring_air", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")

    classes = page.locator('[data-draft-diff]').get_attribute("class") or ""
    # The class string should carry the blue accent and a left border
    # that visually flags this block as separate from the v# rows below.
    assert "blue" in classes
    assert "border-l" in classes


def test_diff_endpoint_returns_404_for_first_version(page, live_server_url):
    """v1 has no prior version, so the endpoint must 404 even for an
    editor (defense in depth: the UI button is also suppressed)."""
    sheet_url = _character_with_two_versions(page, live_server_url, "V1Gate")
    char_id = sheet_url.rstrip("/").split("/")[-1]

    versions = page.evaluate(
        f"() => fetch('/characters/{char_id}/versions').then(r => r.json())"
    )["versions"]
    v1 = next(v for v in versions if v["version_number"] == 1)

    status = page.evaluate(
        f"() => fetch('/characters/{char_id}/versions/{v1['id']}/diff')"
        f"  .then(r => r.status)"
    )
    assert status == 404
