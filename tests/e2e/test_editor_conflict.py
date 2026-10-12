"""E2E: two editors on one character's build.

The editor autosaves effectively the whole build. Before the build revision
existed, a second editor tab (or a GM and a player who both have edit
access) silently overwrote whatever the other had saved. Now the stale save
is refused, saving pauses, and the editor asks the user what to do - it does
NOT adopt the other version silently the way the sheet does, because the
user may be in the middle of typing.
"""

import re

import pytest

from tests.e2e.helpers import (
    apply_changes,
    click_plus,
    select_school,
    start_new_character,
)

pytestmark = [pytest.mark.autosave]

MODAL = '[data-modal="build-conflict"]'
NAME = 'input[name="name"]'


def _new_draft(page, live_server_url, name="Original"):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector(NAME)
    page.fill(NAME, name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    return int(re.search(r"/characters/(\d+)", page.url).group(1))


def _edit_elsewhere(page, name="Theirs"):
    """A second editor tab renames the character and autosaves."""
    other = page.context.new_page()
    other.goto(page.url)
    other.wait_for_selector(NAME)
    with other.expect_response(lambda r: r.url.endswith("/autosave")) as saved:
        other.fill(NAME, name)
    assert saved.value.status == 200
    other.close()


def _stale_edit(page, name="Mine"):
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as refused:
        page.fill(NAME, name)
    assert refused.value.status == 409
    page.wait_for_selector(MODAL, state="visible")


def _saved_name(page):
    """What the SERVER holds, read through a fresh tab."""
    fresh = page.context.new_page()
    fresh.goto(page.url)
    fresh.wait_for_selector(NAME)
    value = fresh.input_value(NAME)
    fresh.close()
    return value


def test_stale_autosave_is_refused_and_the_editor_asks(page, live_server_url):
    _new_draft(page, live_server_url)
    assert not page.locator(MODAL).is_visible()
    _edit_elsewhere(page)
    _stale_edit(page)
    assert "not been saved" in page.locator(MODAL).inner_text()
    # Nothing was overwritten, and this tab's text was left alone.
    assert _saved_name(page) == "Theirs"
    assert page.input_value(NAME) == "Mine"


def test_saving_stays_paused_until_the_user_decides(page, live_server_url):
    _new_draft(page, live_server_url)
    _edit_elsewhere(page)
    _stale_edit(page)
    page.locator('[data-action="conflict-later"]').click()
    page.wait_for_selector(MODAL, state="hidden")

    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("/autosave") else None)
    page.fill(NAME, "Mine again")
    page.wait_for_timeout(2500)             # well past the 1500 ms debounce
    assert requests == [], "autosave must not hammer a refused build"
    assert "changed elsewhere" in page.locator('text=Not saved').first.inner_text()

    page.locator('[data-action="conflict-resolve"]').click()
    page.wait_for_selector(MODAL, state="visible")


def test_load_the_latest_version(page, live_server_url):
    _new_draft(page, live_server_url)
    _edit_elsewhere(page)
    _stale_edit(page)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.type), d.accept()))
    with page.expect_navigation():
        page.locator('[data-action="conflict-reload"]').click()
    page.wait_for_selector(NAME)
    assert page.input_value(NAME) == "Theirs"
    assert dialogs == [], "the unload guard must not second-guess the choice"
    # And the reloaded tab saves normally again.
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as saved:
        page.fill(NAME, "After reload")
    assert saved.value.status == 200


def test_keep_my_version(page, live_server_url):
    _new_draft(page, live_server_url)
    _edit_elsewhere(page)
    _stale_edit(page)
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as saved:
        page.locator('[data-action="conflict-keep-mine"]').click()
    assert saved.value.status == 200
    page.wait_for_selector(MODAL, state="hidden")
    assert not page.locator('[data-action="conflict-resolve"]').is_visible()
    assert _saved_name(page) == "Mine"
    # Saving is un-paused.
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as again:
        page.fill(NAME, "Mine, continued")
    assert again.value.status == 200


def test_apply_refuses_a_draft_this_tab_has_not_seen(page, live_server_url):
    """Nothing unsaved here, but another editor saved after this tab's last
    save: the summary about to be typed would describe a different build."""
    _new_draft(page, live_server_url)
    _edit_elsewhere(page)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]')
    page.fill('textarea[placeholder="Describe your changes..."]', "Mine")
    with page.expect_response(lambda r: r.url.endswith("/publish")) as refused:
        page.locator('div.fixed button:text("Apply Changes")').click()
    assert refused.value.status == 409
    page.wait_for_selector(MODAL, state="visible")
    assert "/edit" in page.url, "nothing was published, so no redirect"


def test_discard_refuses_a_change_that_was_never_listed(page, live_server_url):
    cid = _new_draft(page, live_server_url)
    apply_changes(page, "v1")
    page.goto(f"{live_server_url}/characters/{cid}/edit")
    page.wait_for_selector(NAME)
    with page.expect_response(lambda r: r.url.endswith("/autosave")):
        click_plus(page, "attack")
    page.wait_for_selector('[data-action="discard-changes"]', state="visible")
    page.locator('[data-action="discard-changes"]').click()
    page.wait_for_selector('[data-testid="discard-diff-lines"]')
    before = page.locator('[data-testid="discard-diff-lines"]').inner_text()

    # While the list is open, another editor saves a change of their own.
    other = page.context.new_page()
    other.goto(page.url)
    other.wait_for_selector(NAME)
    with other.expect_response(lambda r: r.url.endswith("/autosave")) as saved:
        click_plus(other, "parry")
    assert saved.value.status == 200
    other.close()

    with page.expect_response(lambda r: r.url.endswith("/discard")) as refused:
        page.locator('[data-action="confirm-discard"]').click()
    assert refused.value.status == 409
    page.wait_for_selector('[data-testid="discard-stale-notice"]', state="visible")
    page.wait_for_selector('[data-testid="discard-diff-lines"]')
    after = page.locator('[data-testid="discard-diff-lines"]').inner_text()
    assert after != before and "arry" in after      # their change is now LISTED

    # Confirming the refreshed list works, and leaves no draft behind.
    with page.expect_navigation():
        page.locator('[data-action="confirm-discard"]').click()
    page.wait_for_selector(NAME)
    assert not page.locator('[data-action="discard-changes"]').is_visible()


def test_conflict_modal_fits_a_phone_screen(page, live_server_url):
    _new_draft(page, live_server_url)
    page.set_viewport_size({"width": 375, "height": 700})
    _edit_elsewhere(page)
    _stale_edit(page)
    for action in ("conflict-later", "conflict-keep-mine", "conflict-reload"):
        box = page.locator(f'[data-action="{action}"]').bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 375, action
        assert box["y"] + box["height"] <= 700, action


def _put_draft_in_a_new_group(page, live_server_url):
    """Create a group and move the open draft into it; returns its id."""
    import uuid
    edit_url = page.url
    gname = "XpConflict-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    page.goto(edit_url)
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label=gname)
    page.wait_for_timeout(400)  # let setGroup() round-trip
    # New drafts start hidden, and a group award skips hidden characters.
    char_id = re.search(r"/characters/(\d+)", edit_url).group(1)
    assert page.request.post(f"{live_server_url}/characters/{char_id}/show").status == 200
    page.reload()
    page.wait_for_selector(NAME)
    return int(page.locator('select[name="gaming_group_id"]').input_value())


def _gm_awards(page, live_server_url, group_id, amount):
    resp = page.request.post(f"{live_server_url}/groups/{group_id}/xp/award",
                             data={"label": "The Haunted Shrine", "amount": amount})
    assert resp.status == 200


def test_keep_my_version_keeps_a_gm_xp_award(page, live_server_url):
    """The award moves the build, so this open tab is refused; keeping its
    version must not take the award back."""
    _new_draft(page, live_server_url)
    gid = _put_draft_in_a_new_group(page, live_server_url)
    _gm_awards(page, live_server_url, gid, 15)
    _stale_edit(page)
    note = page.locator('[data-testid="conflict-xp-note"]')
    assert note.is_visible() and "is now 15" in note.inner_text()
    assert page.input_value('input[name="earned_xp"]') == "15"
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as saved:
        page.locator('[data-action="conflict-keep-mine"]').click()
    assert saved.value.status == 200
    assert _saved_name(page) == "Mine"
    fresh = page.context.new_page()
    fresh.goto(page.url)
    fresh.wait_for_selector(NAME)
    assert fresh.input_value('input[name="earned_xp"]') == "15"
    fresh.close()


def test_a_tab_that_changed_earned_xp_keeps_its_own_value(page, live_server_url):
    """When the refused save IS this tab's own Earned XP edit, the user's
    number stays and no note claims otherwise."""
    _new_draft(page, live_server_url)
    gid = _put_draft_in_a_new_group(page, live_server_url)
    _gm_awards(page, live_server_url, gid, 15)
    with page.expect_response(lambda r: r.url.endswith("/autosave")) as refused:
        page.fill('input[name="earned_xp"]', "7")
    assert refused.value.status == 409
    page.wait_for_selector(MODAL, state="visible")
    assert not page.locator('[data-testid="conflict-xp-note"]').is_visible()
    assert page.input_value('input[name="earned_xp"]') == "7"
