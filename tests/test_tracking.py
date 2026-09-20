"""Optimistic concurrency on tracking state, and starting a combat round.

The shape of the bug this guards against: a sheet tab posts its WHOLE
tracking state to /track, so a tab that had not seen a change made elsewhere
(another tab, a Discord roll command, a party member drawing on this
priest's pool) used to write its stale copy back over it. A void point spent
from Discord came back the next time the player clicked anything.
"""

from app.models import TRACKING_COLUMNS, Character
from app.services.tracking import (
    PER_ROUND_STATE_KEYS,
    claimed_rev_from,
    conviction_refreshes_each_round,
    is_stale,
    start_combat_round,
    tracking_snapshot,
)


OWNER = "183026066498125825"   # conftest's X-Test-User


def _make(client, **kwargs):
    kwargs.setdefault("name", "Tracked")
    kwargs.setdefault("owner_discord_id", OWNER)
    kwargs.setdefault("school", "akodo_bushi")
    kwargs.setdefault("knacks", {"double_attack": 1, "feint": 1, "iaijutsu": 1})
    kwargs.setdefault("current_void_points", 2)
    session = client._test_session_factory()
    char = Character(**kwargs)
    session.add(char)
    session.commit()
    return session, char


def _raw_track(client, char_id, body):
    """POST /track exactly as given - conftest's fresh-tab helper only wraps
    ``client.post``, so this is how a test sends a body with no ``rev``."""
    return client.request("POST", f"/characters/{char_id}/track", json=body)


# ---------------------------------------------------------------------------
# The revision moves when, and only when, tracking state changes
# ---------------------------------------------------------------------------


def test_a_new_character_starts_at_revision_zero(client):
    _, char = _make(client)
    assert char.tracking_rev == 0


def test_every_tracking_column_moves_the_revision(client):
    session, char = _make(client)
    values = {
        "current_light_wounds": 4, "current_serious_wounds": 1,
        "current_void_points": 1, "current_temp_void_points": 2,
        "adventure_state": {"lucky_used": True},
        "action_dice": [{"value": 3, "spent": False}],
        "precepts_pool": [{"value": 7}],
    }
    assert set(values) == set(TRACKING_COLUMNS)
    for expected, (column, value) in enumerate(values.items(), start=1):
        setattr(char, column, value)
        session.commit()
        assert char.tracking_rev == expected, column


def test_build_changes_do_not_move_the_revision(client):
    """An editor autosave must not make every open sheet tab stale."""
    session, char = _make(client)
    char.name = "Renamed"
    char.skills = {"etiquette": 3}
    char.money_ledger = [{"id": "a", "kind": "income", "label": "x", "amount": 1}]
    session.commit()
    assert char.tracking_rev == 0


def test_writing_the_same_value_does_not_move_the_revision(client):
    session, char = _make(client, adventure_state={"lucky_used": True})
    char.current_void_points = 2
    char.adventure_state = {"lucky_used": True}
    char.name = "Forces an UPDATE"
    session.commit()
    assert char.tracking_rev == 0


def test_is_stale():
    char = Character(name="x", tracking_rev=3)
    assert is_stale(char, 3) is False
    assert is_stale(char, 2) is True
    assert is_stale(char, None) is True          # cannot say what it saw
    assert is_stale(char, "3") is True
    assert is_stale(char, True) is True          # bool is an int in Python
    assert is_stale(Character(name="y"), 0) is False
    assert claimed_rev_from({"rev": 5}) == 5
    assert claimed_rev_from(None) is None


# ---------------------------------------------------------------------------
# POST /track
# ---------------------------------------------------------------------------


def test_a_current_write_lands_and_returns_the_new_revision(client):
    _, char = _make(client)
    resp = _raw_track(client, char.id, {"rev": 0, "current_void_points": 1})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "rev": 1}


def test_a_stale_write_is_refused_and_handed_the_current_state(client):
    session, char = _make(client)
    # Tab A spends a void point.
    assert _raw_track(client, char.id, {"rev": 0, "current_void_points": 1}).status_code == 200
    # Tab B, still at revision 0 and still believing void is 2, takes wounds.
    resp = _raw_track(
        client, char.id,
        {"rev": 0, "current_light_wounds": 5, "current_void_points": 2},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "stale"
    assert body["tracking"]["rev"] == 1
    assert body["tracking"]["current_void_points"] == 1
    session.refresh(char)
    assert char.current_void_points == 1          # not refunded
    assert char.current_light_wounds == 0         # nothing partially applied


def test_a_write_that_names_no_revision_is_refused(client):
    session, char = _make(client)
    resp = _raw_track(client, char.id, {"current_void_points": 0})
    assert resp.status_code == 409
    session.refresh(char)
    assert char.current_void_points == 2


def test_the_refused_tab_can_retry_on_the_state_it_was_given(client):
    _, char = _make(client)
    _raw_track(client, char.id, {"rev": 0, "current_void_points": 1})
    refused = _raw_track(client, char.id, {"rev": 0, "current_light_wounds": 5})
    rev = refused.json()["tracking"]["rev"]
    retry = _raw_track(client, char.id, {"rev": rev, "current_light_wounds": 5})
    assert retry.status_code == 200


def test_a_no_op_save_keeps_other_tabs_current(client):
    _, char = _make(client)
    resp = _raw_track(client, char.id, {"rev": 0, "current_void_points": 2})
    assert resp.json()["rev"] == 0


def test_a_server_side_write_makes_an_open_tab_stale(client):
    """R4.4: a command's write is not overwritten by a tab - it makes the
    tab stale. Any writer counts, because the bump is at the ORM layer."""
    session, char = _make(client)
    char.current_void_points = 1           # e.g. a Discord void spend
    session.commit()
    resp = _raw_track(client, char.id, {"rev": 0, "current_void_points": 2})
    assert resp.status_code == 409
    session.refresh(char)
    assert char.current_void_points == 1


def test_another_characters_spend_of_a_priests_conviction_survives(client):
    """The worst instance the audit found: an ally spends the priest's
    conviction, then the priest's own tab saves its render-time
    adventure_state and silently hands the point back."""
    from app.game_data import SCHOOLS

    session, priest = _make(
        client, name="Priest", school="priest",
        knacks=dict.fromkeys(SCHOOLS["priest"].school_knacks, 5),
        adventure_state={},
    )
    priest.adventure_state = {"conviction_used": 1}   # the ally's spend
    session.commit()
    resp = _raw_track(
        client, priest.id, {"rev": 0, "adventure_state": {}, "current_void_points": 1},
    )
    assert resp.status_code == 409
    session.refresh(priest)
    assert priest.adventure_state == {"conviction_used": 1}


def test_pcp_void_refresh_reports_the_revision_it_moved_to(client):
    session, char = _make(
        client, is_published=True, current_void_points=0, earned_xp=50,
    )
    from app.services.versions import publish_character

    publish_character(char, session, summary="start", author_discord_id=OWNER)
    session.commit()
    resp = client.post(
        f"/characters/{char.id}/spend-pcp", json={"use": "void_refresh"},
    )
    assert resp.status_code == 200, resp.text
    session.refresh(char)
    assert resp.json()["tracking_rev"] == char.tracking_rev >= 1


def test_snapshot_shape(client):
    _, char = _make(client, action_dice=[{"value": 2, "spent": True}])
    snap = tracking_snapshot(char)
    assert snap == {
        "rev": 0, "current_light_wounds": 0, "current_serious_wounds": 0,
        "current_void_points": 2, "current_temp_void_points": 0,
        "adventure_state": {}, "action_dice": [{"value": 2, "spent": True}],
        "precepts_pool": [],
    }


def test_the_sheet_embeds_its_revision(client):
    session, char = _make(client, is_published=True)
    char.current_void_points = 1
    session.commit()
    html = client.get(f"/characters/{char.id}").text
    assert "_rev: 1," in html


# ---------------------------------------------------------------------------
# Starting a combat round
# ---------------------------------------------------------------------------


def test_new_dice_replace_the_old_all_unspent(client):
    session, char = _make(
        client, action_dice=[{"value": 9, "spent": True, "spent_by": "Attack"}],
    )
    notes = start_combat_round(char, [
        {"value": 2}, {"value": 5, "athletics_only": True},
        {"value": 1, "athletics_only": True, "mantis_4th_dan": True},
    ])
    session.commit()
    assert notes == []
    assert char.action_dice == [
        {"value": 2, "spent": False},
        {"value": 5, "spent": False, "athletics_only": True},
        {"value": 1, "spent": False, "athletics_only": True, "mantis_4th_dan": True},
    ]


def test_per_round_state_is_cleared_and_everything_else_survives(client):
    survivors = {
        "lucky_used": True, "conviction_used": 2, "worldliness_used": 1,
        "akodo_banked_bonuses": [4], "matsu_banked_wc_bonuses": [6],
    }
    per_round = {
        "mantis_posture_phase": 4,
        "mantis_posture_history": ["offensive", "defensive"],
        "mantis_offensive_3rd_dan_accum": 3,
        "mantis_defensive_3rd_dan_accum": 2,
        "kakita_5th_dan_used": True,
    }
    assert set(per_round) == set(PER_ROUND_STATE_KEYS)
    session, char = _make(
        client, adventure_state={**survivors, **per_round},
        precepts_pool=[{"value": 8}, {"value": 3}],
    )
    start_combat_round(char, [{"value": 4}])
    session.commit()
    assert char.adventure_state == survivors
    # The Priest's pool deliberately outlives a round.
    assert char.precepts_pool == [{"value": 8}, {"value": 3}]


def test_no_dice_at_all(client):
    _, char = _make(client, action_dice=[{"value": 1, "spent": False}])
    start_combat_round(char, [])
    assert char.action_dice == []


def test_priest_5th_dan_gets_conviction_back_each_round(client):
    from app.game_data import SCHOOLS

    knacks = dict.fromkeys(SCHOOLS["priest"].school_knacks, 5)
    _, priest = _make(
        client, school="priest", knacks=knacks,
        adventure_state={"conviction_used": 3},
    )
    assert conviction_refreshes_each_round(priest.to_dict()) is True
    notes = start_combat_round(priest, [{"value": 4}])
    assert priest.adventure_state["conviction_used"] == 0
    assert notes == ["Conviction pool refreshed for the new combat round"]
    # Nothing to refresh, nothing to announce.
    assert start_combat_round(priest, [{"value": 4}]) == []


def test_a_4th_dan_priest_keeps_their_spent_conviction(client):
    from app.game_data import SCHOOLS

    knacks = dict.fromkeys(SCHOOLS["priest"].school_knacks, 4)
    _, priest = _make(
        client, school="priest", knacks=knacks,
        adventure_state={"conviction_used": 3},
    )
    start_combat_round(priest, [{"value": 4}])
    assert priest.adventure_state["conviction_used"] == 3
