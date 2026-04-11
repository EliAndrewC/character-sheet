"""E2E: GM-awarded Rank/Recognition bonuses (modal, history list, lock-out)."""

from tests.e2e.helpers import select_school, apply_changes
import pytest

pytestmark = [pytest.mark.gm_awards, pytest.mark.honor_rank_recognition]


def _go_to_editor(page, live_server_url, name="Award Test"):
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_timeout(300)


def _open_award_modal(page):
    page.locator('[data-action="open-award-modal"]').click()
    page.wait_for_selector('[data-modal="award"]', state="visible", timeout=3000)


def _fill_award_modal(page, source, rank_clicks=0, recog_clicks=0):
    """Click the modal's rank/recognition +/- buttons and fill the source.

    Positive *rank_clicks* clicks +, negative clicks -. Same for recog.
    Use the apply button to commit.
    """
    if rank_clicks > 0:
        for _ in range(rank_clicks):
            page.locator('[data-action="award-modal-rank-plus"]').click()
    elif rank_clicks < 0:
        for _ in range(-rank_clicks):
            page.locator('[data-action="award-modal-rank-minus"]').click()

    if recog_clicks > 0:
        for _ in range(recog_clicks):
            page.locator('[data-action="award-modal-recog-plus"]').click()
    elif recog_clicks < 0:
        for _ in range(-recog_clicks):
            page.locator('[data-action="award-modal-recog-minus"]').click()

    page.locator('input[data-field="award-source"]').fill(source)


# ---------------------------------------------------------------------------
# Modal basics
# ---------------------------------------------------------------------------


def test_award_button_visible_on_editor(page, live_server_url):
    """The 'GM-awarded Bonus' button is present in the editor."""
    _go_to_editor(page, live_server_url)
    btn = page.locator('[data-action="open-award-modal"]')
    assert btn.is_visible()


def test_award_modal_opens_and_closes(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_award_modal(page)
    assert page.locator('input[data-field="award-source"]').is_visible()
    page.locator('[data-action="cancel-award"]').click()
    page.wait_for_timeout(200)
    assert not page.locator('input[data-field="award-source"]').is_visible()


def test_award_apply_disabled_without_source(page, live_server_url):
    """The Apply button is disabled until a source is filled."""
    _go_to_editor(page, live_server_url)
    _open_award_modal(page)
    apply_btn = page.locator('[data-action="apply-award"]')
    assert apply_btn.is_disabled()
    # Adding deltas alone is not enough; source is still required
    _fill_award_modal(page, "", rank_clicks=2)
    assert apply_btn.is_disabled()
    # Filling the source enables it
    page.locator('input[data-field="award-source"]').fill("Defended village")
    assert not apply_btn.is_disabled()


def test_award_apply_disabled_when_both_zero(page, live_server_url):
    """Even with a source, both deltas at 0 is a no-op and stays disabled."""
    _go_to_editor(page, live_server_url)
    _open_award_modal(page)
    page.locator('input[data-field="award-source"]').fill("Some reason")
    assert page.locator('[data-action="apply-award"]').is_disabled()


# ---------------------------------------------------------------------------
# Applying an award updates the character
# ---------------------------------------------------------------------------


def test_apply_award_updates_rank_and_recognition(page, live_server_url):
    _go_to_editor(page, live_server_url)
    rank_before = page.locator('input[name="rank"]').input_value()
    recog_before = page.locator('input[name="recognition"]').input_value()
    _open_award_modal(page)
    _fill_award_modal(page, "Defended village", rank_clicks=2, recog_clicks=1)
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)
    rank_after = page.locator('input[name="rank"]').input_value()
    recog_after = page.locator('input[name="recognition"]').input_value()
    # +2 clicks at 0.5 step = +1.0; +1 click = +0.5
    assert float(rank_after) - float(rank_before) == 1.0
    assert float(recog_after) - float(recog_before) == 0.5


def test_award_appears_in_history_list(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_award_modal(page)
    _fill_award_modal(page, "Heroic stand", rank_clicks=1, recog_clicks=2)
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)
    award_row = page.locator('[data-award-row]').first
    assert award_row.is_visible()
    source_input = award_row.locator('input[type="text"]')
    assert source_input.input_value() == "Heroic stand"


# ---------------------------------------------------------------------------
# Locking the rank/recognition controls
# ---------------------------------------------------------------------------


def test_recognition_locked_after_first_award(page, live_server_url):
    """Once an award exists, the standalone Recognition +/- buttons lock."""
    _go_to_editor(page, live_server_url)
    # Sanity: recognition + is enabled before any awards
    recog_section = page.locator('label:text("Recognition")').first.locator('..')
    plus = recog_section.locator('button', has_text="+").first
    assert not plus.is_disabled()

    _open_award_modal(page)
    _fill_award_modal(page, "First award", rank_clicks=1)
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)

    # Recognition +/- now locked
    minus = recog_section.locator('button', has_text="-").first
    plus = recog_section.locator('button', has_text="+").first
    assert minus.is_disabled()
    assert plus.is_disabled()


def test_recognition_halved_locked_after_first_award(page, live_server_url):
    """The 'Halve starting Recognition' checkbox also locks after the first award."""
    _go_to_editor(page, live_server_url)
    halve = page.locator('input[name="recognition_halved"]')
    assert not halve.is_disabled()

    _open_award_modal(page)
    _fill_award_modal(page, "First award", rank_clicks=1)
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)

    assert halve.is_disabled()


# ---------------------------------------------------------------------------
# Editing and deleting an existing award
# ---------------------------------------------------------------------------


def test_edit_award_rank_delta_updates_rank(page, live_server_url):
    _go_to_editor(page, live_server_url)
    rank_before = float(page.locator('input[name="rank"]').input_value())

    _open_award_modal(page)
    _fill_award_modal(page, "Edit me", rank_clicks=2)  # +1.0
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)
    assert float(page.locator('input[name="rank"]').input_value()) == rank_before + 1.0

    # Click the award row's Rank + once → delta becomes +1.5, rank becomes +0.5 more
    page.locator('[data-action="award-row-rank-plus"]').first.click()
    page.wait_for_timeout(200)
    assert float(page.locator('input[name="rank"]').input_value()) == rank_before + 1.5


def test_delete_award_restores_rank(page, live_server_url):
    _go_to_editor(page, live_server_url)
    rank_before = float(page.locator('input[name="rank"]').input_value())
    recog_before = float(page.locator('input[name="recognition"]').input_value())

    _open_award_modal(page)
    _fill_award_modal(page, "To delete", rank_clicks=2, recog_clicks=1)
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)
    assert float(page.locator('input[name="rank"]').input_value()) > rank_before

    award_row = page.locator('[data-award-row]').first
    award_row.locator('button[title="Delete this award"]').click()
    page.wait_for_timeout(200)

    assert float(page.locator('input[name="rank"]').input_value()) == rank_before
    assert float(page.locator('input[name="recognition"]').input_value()) == recog_before
    # The history list is now empty
    assert page.locator('[data-award-row]').count() == 0


# ---------------------------------------------------------------------------
# Source edit is metadata-only — does NOT trigger draft
# ---------------------------------------------------------------------------


def test_source_edit_does_not_trigger_modified_badge(page, live_server_url):
    """Editing the freeform source on an existing award must not flip the
    character into 'modified' state."""
    _go_to_editor(page, live_server_url, name="MetaSourceTest")
    _open_award_modal(page)
    _fill_award_modal(page, "Original reason", rank_clicks=1)
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)

    # Apply to publish a baseline
    apply_changes(page, "Initial publish with award")
    sheet_url = page.url
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('[data-award-row]')

    # Sanity: no Draft / Modified badge yet
    body = page.text_content("body")
    assert "Draft changes" not in body
    assert "Modified" not in body or "modified" not in body.lower().split("draft changes")[0]

    # Edit the source — debounced fetch triggers after 600ms
    award_row = page.locator('[data-award-row]').first
    source_input = award_row.locator('input[type="text"]')
    source_input.fill("Reworded reason")
    page.wait_for_timeout(1500)  # let the debounced metadata save fire

    # Reload and verify the new source is persisted AND no draft badge
    page.reload()
    page.wait_for_selector('[data-award-row]')
    award_row = page.locator('[data-award-row]').first
    persisted_source = award_row.locator('input[type="text"]').input_value()
    assert persisted_source == "Reworded reason"
    body = page.text_content("body")
    assert "Draft changes" not in body


def test_reputation_tab_applies_good_reputation(page, live_server_url):
    """Switching to the Reputation tab and applying creates a reputation award."""
    _go_to_editor(page, live_server_url)
    _open_award_modal(page)
    # Switch to reputation tab
    page.locator('[data-action="award-tab-reputation"]').click()
    page.wait_for_timeout(200)
    # Select Good Reputation
    page.locator('[data-action="award-rep-good"]').click()
    page.locator('input[data-field="award-rep-text"]').fill("Heroic deed")
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)
    # Should appear in history with badge
    award_row = page.locator('[data-award-row]').first
    assert award_row.is_visible()
    assert "Good Reputation" in award_row.text_content()


def test_reputation_award_shows_badge_in_history(page, live_server_url):
    """A reputation award shows a colored badge (not rank/recog +/-)."""
    _go_to_editor(page, live_server_url)
    _open_award_modal(page)
    page.locator('[data-action="award-tab-reputation"]').click()
    page.wait_for_timeout(200)
    page.locator('[data-action="award-rep-bad"]').click()
    page.locator('input[data-field="award-rep-text"]').fill("Cowardice")
    page.locator('[data-action="apply-award"]').click()
    page.wait_for_timeout(300)
    award_row = page.locator('[data-award-row]').first
    assert "Bad Reputation" in award_row.text_content()
