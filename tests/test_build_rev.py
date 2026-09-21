"""Optimistic concurrency on the character BUILD (the editor's autosave).

The editor posts effectively the whole build on every autosave. Two editor
tabs - or a GM and a player who both have edit access - therefore used to
overwrite each other silently: A raises Fire and saves; B, still holding
Fire 2, edits Honor and saves the whole build; A's raise is gone.

Same mechanism as the tracking revision (tests/test_tracking.py), separate
counter: a sheet tab and an editor tab cannot conflict with each other, so
neither should make the other stale.
"""

from app.models import BUILD_COLUMNS, Character
from app.services.versions import publish_character


OWNER = "183026066498125825"   # conftest's X-Test-User


def _make(client, **kwargs):
    kwargs.setdefault("name", "Built")
    kwargs.setdefault("owner_discord_id", OWNER)
    kwargs.setdefault("school", "akodo_bushi")
    kwargs.setdefault("school_ring_choice", "Water")
    kwargs.setdefault("knacks", {"double_attack": 1, "feint": 1, "iaijutsu": 1})
    session = client._test_session_factory()
    char = Character(**kwargs)
    session.add(char)
    session.commit()
    return session, char


def _raw(client, char_id, path, body=None):
    """POST exactly as given - conftest's fresh-tab helper only wraps
    ``client.post``, so this is how a test sends a body with no revision."""
    return client.request("POST", f"/characters/{char_id}/{path}", json=body or {})


# ---------------------------------------------------------------------------
# The revision moves when, and only when, the build changes
# ---------------------------------------------------------------------------


def test_a_new_character_starts_at_revision_zero(client):
    _, char = _make(client)
    assert char.build_rev == 0


def test_build_columns_cover_everything_autosave_writes():
    """If autosave learns to write a new column, it has to be guarded."""
    import inspect
    import re

    from app.routes import characters

    source = inspect.getsource(characters.autosave_character)
    written = set(re.findall(r"character\.(\w+) = ", source))
    # Live state, not build: guarded by the tracking revision instead.
    written.discard("current_void_points")
    assert written <= set(BUILD_COLUMNS), written - set(BUILD_COLUMNS)


def test_a_build_change_moves_the_build_revision_only(client):
    session, char = _make(client)
    char.skills = {"etiquette": 2}
    session.commit()
    assert (char.build_rev, char.tracking_rev) == (1, 0)
    char.ring_fire = 3
    char.honor = 2.0
    session.commit()
    assert char.build_rev == 2            # one bump per write, not per column


def test_tracking_changes_do_not_move_the_build_revision(client):
    """A wound taken on the sheet must not make an open editor stale."""
    session, char = _make(client)
    char.current_light_wounds = 9
    char.adventure_state = {"lucky_used": True}
    char.money_ledger = [{"id": "a", "kind": "income", "label": "x", "amount": 1}]
    char.is_hidden = True
    char.gaming_group_id = None
    session.commit()
    assert (char.build_rev, char.tracking_rev) == (0, 1)


def test_the_dark_secret_does_not_move_the_build_revision(client):
    """Autosave can neither read nor write it (merge_dark_secret carries the
    persisted entry forward), so it cannot be lost to a stale autosave - and
    the GM setting it must not throw a conflict at the player's editor."""
    session, char = _make(client, advantage_details={"fierce": {"text": "x"}})
    char.advantage_details = {
        "fierce": {"text": "x"}, "dark_secret": {"text": "s", "player": None},
    }
    session.commit()
    assert char.build_rev == 0
    char.advantage_details = {
        "fierce": {"text": "changed"}, "dark_secret": {"text": "s", "player": None},
    }
    session.commit()
    assert char.build_rev == 1            # ordinary detail text DOES count


# ---------------------------------------------------------------------------
# POST /autosave
# ---------------------------------------------------------------------------


def test_a_current_autosave_lands_and_returns_the_new_revision(client):
    _, char = _make(client)
    resp = _raw(client, char.id, "autosave", {"build_rev": 0, "honor": 2.5})
    assert resp.status_code == 200
    assert resp.json()["build_rev"] == 1
    assert resp.json()["status"] == "saved"


def test_two_editor_tabs(client):
    """The scenario from the audit, end to end."""
    session, char = _make(client)
    rings = {"Air": 2, "Fire": 3, "Earth": 2, "Water": 3, "Void": 2}
    # Tab A raises Fire.
    assert _raw(client, char.id, "autosave",
                {"build_rev": 0, "rings": rings}).status_code == 200
    # Tab B, loaded before that and still holding Fire 2, edits Honor.
    stale = _raw(client, char.id, "autosave", {
        "build_rev": 0, "honor": 3.0,
        "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
    })
    assert stale.status_code == 409
    assert stale.json() == {"error": "stale", "build_rev": 1}
    session.refresh(char)
    assert char.ring_fire == 3            # A's raise survived
    assert char.honor == 1.0              # nothing of B's was half-applied


def test_an_autosave_that_names_no_revision_is_refused(client):
    session, char = _make(client)
    assert _raw(client, char.id, "autosave", {"honor": 4.0}).status_code == 409
    session.refresh(char)
    assert char.honor == 1.0


def test_keep_mine_is_a_save_against_the_revision_the_refusal_named(client):
    """The editor's "keep my version" is nothing special server-side: an
    informed overwrite is an ordinary save that names the current revision."""
    session, char = _make(client)
    _raw(client, char.id, "autosave", {"build_rev": 0, "honor": 2.0})
    refused = _raw(client, char.id, "autosave", {"build_rev": 0, "honor": 5.0})
    again = _raw(client, char.id, "autosave",
                 {"build_rev": refused.json()["build_rev"], "honor": 5.0})
    assert again.status_code == 200
    session.refresh(char)
    assert char.honor == 5.0


def test_a_save_that_changes_nothing_keeps_other_tabs_current(client):
    _, char = _make(client)
    resp = _raw(client, char.id, "autosave", {"build_rev": 0, "honor": 1.0})
    assert resp.json()["build_rev"] == 0


def test_a_rejected_autosave_body_does_not_move_the_revision(client):
    session, char = _make(client)
    resp = _raw(client, char.id, "autosave",
                {"build_rev": 0, "honor": 3.0, "rank_recognition_awards": "junk"})
    assert resp.status_code == 400
    session.refresh(char)
    assert (char.build_rev, char.honor) == (0, 1.0)


def test_the_editor_embeds_its_revision(client):
    session, char = _make(client)
    char.honor = 2.0
    session.commit()
    assert "this._buildRev = 1;" in client.get(f"/characters/{char.id}/edit").text


# ---------------------------------------------------------------------------
# Same-tab writers that are NOT autosave hand the revision back
# ---------------------------------------------------------------------------


def test_editing_an_award_source_reports_the_revision_it_moved_to(client):
    award = {"id": "a1", "type": "rank_recognition", "rank_delta": 0.5,
             "recognition_delta": 0.5, "source": "Old", "created_at": ""}
    session, char = _make(client, rank_recognition_awards=[award])
    resp = client.post(f"/characters/{char.id}/set-award-source",
                       json={"award_id": "a1", "source": "New"})
    assert resp.status_code == 200, resp.text
    session.refresh(char)
    assert resp.json()["build_rev"] == char.build_rev == 1


# ---------------------------------------------------------------------------
# Publish and discard act on the draft the user was SHOWN
# ---------------------------------------------------------------------------


def _published(client):
    session, char = _make(client)
    publish_character(char, session, summary="v1", author_discord_id=OWNER)
    session.commit()
    char.honor = 2.0                      # a draft change
    session.commit()
    return session, char


def test_draft_diff_names_the_revision_it_describes(client):
    _, char = _published(client)
    data = client.get(f"/characters/{char.id}/draft-diff").json()
    assert data["build_rev"] == char.build_rev


def test_discard_refuses_a_draft_that_moved_after_the_diff_was_shown(client):
    session, char = _published(client)
    shown = client.get(f"/characters/{char.id}/draft-diff").json()["build_rev"]
    char.ring_fire = 3                    # another editor's autosave
    session.commit()
    resp = _raw(client, char.id, "discard", {"build_rev": shown})
    assert resp.status_code == 409
    assert resp.json()["error"] == "stale"
    session.refresh(char)
    assert (char.ring_fire, char.honor) == (3, 2.0)     # nothing discarded
    # Re-reading the diff and confirming again works.
    shown = client.get(f"/characters/{char.id}/draft-diff").json()["build_rev"]
    assert _raw(client, char.id, "discard", {"build_rev": shown}).status_code == 200


def test_publish_refuses_a_draft_the_editor_has_not_seen(client):
    session, char = _published(client)
    seen = char.build_rev
    char.ring_fire = 3
    session.commit()
    resp = _raw(client, char.id, "publish", {"summary": "mine", "build_rev": seen})
    assert resp.status_code == 409
    ok = _raw(client, char.id, "publish",
              {"summary": "mine", "build_rev": resp.json()["build_rev"]})
    assert ok.status_code == 200


def test_publish_and_discard_without_a_revision_still_work(client):
    """They are operations on server state, not whole-object writes: a
    caller that names no revision is not claiming to have seen anything."""
    _, char = _published(client)
    assert _raw(client, char.id, "publish", {"summary": "x"}).status_code == 200


def test_advantage_details_going_from_null_to_something_counts(client):
    """Legacy rows can hold NULL there; the dark-secret filter must not choke."""
    from sqlalchemy import text

    session, char = _make(client)
    session.execute(text("UPDATE characters SET advantage_details = NULL WHERE id = :i"),
                    {"i": char.id})
    session.commit()
    session.expire_all()
    char.advantage_details = {"fierce": {"text": "x"}}
    session.commit()
    assert char.build_rev == 1
