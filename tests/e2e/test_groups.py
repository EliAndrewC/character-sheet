"""E2E: gaming groups, party effects callout, and admin manage-groups page."""

import re
import pytest

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply, start_new_character

pytestmark = [pytest.mark.groups]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_group_via_editor(page, group_name):
    """Set the gaming group via the edit form's dropdown."""
    select = page.locator('select[name="gaming_group_id"]')
    select.select_option(label=group_name)
    page.wait_for_timeout(300)  # let setGroup() round-trip


def _create_admin_group(page, name):
    """Create a new gaming group via the admin page."""
    page.goto(f"{page.context.pages[0].url.split('/admin')[0].split('/characters')[0].split('//')[0]}//{page.context.pages[0].url.split('//')[1].split('/')[0]}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', name)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Set group via editor
# ---------------------------------------------------------------------------


def test_set_group_via_editor_persists(page, live_server_url):
    """Selecting a gaming group in the editor saves immediately and survives a reload."""
    create_and_apply(page, live_server_url, name="GroupSetTest1", school="akodo_bushi")
    # Now go back to the editor
    edit_url = page.url + "/edit"
    page.goto(edit_url)
    page.wait_for_selector('select[name="gaming_group_id"]')

    select = page.locator('select[name="gaming_group_id"]')
    select.select_option(label="Tuesday Group")
    page.wait_for_timeout(500)

    # Reload the editor and assert the dropdown still shows Tuesday Group
    page.reload()
    page.wait_for_selector('select[name="gaming_group_id"]')
    chosen = page.locator('select[name="gaming_group_id"] option:checked').text_content()
    assert "Tuesday Group" in chosen


def test_set_group_does_not_create_modified_badge(page, live_server_url):
    """Changing only the gaming group must NOT mark the character as modified."""
    create_and_apply(page, live_server_url, name="NoBadgeTest1", school="akodo_bushi")
    edit_url = page.url + "/edit"
    page.goto(edit_url)
    page.wait_for_selector('select[name="gaming_group_id"]')

    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)

    # Navigate to homepage and look at the card for this character
    page.goto(live_server_url)
    card = page.locator('a', has_text="NoBadgeTest1").first
    # Card should NOT have "Draft changes" badge
    assert "Draft changes" not in card.text_content()


# ---------------------------------------------------------------------------
# Homepage clustering
# ---------------------------------------------------------------------------


def test_homepage_group_header_links_to_group_summary(page, live_server_url):
    """Each homepage group section's header is a clickable link to
    ``/groups/{id}``. The Group Summary page then renders one card
    per visible PC with their headshot, name, school, lineage, status
    rows, and the social adv/disadv chips."""
    # Two characters in the same group, named so alphabetical sort
    # is unambiguous. One is given Good Reputation so the card
    # surfaces a social-visible advantage chip.
    create_and_apply(page, live_server_url, name="ZaikoCard", school="akodo_bushi")
    page.goto(page.url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(300)

    create_and_apply(page, live_server_url, name="AkikoCard", school="akodo_bushi")
    page.goto(page.url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    # Jealousy is a social-visible chip with a per-instance text
    # field ("Which skill do you measure yourself by?"). The chip
    # face should show only the disadvantage name; the per-instance
    # text lives in a hover tooltip.
    page.check('input[name="dis_jealousy"]')
    page.wait_for_selector(
        'input[placeholder="Which skill do you measure yourself by?"]',
        timeout=3000,
    )
    page.fill('input[placeholder="Which skill do you measure yourself by?"]',
              "intimidation")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Add jealousy")

    page.goto(live_server_url)
    # Group header is a link.
    link = page.locator('[data-testid="group-link"]', has_text="Tuesday Group")
    assert link.is_visible()
    link.click()
    page.wait_for_url("**/groups/**")
    body = page.text_content("body")
    # Both characters render, alphabetically ordered.
    assert "AkikoCard" in body
    assert "ZaikoCard" in body
    assert body.index("AkikoCard") < body.index("ZaikoCard")
    # Other tests in the same session may have left characters in
    # the same group, so we only assert >= 2 here.
    cards = page.locator('[data-group-card]')
    assert cards.count() >= 2
    akiko = cards.filter(has_text="AkikoCard").first
    assert "Akodo Bushi" in akiko.text_content()
    # Player name is intentionally absent now - the GM knows them.
    assert "Player:" not in akiko.text_content()
    # Honor is inlined on the identity sub-line (not its own status
    # row): "School ... &middot; ... Honor" with the bare number.
    assert "Honor" in akiko.text_content()
    assert akiko.locator(
        '[data-status-row*="honor"]'
    ).count() == 0, "Honor must not get its own status row on the group page"
    # Adv + disadv chips share one strip; color carries the polarity.
    chip_strip = akiko.locator('[data-testid="card-social-chips"]')
    chip = chip_strip.locator('[data-dis-id="jealousy"]')
    assert chip.count() == 1
    # The chip's visible face is only the disadvantage name
    # (Playwright's ``inner_text`` skips hidden tooltip-content
    # children).
    assert chip.inner_text().strip() == "Jealousy"
    # The per-instance detail text lives in the tooltip-content
    # (visibility flips on hover; ``text_content`` reads it regardless).
    tip_text = chip.locator('.tooltip-content').text_content()
    assert "intimidation" in tip_text


def test_group_summary_hides_hidden_characters(page, live_server_url):
    """A character with ``is_hidden=true`` does NOT show up on the
    group summary page even though the viewer (default test fixture)
    is an admin with edit access. Per spec: hidden = "not yet part
    of the group"."""
    create_and_apply(page, live_server_url, name="OpenChar", school="akodo_bushi")
    page.goto(page.url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(300)

    # Start a second character, assign to the group, but keep it
    # hidden (new chars start hidden; we skip Apply Changes so it
    # stays in the hidden draft state).
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "HiddenDraft")
    from tests.e2e.helpers import select_school
    select_school(page, "akodo_bushi")
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_selector('text="Saved"', timeout=5000)
    # Don't apply changes: the character stays hidden in draft state.

    # Now visit the group summary. Hidden draft must NOT appear.
    page.goto(live_server_url)
    page.locator('[data-testid="group-link"]', has_text="Tuesday Group").click()
    page.wait_for_url("**/groups/**")
    body = page.text_content("body")
    assert "OpenChar" in body
    assert "HiddenDraft" not in body


def test_homepage_clusters_characters_by_group(page, live_server_url):
    """Characters in the same group appear under the same heading; unassigned chars
    appear under "Not assigned to a group"."""
    # Create two characters
    create_and_apply(page, live_server_url, name="ClusterTuesA", school="akodo_bushi")
    page.goto(page.url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)

    create_and_apply(page, live_server_url, name="ClusterUnassigned", school="akodo_bushi")
    # Leave unassigned

    page.goto(live_server_url)
    body = page.text_content("body")
    assert "Tuesday Group" in body
    assert "Not assigned to a group" in body
    # Ordering: Tuesday Group section appears before the unassigned section
    assert body.find("Tuesday Group") < body.find("Not assigned to a group")
    # Section headings exist
    assert page.locator('[data-group-section="Tuesday Group"]').count() == 1
    assert page.locator('[data-group-section="Not assigned to a group"]').count() == 1
    # The Tuesday section contains the Tuesday character
    tuesday_section = page.locator('[data-group-section="Tuesday Group"]').first
    assert "ClusterTuesA" in tuesday_section.text_content()


# ---------------------------------------------------------------------------
# Inline party effects on skills / rank
# ---------------------------------------------------------------------------


def _set_group(page, sheet_url, group_label):
    """Open a sheet's editor, assign it to *group_label*, and wait for the save."""
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label=group_label)
    page.wait_for_timeout(500)


def test_party_thoughtless_inline_on_other_tact(page, live_server_url):
    """A party member's Thoughtless adds an inline +10 note on every other
    character's Tact skill row."""
    # Character A: takes Thoughtless and has Tact rank > 0 (so Tact appears)
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "ThoughtlessOne")
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_thoughtless"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Thoughtless character")
    a_url = page.url
    _set_group(page, a_url, "Tuesday Group")

    # Character B: same group, takes Tact 1
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "TactPartner")
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_tact", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Tact partner")
    b_url = page.url
    _set_group(page, b_url, "Tuesday Group")

    # Visit B's sheet — Tact row should show the inline party-member note
    page.goto(b_url)
    body = page.text_content("body")
    assert "ThoughtlessOne's Thoughtless" in body
    assert "+10 to opponents' Manipulation" in body


def test_party_priest_5th_dan_ally_conviction_button(page, live_server_url):
    """A party Priest at 5th Dan exposes a 'Spend [Priest]'s Conviction (+1)'
    button on ally roll modals. Spending it raises the ally's roll by 1."""
    # Character A: Priest at 5th Dan (all school knacks at rank 5)
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "High Priest")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 4)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Priest 5th Dan")
    a_url = page.url
    _set_group(page, a_url, "Tuesday Group")

    # Character B: same group, takes Bragging 1
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "RegularAlly")
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Bragging ally")
    b_url = page.url
    _set_group(page, b_url, "Tuesday Group")

    # Visit B's sheet and roll bragging; the ally-conviction button should appear
    page.goto(b_url)
    # Find a conviction button that mentions the priest's name
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(600)
    # If menu opens, click the main Roll button to get to the result modal
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    if menu.is_visible():
        menu.locator('button.font-medium:has-text("Roll")').first.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)

    # The priest ally spend button should be visible in the dice-roller modal
    # (the specific data-action is on the one inside the regular roll modal).
    spend = page.locator('[data-modal="dice-roller"] button[data-action^="spend-priest-ally-"]').first
    assert spend.is_visible()
    # Its text should include the priest's name
    assert "High Priest" in spend.text_content()

    # Clicking it should raise baseTotal by 1
    before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.baseTotal === 'number') return d.baseTotal;
        }
        return 0;
    }""")
    spend.click()
    page.wait_for_timeout(200)
    after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.baseTotal === 'number') return d.baseTotal;
        }
        return 0;
    }""")
    assert after == before + 1


def test_party_priest_2nd_dan_grants_bragging_free_raise(page, live_server_url):
    """A party member Priest at dan>=2 grants every ally a free raise on
    bragging/precepts/open-sincerity. The bonus shows in the skill tooltip
    line and the dice-roll formula."""
    # Character A: Priest at 2nd Dan (conviction/otherworldliness/pontificate rank 2)
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "PriestAlly")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Priest at 2nd Dan")
    a_url = page.url
    _set_group(page, a_url, "Tuesday Group")

    # Character B: same group, takes Bragging 1
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "BraggingPartner")
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Bragging partner")
    b_url = page.url
    _set_group(page, b_url, "Tuesday Group")

    # Visit B's sheet — the bragging skill row should mention PriestAlly's Priest 2nd Dan
    page.goto(b_url)
    body = page.text_content("body")
    assert "PriestAlly" in body
    assert "Priest 2nd Dan" in body
    # And the skill:bragging formula should carry the +5 flat bonus.
    formula = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        return JSON.parse(el.textContent || '{}')['skill:bragging'];
    }""")
    assert formula is not None
    assert formula["flat"] >= 5
    assert any("Priest 2nd Dan" in b.get("label", "") for b in formula.get("bonuses", []))


def test_self_thoughtless_inline_on_own_tact(page, live_server_url):
    """A character with Thoughtless sees the +20 note on their own Tact row,
    NOT on Sincerity."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "SelfThoughtless")
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_tact", 1)
    click_plus(page, "skill_sincerity", 1)
    page.check('input[name="dis_thoughtless"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Self Thoughtless")
    sheet_url = page.url

    page.goto(sheet_url)
    # The +20 note appears (on Tact)
    body = page.text_content("body")
    assert "+20 to opponents' Manipulation from Thoughtless" in body
    # And the Party Effects section is gone
    assert "Party Effects" not in body


def test_no_party_effects_section_present(page, live_server_url):
    """The standalone Party Effects section is removed entirely — no character
    should ever show it, even with group-effect disadvantages."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "NoSectionTest")
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_thoughtless"]')
    page.check('input[name="camp_dis_lion_enmity"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Lots of party effects")
    body = page.text_content("body")
    assert "Party Effects" not in body


# ---------------------------------------------------------------------------
# Admin Manage Groups page
# ---------------------------------------------------------------------------


def test_admin_groups_page_renders_for_admin(page, live_server_url):
    page.goto(f"{live_server_url}/admin/groups")
    assert "Manage Gaming Groups" in page.text_content("body")
    # Seeded groups appear as input values in the rename forms
    assert page.locator('input[name="name"][value="Tuesday Group"]').count() == 1
    assert page.locator('input[name="name"][value="Wednesday Group"]').count() == 1


def test_admin_groups_forbidden_for_non_admin(page_nonadmin, live_server_url):
    page_nonadmin.goto(f"{live_server_url}/admin/groups")
    assert "Admin access required" in page_nonadmin.text_content("body")


def test_admin_create_new_group(page, live_server_url):
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', "AdminCreatedTestGroup")
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    assert page.locator('input[name="name"][value="AdminCreatedTestGroup"]').count() == 1


def test_admin_rename_group(page, live_server_url):
    # First create a unique group, then rename it (avoids mutating the seeded ones)
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', "RenameTestOriginal")
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    # Find that group's row by its rename input value
    row = page.locator('li', has=page.locator('input[name="name"][value="RenameTestOriginal"]')).first
    rename_form = row.locator('form[action*="/rename"]')
    rename_form.locator('input[name="name"]').fill("RenameTestNew")
    rename_form.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    assert page.locator('input[name="name"][value="RenameTestNew"]').count() == 1
    assert page.locator('input[name="name"][value="RenameTestOriginal"]').count() == 0


def test_admin_delete_group_unassigns_characters(page, live_server_url):
    # Create a unique group, assign a character to it, delete the group
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', "DeleteTestGroup")
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    # Create a character and assign to the new group
    create_and_apply(page, live_server_url, name="DeleteTestChar", school="akodo_bushi")
    page.goto(page.url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="DeleteTestGroup")
    page.wait_for_timeout(500)

    # Now delete the group via admin (skip the JS confirm)
    page.goto(f"{live_server_url}/admin/groups")
    page.evaluate("window.confirm = () => true")
    row = page.locator('li', has=page.locator('input[name="name"][value="DeleteTestGroup"]')).first
    row.locator('form[action*="/delete"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    assert page.locator('input[name="name"][value="DeleteTestGroup"]').count() == 0

    # The character should now appear in the unassigned section on the homepage
    page.goto(live_server_url)
    unassigned_section = page.locator('[data-group-section="Not assigned to a group"]').first
    assert "DeleteTestChar" in unassigned_section.text_content()
