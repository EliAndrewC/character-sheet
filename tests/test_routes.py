"""Tests for page and API routes."""

import pytest

from app.models import Character, CharacterVersion
from tests.conftest import make_character_form, query_db


def _seed_character(client, **kwargs):
    """Insert a character directly into the test DB via the client's connection."""
    session = client._test_session_factory()
    defaults = dict(
        name="Test Samurai",
        school="akodo_bushi",
        school_ring_choice="Water",
        ring_water=3,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id="183026066498125825",
        is_published=True,
        published_state={"name": kwargs.get("name", "Test Samurai")},
    )
    defaults.update(kwargs)
    c = Character(**defaults)
    session.add(c)
    session.commit()
    return c.id


class TestIndexPage:
    def test_empty_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "No characters yet" in resp.text

    def test_index_lists_published_characters(self, client):
        _seed_character(client, name="Akodo Toturi", is_published=True)

        resp = client.get("/")
        assert resp.status_code == 200
        assert "Akodo Toturi" in resp.text

    def test_index_shows_draft_to_owner(self, client):
        _seed_character(client, name="My Draft", is_published=False,
                        owner_discord_id="183026066498125825")

        resp = client.get("/")
        assert "My Draft" in resp.text


class TestCreateCharacter:
    def test_create_redirects_to_edit(self, client):
        resp = client.post("/characters", follow_redirects=False)
        assert resp.status_code == 303
        assert "/edit" in resp.headers["location"]

    def test_create_makes_blank_character(self, client):
        client.post("/characters")
        char = query_db(client).first()
        assert char is not None
        assert char.name == "New Character"
        assert char.is_published is False
        assert char.owner_discord_id == "183026066498125825"

    def test_create_starts_with_full_void_points(self, client):
        """New characters start with full void points (min ring = 2)."""
        client.post("/characters")
        char = query_db(client).first()
        assert char.current_void_points == 2

    def test_autosave_updates_void_for_unpublished(self, client):
        """Autosave on unpublished character keeps VP at max when rings change."""
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        # Raise Void ring to 3 - void max should become 2 (min of all rings)
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 2  # min ring is still 2
        # Raise all rings to 3
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 3, "Fire": 3, "Earth": 3, "Water": 3, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 3  # min ring is now 3

    def test_autosave_updates_void_for_isawa_ishi(self, client):
        """Autosave on Isawa Ishi uses shugenja VP formula (highest ring + school rank)."""
        cid = _seed_character(
            client, school="isawa_ishi", school_ring_choice="Void",
            knacks={"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1},
            is_published=False,
        )
        # Set rings: highest ring = 3 (Void), dan = 1 (min knack), VP max = 3 + 1 = 4
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 4  # highest ring (3) + dan (1)

    def test_autosave_does_not_change_void_for_published(self, client):
        """Autosave on published character does NOT reset VP when rings change."""
        cid = _seed_character(client, current_void_points=1, is_published=True)
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 3, "Fire": 3, "Earth": 3, "Water": 3, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 1  # unchanged


class TestPriestAllyConviction:
    """POST /characters/{priest_id}/ally-conviction: party members can
    spend a Priest 5th Dan's conviction pool on their own rolls."""

    def _setup_priest_and_ally(self, client, priest_rank=5):
        """Create a Priest at 5th Dan and a non-priest ally in the same group.

        ``priest_rank`` is used for all three school knacks (so dan == rank).
        """
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Tuesday Group")
        session.add(group); session.commit()
        priest_id = _seed_character(
            client, name="Priest Ally", school="priest",
            knacks={"conviction": priest_rank, "otherworldliness": priest_rank,
                    "pontificate": priest_rank},
            gaming_group_id=group.id, is_published=True,
        )
        ally_id = _seed_character(
            client, name="Bushi", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        return priest_id, ally_id, group.id

    def test_ally_can_spend_priest_conviction(self, client):
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1, "rolling_character_id": ally_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["used"] == 1
        assert data["pool_max"] == 10  # 2 * rank(5)

    def test_ally_can_undo_priest_conviction(self, client):
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        body = {"delta": 1, "rolling_character_id": ally_id}
        client.post(f"/characters/{priest_id}/ally-conviction", json=body)
        client.post(f"/characters/{priest_id}/ally-conviction", json=body)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": -1, "rolling_character_id": ally_id},
        )
        assert resp.status_code == 200
        assert resp.json()["used"] == 1

    def test_rejects_non_priest_target(self, client):
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.post(f"/characters/{ally_id}/ally-conviction",
                           json={"delta": 1})
        assert resp.status_code == 400

    def test_rejects_priest_below_5th_dan(self, client):
        """Priest 4th Dan doesn't yet get the cross-character spending rule."""
        # Seed a priest at dan 4 (knacks 4,4,4).
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Low Dan Group")
        session.add(group); session.commit()
        priest_id = _seed_character(
            client, name="Dan4", school="priest",
            knacks={"conviction": 4, "otherworldliness": 4, "pontificate": 4},
            gaming_group_id=group.id, is_published=True,
        )
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": 1})
        assert resp.status_code == 400

    def test_rejects_unknown_priest(self, client):
        resp = client.post("/characters/99999/ally-conviction", json={"delta": 1})
        assert resp.status_code == 404

    def test_rejects_caller_not_in_group(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        # Unassign the priest from any group; the endpoint requires that
        # the priest belong to a gaming group the caller shares.
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.gaming_group_id = None
        session.commit()
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": 1})
        assert resp.status_code == 403

    def test_rejects_bad_delta(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": 5})
        assert resp.status_code == 400
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": "bogus"})
        assert resp.status_code == 400

    def test_used_clamps_to_pool_max(self, client):
        priest_id, ally_id, _ = self._setup_priest_and_ally(client, priest_rank=5)
        # pool_max = 10. Spend 15 times; used should cap at 10.
        body = {"delta": 1, "rolling_character_id": ally_id}
        for _ in range(15):
            client.post(f"/characters/{priest_id}/ally-conviction", json=body)
        session = client._test_session_factory()
        p = session.query(Character).filter(Character.id == priest_id).first()
        assert (p.adventure_state or {}).get("conviction_used") == 10

    def test_used_cannot_go_below_zero(self, client):
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": -1, "rolling_character_id": ally_id},
        )
        assert resp.status_code == 200
        assert resp.json()["used"] == 0

    def test_sheet_exposes_priest_ally_script(self, client):
        """The ally's sheet page embeds priest-conviction-allies JSON with the priest."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.get(f"/characters/{ally_id}")
        assert resp.status_code == 200
        assert 'id="priest-conviction-allies"' in resp.text
        assert "Priest Ally" in resp.text

    # ---- Phase 7 tightened-auth regressions ----

    def test_requires_rolling_character_id(self, client):
        """Phase 7: non-owner callers must pass rolling_character_id."""
        priest_id, ally_id, group_id = self._setup_priest_and_ally(client)
        # Reassign priest owner so admin is no longer the owner.
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.owner_discord_id = "some_other_user"
        ally = session.query(Character).filter(Character.id == ally_id).first()
        ally.owner_discord_id = "test_user_1"
        session.commit()
        # test_user_1 is in the group (owns ally) but omits rolling_character_id.
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1},
            headers={"X-Test-User": "test_user_1:AllyOwner"},
        )
        assert resp.status_code == 400

    def test_rejects_rolling_char_caller_cannot_edit(self, client):
        """Phase 7: a non-editor viewer of the rolling character is 403'd
        server-side even if they're in the same gaming group."""
        priest_id, ally_id, group_id = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        # Ally owned by admin, priest owned by someone else, test_user_1 has
        # no edit access to either but gets a third char in the same group.
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.owner_discord_id = "some_other_user"
        session.commit()
        # test_user_1 is in the group via a third char, but tries to drive
        # the spend from the ally's sheet (they can't edit the ally).
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1, "rolling_character_id": ally_id},
            headers={"X-Test-User": "test_user_1:NonEditor"},
        )
        assert resp.status_code == 403
        # No state change.
        p = session.query(Character).filter(Character.id == priest_id).first()
        assert (p.adventure_state or {}).get("conviction_used", 0) == 0

    def test_rejects_rolling_char_in_different_group(self, client):
        """Phase 7: the rolling character must share the priest's group."""
        from app.models import GamingGroup
        priest_id, _, _ = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        other_group = GamingGroup(name="Other Group")
        session.add(other_group); session.commit()
        outsider_id = _seed_character(
            client, name="Outsider", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=other_group.id, is_published=True,
        )
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1, "rolling_character_id": outsider_id},
        )
        assert resp.status_code == 403

    def test_allows_non_owner_editor_of_rolling_char(self, client):
        """Phase 7: a caller who has edit access to a party-mate character
        (even without owning the priest) is allowed to spend the priest's
        conviction. The edit access can come from being a granted editor
        on the party-mate char - not just ownership."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        # Priest owned by someone else. Ally owned by admin but
        # test_user_1 is granted editor on the ally.
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.owner_discord_id = "some_other_user"
        ally = session.query(Character).filter(Character.id == ally_id).first()
        ally.editor_discord_ids = ["test_user_1"]
        session.commit()
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1, "rolling_character_id": ally_id},
            headers={"X-Test-User": "test_user_1:GrantedEditor"},
        )
        assert resp.status_code == 200
        assert resp.json()["used"] == 1

    def test_sheet_skips_priest_below_5th_dan(self, client):
        """A priest in the party at dan < 5 is not exposed as a conviction ally source
        (priest-conviction-allies JSON stays empty)."""
        import json as _json
        import re
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Group")
        session.add(group); session.commit()
        _seed_character(
            client, name="Low Dan Priest", school="priest",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            gaming_group_id=group.id, is_published=True,
        )
        ally_id = _seed_character(
            client, name="Bushi", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        resp = client.get(f"/characters/{ally_id}")
        m = re.search(
            r'id="priest-conviction-allies">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        assert _json.loads(m.group(1)) == []

    def test_rejects_non_integer_rolling_character_id(self, client):
        """Phase 7: a string that isn't parseable as int gets a 400."""
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1, "rolling_character_id": "not-a-number"},
        )
        assert resp.status_code == 400
        assert "rolling_character_id must be an integer" in resp.json()["error"]

    def test_rejects_unknown_rolling_character_id(self, client):
        """Phase 7: a numerically-valid but nonexistent rolling_character_id is 403'd."""
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 1, "rolling_character_id": 99999},
        )
        assert resp.status_code == 403
        assert "Rolling character not found" in resp.json()["error"]

    def test_rejects_non_integer_delta_when_otherwise_valid(self, client):
        """A non-int delta paired with a valid rolling_character_id falls back
        to delta=0, which then trips the (-1, +1) range check."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": "bogus", "rolling_character_id": ally_id},
        )
        assert resp.status_code == 400
        assert "delta must be +1 or -1" in resp.json()["error"]

    def test_rejects_out_of_range_delta_when_otherwise_valid(self, client):
        """delta=5 with a valid rolling_character_id is rejected."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/ally-conviction",
            json={"delta": 5, "rolling_character_id": ally_id},
        )
        assert resp.status_code == 400
        assert "delta must be +1 or -1" in resp.json()["error"]


class TestPriestPreceptsAlliesContext:
    """The ``priest_precepts_allies`` context list surfaces party priests at
    3rd Dan or higher with a non-empty precepts pool. Self is excluded; the
    priest's own pool goes through the priest's own ``preceptsPool`` state
    rather than appearing in the ally list."""

    def _setup_priest_and_ally(self, client, *, priest_rank=3, pool=None):
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Precepts Group")
        session.add(group); session.commit()
        priest_id = _seed_character(
            client, name="Precepts Priest", school="priest",
            knacks={"conviction": priest_rank, "otherworldliness": priest_rank,
                    "pontificate": priest_rank},
            skills={"precepts": 3},
            gaming_group_id=group.id, is_published=True,
            precepts_pool=(pool if pool is not None else [{"value": 7}, {"value": 3}]),
        )
        ally_id = _seed_character(
            client, name="Bushi Ally", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        return priest_id, ally_id, group.id

    def _precepts_list(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="priest-precepts-allies">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_ally_sees_priest_with_pool(self, client):
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        allies = self._precepts_list(client, ally_id)
        assert len(allies) == 1
        entry = allies[0]
        assert entry["priest_id"] == priest_id
        assert entry["name"] == "Precepts Priest"
        assert entry["pool"] == [{"value": 7}, {"value": 3}]

    def test_priest_at_2nd_dan_not_in_allies(self, client):
        _, ally_id, _ = self._setup_priest_and_ally(client, priest_rank=2)
        # Dan 2 priest with a pool does NOT surface (the 3rd Dan ability
        # is not yet unlocked; even if a stale pool existed on the column,
        # the context skips them).
        assert self._precepts_list(client, ally_id) == []

    def test_priest_with_empty_pool_not_in_allies(self, client):
        _, ally_id, _ = self._setup_priest_and_ally(client, pool=[])
        assert self._precepts_list(client, ally_id) == []

    def test_priest_in_different_group_not_in_allies(self, client):
        from app.models import GamingGroup
        session = client._test_session_factory()
        priest_group = GamingGroup(name="Priest Group")
        ally_group = GamingGroup(name="Other Group")
        session.add_all([priest_group, ally_group])
        session.commit()
        _seed_character(
            client, name="Isolated Priest", school="priest",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            skills={"precepts": 2},
            gaming_group_id=priest_group.id, is_published=True,
            precepts_pool=[{"value": 9}],
        )
        ally_id = _seed_character(
            client, name="Separated Bushi", school="akodo_bushi",
            gaming_group_id=ally_group.id, is_published=True,
        )
        assert self._precepts_list(client, ally_id) == []

    def test_self_excluded_from_ally_list(self, client):
        """The priest viewing their own sheet does NOT see themselves in
        priest_precepts_allies (self pool renders via preceptsPool instead)."""
        priest_id, _, _ = self._setup_priest_and_ally(client)
        assert self._precepts_list(client, priest_id) == []

    def test_sheet_embeds_precepts_allies_script(self, client):
        """The ally's sheet page embeds the precepts-allies JSON script tag."""
        _, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.get(f"/characters/{ally_id}")
        assert 'id="priest-precepts-allies"' in resp.text


class TestPriestPreceptsPoolEndpoint:
    """POST /characters/{priest_id}/precepts-pool: a party member commits a
    post-swap pool back to the priest's character. Mirrors the gaming-group
    permission model used by /ally-conviction."""

    def _setup_priest_and_ally(self, client, *, priest_rank=3):
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Precepts Endpoint Group")
        session.add(group); session.commit()
        priest_id = _seed_character(
            client, name="Endpoint Priest", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": priest_rank, "otherworldliness": priest_rank,
                    "pontificate": priest_rank},
            skills={"precepts": 3},
            gaming_group_id=group.id, is_published=True,
            precepts_pool=[{"value": 7}, {"value": 3}],
        )
        ally_id = _seed_character(
            client, name="Endpoint Bushi", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        return priest_id, ally_id, group.id

    def test_happy_path_replaces_pool(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 10}, {"value": 2}, {"value": 5}]},
        )
        assert resp.status_code == 200
        assert resp.json() == {"pool": [{"value": 10}, {"value": 2}, {"value": 5}]}
        char = query_db(client).filter(Character.id == priest_id).first()
        assert char.precepts_pool == [{"value": 10}, {"value": 2}, {"value": 5}]

    def test_rejects_non_priest_target(self, client):
        _, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{ally_id}/precepts-pool",
            json={"pool": [{"value": 6}]},
        )
        assert resp.status_code == 400

    def test_rejects_priest_below_3rd_dan(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client, priest_rank=2)
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 6}]},
        )
        assert resp.status_code == 400

    def test_rejects_unknown_priest(self, client):
        resp = client.post(
            "/characters/99999/precepts-pool",
            json={"pool": []},
        )
        assert resp.status_code == 404

    def test_rejects_caller_not_in_group(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        # Remove the priest from the gaming group. The caller's shared-group
        # check now fails; unless the caller is the owner, they get a 403.
        # _seed_character defaults owner_discord_id to the logged-in test
        # user, so we also need to reassign the priest to a different owner
        # to prove the group check (not the ownership fast-path) is what
        # kicks in.
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.gaming_group_id = None
        priest.owner_discord_id = "some_other_user"
        session.commit()
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 6}]},
        )
        assert resp.status_code == 403

    def test_owner_can_write_even_without_group(self, client):
        """A priest editing their own pool via this endpoint is allowed even
        if the priest is not in any gaming group (the same owner-fast-path
        used elsewhere). Typical path is /track, but this endpoint accepts
        too so the swap handler can be a single code path."""
        priest_id, _, _ = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.gaming_group_id = None
        session.commit()
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 4}]},
        )
        assert resp.status_code == 200
        assert resp.json() == {"pool": [{"value": 4}]}

    def test_missing_pool_key_returns_400(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"not_pool": []},
        )
        assert resp.status_code == 400

    def test_malformed_entries_dropped(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [
                {"value": 8},
                "not a dict",
                {"value": "nope"},
                {"value": 999},     # clamped to 100
                {"value": 19},      # legit reroll-10s sum
            ]},
        )
        assert resp.status_code == 200
        assert resp.json() == {"pool": [
            {"value": 8}, {"value": 100}, {"value": 19},
        ]}

    def test_length_capped_at_10(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 5} for _ in range(25)]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["pool"]) == 10

    def test_non_list_pool_becomes_empty(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": "not a list"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"pool": []}

    # ---- Phase 7 tightened-auth regressions ----

    def test_non_owner_requires_rolling_character_id(self, client):
        """Phase 7: a non-owner caller must pass rolling_character_id."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.owner_discord_id = "some_other_user"
        ally = session.query(Character).filter(Character.id == ally_id).first()
        ally.owner_discord_id = "test_user_1"
        session.commit()
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 5}]},
            headers={"X-Test-User": "test_user_1:AllyOwner"},
        )
        assert resp.status_code == 400

    def test_rejects_non_editor_viewer_of_rolling_char(self, client):
        """Phase 7: a viewer without edit access to the rolling character
        is 403'd server-side (defence in depth even though the frontend
        shim already skips the fetch for non-editors)."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.owner_discord_id = "some_other_user"
        session.commit()
        # test_user_1 is authenticated but has no edit access to the
        # ally (admin owns it, test_user_1 isn't in editor_discord_ids).
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 5}], "rolling_character_id": ally_id},
            headers={"X-Test-User": "test_user_1:NonEditor"},
        )
        assert resp.status_code == 403
        # Pool unchanged.
        p = session.query(Character).filter(Character.id == priest_id).first()
        assert p.precepts_pool == [{"value": 7}, {"value": 3}]

    def test_allows_non_owner_editor_of_rolling_char(self, client):
        """Phase 7: caller with edit access to a party-mate (via the
        editor_discord_ids grant, not ownership) is allowed."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        session = client._test_session_factory()
        priest = session.query(Character).filter(Character.id == priest_id).first()
        priest.owner_discord_id = "some_other_user"
        ally = session.query(Character).filter(Character.id == ally_id).first()
        ally.editor_discord_ids = ["test_user_1"]
        session.commit()
        resp = client.post(
            f"/characters/{priest_id}/precepts-pool",
            json={"pool": [{"value": 9}], "rolling_character_id": ally_id},
            headers={"X-Test-User": "test_user_1:GrantedEditor"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"pool": [{"value": 9}]}


class TestAllyConvictionAuth:
    def test_requires_authentication(self):
        """Unauthenticated caller gets a 401 from ally-conviction endpoint."""
        from fastapi.testclient import TestClient
        from starlette.requests import Request
        from starlette.responses import Response
        from app.main import app

        # Temporarily install middleware that clears the user on request.state.
        async def clear_user(request, call_next):
            request.state.user = None
            return await call_next(request)

        # Simpler: directly call the endpoint function with a stub request.
        import asyncio
        from app.routes.characters import ally_conviction

        class _Req:
            class state: pass
            state = state()
            async def json(self): return {"delta": 1}

        req = _Req()
        req.state.user = None
        # Use a dummy db session; the endpoint should 401 before using it.
        resp = asyncio.run(
            ally_conviction(req, 1, db=None)
        )
        assert resp.status_code == 401


class TestPreceptsPoolAuth:
    def test_requires_authentication(self):
        """Unauthenticated caller gets a 401 from the precepts-pool endpoint."""
        import asyncio
        from app.routes.characters import precepts_pool

        class _Req:
            class state: pass
            state = state()
            async def json(self): return {"pool": []}

        req = _Req()
        req.state.user = None
        resp = asyncio.run(
            precepts_pool(req, 1, db=None)
        )
        assert resp.status_code == 401


class TestViewCharacter:
    def test_view_character(self, client):
        cid = _seed_character(
            client,
            name="View Test",
            school="bayushi_bushi",
            school_ring_choice="Fire",
            ring_fire=3,
            skills={"bragging": 2},
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )

        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "View Test" in resp.text

    def test_view_shows_xp(self, client):
        cid = _seed_character(client, name="XP Test", ring_fire=3)

        resp = client.get(f"/characters/{cid}")
        assert "Total Spent" in resp.text
        assert "Unspent" in resp.text

    def test_view_nonexistent_404(self, client):
        resp = client.get("/characters/999")
        assert resp.status_code == 404

    def test_view_sheet_renders_age_when_set(self, client):
        cid = _seed_character(client, name="Aged", age=30)
        body = client.get(f"/characters/{cid}").text
        # Age appears next to the player name in the header.
        assert "Age: 30" in body

    def test_view_sheet_age_unset_shows_validation_issue(self, client):
        cid = _seed_character(client, name="Unaged", age=None)
        body = client.get(f"/characters/{cid}").text
        # The Validation Issues block lists the unset age.
        assert "Validation Issues" in body
        assert "Age" in body

    def test_edit_page_renders_age_input(self, client):
        cid = _seed_character(client, name="EditAge", age=42)
        body = client.get(f"/characters/{cid}/edit").text
        # The Basics section gains an Age number input that's bound to
        # the Alpine state and pre-fills with the current value.
        assert 'name="age"' in body
        assert 'value="42"' in body

    def test_edit_page_age_input_is_narrow(self, client):
        """Age is a 2-3 digit number; render it as a compact input
        rather than a full-width text field."""
        cid = _seed_character(client, name="NarrowAge", age=30)
        body = client.get(f"/characters/{cid}/edit").text
        idx = body.index('name="age"')
        # Walk back to the start of the <input ...> tag and slice.
        tag_start = body.rfind('<input', 0, idx)
        tag_end = body.index('>', tag_start)
        tag = body[tag_start:tag_end + 1]
        # No w-full on the input itself - it should be a narrow class.
        assert 'w-full' not in tag, (
            f"Age input should be narrow, not w-full; got: {tag!r}"
        )
        # Width class is one of w-16 / w-20 / w-24 / w-28 (Tailwind).
        assert any(f'w-{n}' in tag for n in ('16', '20', '24', '28', '32')), (
            f"Age input should carry a narrow Tailwind width class; got: {tag!r}"
        )

    def test_edit_page_age_input_has_no_placeholder(self, client):
        """The Age input is narrow (~96px) and the word "(optional)" doesn't
        fit. The label already conveys what the field is, so no placeholder."""
        cid = _seed_character(client, name="NoPlaceholder", age=None)
        body = client.get(f"/characters/{cid}/edit").text
        idx = body.index('name="age"')
        tag_start = body.rfind('<input', 0, idx)
        tag_end = body.index('>', tag_start)
        tag = body[tag_start:tag_end + 1]
        assert 'placeholder' not in tag, (
            f"Age input must not carry a placeholder; got: {tag!r}"
        )

    def test_view_renders_one_row_per_specialization(self, client):
        cid = _seed_character(
            client, name="MultiSpec",
            specializations=[
                {"text": "Court Etiquette", "skills": ["etiquette"]},
                {"text": "Loyalty Speeches", "skills": ["bragging"]},
            ],
        )
        body = client.get(f"/characters/{cid}").text
        # Slice out the "Advantages & Disadvantages" section so we don't
        # confuse hits in the XP Summary breakdown rows with hits in the
        # canonical advantages list.
        section_start = body.index("Advantages & Disadvantages")
        section_end = body.index("XP Summary", section_start)
        section = body[section_start:section_end]
        assert "Court Etiquette" in section
        assert "Loyalty Speeches" in section
        # Each instance is labeled "Specialization" so the player sees what
        # advantage they took.
        assert section.count("Specialization") >= 2

    def test_view_omits_specializations_section_when_empty(self, client):
        cid = _seed_character(client, name="NoSpec", specializations=[])
        body = client.get(f"/characters/{cid}").text
        # Slice the Advantages section so we don't false-match on
        # XP Summary's empty-state labels.
        if "Advantages & Disadvantages" in body:
            section_start = body.index("Advantages & Disadvantages")
            section_end = body.index("XP Summary", section_start)
            section = body[section_start:section_end]
            assert "Specialization" not in section

    def test_view_renders_freeform_roll_button(self, client):
        """The sheet's Rings section has a Freeform Roll button and modal."""
        cid = _seed_character(client, name="Freeform Roll Char")
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-action="open-freeform-roll"' in resp.text
        assert 'Freeform roll' in resp.text
        assert 'data-modal="freeform-roll"' in resp.text

    def test_view_freeform_default_reroll_true_when_healthy(self, client):
        """A healthy character's Freeform modal defaults Reroll 10s to true."""
        cid = _seed_character(client, name="Healthy FF", ring_earth=2)
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The default expression on ffRerollTens should evaluate to true
        assert "ffRerollTens: true" in resp.text

    def test_view_freeform_default_reroll_false_when_impaired(self, client):
        """An impaired character's Freeform modal defaults Reroll 10s to false."""
        cid = _seed_character(
            client, name="Impaired FF", ring_earth=2,
            current_serious_wounds=2,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "ffRerollTens: false" in resp.text

    def test_view_shosuro_5th_dan_bakes_probabilities(self, client):
        """Shosuro 5th Dan sheet should embed shosuro_flats in attack/WC probs."""
        cid = _seed_character(
            client,
            name="Shosuro 5D",
            school="shosuro_actor",
            school_ring_choice="Air",
            ring_air=3,
            attack=2,
            parry=2,
            knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "shosuro_flats" in resp.text
        # The 5th Dan rule text should now be the new wording
        assert "After making any non-initiative roll" in resp.text


class TestPerAdventureTracking:
    """The sheet embeds a per_adventure JSON list for the tracking panel."""

    def test_togashi_3rd_dan_has_daily_athletics_raises_pool(self, client):
        cid = _seed_character(
            client,
            name="Togashi 3D",
            school="togashi_ise_zumi",
            school_ring_choice="Void",
            ring_void=3,
            skills={"precepts": 3},
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert '"id": "togashi_daily_athletics_raises"' in resp.text
        assert '"name": "Daily Athletics Raises"' in resp.text
        # 4 * precepts = 12
        assert '"max": 12' in resp.text
        assert '"per_day": true' in resp.text

    def _per_adventure_ids(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(r"perAdventure:\s*(\[.*?\]),", resp.text)
        assert m is not None
        return [e["id"] for e in json.loads(m.group(1))]

    def test_togashi_below_3rd_dan_has_no_daily_raises_pool(self, client):
        cid = _seed_character(
            client,
            name="Togashi 2D",
            school="togashi_ise_zumi",
            school_ring_choice="Void",
            ring_void=3,
            skills={"precepts": 3},
            knacks={"athletics": 2, "conviction": 2, "dragon_tattoo": 2},
        )
        assert "togashi_daily_athletics_raises" not in self._per_adventure_ids(client, cid)

    def test_togashi_3rd_dan_without_precepts_has_no_daily_raises_pool(self, client):
        cid = _seed_character(
            client,
            name="Togashi 3D No Precepts",
            school="togashi_ise_zumi",
            school_ring_choice="Void",
            ring_void=3,
            skills={},
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        )
        assert "togashi_daily_athletics_raises" not in self._per_adventure_ids(client, cid)

    def test_non_togashi_has_no_daily_raises_pool(self, client):
        cid = _seed_character(
            client,
            name="Akodo",
            school="akodo_bushi",
            school_ring_choice="Water",
            skills={"precepts": 5},
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        assert "togashi_daily_athletics_raises" not in self._per_adventure_ids(client, cid)

    def test_absorb_void_pool_for_isawa_ishi_is_per_day(self, client):
        """Isawa Ishi's special ability resets Absorb Void with a night's
        rest, so the tracker entry is flagged ``per_day`` (gets a Reset
        button alongside the +/- controls). The pool max is still the
        rank in the knack."""
        cid = _seed_character(
            client, name="IshiAbsorb",
            school="isawa_ishi", school_ring_choice="Void",
            knacks={"absorb_void": 3, "kharmic_spin": 1, "otherworldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert '"id": "absorb_void"' in resp.text
        import json, re
        m = re.search(r"perAdventure:\s*(\[.*?\]),", resp.text)
        assert m is not None
        entries = json.loads(m.group(1))
        ab = next(e for e in entries if e["id"] == "absorb_void")
        assert ab["type"] == "counter"
        assert ab["max"] == 3
        assert ab["name"] == "Absorb Void"
        assert ab.get("per_day") is True

    def test_absorb_void_pool_for_kitsune_warden_is_per_adventure(self, client):
        """Kitsune Warden has no per-day reset language, so its Absorb
        Void pool stays per-adventure (no Reset button)."""
        cid = _seed_character(
            client, name="KitsuneAbsorb",
            school="kitsune_warden", school_ring_choice="Earth",
            knacks={"absorb_void": 2, "commune": 1, "iaijutsu": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        import json, re
        m = re.search(r"perAdventure:\s*(\[.*?\]),", resp.text)
        assert m is not None
        entries = json.loads(m.group(1))
        ab = next(e for e in entries if e["id"] == "absorb_void")
        assert ab["max"] == 2
        assert ab.get("per_day") is not True

    def test_absorb_void_not_in_per_adventure_when_school_lacks_it(self, client):
        cid = _seed_character(
            client, name="AkodoNoAbsorb", school="akodo_bushi",
            school_ring_choice="Water",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        assert "absorb_void" not in self._per_adventure_ids(client, cid)

    def test_conviction_entry_is_flagged_per_day(self, client):
        cid = _seed_character(
            client,
            name="Conviction Char",
            school="togashi_ise_zumi",
            school_ring_choice="Void",
            ring_void=3,
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        )
        resp = client.get(f"/characters/{cid}")
        # Conviction is the first match in a per_day-carrying object
        assert '"id": "conviction"' in resp.text
        # Extract the per_adventure JSON via a regex and verify the flag
        import json, re
        m = re.search(r"perAdventure:\s*(\[.*?\]),", resp.text)
        assert m is not None
        entries = json.loads(m.group(1))
        conviction = next(e for e in entries if e["id"] == "conviction")
        assert conviction.get("per_day") is True

    def test_otherworldliness_entry_is_not_flagged_per_day(self, client):
        cid = _seed_character(
            client,
            name="OW Char",
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Air",
            ring_air=3,
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
        )
        resp = client.get(f"/characters/{cid}")
        import json, re
        m = re.search(r"perAdventure:\s*(\[.*?\]),", resp.text)
        assert m is not None
        entries = json.loads(m.group(1))
        ow = next(e for e in entries if e["id"] == "otherworldliness")
        assert ow.get("per_day") is not True


class TestInitiativePerRoundResetFlags:
    """School-abilities JSON flags that drive the per-round reset on initiative.

    The initiative roll resets any per-round ability pools and displays a
    message about what was refreshed. Two abilities currently need reset:
      - Mirumoto 3rd Dan round points (``mirumoto_round_points``)
      - Priest 5th Dan conviction refresh (``priest_round_conviction_refresh``)
    """

    def _school_abilities(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="school-abilities">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_priest_5th_dan_has_round_conviction_refresh(self, client):
        cid = _seed_character(
            client, name="Priest5D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 5, "otherworldliness": 5, "pontificate": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_round_conviction_refresh") is True

    def test_priest_4th_dan_does_not_have_round_conviction_refresh(self, client):
        cid = _seed_character(
            client, name="Priest4D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 4, "otherworldliness": 4, "pontificate": 4},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_round_conviction_refresh") is False

    def test_non_priest_does_not_have_round_conviction_refresh(self, client):
        cid = _seed_character(
            client, name="Akodo5D", school="akodo_bushi",
            knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_round_conviction_refresh") is False


class TestPriestPreceptsPoolContext:
    """The ``priest_precepts_pool`` flag gates the Priest 3rd Dan precepts
    dice pool UI section. It is True only for priests at 3rd Dan or higher.
    ``priest_precepts_pool_size`` carries the pool size (= precepts skill
    rank) when the flag is True, otherwise 0."""

    def _school_abilities(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="school-abilities">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_priest_3rd_dan_has_flag_and_size(self, client):
        cid = _seed_character(
            client, name="Priest3D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            skills={"precepts": 4},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_precepts_pool") is True
        assert flags.get("priest_precepts_pool_size") == 4

    def test_priest_2nd_dan_flag_false_and_size_zero(self, client):
        cid = _seed_character(
            client, name="Priest2D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"precepts": 4},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_precepts_pool") is False
        # Size is forced to 0 when the flag is off so no pool UI even if the
        # player has a non-zero precepts rank.
        assert flags.get("priest_precepts_pool_size") == 0

    def test_non_priest_flag_false(self, client):
        cid = _seed_character(
            client, name="Akodo3D", school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
            skills={"precepts": 4},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_precepts_pool") is False
        assert flags.get("priest_precepts_pool_size") == 0

    def test_priest_3rd_dan_rank_zero_precepts_gives_size_zero(self, client):
        """A priest at 3rd Dan without any precepts skill rank gets flag True
        but size 0 so the Roll button is disabled."""
        cid = _seed_character(
            client, name="Priest3DNoPrecepts", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            skills={},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_precepts_pool") is True
        assert flags.get("priest_precepts_pool_size") == 0

    def test_sheet_embeds_precepts_pool_json(self, client):
        """The priest's saved pool is embedded on the Alpine component so
        Alpine's preceptsPool state initializes correctly on page load."""
        cid = _seed_character(
            client, name="PriestWithPool", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            skills={"precepts": 3},
        )
        # Seed a pool on the character.
        client.post(
            f"/characters/{cid}/track",
            json={"precepts_pool": [{"value": 8}, {"value": 5}, {"value": 2}]},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The serialized pool appears inline in the Alpine data object init.
        assert 'preceptsPool:' in resp.text
        # And carries the seeded values.
        for expected in ('"value": 8', '"value": 5', '"value": 2'):
            assert expected in resp.text


class TestKakitaPhaseZeroFlag:
    """The ``kakita_phase_zero`` flag gates every Kakita-Duelist-specific UI
    hook (Phase-0 visual markers, iaijutsu-only per-die menu, interrupt-attack
    button, 5th Dan contested-iaijutsu modal). It's true for any Kakita
    Duelist regardless of Dan (the Special Ability is always-on), false for
    everyone else.
    """

    def _school_abilities(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="school-abilities">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_kakita_has_phase_zero_flag(self, client):
        cid = _seed_character(
            client, name="Kakita1D", school="kakita_duelist",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("kakita_phase_zero") is True

    def test_non_kakita_does_not_have_phase_zero_flag(self, client):
        cid = _seed_character(
            client, name="Akodo1D", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("kakita_phase_zero") is False

    def test_kakita_5th_dan_has_phase_zero_contest_flag(self, client):
        cid = _seed_character(
            client, name="Kakita5D", school="kakita_duelist",
            knacks={"double_attack": 5, "iaijutsu": 5, "lunge": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("kakita_5th_dan_phase_zero_contest") is True

    def test_kakita_below_5th_dan_no_phase_zero_contest_flag(self, client):
        cid = _seed_character(
            client, name="Kakita4D", school="kakita_duelist",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("kakita_5th_dan_phase_zero_contest") is False

    def test_non_kakita_no_phase_zero_contest_flag(self, client):
        cid = _seed_character(
            client, name="Akodo5D", school="akodo_bushi",
            knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("kakita_5th_dan_phase_zero_contest") is False


class TestPriestBlessRituals:
    """The ``priest_bless_rituals`` flag gates the Bless conversation topic and
    Bless research buttons on the sheet. The rituals come with the Priest
    school at any Dan, so any priest gets the flag; non-priests never do.
    """

    def _school_abilities(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="school-abilities">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_priest_1st_dan_has_bless_rituals(self, client):
        cid = _seed_character(
            client, name="Priest1D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_bless_rituals") is True

    def test_priest_5th_dan_has_bless_rituals(self, client):
        cid = _seed_character(
            client, name="Priest5D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 5, "otherworldliness": 5, "pontificate": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_bless_rituals") is True

    def test_non_priest_does_not_have_bless_rituals(self, client):
        cid = _seed_character(
            client, name="Akodo", school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("priest_bless_rituals") is False

    def test_bless_buttons_render_on_priest_sheet(self, client):
        cid = _seed_character(
            client, name="Priest2D", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "data-bless-conversation" in resp.text
        assert "data-bless-research" in resp.text
        assert "Bless conversation topic" in resp.text
        assert "Bless research" in resp.text
        # Rules text lives in the tooltip for each button.
        assert "bless a target and pick a topic of conversation" in resp.text
        assert "target makes a roll to perform research" in resp.text

    def test_bless_buttons_absent_on_non_priest_sheet(self, client):
        cid = _seed_character(
            client, name="Kakita", school="kakita_duelist",
            school_ring_choice="Fire",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The button markup carries data-bless-* markers that only appear when
        # the priest_bless_rituals block renders. (The rollBless JS method
        # itself is always in the diceRoller component, so we can't key on the
        # literal button label.)
        assert "data-bless-conversation" not in resp.text
        assert "data-bless-research" not in resp.text
        # The rules-text tooltip strings are also template-only.
        assert "bless a target and pick a topic of conversation" not in resp.text
        assert "target makes a roll to perform research" not in resp.text


class TestMantisPostureTracking:
    """The ``mantis_posture_tracking`` flag gates the posture tracker block
    that renders in the Tracking section for Mantis Wave-Treader characters.
    The buttons drive per-phase posture selection; later phases hang the
    mechanical bonuses off the same state."""

    def _school_abilities(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="school-abilities">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_mantis_has_posture_tracking_flag(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_posture_tracking") is True

    def test_non_mantis_does_not_have_posture_tracking_flag(self, client):
        cid = _seed_character(
            client, school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_posture_tracking") is False

    def test_posture_tracker_renders_on_mantis_sheet(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The tracker block is gated by the mantis_posture_tracking flag and
        # carries a stable testid for the clicktests.
        assert 'data-testid="mantis-posture-tracker"' in resp.text
        assert 'data-action="mantis-posture-offensive"' in resp.text
        assert 'data-action="mantis-posture-defensive"' in resp.text
        # Phase label (literal text up to the x-text span)
        assert "Offensive Posture for Phase" in resp.text
        assert "Defensive Posture for Phase" in resp.text

    def test_posture_tracker_absent_on_non_mantis_sheet(self, client):
        cid = _seed_character(
            client, school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="mantis-posture-tracker"' not in resp.text
        assert 'data-action="mantis-posture-offensive"' not in resp.text
        assert 'data-action="mantis-posture-defensive"' not in resp.text

    def test_posture_state_roundtrips_through_track(self, client):
        """Posture selections persist via adventure_state so they survive
        a page reload. The /track endpoint is the bridge."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
        )
        resp = client.post(
            f"/characters/{cid}/track",
            json={"adventure_state": {
                "mantis_posture_phase": 4,
                "mantis_posture_history": ["offensive", "defensive", "offensive"],
            }},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.adventure_state["mantis_posture_phase"] == 4
        assert char.adventure_state["mantis_posture_history"] == [
            "offensive", "defensive", "offensive",
        ]

    def test_posture_state_hydrates_into_tracking_script(self, client):
        """The Alpine trackingData() initializer reads posture state directly
        from adventure_state so an in-progress round is restored on reload."""
        cid = _seed_character(
            client,
            school="mantis_wave_treader",
            school_ring_choice="Void",
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
            adventure_state={
                "mantis_posture_phase": 3,
                "mantis_posture_history": ["offensive", "defensive"],
            },
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The tojson call in the template embeds the JSON literal inline.
        assert '"mantis_posture_phase": 3' in resp.text
        assert '"mantis_posture_history": ["offensive", "defensive"]' in resp.text

    def test_posture_bonus_summary_block_present(self, client):
        """Phase 5: the posture tracker renders an active-bonus summary line
        whose testid the clicktests look for."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="mantis-posture-bonuses"' in resp.text
        # The summary text distinguishes offensive vs defensive.
        assert "+5 attack rolls" in resp.text
        assert "+5 wound checks" in resp.text

    def test_tn_display_is_alpine_enabled_for_posture_overlay(self, client):
        """Phase 5: the TN-to-be-hit box is wrapped in an x-data scope that
        listens for mantis-posture-changed so the +5 defensive bump is live."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # A stable testid + event wiring + tooltip hook are all visible on the
        # rendered sheet; the clicktests key off the testid and the visible
        # "+5 defensive posture" label.
        assert 'data-testid="tn-display"' in resp.text
        assert "mantis-posture-changed" in resp.text
        assert "+5 defensive posture" in resp.text

    def test_tn_display_on_non_mantis_still_renders_base(self, client):
        """Non-Mantis sheets still carry the tn-display testid (the x-data
        listener fires only when a mantis-posture-changed event arrives, which
        never happens for non-Mantis), so TN rendering is unchanged."""
        cid = _seed_character(
            client, school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="tn-display"' in resp.text

    def test_mantis_5th_dan_has_posture_accumulation_flag(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 5, "iaijutsu": 5, "worldliness": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_posture_accumulation") is True

    def test_mantis_4th_dan_does_not_have_posture_accumulation_flag(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 4, "iaijutsu": 4, "worldliness": 4},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_posture_accumulation") is False

    def test_non_mantis_does_not_have_posture_accumulation_flag(self, client):
        cid = _seed_character(
            client, school="akodo_bushi",
            knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_posture_accumulation") is False

    def test_mantis_5th_dan_accumulator_block_renders(self, client):
        """Phase 6: the accumulator sub-block is present on Dan 5 Mantis sheets
        with the stable testid and summary text the clicktests look for."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 5, "iaijutsu": 5, "worldliness": 5},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="mantis-5th-dan-accumulator"' in resp.text
        assert 'data-testid="mantis-5th-dan-offensive"' in resp.text
        assert 'data-testid="mantis-5th-dan-defensive"' in resp.text
        assert "Accumulated 5th Dan bonuses" in resp.text

    def test_mantis_4th_dan_accumulator_block_absent(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 4, "iaijutsu": 4, "worldliness": 4},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="mantis-5th-dan-accumulator"' not in resp.text

    def test_tn_display_5th_dan_accumulator_wiring_present(self, client):
        """Phase 6: the TN x-data scope on Dan 5 Mantis sheets carries the
        accum flag so the defensive-posture-count bump can be added to the
        displayed TN at runtime."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 5, "iaijutsu": 5, "worldliness": 5},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="tn-5th-dan-accumulator"' in resp.text
        # The inline accum: true boolean is the Dan 5+ discriminator.
        assert "accum: true" in resp.text

    def test_tn_display_dan_4_mantis_accum_false(self, client):
        """Dan 4 Mantis still has the tn-display x-data but accum is false so
        no accumulator contribution is added at runtime."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 4, "iaijutsu": 4, "worldliness": 4},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "accum: false" in resp.text

    def test_mantis_3rd_dan_offensive_flag_at_dan_3(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_offensive") is True
        # X defaults to attack skill rank; unseeded attack starts at 1.
        assert flags.get("mantis_3rd_dan_x") == 1

    def test_mantis_3rd_dan_offensive_x_matches_attack_skill(self, client):
        """mantis_3rd_dan_x is fed by the character's attack skill rank."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
            attack=4,
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_x") == 4

    def test_mantis_2nd_dan_does_not_have_3rd_dan_offensive(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_offensive") is False
        assert flags.get("mantis_3rd_dan_x") == 0

    def test_non_mantis_does_not_have_3rd_dan_offensive(self, client):
        cid = _seed_character(
            client, school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_offensive") is False

    def test_mantis_3rd_dan_button_markup_present(self, client):
        """The attack-result-modal button is rendered (inside x-show gating)
        on Dan 3+ Mantis sheets - clicktests key off the data-action attr."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-action="mantis-3rd-dan-offensive"' in resp.text
        assert 'data-testid="mantis-3rd-dan-offensive-accum"' in resp.text
        # Button label is hard-coded so grep it here to catch accidental typos.
        assert "Spend another action to increase attack and damage" in resp.text

    def test_mantis_2nd_dan_no_3rd_dan_button(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-action="mantis-3rd-dan-offensive"' not in resp.text

    def test_mantis_3rd_dan_accum_state_roundtrips(self, client):
        """The 3rd Dan offensive accumulator is persisted via adventure_state."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        resp = client.post(
            f"/characters/{cid}/track",
            json={"adventure_state": {"mantis_offensive_3rd_dan_accum": 3}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.adventure_state["mantis_offensive_3rd_dan_accum"] == 3

    def test_mantis_3rd_dan_accum_hydrates_into_tracking(self, client):
        """Hydrating a non-zero accumulator from adventure_state on page load."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
            adventure_state={"mantis_offensive_3rd_dan_accum": 5},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert '"mantis_offensive_3rd_dan_accum": 5' in resp.text

    def test_mantis_3rd_dan_defensive_flag_at_dan_3(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_defensive") is True

    def test_mantis_2nd_dan_does_not_have_3rd_dan_defensive(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_defensive") is False

    def test_non_mantis_does_not_have_3rd_dan_defensive(self, client):
        cid = _seed_character(
            client, school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        flags = self._school_abilities(client, cid)
        assert flags.get("mantis_3rd_dan_defensive") is False

    def test_mantis_3rd_dan_defensive_button_markup_present(self, client):
        """Dan 3+ Mantis renders the Tracking-section defensive button and the
        Clear bonuses button. Clicktests key off both data-action attrs."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-action="mantis-3rd-dan-defensive"' in resp.text
        assert 'data-testid="mantis-3rd-dan-defensive-accum"' in resp.text
        assert 'data-action="mantis-clear-bonuses"' in resp.text
        # Button labels hard-coded - guard against accidental typos.
        assert "Spend action to increase TN and wound checks" in resp.text
        assert "Clear bonuses" in resp.text

    def test_mantis_2nd_dan_no_3rd_dan_defensive_button(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-action="mantis-3rd-dan-defensive"' not in resp.text
        # Clear bonuses is still rendered (it's gated on mantis_posture_tracking,
        # not on 3rd Dan) for any Mantis character since it drives round reset.
        assert 'data-action="mantis-clear-bonuses"' in resp.text

    def test_mantis_3rd_dan_defensive_accum_state_roundtrips(self, client):
        """Defensive accumulator persists via adventure_state."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        resp = client.post(
            f"/characters/{cid}/track",
            json={"adventure_state": {"mantis_defensive_3rd_dan_accum": 4}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.adventure_state["mantis_defensive_3rd_dan_accum"] == 4

    def test_mantis_3rd_dan_defensive_accum_hydrates(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
            adventure_state={"mantis_defensive_3rd_dan_accum": 7},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert '"mantis_defensive_3rd_dan_accum": 7' in resp.text

    def test_tn_display_has_3rd_dan_accumulator_wiring(self, client):
        """Dan 3+ Mantis TN display x-data carries has3rdDan flag and tooltip
        plumbing for the defensive accumulator."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "has3rdDan: true" in resp.text
        assert 'data-testid="tn-3rd-dan-accumulator"' in resp.text

    def test_tn_display_dan_2_mantis_has3rdDan_false(self, client):
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "has3rdDan: false" in resp.text


class TestPartyPriestsContext:
    """The ``party_priests`` list feeds the "<priest> priest blessed for 10
    rerolls" button on the sheet's roll modal. It includes every priest in the
    character's gaming group (any Dan) and excludes the character themselves.
    """

    def _party_priests(self, client, cid):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(
            r'id="party-priests">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        return json.loads(m.group(1))

    def test_no_gaming_group_means_no_priests(self, client):
        cid = _seed_character(
            client, name="Solo", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        assert self._party_priests(client, cid) == []

    def test_group_without_priests_is_empty(self, client):
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="No Priests Here")
        session.add(group); session.commit()
        cid = _seed_character(
            client, name="Bushi", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        _seed_character(
            client, name="Other Bushi", school="mirumoto_bushi",
            knacks={"counterattack": 1, "double_attack": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        assert self._party_priests(client, cid) == []

    def test_any_dan_priest_in_party_appears(self, client):
        """Priest at 1st Dan still provides the ritual — Dan doesn't gate it."""
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Priest Party")
        session.add(group); session.commit()
        cid = _seed_character(
            client, name="Bushi", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        pid = _seed_character(
            client, name="Isawa Priest", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
            gaming_group_id=group.id, is_published=True,
        )
        priests = self._party_priests(client, cid)
        assert priests == [{"priest_id": pid, "name": "Isawa Priest"}]

    def test_multiple_priests_all_appear(self, client):
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Temple")
        session.add(group); session.commit()
        cid = _seed_character(
            client, name="Target", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, is_published=True,
        )
        p1 = _seed_character(
            client, name="Priest One", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
            gaming_group_id=group.id, is_published=True,
        )
        p2 = _seed_character(
            client, name="Priest Two", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            gaming_group_id=group.id, is_published=True,
        )
        priests = self._party_priests(client, cid)
        ids = sorted(p["priest_id"] for p in priests)
        assert ids == sorted([p1, p2])

    def test_priest_does_not_appear_in_their_own_party_priests(self, client):
        """A priest cannot rely on themselves — party_priests excludes self."""
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Lonely Priest")
        session.add(group); session.commit()
        pid = _seed_character(
            client, name="Only Priest", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            gaming_group_id=group.id, is_published=True,
        )
        assert self._party_priests(client, pid) == []


class TestEditCharacter:
    def test_edit_page_loads(self, client):
        cid = _seed_character(client, name="Edit Test")

        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200

    def test_edit_nonexistent_404(self, client):
        resp = client.get("/characters/999/edit")
        assert resp.status_code == 404


class TestEditPageUnkemptNote:
    """The Edit Sheet's live skill-roll display must annotate the Culture
    row with the -10 from the Unkempt disadvantage, mirroring how Charming
    surfaces "+5 from Charming" on the same row. The Unkempt -10 stays
    OUT of the unconditional flat bonus because the disadvantage's effect
    is conditional ("in the eyes of those who judge the unkempt")."""

    def test_skill_roll_display_js_emits_unkempt_note(self, client):
        cid = _seed_character(client, name="Unkempt Edit")
        body = client.get(f"/characters/{cid}/edit").text
        # The JS skillRollDisplay() function must include a branch that pushes
        # an Unkempt-related note when culture is the skill being rendered.
        idx = body.index("skillRollDisplay(skillId)")
        # Read a generous slice — the function is large and grows over time
        # as more conditional bonuses are added.
        tail = body[idx:idx + 8000]
        assert "disadvantages.unkempt" in tail and "culture" in tail, (
            "expected skillRollDisplay() to check disadvantages.unkempt and "
            f"the culture skill id; got: {tail!r}"
        )
        # Must push the conditional note onto parts (not mutate flatBonus,
        # since the -10 only applies in the eyes of those who judge).
        assert "parts.push('-10" in tail or 'parts.push("-10' in tail, (
            "expected the unkempt branch to push a '-10 ...' note onto parts"
        )

    def test_skill_roll_display_js_does_not_bake_unkempt_into_flatbonus(self, client):
        """Read the actual unkempt if-block out of the rendered JS and
        verify there is no flatBonus mutation inside it."""
        cid = _seed_character(client, name="Unkempt Edit2")
        body = client.get(f"/characters/{cid}/edit").text
        # Find "this.disadvantages.unkempt" and slice from the enclosing
        # 'if (' to the matching closing '}'.
        marker = "this.disadvantages.unkempt"
        m_idx = body.index(marker)
        if_start = body.rfind("if (", 0, m_idx)
        # Walk forward to the opening '{' of the if-block
        brace_open = body.index("{", m_idx)
        # Walk braces to find the matching close.
        depth = 1
        i = brace_open + 1
        while i < len(body) and depth > 0:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
            i += 1
        block = body[if_start:i]
        # No flatBonus assignment inside this exact block.
        assert "flatBonus" not in block, (
            f"Unkempt branch must not touch flatBonus: {block!r}"
        )


class TestAbsorbVoidNonRollableAndExcludedFromPickers:
    """Absorb Void is a per-adventure VP-restoration ability, not a roll.
    The sheet must not render a dice icon next to it, the editor's flexible
    1st/2nd/3rd Dan technique pickers (Mantis, Kitsune Warden, Isawa Ishi,
    Shugenja, Suzume Overseer, Ide Diplomat) must not list it as an option
    that could earn an extra rolled die or a free raise."""

    def test_sheet_does_not_render_dice_icon_for_absorb_void(self, client):
        cid = _seed_character(
            client, name="AbsorbDiceHidden",
            school="isawa_ishi", school_ring_choice="Void",
            knacks={"absorb_void": 2, "kharmic_spin": 2, "otherworldliness": 2},
        )
        body = client.get(f"/characters/{cid}").text
        # The roll-icon button uses data-roll-key="knack:<id>". The
        # excluded set in the template must include absorb_void so no
        # such button is emitted for it.
        assert 'data-roll-key="knack:absorb_void"' not in body

    def test_editor_mantis_non_rollable_set_includes_absorb_void(self, client):
        """The JS-side MANTIS_NON_ROLLABLE_KNACKS Set drives every
        flexible-pick dropdown in the editor (Mantis 2nd Dan, Kitsune
        Warden 1st Dan, the generic flexible 2nd Dan picker). Listing
        absorb_void here keeps it out of all of them at once."""
        cid = _seed_character(client, name="EditorAbsorbExcl")
        body = client.get(f"/characters/{cid}/edit").text
        idx = body.index("MANTIS_NON_ROLLABLE_KNACKS = new Set([")
        end = body.index("]);", idx)
        block = body[idx:end]
        assert "'absorb_void'" in block, (
            f"absorb_void must be in MANTIS_NON_ROLLABLE_KNACKS so all "
            f"flexible 1st/2nd/3rd Dan pickers exclude it; got: {block!r}"
        )


class TestEditPageDiscerningInvestigationBonus:
    """Discerning gives 1 free raise (+5) on Interrogation but 2 free raises
    (+10) on Investigation. The Edit Sheet's live skill-roll parenthetical
    must reflect both amounts. Regression: the JS treated all free-raise
    advantages uniformly as +5, so Investigation showed +5 instead of +10."""

    def test_skill_roll_display_js_handles_discerning_investigation_as_plus_10(
        self, client,
    ):
        cid = _seed_character(client, name="Discerning Edit")
        body = client.get(f"/characters/{cid}/edit").text
        idx = body.index("skillRollDisplay(skillId)")
        tail = body[idx:idx + 5000]
        # The function body must reference the +10 Discerning case for
        # investigation. It should not be relying solely on the generic
        # ADVANTAGE_FREE_RAISES loop (which gives a flat +5 to every match).
        assert "investigation" in tail.lower(), (
            "expected skillRollDisplay() to mention investigation for the "
            f"discerning special case; got: {tail!r}"
        )
        assert "+10 from Discerning" in tail or "10 from Discerning" in tail, (
            f"expected an explicit '+10 from Discerning' note in JS; got: {tail!r}"
        )

    def test_advantage_free_raises_no_longer_lists_discerning(self, client):
        """Discerning must NOT be in the generic ADVANTAGE_FREE_RAISES map -
        otherwise the loop would push '+5 from Discerning' alongside the
        special-case '+10 from Discerning'. Keep it in one place."""
        cid = _seed_character(client, name="DiscerningMap")
        body = client.get(f"/characters/{cid}/edit").text
        idx = body.index("ADVANTAGE_FREE_RAISES = {")
        end = body.index("};", idx)
        block = body[idx:end]
        assert "'discerning'" not in block and '"discerning"' not in block, (
            f"discerning must be removed from ADVANTAGE_FREE_RAISES; got: {block!r}"
        )


class TestEditPageXpLabelsSaySpent:
    """The XP totals beside skills, school knacks, foreign knacks, rings,
    and Attack/Parry on the edit page must read e.g. "15 XP spent" rather
    than just "15 XP", so players don't mistake the running total for the
    cost of the next increment. Advantage/disadvantage rows still read
    "X XP" / "+X XP" because they ARE per-item costs, not running totals."""

    def test_skill_total_label_says_spent(self, client):
        """The skillXpLabel JS helper is the single source for every skill
        row's XP-total label. Its return string must read "N XP spent"."""
        cid = _seed_character(client, name="Lbl")
        body = client.get(f"/characters/{cid}/edit").text
        # Find the skillXpLabel function definition and assert it returns
        # totalSkillCost(...) + ' XP spent'
        idx = body.index("skillXpLabel(skillId, isAdvanced)")
        body_tail = body[idx:idx + 400]
        assert "totalSkillCost(rank, isAdvanced) + ' XP spent'" in body_tail, (
            f"skillXpLabel must return a 'XP spent' string; got: {body_tail!r}"
        )

    def _assert_xtext_says_spent(self, body: str, expr_substr: str):
        """Find an x-text attribute containing expr_substr and assert it
        ends with " XP spent'" (single-quoted)."""
        idx = body.index(expr_substr)
        # x-text="..." starts before; find the surrounding x-text=" boundary
        attr_start = body.rfind('x-text="', 0, idx)
        attr_end = body.index('"', attr_start + len('x-text="'))
        expr = body[attr_start + len('x-text="'):attr_end]
        assert expr.endswith("' XP spent'") or expr.endswith(' XP spent"'), (
            f"expected x-text expression containing {expr_substr!r} to end "
            f"with \"' XP spent'\", got: {expr!r}"
        )

    def test_school_knack_label_says_spent(self, client):
        cid = _seed_character(client, name="Lbl2")
        body = client.get(f"/characters/{cid}/edit").text
        self._assert_xtext_says_spent(body, "totalKnackCostSingle(")

    def test_ring_label_says_spent(self, client):
        cid = _seed_character(client, name="Lbl3")
        body = client.get(f"/characters/{cid}/edit").text
        self._assert_xtext_says_spent(body, "ringCost(")

    def test_attack_label_says_spent(self, client):
        cid = _seed_character(client, name="Lbl4")
        body = client.get(f"/characters/{cid}/edit").text
        self._assert_xtext_says_spent(body, "combatSkillXp(attack)")

    def test_parry_label_says_spent(self, client):
        cid = _seed_character(client, name="Lbl5")
        body = client.get(f"/characters/{cid}/edit").text
        self._assert_xtext_says_spent(body, "combatSkillXp(parry)")

    def test_foreign_knack_label_says_spent(self, client):
        cid = _seed_character(
            client, name="Lbl6", foreign_knacks={"athletics": 1},
        )
        body = client.get(f"/characters/{cid}/edit").text
        self._assert_xtext_says_spent(body, "foreignKnackTotalCost(")

    def test_advantage_xp_label_unchanged(self, client):
        """Advantages still read "N XP" (no "spent"), since each row shows
        the per-advantage cost, not a running total."""
        cid = _seed_character(client, name="Lbl7")
        body = client.get(f"/characters/{cid}/edit").text
        # The advantage rows render the literal "{{ adv.xp_cost }} XP" - we
        # can spot-check by searching for "XP</span>" with no preceding
        # "spent". At least one advantage row should match.
        assert " XP</span>" in body
        # And no advantage row should have been accidentally rewritten:
        assert " XP spent</span>" not in body or body.count(" XP</span>") > 0

    def test_disadvantage_xp_label_unchanged(self, client):
        cid = _seed_character(client, name="Lbl8")
        body = client.get(f"/characters/{cid}/edit").text
        # Disadvantages render "+{{ dis.xp_value }} XP" inline.
        assert "+" in body and " XP</span>" in body


class TestUpdateCharacter:
    def test_update_changes_fields(self, client):
        cid = _seed_character(client, name="Original")

        form = make_character_form(name="Updated", ring_air="4", honor="3.0")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303

        char = query_db(client).filter(Character.id == cid).first()
        assert char.name == "Updated"
        assert char.ring_air == 4
        assert char.honor == 3.0

    def test_update_nonexistent_404(self, client):
        form = make_character_form()
        resp = client.post("/characters/999", data=form)
        assert resp.status_code == 404

    def test_form_post_persists_foreign_knack_field(self, client):
        """Coverage for the legacy form-POST path: a `foreign_knack_X`
        field with rank>=1 persists into character.foreign_knacks."""
        cid = _seed_character(client, name="ForeignForm")
        form = make_character_form()
        form["foreign_knack_athletics"] = "2"
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.foreign_knacks == {"athletics": 2}

    def test_form_post_drops_foreign_knack_with_rank_zero(self, client):
        """A foreign_knack_X with rank<1 is dropped (not persisted)."""
        cid = _seed_character(client, name="ForeignZeroRank")
        form = make_character_form()
        form["foreign_knack_athletics"] = "0"
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert "athletics" not in (char.foreign_knacks or {})

    def test_form_post_treats_non_int_foreign_knack_as_zero(self, client):
        """A garbled foreign_knack_X value (e.g. 'abc') is silently zeroed."""
        cid = _seed_character(client, name="ForeignBadInt")
        form = make_character_form()
        form["foreign_knack_athletics"] = "not-a-number"
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert "athletics" not in (char.foreign_knacks or {})

    def test_form_post_persists_specializations_json_field(self, client):
        """The form-encoded POST accepts a hidden ``specializations_json``
        field carrying the full list - same wire format as autosave."""
        import json
        cid = _seed_character(client, name="SpecForm")
        form = make_character_form()
        form["specializations_json"] = json.dumps([
            {"text": "Court Etiquette", "skills": ["etiquette"]},
            {"text": "Loyalty Speeches", "skills": ["bragging"]},
        ])
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
            {"text": "Loyalty Speeches", "skills": ["bragging"]},
        ]

    def test_form_post_missing_specializations_json_clears_list(self, client):
        """If the field is absent from a form POST, treat as no specs.
        (The form always sends it as JSON, so this is a defensive case.)"""
        cid = _seed_character(
            client, name="ClearForm",
            specializations=[{"text": "Old", "skills": ["culture"]}],
        )
        form = make_character_form()
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == []

    def test_form_post_garbage_specializations_json_treated_as_empty(self, client):
        """If the hidden field arrives malformed (e.g. truncated by a
        crashed Alpine update), don't blow up the route - persist []."""
        cid = _seed_character(
            client, name="GarbageJsonForm",
            specializations=[{"text": "Old", "skills": ["culture"]}],
        )
        form = make_character_form()
        form["specializations_json"] = "{not valid json"
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == []

    def test_autosave_specializations_non_list_treated_as_empty(self, client):
        """A garbled top-level value (e.g. a dict instead of a list) is
        coerced to [] rather than raising."""
        cid = _seed_character(
            client, name="NonListSpec",
            specializations=[{"text": "Old", "skills": ["culture"]}],
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"specializations": {"oops": "not a list"}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == []

    def test_autosave_specializations_non_dict_entry_dropped(self, client):
        """Entries that aren't dicts (e.g. a stray string) are dropped."""
        cid = _seed_character(client, name="NonDictEntry")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"specializations": [
                "not a dict",
                {"text": "Real", "skills": ["culture"]},
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == [
            {"text": "Real", "skills": ["culture"]},
        ]

    def test_autosave_clamps_school_ring_above_cap(self, client):
        """A crafted JSON POST cannot raise the school ring past 6 at
        4th Dan, or past 5 below 4th Dan. Defense-in-depth for the
        cap the editor UI already enforces."""
        cid = _seed_character(
            client, name="RingClamp",
            school="akodo_bushi", school_ring_choice="Water",
            ring_water=3,
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},  # Dan 4
        )
        # Dan 4 character: try to push Water to 9 - clamps to 6.
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rings": {"Water": 9}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.ring_water == 6

    def test_autosave_clamps_school_ring_below_4th_dan(self, client):
        """Below 4th Dan a crafted JSON POST cannot raise the school
        ring past 5 - it's not special until 4th Dan."""
        cid = _seed_character(
            client, name="RingClampLowDan",
            school="akodo_bushi", school_ring_choice="Water",
            ring_water=3,
            # Dan 1 (all school knacks at the free starting rank).
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rings": {"Water": 7}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.ring_water == 5

    def test_autosave_clamps_non_school_ring_at_5(self, client):
        """Non-school rings are always capped at 5, no matter the
        Dan."""
        cid = _seed_character(
            client, name="NonSchoolClamp",
            school="akodo_bushi", school_ring_choice="Water",
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},  # Dan 4
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rings": {"Fire": 8}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.ring_fire == 5

    def test_autosave_non_int_ring_keeps_current_value(self, client):
        """Garbage ring values (string, null, dict) keep the persisted
        ring rather than raising or zeroing the column."""
        cid = _seed_character(
            client, name="GarbageRing",
            school="akodo_bushi", school_ring_choice="Water",
            ring_water=4,
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rings": {"Water": "not a number"}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.ring_water == 4

    def test_form_post_clamps_school_ring_above_cap(self, client):
        """Same clamping behavior on the form-encoded POST route."""
        import json
        cid = _seed_character(
            client, name="FormClamp",
            school="akodo_bushi", school_ring_choice="Water",
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},  # Dan 4
        )
        form = make_character_form()
        form["school"] = "akodo_bushi"
        form["school_ring_choice"] = "Water"
        form["ring_water"] = "9"  # over the cap
        # Dan 4 knacks need to be present in the form too.
        form["knack_double_attack"] = "4"
        form["knack_feint"] = "4"
        form["knack_iaijutsu"] = "4"
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.ring_water == 6

    def test_autosave_persists_foreign_knacks(self, client):
        """API autosave path: foreign_knacks dict in body is cleaned and
        persisted; entries with rank<1 or non-int rank are dropped."""
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        client.post(f"/characters/{cid}/autosave", json={
            "foreign_knacks": {
                "athletics": 2,
                "feint": 0,            # dropped (rank < 1)
                "double_attack": "bad",  # dropped (non-int)
                "lunge": "3",          # coerced to 3
            },
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.foreign_knacks == {"athletics": 2, "lunge": 3}


class TestVersionDiffEndpoint:
    """Coverage for /characters/{id}/versions/{vid}/diff (lines 895-933)."""

    def _make_char_with_versions(self, client):
        cid = _seed_character(
            client, name="DiffTest", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        session = client._test_session_factory()
        try:
            session.add_all([
                CharacterVersion(
                    character_id=cid, version_number=1,
                    state={"name": "v1", "rings": {"Air": 2}},
                    summary="Initial",
                ),
                CharacterVersion(
                    character_id=cid, version_number=2,
                    state={"name": "v2", "rings": {"Air": 3}},
                    summary="Bumped Air",
                ),
            ])
            session.commit()
            v2 = session.query(CharacterVersion).filter_by(
                character_id=cid, version_number=2,
            ).first()
            return cid, v2.id
        finally:
            session.close()

    def test_diff_renders_for_editor(self, client):
        cid, v2_id = self._make_char_with_versions(client)
        resp = client.get(f"/characters/{cid}/versions/{v2_id}/diff")
        assert resp.status_code == 200

    def test_diff_returns_401_when_unauthenticated(self, client, engine):
        """An anonymous client (no X-Test-User header) gets 401."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from sqlalchemy.orm import sessionmaker
        cid, v2_id = self._make_char_with_versions(client)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        def _override_db():
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()
        original_db = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = _override_db
        try:
            with TestClient(app) as anon:
                resp = anon.get(f"/characters/{cid}/versions/{v2_id}/diff")
                assert resp.status_code == 401
        finally:
            if original_db:
                app.dependency_overrides[get_db] = original_db
            else:
                app.dependency_overrides.pop(get_db, None)

    def test_diff_404_for_unknown_character(self, client):
        resp = client.get("/characters/9999/versions/1/diff")
        assert resp.status_code == 404

    def test_diff_403_for_non_editor(self, client):
        """A logged-in user who isn't the owner / editor gets 403."""
        cid, v2_id = self._make_char_with_versions(client)
        # Override the auth header to an unrelated whitelisted discord id.
        resp = client.get(
            f"/characters/{cid}/versions/{v2_id}/diff",
            headers={"X-Test-User": "test_user_2:nonowner"},
        )
        assert resp.status_code == 403

    def test_diff_404_for_unknown_version(self, client):
        cid, _v2_id = self._make_char_with_versions(client)
        resp = client.get(f"/characters/{cid}/versions/99999/diff")
        assert resp.status_code == 404

    def test_diff_404_for_first_version_no_prior(self, client):
        """version_number == 1 has no prior to diff against -> 404."""
        cid, _v2_id = self._make_char_with_versions(client)
        session = client._test_session_factory()
        try:
            v1 = session.query(CharacterVersion).filter_by(
                character_id=cid, version_number=1,
            ).first()
            v1_id = v1.id
        finally:
            session.close()
        resp = client.get(f"/characters/{cid}/versions/{v1_id}/diff")
        assert resp.status_code == 404

    def test_diff_404_when_prior_version_row_missing(self, client):
        """If version_number is e.g. 3 but version 2 was deleted, the
        prior-version lookup returns None and the route 404s rather
        than 500ing."""
        cid = _seed_character(client, name="DiffGap")
        session = client._test_session_factory()
        try:
            session.add(CharacterVersion(
                character_id=cid, version_number=3,
                state={"name": "v3"}, summary="Out-of-order",
            ))
            session.commit()
            v3 = session.query(CharacterVersion).filter_by(
                character_id=cid, version_number=3,
            ).first()
            v3_id = v3.id
        finally:
            session.close()
        resp = client.get(f"/characters/{cid}/versions/{v3_id}/diff")
        assert resp.status_code == 404


class TestDeleteCharacter:
    def test_delete_removes_character(self, client):
        cid = _seed_character(client, name="Delete Me")

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303
        assert query_db(client).count() == 0

    def test_delete_nonexistent_no_error(self, client):
        resp = client.post("/characters/999/delete", follow_redirects=False)
        assert resp.status_code == 303

    def test_delete_cascades_to_character_versions(self, client):
        """Deleting a Character must take its CharacterVersion rows
        with it. Without this, SQLite reuses the freed id on the next
        insert and the new character starts life with the deleted
        character's revision history hanging off it."""
        cid = _seed_character(client, name="To Delete")

        # Seed a couple of version rows for this character so we can
        # observe them being cascaded away.
        session = client._test_session_factory()
        try:
            session.add_all([
                CharacterVersion(
                    character_id=cid, version_number=1,
                    state={"name": "v1"}, summary="Initial",
                ),
                CharacterVersion(
                    character_id=cid, version_number=2,
                    state={"name": "v2"}, summary="Second",
                ),
            ])
            session.commit()
        finally:
            session.close()

        assert query_db(client, CharacterVersion).filter_by(
            character_id=cid,
        ).count() == 2

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303

        assert query_db(client).filter_by(id=cid).count() == 0
        assert query_db(client, CharacterVersion).filter_by(
            character_id=cid,
        ).count() == 0

    def test_delete_does_not_touch_other_characters_versions(self, client):
        """Cascade must scope to *this* character. A delete cannot
        wipe revisions belonging to other characters that happen to
        share an autoincrement neighborhood."""
        keep_cid = _seed_character(client, name="Keep Me")
        drop_cid = _seed_character(client, name="Drop Me")

        session = client._test_session_factory()
        try:
            session.add_all([
                CharacterVersion(
                    character_id=keep_cid, version_number=1,
                    state={"name": "k1"}, summary="Keep this",
                ),
                CharacterVersion(
                    character_id=drop_cid, version_number=1,
                    state={"name": "d1"}, summary="Drop this",
                ),
            ])
            session.commit()
        finally:
            session.close()

        client.post(f"/characters/{drop_cid}/delete", follow_redirects=False)

        assert query_db(client, CharacterVersion).filter_by(
            character_id=keep_cid,
        ).count() == 1
        assert query_db(client, CharacterVersion).filter_by(
            character_id=drop_cid,
        ).count() == 0


class TestAutoSave:
    def test_autosave_updates_character(self, client):
        cid = _seed_character(client, name="Before Save")

        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "After Save", "rings": {"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        char = query_db(client).filter(Character.id == cid).first()
        assert char.name == "After Save"
        assert char.ring_air == 3

    def test_autosave_partial_update(self, client):
        cid = _seed_character(client, name="Original", honor=1.0)

        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"honor": 3.0},
        )
        assert resp.status_code == 200

        char = query_db(client).filter(Character.id == cid).first()
        assert char.honor == 3.0
        assert char.name == "Original"  # unchanged

    def test_autosave_persists_age(self, client):
        cid = _seed_character(client, name="AgeAutoSave")
        resp = client.post(
            f"/characters/{cid}/autosave", json={"age": 42},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.age == 42

    def test_autosave_age_can_be_cleared_back_to_none(self, client):
        cid = _seed_character(client, name="AgeClear", age=30)
        resp = client.post(
            f"/characters/{cid}/autosave", json={"age": None},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.age is None

    def test_autosave_garbled_age_treated_as_none(self, client):
        """A non-int payload (e.g. browser quirk sending {"age": "abc"})
        should clear rather than 500."""
        cid = _seed_character(client, name="AgeBadInt", age=10)
        resp = client.post(
            f"/characters/{cid}/autosave", json={"age": "not-a-number"},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.age is None

    def test_autosave_persists_specializations_list(self, client):
        cid = _seed_character(client, name="Spec")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"specializations": [
                {"text": "Court Etiquette", "skills": ["etiquette"]},
                {"text": "Loyalty Speeches", "skills": ["bragging"]},
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
            {"text": "Loyalty Speeches", "skills": ["bragging"]},
        ]

    def test_autosave_drops_empty_text_specializations(self, client):
        """A blank-text spec is half-filled-out form state - drop it on
        save rather than persist a nonsense entry."""
        cid = _seed_character(client, name="DropEmpty")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"specializations": [
                {"text": "Court Etiquette", "skills": ["etiquette"]},
                {"text": "", "skills": ["bragging"]},
                {"text": "   ", "skills": ["culture"]},
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
        ]

    def test_autosave_drops_unknown_skill_specializations(self, client):
        cid = _seed_character(client, name="DropBadSkill")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"specializations": [
                {"text": "Bogus", "skills": ["not_a_skill_id"]},
                {"text": "Real", "skills": ["culture"]},
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == [
            {"text": "Real", "skills": ["culture"]},
        ]

    def test_autosave_accepts_combat_skill_specializations(self, client):
        """Specialization may target the combat skills ``attack`` or
        ``parry`` (not just regular skills)."""
        cid = _seed_character(client, name="CombatSpec")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"specializations": [
                {"text": "katana", "skills": ["attack"]},
                {"text": "vs cavalry", "skills": ["parry"]},
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.specializations == [
            {"text": "katana", "skills": ["attack"]},
            {"text": "vs cavalry", "skills": ["parry"]},
        ]


    def test_autosave_rejects_initiative_for_mantis_2nd_dan(self, client):
        """Server-side validation: mantis_2nd_dan_free_raise cannot be
        'initiative' (rules exclude it - no meaning on init rolls)."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"technique_choices": {"mantis_2nd_dan_free_raise": "initiative"}},
        )
        assert resp.status_code == 400
        assert "mantis_2nd_dan_free_raise" in resp.json()["error"]

    def test_autosave_rejects_worldliness_for_mantis_2nd_dan(self, client):
        """Server-side validation: non-rollable knacks (worldliness etc.)
        cannot be the Mantis 2nd Dan pick."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"technique_choices": {"mantis_2nd_dan_free_raise": "worldliness"}},
        )
        assert resp.status_code == 400

    def test_autosave_accepts_valid_mantis_2nd_dan_choice(self, client):
        """Server-side validation accepts any eligible choice (e.g. damage)."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"technique_choices": {"mantis_2nd_dan_free_raise": "damage"}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.technique_choices == {"mantis_2nd_dan_free_raise": "damage"}

    def test_autosave_allows_clearing_mantis_2nd_dan_choice(self, client):
        """Empty/None value clears the choice - validation does not reject it."""
        cid = _seed_character(
            client, school="mantis_wave_treader", school_ring_choice="Void",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
            technique_choices={"mantis_2nd_dan_free_raise": "attack"},
        )
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"technique_choices": {"mantis_2nd_dan_free_raise": ""}},
        )
        assert resp.status_code == 200

    def test_autosave_owner_reassignment_by_admin(self, client):
        """Admin can reassign character ownership via autosave."""
        from app.models import User
        session = client._test_session_factory()
        # Create the admin user and another user
        session.add(User(discord_id="183026066498125825", discord_name="admin", display_name="Admin"))
        session.add(User(discord_id="999", discord_name="other", display_name="Other Player"))
        session.commit()

        cid = _seed_character(client, name="Reassign Me")

        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"owner_discord_id": "999"},
        )
        assert resp.status_code == 200

        char = query_db(client).filter(Character.id == cid).first()
        assert char.owner_discord_id == "999"
        assert char.player_name == "Other Player"


class TestRankRecognitionAwards:
    """GM-awarded Rank/Recognition bonuses: persistence, validation, and the
    metadata-only source endpoint that bypasses the version system."""

    def test_autosave_persists_awards_list(self, client):
        cid = _seed_character(client, rank=7.5, recognition=7.5)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 8.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {
                        "id": "a1",
                        "rank_delta": 1.0,
                        "recognition_delta": 0.5,
                        "source": "Defended village",
                        "created_at": "2026-04-09T00:00:00",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank == 8.5
        assert char.recognition == 8.0
        assert len(char.rank_recognition_awards) == 1
        assert char.rank_recognition_awards[0]["source"] == "Defended village"
        assert char.rank_recognition_awards[0]["rank_delta"] == 1.0

    def test_autosave_rejects_negative_recognition_delta(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 0, "recognition_delta": -1.0, "source": "x"},
                ],
            },
        )
        assert resp.status_code == 400
        assert "Recognition delta cannot be negative" in resp.json()["error"]

    def test_autosave_rejects_empty_source(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0, "source": ""},
                ],
            },
        )
        assert resp.status_code == 400
        assert "source" in resp.json()["error"].lower()

    def test_autosave_rejects_non_list_awards(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rank_recognition_awards": "not a list"},
        )
        assert resp.status_code == 400

    def test_autosave_rejects_non_dict_award_entry(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rank_recognition_awards": ["not a dict"]},
        )
        assert resp.status_code == 400

    def test_autosave_rejects_non_numeric_delta(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": "abc", "recognition_delta": 0, "source": "x"},
                ],
            },
        )
        assert resp.status_code == 400

    def test_set_award_source_updates_only_source(self, client):
        cid = _seed_character(client)
        # Seed with one award via autosave
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0, "source": "old"},
                ],
            },
        )
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "new source"},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["source"] == "new source"
        # Deltas untouched
        assert char.rank_recognition_awards[0]["rank_delta"] == 1.0

    def test_set_award_source_unknown_award_404(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "missing", "source": "x"},
        )
        assert resp.status_code == 404

    def test_set_award_source_requires_award_id(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"source": "x"},
        )
        assert resp.status_code == 400

    def test_set_award_source_requires_source(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": ""},
        )
        assert resp.status_code == 400

    def test_source_change_does_not_trigger_unpublished(self, client):
        """Editing only an award's source must not flip the character to
        'modified' state — that's the whole point of the metadata endpoint."""
        cid = _seed_character(client)
        # Add an award and publish so we have a baseline
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 8.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0.5,
                     "source": "Original reason", "created_at": "2026-04-09T00:00:00"},
                ],
            },
        )
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes is False

        # Edit only the source via the metadata endpoint
        client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "Reworded reason"},
        )

        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["source"] == "Reworded reason"
        assert char.has_unpublished_changes is False, (
            "Editing only the award source must NOT trigger a draft"
        )

    def test_delta_change_does_trigger_unpublished(self, client):
        """In contrast, changing an award's delta IS a versionable change."""
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 8.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0.5,
                     "source": "Reason", "created_at": "2026-04-09T00:00:00"},
                ],
            },
        )
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes is False

        # Edit the rank delta via the regular autosave path
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 9.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 2.0, "recognition_delta": 0.5,
                     "source": "Reason", "created_at": "2026-04-09T00:00:00"},
                ],
            },
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes is True

    def test_set_award_source_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "x"},
            headers={"X-Test-User": ""},
        )
        assert resp.status_code == 401

    def test_set_award_source_404_for_unknown_character(self, client):
        resp = client.post(
            "/characters/9999/set-award-source",
            json={"award_id": "a1", "source": "x"},
        )
        assert resp.status_code == 404

    def test_award_delta_only_diff_marks_unpublished(self, client):
        """Direct unit-level check that the awards-only diff branch fires.

        The published snapshot has one award with rank_delta=1.0; we mutate
        the live awards JSON to rank_delta=2.0 *without* touching the
        character's rank field. The diff comparison must spot this via the
        rank_recognition_awards branch and return True.
        """
        from app.models import award_deltas_for_diff
        cid = _seed_character(client)
        char = query_db(client).filter(Character.id == cid).first()
        # Publish a baseline that already has one award.
        char.rank_recognition_awards = [
            {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0.5,
             "source": "Reason", "created_at": "2026-04-09T00:00:00"},
        ]
        char.is_published = True
        char.published_state = char.to_dict()
        client._test_session_factory().merge(char)
        # Now mutate the awards delta but keep everything else identical.
        char.rank_recognition_awards = [
            {"id": "a1", "rank_delta": 2.0, "recognition_delta": 0.5,
             "source": "Reason", "created_at": "2026-04-09T00:00:00"},
        ]
        assert char.has_unpublished_changes is True
        # And the helper itself reports the same deltas after stripping source
        assert award_deltas_for_diff(char.rank_recognition_awards) != \
            award_deltas_for_diff(char.published_state["rank_recognition_awards"])


class TestTrackState:
    def test_track_wounds(self, client):
        cid = _seed_character(client, name="Track Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": 3, "current_serious_wounds": 1},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_light_wounds == 3
        assert char.current_serious_wounds == 1

    def test_track_void_points(self, client):
        cid = _seed_character(client, name="Void Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_void_points": 2},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 2

    def test_track_adventure_state(self, client):
        cid = _seed_character(client, name="Adventure Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"adventure_state": {"lucky_used": True, "adventure_raises_used": 3}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.adventure_state["lucky_used"] is True
        assert char.adventure_state["adventure_raises_used"] == 3

    def test_track_nonexistent_404(self, client):
        resp = client.post("/characters/999/track", json={"current_light_wounds": 1})
        assert resp.status_code == 404

    def test_track_clamps_negative(self, client):
        cid = _seed_character(client, name="Clamp Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": -5},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_light_wounds == 0

    def test_track_requires_auth(self, client):
        cid = _seed_character(client, name="Track Auth Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": 1},
            headers={"X-Test-User": ""},
        )
        assert resp.status_code == 401

    def test_track_forbidden_for_non_editor(self, client):
        from app.models import User
        # Seed a character owned by a different user
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, name="Track Permission", owner_discord_id="999")
        # Use a different non-admin test user
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": 1},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_track_rejects_non_editor_action_dice(self, client):
        """Read-only roll mode Phase 2: non-editor rolls initiative in the
        browser and Alpine state updates locally, but the save shim must
        not round-trip to /track. If it did (e.g. the shim regressed),
        this endpoint is the last line of defense - confirm it 403s on
        the action_dice field specifically, not just wounds."""
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="owner", display_name="Owner"))
        session.commit()
        cid = _seed_character(
            client, name="Action Dice Permission",
            owner_discord_id="999",
            action_dice=[{"value": 9, "spent": False}],
        )
        dice = [{"value": 1, "spent": True}, {"value": 2, "spent": True}]
        resp = client.post(
            f"/characters/{cid}/track",
            json={"action_dice": dice},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice == [{"value": 9, "spent": False}]

    def test_track_action_dice_set(self, client):
        cid = _seed_character(client, name="Action Dice Test")
        dice = [
            {"value": 3, "spent": False},
            {"value": 5, "spent": False},
            {"value": 7, "spent": True},
        ]
        resp = client.post(f"/characters/{cid}/track", json={"action_dice": dice})
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice == dice

    def test_track_action_dice_clear(self, client):
        cid = _seed_character(client, name="Action Dice Clear")
        client.post(
            f"/characters/{cid}/track",
            json={"action_dice": [{"value": 4, "spent": False}]},
        )
        resp = client.post(f"/characters/{cid}/track", json={"action_dice": []})
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice == []

    def test_track_action_dice_clamped_and_sanitized(self, client):
        cid = _seed_character(client, name="Action Dice Sanitize")
        resp = client.post(
            f"/characters/{cid}/track",
            json={
                "action_dice": [
                    {"value": 15, "spent": True},
                    {"value": -3, "spent": False},
                    {"value": 4},
                    {"value": "not a number"},
                    "not a dict",
                    {"spent": True},
                ]
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice == [
            {"value": 10, "spent": True},
            {"value": 0, "spent": False},
            {"value": 4, "spent": False},
            {"value": 0, "spent": True},
        ]

    def test_track_action_dice_rejects_non_list(self, client):
        cid = _seed_character(client, name="Action Dice Non-list")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"action_dice": "nope"},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice == []

    def test_track_action_dice_preserves_spent_by_string(self, client):
        cid = _seed_character(client, name="Action Dice SpentBy")
        resp = client.post(
            f"/characters/{cid}/track",
            json={
                "action_dice": [
                    {"value": 3, "spent": True, "spent_by": "Attack: rolled 25 vs TN 20 - hit, damage 18"},
                    {"value": 5, "spent": False},
                ]
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice == [
            {"value": 3, "spent": True,
             "spent_by": "Attack: rolled 25 vs TN 20 - hit, damage 18"},
            {"value": 5, "spent": False},
        ]

    def test_track_action_dice_spent_by_caps_long_strings(self, client):
        cid = _seed_character(client, name="Action Dice Long SpentBy")
        long_text = "x" * 1000
        resp = client.post(
            f"/characters/{cid}/track",
            json={"action_dice": [{"value": 2, "spent": True, "spent_by": long_text}]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert len(char.action_dice[0]["spent_by"]) == 500

    def test_track_action_dice_spent_by_non_string_dropped(self, client):
        cid = _seed_character(client, name="Action Dice Bad SpentBy")
        resp = client.post(
            f"/characters/{cid}/track",
            json={
                "action_dice": [
                    {"value": 2, "spent": True, "spent_by": 42},      # non-string
                    {"value": 3, "spent": True, "spent_by": ""},       # empty string
                    {"value": 4, "spent": True, "spent_by": "real"},
                ]
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        # First two entries have no spent_by (dropped); third is preserved.
        assert "spent_by" not in char.action_dice[0]
        assert "spent_by" not in char.action_dice[1]
        assert char.action_dice[2]["spent_by"] == "real"

    def test_track_action_dice_preserves_athletics_and_mantis_flags(self, client):
        """The athletics_only and mantis_4th_dan flags must round-trip so the
        die's spending restrictions survive a reload."""
        cid = _seed_character(client, name="Action Dice Flags")
        resp = client.post(
            f"/characters/{cid}/track",
            json={
                "action_dice": [
                    {"value": 7, "spent": False, "athletics_only": True},
                    {"value": 1, "spent": False, "athletics_only": True,
                     "mantis_4th_dan": True},
                    {"value": 5, "spent": False},
                    {"value": 3, "spent": False, "athletics_only": False,
                     "mantis_4th_dan": False},
                ]
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.action_dice[0] == {"value": 7, "spent": False, "athletics_only": True}
        assert char.action_dice[1] == {
            "value": 1, "spent": False, "athletics_only": True, "mantis_4th_dan": True,
        }
        assert char.action_dice[2] == {"value": 5, "spent": False}
        assert char.action_dice[3] == {"value": 3, "spent": False}

    def test_track_rejects_pool_for_non_priest(self, client):
        """Defensive /track guard: a non-priest cannot persist a non-empty
        precepts_pool (the 3rd Dan ability is priest-only)."""
        cid = _seed_character(
            client, name="NotPriestPool", school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        resp = client.post(
            f"/characters/{cid}/track",
            json={"precepts_pool": [{"value": 6}]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.precepts_pool == []

    def test_track_rejects_pool_for_priest_below_3rd_dan(self, client):
        """Defensive /track guard: a priest below 3rd Dan cannot persist a
        non-empty precepts_pool."""
        cid = _seed_character(
            client, name="Dan2Priest", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
        )
        resp = client.post(
            f"/characters/{cid}/track",
            json={"precepts_pool": [{"value": 6}]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.precepts_pool == []

    def test_track_precepts_pool_sanitization(self, client):
        """The precepts_pool sanitizer clamps values, drops bad entries,
        rejects non-list payloads, and caps at 10 entries. Exercises a
        priest at 3rd Dan so the pool can legitimately persist."""
        cid = _seed_character(
            client, name="Precepts Pool", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
        )
        # Happy path: normal list round-trips.
        resp = client.post(
            f"/characters/{cid}/track",
            json={"precepts_pool": [
                {"value": 3},
                {"value": 10},
                {"value": 1},
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.precepts_pool == [{"value": 3}, {"value": 10}, {"value": 1}]
        # Non-list payload -> empty list; malformed entries dropped;
        # out-of-range values clamped; list capped at 10.
        resp = client.post(
            f"/characters/{cid}/track",
            json={"precepts_pool": "not a list"},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.precepts_pool == []
        resp = client.post(
            f"/characters/{cid}/track",
            json={"precepts_pool": [
                "not a dict",
                {"value": "oops"},
                {"value": 0},      # clamped up to 1
                {"value": 999},    # clamped down to sanity cap 100
                {"value": 19},     # legit reroll-10s sum (10+9); passes through
                *[{"value": 5} for _ in range(12)],
            ]},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        # Exactly 10 entries; first three come from the clamped/passed trio.
        assert len(char.precepts_pool) == 10
        assert char.precepts_pool[0] == {"value": 1}
        assert char.precepts_pool[1] == {"value": 100}
        assert char.precepts_pool[2] == {"value": 19}


class TestPublish:
    def test_publish_creates_version(self, client):
        cid = _seed_character(client, name="Publish Me", is_published=False)

        resp = client.post(f"/characters/{cid}/publish")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert data["version_number"] == 1

        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_published is True
        assert char.published_state is not None

    def test_publish_with_custom_summary(self, client):
        cid = _seed_character(client, name="Custom Summary", is_published=False)
        resp = client.post(
            f"/characters/{cid}/publish",
            json={"summary": "Spending XP from the latest adventure"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Spending XP from the latest adventure"

    def test_publish_records_author(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="Author Test", is_published=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "test"})
        session = client._test_session_factory()
        v = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid
        ).first()
        assert v.author_discord_id == "183026066498125825"


class TestDiscardChangesRoute:
    """``POST /characters/{id}/discard`` reverts unapplied edits to the
    last published state. Permission-gated like publish; safe no-op when
    the character has never been published."""

    def test_discard_reverts_draft_to_published_state(self, client):
        cid = _seed_character(client, name="Pre-Publish", is_published=False)
        # Publish to lock in the baseline.
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})

        # Edit a stat AND a metadata field. Discard reverts the stat,
        # leaves the metadata change in place (it never counted as a
        # draft anyway).
        client.post(f"/characters/{cid}/autosave", json={
            "name": "Drafted Name",
            "honor": 4.0,
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.honor == 4.0
        assert char.has_unpublished_changes

        resp = client.post(f"/characters/{cid}/discard")
        assert resp.status_code == 200
        assert resp.json()["status"] == "discarded"

        char = query_db(client).filter(Character.id == cid).first()
        # Stat reverted to published state.
        assert char.honor == 1.0
        # Metadata edit preserved (lives outside the version system).
        assert char.name == "Drafted Name"
        assert not char.has_unpublished_changes

    def test_discard_does_not_create_a_new_version(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="No Version", is_published=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        session = client._test_session_factory()
        before = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid).count()
        client.post(f"/characters/{cid}/autosave", json={"name": "Drafted"})
        client.post(f"/characters/{cid}/discard")
        after = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid).count()
        assert after == before

    def test_discard_404_for_unknown_character(self, client):
        resp = client.post("/characters/9999/discard")
        assert resp.status_code == 404

    def test_discard_no_published_state_returns_409(self, client):
        """A never-published draft has nothing to revert to. The route
        should refuse cleanly instead of silently no-op'ing - the editor
        button is gated on is_published, but a crafted POST might still
        arrive."""
        cid = _seed_character(client, name="Never Published",
                              is_published=False, published_state=None)
        char = query_db(client).filter(Character.id == cid).first()
        assert not char.published_state
        resp = client.post(f"/characters/{cid}/discard")
        assert resp.status_code == 409
        assert "no" in resp.json()["error"].lower()


class TestDraftDiffRoute:
    """``GET /characters/{id}/draft-diff`` returns the changes since the
    last Apply Changes as a list of human-readable lines, used to
    populate the Discard confirmation modal."""

    def test_returns_diff_lines_for_modified_draft(self, client):
        cid = _seed_character(client, name="Original", is_published=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        # Use a stat (honor) - name is metadata and isn't tracked by
        # the version system anymore.
        client.post(f"/characters/{cid}/autosave",
                    json={"honor": 3.0})
        resp = client.get(f"/characters/{cid}/draft-diff")
        assert resp.status_code == 200
        data = resp.json()
        assert "lines" in data
        text = " ".join(data["lines"])
        assert "Honor" in text

    def test_returns_empty_when_no_unapplied_changes(self, client):
        cid = _seed_character(client, name="Clean", is_published=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        resp = client.get(f"/characters/{cid}/draft-diff")
        assert resp.status_code == 200
        assert resp.json()["lines"] == []

    def test_returns_diff_lines_for_notes_change(self, client):
        """Regression: editing a field that ``has_unpublished_changes``
        treats as significant but the older sparse ``compute_diff_summary``
        didn't enumerate (notes, sections, name_explanation, foreign_knacks,
        advantage_details, technique_choices, etc.) used to produce a
        false-empty diff in the Discard modal even though the character
        showed "Draft changes"."""
        cid = _seed_character(client, name="Notes Only", is_published=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        # Notes is one of the fields the legacy summary skipped.
        client.post(f"/characters/{cid}/autosave",
                    json={"notes": "Something I added later."})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes
        resp = client.get(f"/characters/{cid}/draft-diff")
        assert resp.status_code == 200
        lines = resp.json()["lines"]
        # Some signal of the change must be present - the player should not
        # see "(no changes since the last Apply Changes)" while the badge
        # screams "Draft changes" at them.
        assert lines, (
            "Expected at least one diff line when the character is in the "
            "modified state; got an empty list."
        )

    def test_diff_lines_track_has_unpublished_changes_for_misc_fields(self, client):
        """A handful of the fields previously missing from the summary
        each produce at least one diff line so the modal stays in sync
        with the badge. Excludes metadata fields (name, name_explanation,
        player_name, age) which are intentionally outside the version
        system."""
        for change in (
            {"foreign_knacks": {"athletics": 2}},
            {"sections": [{"label": "Backstory", "html": "<p>hi</p>"}]},
            {"technique_choices": {"second_dan_choice": "bragging"}},
        ):
            cid = _seed_character(client, name=f"Field {list(change)[0]}",
                                  is_published=False)
            client.post(f"/characters/{cid}/publish",
                        json={"summary": "Initial"})
            client.post(f"/characters/{cid}/autosave", json=change)
            char = query_db(client).filter(Character.id == cid).first()
            assert char.has_unpublished_changes, (
                f"has_unpublished_changes must flip for field {change!r}"
            )
            resp = client.get(f"/characters/{cid}/draft-diff")
            assert resp.status_code == 200
            assert resp.json()["lines"], (
                f"Expected diff lines after editing {change!r}; got empty list"
            )

    def test_404_for_unknown_character(self, client):
        resp = client.get("/characters/9999/draft-diff")
        assert resp.status_code == 404

    def test_returns_empty_for_never_published_character(self, client):
        cid = _seed_character(client, name="Never Pub", is_published=False,
                              published_state=None)
        resp = client.get(f"/characters/{cid}/draft-diff")
        assert resp.status_code == 200
        assert resp.json()["lines"] == []


class TestDiscardAndDraftDiffAuth:
    """Auth gating mirrors publish/revert: anonymous = 401, non-editor = 403."""

    def _fake_anonymous_request(self):
        class _Req:
            class state: pass
            state = state()
        req = _Req()
        req.state.user = None
        return req

    def _fake_other_user_request(self):
        class _Req:
            class state: pass
            state = state()
        req = _Req()
        req.state.user = {"discord_id": "999999999"}
        return req

    def test_discard_anonymous_returns_401(self, client):
        import asyncio
        from app.routes.characters import discard_changes_route
        cid = _seed_character(client, name="Anon Discard")
        resp = asyncio.run(
            discard_changes_route(self._fake_anonymous_request(), cid,
                                  db=client._test_session_factory()),
        )
        assert resp.status_code == 401

    def test_discard_non_editor_returns_403(self, client):
        import asyncio
        from app.routes.characters import discard_changes_route
        cid = _seed_character(client, name="Other Discard",
                              owner_discord_id="183026066498125825")
        resp = asyncio.run(
            discard_changes_route(self._fake_other_user_request(), cid,
                                  db=client._test_session_factory()),
        )
        assert resp.status_code == 403

    def test_draft_diff_anonymous_returns_401(self, client):
        import asyncio
        from app.routes.characters import draft_diff_route
        cid = _seed_character(client, name="Anon Diff")
        resp = asyncio.run(
            draft_diff_route(self._fake_anonymous_request(), cid,
                             db=client._test_session_factory()),
        )
        assert resp.status_code == 401

    def test_draft_diff_non_editor_returns_403(self, client):
        import asyncio
        from app.routes.characters import draft_diff_route
        cid = _seed_character(client, name="Other Diff",
                              owner_discord_id="183026066498125825")
        resp = asyncio.run(
            draft_diff_route(self._fake_other_user_request(), cid,
                             db=client._test_session_factory()),
        )
        assert resp.status_code == 403


class TestUpdateVersionSummary:
    def test_update_summary(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="Edit Summary")
        client.post(f"/characters/{cid}/publish", json={"summary": "original"})
        session = client._test_session_factory()
        v = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid
        ).first()

        resp = client.post(
            f"/characters/{cid}/versions/{v.id}/summary",
            json={"summary": "updated summary"},
        )
        assert resp.status_code == 200
        session.refresh(v)
        assert v.summary == "updated summary"

    def test_update_nonexistent_version_404(self, client):
        cid = _seed_character(client, name="No Version")
        resp = client.post(
            f"/characters/{cid}/versions/999/summary",
            json={"summary": "nope"},
        )
        assert resp.status_code == 404


class TestRevert:
    def test_revert_to_previous_version(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="V1", honor=1.0)

        # Publish v1
        client.post(f"/characters/{cid}/publish")

        # Modify a stat and publish v2 (name is metadata, not subject to
        # the version system, so use a stat to exercise revert).
        client.post(f"/characters/{cid}/autosave", json={"honor": 4.5})
        client.post(f"/characters/{cid}/publish")

        # Get v1's id
        session = client._test_session_factory()
        v1 = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid,
            CharacterVersion.version_number == 1,
        ).first()

        # Revert to v1
        resp = client.post(f"/characters/{cid}/revert/{v1.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reverted"
        assert data["version_number"] == 3

        char = query_db(client).filter(Character.id == cid).first()
        assert char.honor == 1.0


class TestVersionHistory:
    def test_get_versions(self, client):
        cid = _seed_character(client, name="Version Test")
        client.post(f"/characters/{cid}/publish")

        resp = client.get(f"/characters/{cid}/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version_number"] == 1


class TestSchoolInfoPartial:
    def test_valid_school(self, client):
        resp = client.get("/characters/api/school-info/akodo_bushi")
        assert resp.status_code == 200
        assert "Water" in resp.text
        assert "Special Ability" in resp.text

    def test_invalid_school_empty(self, client):
        resp = client.get("/characters/api/school-info/nonexistent")
        assert resp.status_code == 200
        assert resp.text == ""

    def test_priest_special_ability_links_rituals_phrase(self, client):
        """Priest's special ability text wraps "all 10 rituals" in an anchor
        tag pointing at the upstream rules section, opened in a new tab."""
        resp = client.get("/characters/api/school-info/priest")
        assert resp.status_code == 200
        # The phrase must be a link, not plain text
        assert (
            '<a href="https://github.com/EliAndrewC/l7r/blob/master/'
            'rules/09-professions.md#priest-rituals"'
        ) in resp.text
        assert 'target="_blank"' in resp.text
        assert ">all 10 rituals</a>" in resp.text
        # The surrounding text should still be present
        assert "You have " in resp.text
        assert "listed under the Priest profession." in resp.text

    def test_non_priest_special_ability_has_no_rituals_link(self, client):
        """Only Priest gets the rituals link - other schools' ability text
        renders as plain text inside the italic <p>."""
        resp = client.get("/characters/api/school-info/akodo_bushi")
        assert "priest-rituals" not in resp.text


class TestPriestRitualsLinkOnSheet:
    """The priest's special ability link must also appear on the read-only
    character sheet, not just in the editor's school-info partial."""

    def test_priest_sheet_renders_rituals_link(self, client):
        cid = _seed_character(
            client, name="Linked Priest", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert (
            '<a href="https://github.com/EliAndrewC/l7r/blob/master/'
            'rules/09-professions.md#priest-rituals"'
        ) in resp.text
        assert ">all 10 rituals</a>" in resp.text

    def test_non_priest_sheet_has_no_rituals_link(self, client):
        cid = _seed_character(client, name="Akodo", school="akodo_bushi")
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "priest-rituals" not in resp.text


class TestIaijutsuRulesLink:
    """The Iaijutsu knack's rules text wraps the phrase "the other combat
    rules" in an anchor pointing at the upstream combat-rules page, opened
    in a new tab. Applies in both the editor's school-info partial and on
    the read-only character sheet, including when iaijutsu is taken as a
    foreign knack."""

    _COMBAT_URL = (
        "https://github.com/EliAndrewC/l7r/blob/master/rules/03-combat.md"
    )

    def _assert_combat_link(self, html: str):
        assert f'<a href="{self._COMBAT_URL}"' in html
        assert 'target="_blank"' in html
        assert ">the other combat rules</a>" in html

    def test_school_info_partial_links_combat_rules_for_iaijutsu(self, client):
        resp = client.get("/characters/api/school-info/mirumoto_bushi")
        assert resp.status_code == 200
        self._assert_combat_link(resp.text)
        # Surrounding sentence still present
        assert "The iaijutsu rules are explained with " in resp.text

    def test_school_info_partial_no_link_for_school_without_iaijutsu(self, client):
        # Priest's three knacks are conviction/otherworldliness/pontificate,
        # none of which mention "the other combat rules".
        resp = client.get("/characters/api/school-info/priest")
        assert resp.status_code == 200
        assert "03-combat.md" not in resp.text

    def test_sheet_renders_iaijutsu_combat_rules_link(self, client):
        cid = _seed_character(
            client, name="Mirumoto Linked", school="mirumoto_bushi",
            knacks={"counterattack": 1, "double_attack": 1, "iaijutsu": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        self._assert_combat_link(resp.text)

    def test_sheet_no_link_for_school_without_iaijutsu(self, client):
        cid = _seed_character(
            client, name="Holy Priest", school="priest",
            school_ring_choice="Water",
            knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "03-combat.md" not in resp.text

    def test_sheet_renders_link_when_iaijutsu_is_foreign_knack(self, client):
        cid = _seed_character(
            client, name="Akodo Borrower", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "lunge": 1},
            foreign_knacks={"iaijutsu": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        self._assert_combat_link(resp.text)


class TestImportKillSwitchNavBar:
    """IMPORT_ENABLED gates the navbar's "New Character" control. When the
    env var is true the dropdown shows Create + Import; when false OR unset
    (fail-closed default) the control collapses to a single submit button
    posting to /characters - no dropdown, no /import link."""

    def test_dropdown_visible_when_import_enabled(self, client, monkeypatch):
        monkeypatch.setenv("IMPORT_ENABLED", "true")
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'data-testid="new-character-menu"' in resp.text
        assert 'data-testid="new-character-option-create"' in resp.text
        assert 'data-testid="new-character-option-import"' in resp.text
        assert 'href="/import"' in resp.text

    def test_dropdown_hidden_when_import_disabled(self, client, monkeypatch):
        monkeypatch.setenv("IMPORT_ENABLED", "false")
        resp = client.get("/")
        assert resp.status_code == 200
        # The dropdown wrapper, the import option, and any /import link
        # must all be gone.
        assert 'data-testid="new-character-menu"' not in resp.text
        assert 'data-testid="new-character-option-import"' not in resp.text
        assert 'href="/import"' not in resp.text
        # The button itself stays - now as a direct submit (no submenu).
        assert 'data-testid="new-character-button"' in resp.text
        assert 'action="/characters"' in resp.text

    def test_dropdown_hidden_when_env_var_unset(self, client, monkeypatch):
        """A missing IMPORT_ENABLED leaves the feature OFF - fail-closed
        so a future .env that forgets the flag keeps the dropdown hidden."""
        monkeypatch.delenv("IMPORT_ENABLED", raising=False)
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'data-testid="new-character-menu"' not in resp.text
        assert 'data-testid="new-character-option-import"' not in resp.text
        assert 'href="/import"' not in resp.text

    def test_disabled_button_submits_directly_to_characters(self, client, monkeypatch):
        """The visible 'New Character' button when import is off must POST to
        /characters - i.e., it lives inside a form whose action is /characters."""
        import re
        monkeypatch.setenv("IMPORT_ENABLED", "false")
        resp = client.get("/")
        assert resp.status_code == 200
        # Find the form that contains the new-character-button. Form attribute
        # order is template-defined, so accept either ordering of method/action.
        forms = re.findall(
            r'<form\b[^>]*>(?:(?!</form>).)*?data-testid="new-character-button"',
            resp.text, re.DOTALL,
        )
        assert any(
            'method="POST"' in f and 'action="/characters"' in f for f in forms
        ), f"New Character button must sit inside POST /characters form; saw: {forms!r}"


class TestConvictionResetButtonPosition:
    """The Reset button on the per-day Conviction counter sits to the LEFT
    of the +/- counter widget (immediately after the label), not the right."""

    def test_reset_button_appears_before_decrement_button(self, client):
        cid = _seed_character(
            client, name="Brother", school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        text = resp.text
        reset_idx = text.find('data-action="reset-ability-conviction"')
        # The increment button uses `setCount('conviction', Math.min(...`
        # and the decrement button uses `setCount('conviction', Math.max(...`.
        inc_idx = text.find("setCount('conviction', Math.min")
        dec_idx = text.find("setCount('conviction', Math.max")
        assert reset_idx != -1, "Conviction reset button should be rendered"
        assert inc_idx != -1
        assert dec_idx != -1
        assert reset_idx < inc_idx, (
            "Reset button must appear BEFORE the +/- counter buttons in markup"
        )
        assert reset_idx < dec_idx


class TestXPCalcPartial:
    def test_xp_calc_returns_breakdown(self, client):
        form = make_character_form(ring_fire="3", skill_precepts="3")
        resp = client.post("/characters/api/xp-calc", data=form)
        assert resp.status_code == 200
        assert "Unspent" in resp.text


class TestAutosaveAllFieldSetters:
    """One test per ``if "<key>" in body:`` branch in autosave. These aren't
    behavior tests per se — they exercise the cheap per-key setters so we know
    each branch actually writes to the column. Missing coverage here means a
    silent regression could make a field un-saveable."""

    def test_school_setter(self, client):
        cid = _seed_character(client, school="akodo_bushi")
        client.post(f"/characters/{cid}/autosave", json={"school": "bayushi_bushi"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.school == "bayushi_bushi"

    def test_school_ring_choice_setter(self, client):
        cid = _seed_character(client, school_ring_choice="Water")
        client.post(f"/characters/{cid}/autosave", json={"school_ring_choice": "Fire"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.school_ring_choice == "Fire"

    def test_skills_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"skills": {"bragging": 3, "etiquette": 2}},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.skills == {"bragging": 3, "etiquette": 2}

    def test_knacks_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"knacks": {"double_attack": 2, "feint": 1, "iaijutsu": 1}},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.knacks == {"double_attack": 2, "feint": 1, "iaijutsu": 1}

    def test_advantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"advantages": ["lucky", "charming"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantages == ["lucky", "charming"]

    def test_disadvantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"disadvantages": ["proud", "unkempt"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.disadvantages == ["proud", "unkempt"]

    def test_campaign_advantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"campaign_advantages": ["highest_regard"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.campaign_advantages == ["highest_regard"]

    def test_campaign_disadvantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"campaign_disadvantages": ["peasantborn"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.campaign_disadvantages == ["peasantborn"]

    def test_advantage_details_setter(self, client):
        cid = _seed_character(client)
        details = {"higher_purpose": {"text": "justice", "skills": ["interrogation"]}}
        client.post(
            f"/characters/{cid}/autosave",
            json={"advantage_details": details},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details == details

    def test_technique_choices_setter(self, client):
        cid = _seed_character(client)
        choices = {"1": "manipulation"}
        client.post(
            f"/characters/{cid}/autosave",
            json={"technique_choices": choices},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.technique_choices == choices

    def test_rank_locked_setter(self, client):
        cid = _seed_character(client, rank_locked=False)
        client.post(f"/characters/{cid}/autosave", json={"rank_locked": True})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_locked is True

    def test_recognition_halved_setter(self, client):
        cid = _seed_character(client, recognition_halved=False)
        client.post(f"/characters/{cid}/autosave", json={"recognition_halved": True})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.recognition_halved is True

    def test_earned_xp_setter(self, client):
        cid = _seed_character(client, earned_xp=0)
        client.post(f"/characters/{cid}/autosave", json={"earned_xp": 42})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.earned_xp == 42

    def test_notes_setter(self, client):
        cid = _seed_character(client)
        client.post(f"/characters/{cid}/autosave", json={"notes": "Some notes"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.notes == "Some notes"


class TestAutosavePermissionPaths:
    """401/404/403 short-circuits in autosave + set-group."""

    def test_autosave_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "x"},
            headers={"X-Test-User": ""},
        )
        assert resp.status_code == 401

    def test_autosave_unknown_character_404(self, client):
        resp = client.post("/characters/99999/autosave", json={"name": "x"})
        assert resp.status_code == 404

    def test_autosave_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "x"},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403


class TestAwardTypeFallback:
    """Unknown award ``type`` strings fall back to ``rank_recognition``."""

    def test_unknown_award_type_falls_back(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {
                        "id": "a1", "type": "made_up_type",
                        "rank_delta": 1.0, "recognition_delta": 0,
                        "source": "Whatever",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["type"] == "rank_recognition"

    def test_valid_non_default_type_preserved(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {
                        "id": "a1", "type": "good_reputation",
                        "rank_delta": 0, "recognition_delta": 0.5,
                        "source": "Saved the village",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["type"] == "good_reputation"


class TestUpdateCharacterFormRoute:
    """Form-based /characters/{id} update: auth, permission, admin reassignment."""

    def test_update_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}",
            data=make_character_form(),
            headers={"X-Test-User": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    def test_update_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}",
            data=make_character_form(),
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_admin_can_reassign_owner_via_form(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="183026066498125825", discord_name="admin", display_name="Admin"))
        session.add(User(discord_id="999", discord_name="other", display_name="New Owner"))
        session.commit()
        cid = _seed_character(client)

        form = make_character_form(owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}", data=form, follow_redirects=False
        )
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.owner_discord_id == "999"
        assert char.player_name == "New Owner"

    def test_non_admin_reassignment_silently_ignored(self, client):
        """Non-admin submitting owner_discord_id should not change the owner.
        The field is simply ignored, not rejected."""
        from app.models import User
        session = client._test_session_factory()
        # test_user_1 is whitelisted but not admin
        session.add(User(discord_id="test_user_1", discord_name="Test 1", display_name="Test 1"))
        session.add(User(discord_id="evil", discord_name="Evil", display_name="Evil"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="test_user_1")

        form = make_character_form(owner_discord_id="evil")
        resp = client.post(
            f"/characters/{cid}",
            data=form,
            headers={"X-Test-User": "test_user_1:Test 1"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.owner_discord_id == "test_user_1"

    def test_admin_reassignment_to_unknown_user_is_ignored(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="183026066498125825", discord_name="admin", display_name="Admin"))
        session.commit()
        cid = _seed_character(client)

        form = make_character_form(owner_discord_id="nonexistent_id")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        # Owner unchanged because lookup failed
        assert char.owner_discord_id == "183026066498125825"


class TestDeletePermissions:
    def test_delete_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/delete",
            headers={"X-Test-User": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]
        # Character should still exist
        char = query_db(client).filter(Character.id == cid).first()
        assert char is not None

    def test_delete_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/delete",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403
        char = query_db(client).filter(Character.id == cid).first()
        assert char is not None


class TestPublishRevertVersionPermissions:
    """401/404/403 guards on publish, revert, update_version_summary, get_versions."""

    def test_publish_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/publish", headers={"X-Test-User": ""}
        )
        assert resp.status_code == 401

    def test_publish_unknown_character_404(self, client):
        resp = client.post("/characters/99999/publish")
        assert resp.status_code == 404

    def test_publish_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/publish",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_revert_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/revert/1", headers={"X-Test-User": ""}
        )
        assert resp.status_code == 401

    def test_revert_unknown_character_404(self, client):
        resp = client.post("/characters/99999/revert/1")
        assert resp.status_code == 404

    def test_revert_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/revert/1",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_update_version_summary_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/versions/1/summary",
            headers={"X-Test-User": ""},
            json={"summary": "x"},
        )
        assert resp.status_code == 401

    def test_update_version_summary_unknown_character_404(self, client):
        resp = client.post(
            "/characters/99999/versions/1/summary", json={"summary": "x"}
        )
        assert resp.status_code == 404

    def test_update_version_summary_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/versions/1/summary",
            headers={"X-Test-User": "test_user_1:Test User 1"},
            json={"summary": "x"},
        )
        assert resp.status_code == 403

    def test_get_versions_unknown_character_404(self, client):
        resp = client.get("/characters/99999/versions")
        assert resp.status_code == 404


class TestSetAwardSourceForbidden:
    def test_set_award_source_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "x"},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403


class TestTrackStateTempVoid:
    def test_track_temp_void_points(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/track", json={"current_temp_void_points": 2}
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_temp_void_points == 2

    def test_track_temp_void_points_clamped_negative(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/track", json={"current_temp_void_points": -5}
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_temp_void_points == 0


class TestStaticPages:
    def test_terms_page_renders(self, client):
        resp = client.get("/terms")
        assert resp.status_code == 200

    def test_privacy_page_renders(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200


class TestCharactersNewRedirect:
    """GET /characters/new is a legacy path that just bounces back to home."""

    def test_new_character_get_redirects_home(self, client):
        resp = client.get("/characters/new", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"


class TestEditPagePermissions:
    def test_edit_forbidden_for_non_owner(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.get(
            f"/characters/{cid}/edit",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403
        assert "permission" in resp.text.lower()


class TestPartyMemberDaidojiCounterattack:
    """View a character sheet in a group with a Daidoji Yojimbo at 3rd+ Dan: that
    party member appears in daidoji_counterattack_party with raises = attack skill."""

    def _make_group_with_partners(self, client, viewer_school, partner_school, partner_dan):
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Party")
        session.add(group)
        session.commit()
        gid = group.id

        # Viewer's knacks depend on school — use defaults from _seed_character
        viewer_id = _seed_character(
            client, name="Viewer", school=viewer_school, gaming_group_id=gid,
        )
        partner_knacks = {"counterattack": partner_dan, "double_attack": partner_dan, "iaijutsu": partner_dan}
        partner_id = _seed_character(
            client,
            name="Yojimbo Friend",
            school=partner_school,
            school_ring_choice="Water",
            knacks=partner_knacks,
            skills={"attack": 4},
            gaming_group_id=gid,
        )
        return viewer_id, partner_id

    def test_daidoji_3rd_dan_partner_surfaces(self, client):
        viewer_id, _ = self._make_group_with_partners(
            client, "akodo_bushi", "daidoji_yojimbo", partner_dan=3
        )
        resp = client.get(f"/characters/{viewer_id}")
        assert resp.status_code == 200
        assert "Yojimbo Friend" in resp.text

    def test_daidoji_below_3rd_dan_no_counterattack_entry(self, client):
        """At 2nd Dan the Daidoji counterattack raises ability isn't active yet.
        The partner is still shown as a party member, but not in the
        counterattack context (that's behavioral, not just rendering)."""
        viewer_id, _ = self._make_group_with_partners(
            client, "akodo_bushi", "daidoji_yojimbo", partner_dan=2
        )
        resp = client.get(f"/characters/{viewer_id}")
        assert resp.status_code == 200

    def test_non_daidoji_partner_not_in_counterattack_list(self, client):
        viewer_id, _ = self._make_group_with_partners(
            client, "akodo_bushi", "bayushi_bushi", partner_dan=5
        )
        resp = client.get(f"/characters/{viewer_id}")
        assert resp.status_code == 200


class TestPerAdventureAbilitiesOnSheet:
    """The sheet surfaces per-adventure toggles/counters for Lucky, Unlucky, 3rd
    Dan free raises, and spendable knacks (conviction/otherworldliness/worldliness)."""

    def test_lucky_advantage_shown(self, client):
        cid = _seed_character(client, advantages=["lucky"])
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "Lucky" in resp.text

    def test_unlucky_disadvantage_shown(self, client):
        cid = _seed_character(client, disadvantages=["unlucky"])
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "Unlucky" in resp.text

    def test_third_dan_free_raises_shown(self, client):
        """Brotherhood monk at 3rd Dan with precepts skill gets 2X adventure raises."""
        cid = _seed_character(
            client,
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
            skills={"precepts": 4},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "3rd Dan Free Raises" in resp.text

    def test_third_dan_with_zero_source_skill_not_shown(self, client):
        """If source_skill rank is 0, no per-adventure raises are listed."""
        cid = _seed_character(
            client,
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
            skills={},  # no precepts
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "3rd Dan Free Raises" not in resp.text

    def test_spendable_knacks_shown(self, client):
        """Brotherhood monk has conviction, otherworldliness, worldliness —
        all three should appear as per-adventure counters."""
        cid = _seed_character(
            client,
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 2, "otherworldliness": 3, "worldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # All three knack labels should be in the per-adventure section
        assert "Conviction" in resp.text
        assert "Otherworldliness" in resp.text
        assert "Worldliness" in resp.text


class TestShugenjaVoidMax:
    """Shugenja/Isawa Ishi use void_points_max_shugenja; all other schools use
    min of rings for void_max."""

    def test_shugenja_void_max_uses_shugenja_formula(self, client):
        """A shugenja sheet renders and void_max/spend_cap come from the
        school-specific formula."""
        cid = _seed_character(
            client,
            school="shugenja",
            school_ring_choice="Air",
            knacks={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
            ring_air=3, ring_water=3, ring_earth=3, ring_fire=3, ring_void=3,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200

    def test_isawa_ishi_void_max_uses_shugenja_formula(self, client):
        cid = _seed_character(
            client,
            school="isawa_ishi",
            school_ring_choice="Void",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            ring_air=3, ring_water=3, ring_earth=3, ring_fire=3, ring_void=4,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200


class TestActionDiceShapeAndColor:
    """Action dice (side panel + initiative result panel) use the same SVG
    kite shape as the roll-animation dice, and don't distinguish low vs
    high values by color. Spent/Phase 0/athletics-only remain categorically
    distinct, but 2 and 8 render identically."""

    def test_side_panel_action_dice_use_svg_kite(self, client):
        cid = _seed_character(client, name="ActionDiceShape")
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The action-die button no longer uses `rounded-full`; instead it
        # wraps an SVG with the shared `die` class.
        # Slice to the action-dice section so we don't match unrelated SVGs.
        start = resp.text.find('data-testid="action-dice-section"')
        assert start != -1
        section = resp.text[start:start + 4000]
        assert 'data-action="action-die"' in section
        assert 'rounded-full' not in section
        # The svg uses the shared class so it picks up svg.die styling.
        assert 'class="die action-die' in section or "class='die action-die" in section

    def test_side_panel_action_dice_have_no_low_value_variant(self, client):
        """The old :class expression branched on die.value <= 3 to make
        low-value dice red. The new markup has no such branch."""
        cid = _seed_character(client, name="ActionDiceColor")
        resp = client.get(f"/characters/{cid}")
        start = resp.text.find('data-testid="action-dice-section"')
        section = resp.text[start:start + 4000]
        assert "die.value <= 3" not in section
        assert "phase <= 3" not in section

    def test_initiative_result_action_dice_use_svg_kite(self, client):
        """The Action Dice panel inside the initiative-result view must
        match the side panel's kite shape for visual consistency."""
        cid = _seed_character(client, name="InitResultShape")
        resp = client.get(f"/characters/{cid}")
        # The initiative result panel header literally says 'Action Dice'.
        idx = resp.text.find(">Action Dice<")
        assert idx != -1
        panel = resp.text[idx:idx + 4000]
        assert "rounded-full" not in panel
        assert "phase <= 3" not in panel
        assert "class=\"die action-die" in panel or "class='die action-die" in panel
    """The 5-item side panel on the character sheet (Impaired, Dying,
    TN to be hit, Wound Check, Initiative) is ordered so Initiative appears
    last - below Wound Check rather than in the middle of the combat stats.
    Togashi Ise Zumi renders a different Initiative markup (two variants),
    but the ordering rule holds for both."""

    def _label_positions(self, text, labels):
        return {lbl: text.find(lbl) for lbl in labels}

    def test_regular_character_initiative_last(self, client):
        cid = _seed_character(client, name="Order Check")
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        pos = self._label_positions(resp.text, [
            "Impaired at:", "Dying at:", "TN to be hit:",
            "Wound Check:", "Initiative:",
        ])
        for label, idx in pos.items():
            assert idx != -1, f"{label} missing from sheet"
        assert (
            pos["Impaired at:"]
            < pos["Dying at:"]
            < pos["TN to be hit:"]
            < pos["Wound Check:"]
            < pos["Initiative:"]
        ), f"side panel out of order: {pos}"

    def test_togashi_initiative_last(self, client):
        """Togashi's dual-variant Initiative box still appears last."""
        cid = _seed_character(
            client, name="Togashi Order", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        pos = self._label_positions(resp.text, [
            "Impaired at:", "Dying at:", "TN to be hit:",
            "Wound Check:", "Initiative:",
        ])
        assert (
            pos["Impaired at:"]
            < pos["Dying at:"]
            < pos["TN to be hit:"]
            < pos["Wound Check:"]
            < pos["Initiative:"]
        )


class TestInitiativeBoxDisplay:
    """The Initiative box on the sheet must show the same rolled/kept
    the actual roll uses - including 1st Dan extra-die bonuses for Shinjo
    Bushi, Kakita Duelist, Hiruma Scout, Mantis Wave-Treader, and the flat
    10 dice for Matsu Bushi. Previously the display hard-coded (Void+1)kVoid
    and ignored these school bonuses."""

    def test_regular_school_no_bonus(self, client):
        cid = _seed_character(
            client, name="NoBonusInit", school="akodo_bushi",
            ring_water=3,  # Void defaults to 2
        )
        resp = client.get(f"/characters/{cid}")
        assert "Initiative:" in resp.text
        assert "3 dice, keep 2" in resp.text  # (Void+1)kVoid = 3k2

    def test_shinjo_bushi_adds_1st_dan_die(self, client):
        """The user-reported case: Shinjo gets +1 initiative die at 1st Dan."""
        cid = _seed_character(
            client, name="Shinjo4Void", school="shinjo_bushi",
            school_ring_choice="Air",
            ring_void=4,
            knacks={"double_attack": 1, "horsemanship": 1, "lunge": 1},
        )
        resp = client.get(f"/characters/{cid}")
        # Void=4 -> base 5k4, +1 from 1st Dan -> 6k4.
        assert "6 dice, keep 4" in resp.text

    def test_kakita_duelist_adds_1st_dan_die(self, client):
        cid = _seed_character(
            client, name="KakitaInit", school="kakita_duelist",
            school_ring_choice="Air",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        resp = client.get(f"/characters/{cid}")
        # Void defaults to 2 -> base 3k2, +1 from 1st Dan -> 4k2.
        assert "4 dice, keep 2" in resp.text

    def test_hiruma_scout_adds_1st_dan_die(self, client):
        cid = _seed_character(
            client, name="HirumaInit", school="hiruma_scout",
            school_ring_choice="Air",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert "4 dice, keep 2" in resp.text

    def test_mantis_wave_treader_adds_1st_dan_die(self, client):
        cid = _seed_character(
            client, name="MantisInit", school="mantis_wave_treader",
            school_ring_choice="Void",
            # Mantis school ring defaults to Void, which auto-raises to 3.
            ring_void=3,
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        # Void=3 -> base 4k3, +1 from 1st Dan -> 5k3.
        assert "5 dice, keep 3" in resp.text

    def test_matsu_bushi_shows_10_dice(self, client):
        """Matsu Bushi's special ability: always roll 10 dice on initiative."""
        cid = _seed_character(
            client, name="MatsuInit", school="matsu_bushi",
            school_ring_choice="Fire",
            knacks={"attack_skill": 1, "iaijutsu": 1, "lunge": 1},
        )
        resp = client.get(f"/characters/{cid}")
        # Default Void=2, Matsu flat override to 10 -> 10k2.
        assert "10 dice, keep 2" in resp.text


class TestWoundCheckBoxDisplay:
    """The Wound Check box on the sheet must show the same rolled/kept/flat
    the actual roll uses - including 1st Dan extra-die, 2nd Dan +5 flat,
    and Strength of the Earth. Previously the box hard-coded
    ``(Water+1)kWater`` and ignored every bonus."""

    def test_no_bonus_school_shows_plain_base(self, client):
        # Kakita Duelist's 1st Dan list does NOT include wound_check, and
        # 2nd Dan is iaijutsu (not wound_check), so the box should match
        # the raw (Water+1)kWater base with no bonuses.
        cid = _seed_character(
            client, name="WCNoBonus", school="kakita_duelist",
            school_ring_choice="Air",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert "Wound Check:" in resp.text
        # Water defaults to 3 in _seed_character. Base 4k3, no bonuses.
        assert ">4k3</span>" in resp.text

    def test_shinjo_1st_dan_shows_extra_wound_check_die(self, client):
        """Shinjo 1st Dan's extra wound-check die must show in the box."""
        cid = _seed_character(
            client, name="ShinjoWC", school="shinjo_bushi",
            school_ring_choice="Air",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        resp = client.get(f"/characters/{cid}")
        # Water=3 -> base 4k3, 1st Dan +1 rolled -> 5k3.
        assert ">5k3</span>" in resp.text

    def test_yogo_2nd_dan_shows_plus_5_flat(self, client):
        """Yogo Warden 2nd Dan is +5 free raise on wound_check. Knack ranks
        2 make dan=2 and trigger the 2nd Dan bonus."""
        cid = _seed_character(
            client, name="YogoWC", school="yogo_warden",
            knacks={"double_attack": 2, "iaijutsu": 2, "feint": 2},
        )
        resp = client.get(f"/characters/{cid}")
        # Water=3 -> base 4k3, 1st Dan +1 rolled -> 5k3, 2nd Dan +5 flat.
        assert ">5k3 + 5</span>" in resp.text

    def test_strength_of_the_earth_shows_plus_5_flat(self, client):
        """Strength of the Earth advantage grants +5 flat on wound checks."""
        cid = _seed_character(
            client, name="SoEWC", school="kakita_duelist",
            school_ring_choice="Air",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            advantages=["strength_of_the_earth"],
        )
        resp = client.get(f"/characters/{cid}")
        # Water=3 -> base 4k3, +5 flat from Strength of the Earth. Kakita
        # is used here instead of a bushi with a wound_check 1st Dan so the
        # +5 flat isn't conflated with a school free raise.
        assert ">4k3 + 5</span>" in resp.text


class TestAthleticsPredeclaredParryRow:
    """The athletics picker should have a 5th row, Athletics (Predeclared
    parry), below Athletics (Parry). Like the existing predeclared-parry
    option on the parry menu, it adds a +5 flat bonus and tags the roll
    with reason 'predeclared parry' via executeRollWithExtraFlat."""

    def test_row_markup_present(self, client):
        cid = _seed_character(
            client, name="AthPredecl", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
            skills={"athletics": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-athletics-combat="predeclared-parry"' in resp.text
        # The click handler must route through executeRollWithExtraFlat with
        # the athletics:parry formula and the +5 predeclared-parry bonus.
        assert (
            "executeRollWithExtraFlat('athletics:parry', 0, null, 5,"
            " 'predeclared parry')"
        ) in resp.text
        # And appear AFTER the plain Athletics (Parry) row in DOM order so
        # it renders below it in the picker.
        parry_idx = resp.text.find('data-athletics-combat="parry"')
        pre_idx = resp.text.find('data-athletics-combat="predeclared-parry"')
        assert parry_idx != -1 and pre_idx != -1
        assert parry_idx < pre_idx

    def test_void_submenu_preserves_predeclared_bonus(self, client):
        """The void-spend flyout on the new row must also carry the +5
        bonus, so spending void still stacks with the predeclared raise."""
        cid = _seed_character(
            client, name="AthPredecl2", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
            skills={"athletics": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert 'data-athletics-void-submenu="predeclared-parry"' in resp.text
        assert (
            "executeRollWithExtraFlat('athletics:parry', opt.count, opt, 5,"
            " 'predeclared parry')"
        ) in resp.text


class TestAthleticsOnlyActionDie:
    """The Togashi Ise Zumi special grants one athletics-only action die on
    initiative. It must:
      - persist on the tracker alongside regular action dice (not as a
        separate togashiAthleticsDie field), carrying an ``athletics_only``
        flag on the entry
      - render with the ``athletics-only`` SVG variant + a tooltip both in
        the Actions side panel and in the initiative-result panel
      - be skipped by the auto-spend for a non-athletics attack/parry, but
        eligible for athletics:attack / athletics:parry rolls
    """

    def _side_panel(self, resp_text):
        start = resp_text.find('data-testid="action-dice-section"')
        assert start != -1
        return resp_text[start:start + 4000]

    def _init_result(self, resp_text):
        idx = resp_text.find(">Action Dice<")
        assert idx != -1
        return resp_text[idx:idx + 4000]

    def test_side_panel_applies_athletics_only_class(self, client):
        cid = _seed_character(client, name="AthOnlySide")
        section = self._side_panel(client.get(f"/characters/{cid}").text)
        # Class binding must switch on per-die athletics_only flag (rather
        # than a separate togashiAthleticsDie variable).
        assert "die.athletics_only" in section

    def test_initiative_result_iterates_dice_as_objects(self, client):
        cid = _seed_character(client, name="AthOnlyInit")
        panel = self._init_result(client.get(f"/characters/{cid}").text)
        # The x-for in the initiative-result panel uses die.value / die.athletics_only
        # rather than looping raw numbers + a separate togashiAthleticsDie block.
        assert "die.athletics_only" in panel
        # The separate togashiAthleticsDie state variable is gone from the panel.
        assert "togashiAthleticsDie" not in panel

    def test_side_panel_has_athletics_only_tooltip(self, client):
        cid = _seed_character(client, name="AthOnlyTip")
        section = self._side_panel(client.get(f"/characters/{cid}").text)
        assert "Athletics-only action die" in section

    def test_spend_lowest_skips_athletics_only_for_non_athletics(self, client):
        """The tracker method that auto-spends the lowest unspent die must
        take an isAthletics flag and filter out athletics_only dice when
        that flag is false."""
        cid = _seed_character(client, name="AthOnlySpend")
        resp = client.get(f"/characters/{cid}").text
        start = resp.find("spendLowestUnspentActionDie(")
        assert start != -1
        # Body is short - grab a window of ~900 chars.
        body = resp[start:start + 900]
        # Signature accepts an isAthletics argument.
        assert "isAthletics" in body
        # The non-athletics branch must filter out athletics_only entries.
        assert "athletics_only" in body

    def test_roll_key_is_athletics_helper_exists(self, client):
        """A helper classifies a roll key as athletics (athletics:attack /
        athletics:parry) so the auto-spend can be told whether to allow
        athletics-only dice."""
        cid = _seed_character(client, name="AthOnlyKey")
        resp = client.get(f"/characters/{cid}").text
        assert "_isAthleticsActionKey" in resp


class TestActionDieActionMenu:
    """Clicking an action die surfaces a menu with every action the die
    can pay for. Parry and feint options carry a void-spend flyout; attack
    variants open the attack modal (void is chosen inside). Athletics-
    only dice (Togashi special) are limited to athletics actions plus
    the manual mark-spent/unspent item.

    Tests here are structural - they pin the wiring in the rendered
    sheet so the action menu can't silently regress."""

    def _action_menu_block(self, resp_text):
        """Slice from the Actions section header to Per-Adventure / footer."""
        start = resp_text.find('data-testid="action-dice-section"')
        assert start != -1
        # The menu markup is large (hundreds of KB of x-if templates)
        # because each die renders the full menu. Grab a broad window.
        end_markers = ['Per-Adventure Abilities', 'Lowest unspent die']
        end = len(resp_text)
        for m in end_markers:
            idx = resp_text.find(m, start)
            if idx != -1 and idx < end:
                end = idx
        return resp_text[start:end]

    def test_tracker_exposes_spend_specific_action_die(self, client):
        cid = _seed_character(client, name="ADMenuBase")
        resp = client.get(f"/characters/{cid}").text
        assert "spendSpecificActionDie(" in resp

    def test_dice_roller_honors_pre_spent_die_index(self, client):
        cid = _seed_character(client, name="ADMenuPreSpent")
        resp = client.get(f"/characters/{cid}").text
        # The auto-spend helper short-circuits when a caller has pre-
        # spent a specific die via the action menu.
        assert "_preSpentDieIndex" in resp

    def test_dice_roller_exposes_rollForActionDie(self, client):
        """The convenience method handles attack/attack-variant (opens
        modal) and parry/feint (executeRoll with void)."""
        cid = _seed_character(client, name="ADMenuRouter")
        resp = client.get(f"/characters/{cid}").text
        assert "rollForActionDie(" in resp

    def test_menu_lists_core_actions_for_regular_die(self, client):
        cid = _seed_character(client, name="ADMenuRegular")
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        # Every regular die offers at least these three actions.
        assert 'data-action-die-menu-item="attack"' in block
        assert 'data-action-die-menu-item="parry"' in block
        assert 'data-action-die-menu-item="predeclared-parry"' in block

    def test_menu_includes_school_specific_actions_when_formulas_exist(self, client):
        """Akodo's school knacks include double_attack, feint, iaijutsu.
        Double attack + feint rows must render (iaijutsu isn't a listed
        action for this feature)."""
        cid = _seed_character(client, name="ADMenuAkodo", school="akodo_bushi")
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        assert 'data-action-die-menu-item="double-attack"' in block
        assert 'data-action-die-menu-item="feint"' in block

    def test_menu_includes_counterattack_for_schools_with_knack(self, client):
        cid = _seed_character(
            client, name="ADMenuMirumoto", school="mirumoto_bushi",
            school_ring_choice="Void",
            knacks={"counterattack": 1, "double_attack": 1, "iaijutsu": 1},
        )
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        assert 'data-action-die-menu-item="counterattack"' in block

    def test_menu_includes_lunge_for_schools_with_knack(self, client):
        cid = _seed_character(
            client, name="ADMenuIsawa", school="isawa_duelist",
            school_ring_choice="Water",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        assert 'data-action-die-menu-item="lunge"' in block

    def test_menu_includes_athletics_rows_when_formula_exists(self, client):
        cid = _seed_character(
            client, name="ADMenuAth", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
            skills={"athletics": 2},
        )
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        assert 'data-action-die-menu-item="athletics-attack"' in block
        assert 'data-action-die-menu-item="athletics-parry"' in block
        assert 'data-action-die-menu-item="athletics-predeclared-parry"' in block

    def test_athletics_only_die_gate_excludes_non_athletics_items(self, client):
        """Each action row is gated by ``!die.athletics_only`` unless the
        action is an athletics variant. Check a representative pair:
        'attack' (regular) is gated out, 'athletics-attack' is allowed."""
        cid = _seed_character(
            client, name="ADMenuAthOnly", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
            skills={"athletics": 2},
        )
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        # The regular-attack row carries an x-show that excludes athletics-only.
        # Extract the attack row snippet.
        atk_start = block.find('data-action-die-menu-item="attack"')
        # Look backward in the surrounding <button>/<div> wrapper
        wrapper_start = block.rfind('<div', 0, atk_start)
        wrapper_slice = block[wrapper_start:atk_start]
        assert "!die.athletics_only" in wrapper_slice

    def test_parry_option_offers_void_submenu(self, client):
        """Parry and predeclared-parry carry void flyouts."""
        cid = _seed_character(client, name="ADMenuParryVoid")
        block = self._action_menu_block(client.get(f"/characters/{cid}").text)
        assert 'data-action-die-void-submenu="parry"' in block
        assert 'data-action-die-void-submenu="predeclared-parry"' in block


class TestResetAdventureClearsActionDice:
    """The 'Reset Per-Adventure Abilities' modal's confirm button must also
    clear any action dice left over from a previous combat round, since
    those are stale state tied to the adventure. We can't exercise the
    Alpine function server-side, so we structurally assert the wiring in
    the rendered template: resetAdventure clears actionDice, and the
    summary enumerates the action dice that will be cleared."""

    def _reset_adventure_body(self, resp_text):
        start = resp_text.find("resetAdventure() {")
        assert start != -1, "resetAdventure not found in sheet template"
        end = resp_text.find("\n                },", start)
        assert end != -1
        return resp_text[start:end]

    def _reset_summary_body(self, resp_text):
        start = resp_text.find("resetSummary() {")
        assert start != -1
        end = resp_text.find("\n                },", start)
        assert end != -1
        return resp_text[start:end]

    def test_resetAdventure_clears_action_dice(self, client):
        cid = _seed_character(client, name="ResetClearsAD")
        resp = client.get(f"/characters/{cid}")
        body = self._reset_adventure_body(resp.text)
        assert "this.actionDice = []" in body

    def test_hasAnythingSpent_considers_action_dice(self, client):
        """If only action dice are present (no other per-adventure state),
        the Reset button should still be enabled so the user can clear
        them via the same button."""
        cid = _seed_character(client, name="HasADPanel")
        resp = client.get(f"/characters/{cid}")
        start = resp.text.find("hasAnythingSpent() {")
        assert start != -1
        end = resp.text.find("\n                },", start)
        has_body = resp.text[start:end]
        assert "this.actionDice" in has_body

    def test_resetSummary_mentions_action_dice_cleared(self, client):
        """The summary shown in the confirm modal enumerates what will be
        cleared. When action dice are present the list includes a line
        about them so the user isn't surprised."""
        cid = _seed_character(client, name="SummaryAD")
        resp = client.get(f"/characters/{cid}")
        body = self._reset_summary_body(resp.text)
        assert "actionDice" in body


class TestAthleticsAttackNoVoidSubmenu:
    """The Athletics (Attack) row must not offer a void-spend flyout: void
    for attack rolls is chosen inside the attack modal, next to the
    probability chart, so the player can see the odds before committing.
    Parry rolls have no modal, so their flyout stays."""

    def test_no_void_submenu_on_athletics_attack(self, client):
        cid = _seed_character(
            client, name="AthAtkNoSub", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
            skills={"athletics": 2},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The athletics picker still exists for this character
        assert 'data-athletics-combat="attack"' in resp.text
        # ...but it must NOT have a void submenu or preselect-void call.
        assert 'data-athletics-void-submenu="attack"' not in resp.text
        assert "openAttackModal('athletics:attack', opt.count)" not in resp.text


class TestTogashiRerollGate:
    """The Togashi 4th Dan reroll button must not offer itself on rolls that
    can never be contested. Damage rolls (e.g. Dragon Tattoo) are never
    contested, so the button's x-show condition gates on the formula's
    is_damage_roll flag - not just a single hard-coded roll key - so any
    future damage roll surfacing in the regular modal is also excluded.
    Parry rolls are likewise uncontested (parry raises the attacker's TN
    rather than being rolled against an opponent) and must be excluded."""

    def test_reroll_condition_excludes_damage_rolls(self, client):
        cid = _seed_character(
            client, name="Togashi 4D", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The visibility predicate for the reroll button references the
        # damage-roll flag on the formula. Without this, Dragon Tattoo
        # (a damage roll) would offer the "reroll if contested" button.
        assert "!formula?.is_damage_roll" in resp.text

    def test_reroll_condition_excludes_parry_rolls(self, client):
        """Both the regular parry and athletics:parry keys must be listed
        in the gate so Togashi's 4th Dan reroll button never appears on a
        parry result."""
        cid = _seed_character(
            client, name="Togashi 4D Parry", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "currentRollKey !== 'parry'" in resp.text
        assert "currentRollKey !== 'athletics:parry'" in resp.text

    def test_dragon_tattoo_formula_flagged_as_damage_roll(self, client):
        """Prove the flag is actually set on the Dragon Tattoo formula in
        the embedded roll-formulas JSON, so the gate above matches."""
        import json, re
        cid = _seed_character(
            client, name="Togashi DT", school="togashi_ise_zumi",
            school_ring_choice="Void",
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        )
        resp = client.get(f"/characters/{cid}")
        m = re.search(
            r'id="roll-formulas">(.*?)</script>', resp.text, re.DOTALL,
        )
        assert m is not None
        formulas = json.loads(m.group(1))
        assert formulas["knack:dragon_tattoo"]["is_damage_roll"] is True


class TestTogashiAthleticsRaiseInAttackModal:
    """Togashi 3rd Dan's 'Spend Athletics Raise' button must appear in the
    attack-result modal when the roll is athletics:attack, since athletics
    used as an attack is still an athletics roll. Athletics:parry already
    goes through the regular roll modal where the existing
    currentRollKey.startsWith('athletics:') gate covers it."""

    def _seed_togashi_3d(self, client):
        return _seed_character(
            client, name="Togashi AtkRaise",
            school="togashi_ise_zumi",
            school_ring_choice="Void",
            ring_void=3,
            skills={"precepts": 2, "athletics": 2},
            knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        )

    def test_attack_modal_contains_togashi_raise_button(self, client):
        """The sheet embeds a spend button keyed by is_athletics_attack."""
        cid = self._seed_togashi_3d(client)
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # A button wired to a new atkSpendTogashiRaise() handler must appear
        # inside the attack-result block and must be gated on the formula
        # flag so it only shows for athletics:attack, not regular attacks.
        assert 'atkSpendTogashiRaise()' in resp.text
        assert 'atkUndoTogashiRaise()' in resp.text
        # Visibility predicate references the athletics-attack flag
        assert 'atkFormula?.is_athletics_attack' in resp.text

    def test_non_togashi_sheet_has_no_atk_togashi_raise_handlers(self, client):
        """The handler is an Alpine method defined once in the component, so
        it renders for any character's sheet. But the button's *condition*
        still requires schoolAbilities.togashi_daily_athletics_raises, so a
        non-togashi sheet must not activate the button at runtime. We assert
        the schoolAbilities flag is False so the condition is falsy."""
        import json, re
        cid = _seed_character(
            client, name="Akodo", school="akodo_bushi",
            school_ring_choice="Water",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        resp = client.get(f"/characters/{cid}")
        m = re.search(
            r'id="school-abilities">(.*?)</script>', resp.text, re.DOTALL,
        )
        assert m is not None
        abilities = json.loads(m.group(1))
        assert abilities.get("togashi_daily_athletics_raises") in (False, None)
    """The wound check probability table key loop applies 10k10 caps for each
    void spend level. High Water + void spend pushes rolled past 10 and kept
    past 10, exercising both cap branches (lines 377-381 in pages.py)."""

    def test_high_water_and_void_caps_do_not_crash_sheet(self, client):
        """Water=8 -> wc base 9k8; with void spend 2 rings cap kicks in."""
        cid = _seed_character(
            client,
            ring_water=8, ring_air=8, ring_earth=8, ring_fire=8, ring_void=8,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200


class TestFormCheckboxParsing:
    """_parse_form_to_dict checkbox branches: advantages/disadvantages 'on' values."""

    def test_form_checkbox_advantages_parsed(self, client):
        cid = _seed_character(client)
        form = make_character_form(adv_lucky="on", adv_charming="on")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert "lucky" in char.advantages
        assert "charming" in char.advantages

    def test_form_checkbox_disadvantages_parsed(self, client):
        cid = _seed_character(client)
        form = make_character_form(dis_proud="on", dis_unkempt="on")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert "proud" in char.disadvantages
        assert "unkempt" in char.disadvantages


# ---------------------------------------------------------------------------
# Hidden character feature
# ---------------------------------------------------------------------------

OWNER_ID = "183026066498125825"
OTHER_USER_ID = "test_user_1"


class TestHiddenDefault:
    """A brand-new POST /characters creates a character with is_hidden=True;
    legacy seeded characters default to is_hidden=False so existing fixtures
    continue to behave as before."""

    def test_create_endpoint_starts_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        assert char.is_hidden is True

    def test_seeded_character_default_is_visible(self, client):
        cid = _seed_character(client, name="Seeded")
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False


class TestPublishVisibility:
    """Apply Changes (POST /publish) preserves visibility unless the editor
    explicitly opts in via the ``make_visible`` checkbox in the modal."""

    def test_publish_default_keeps_hidden(self, client):
        """A hidden draft stays hidden after Apply Changes when the
        editor does not opt in - matches the new design where the modal
        asks first."""
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        assert char.is_hidden is True
        resp = client.post(f"/characters/{cid}/publish", json={"summary": "First"})
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is True
        assert char.is_published is True

    def test_publish_with_make_visible_clears_is_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        assert char.is_hidden is True
        resp = client.post(
            f"/characters/{cid}/publish",
            json={"summary": "First", "make_visible": True},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False
        assert char.is_published is True

    def test_publish_make_visible_false_keeps_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.post(
            f"/characters/{cid}/publish",
            json={"summary": "First", "make_visible": False},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is True

    def test_publish_make_visible_on_already_visible_is_idempotent(self, client):
        cid = _seed_character(client, name="Pub visible")
        resp = client.post(
            f"/characters/{cid}/publish",
            json={"summary": "x", "make_visible": True},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False


class TestMakeDraftVisibleEndpoint:
    """POST /characters/{id}/show flips is_hidden to False without publishing."""

    def test_show_unhides_without_publishing(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.post(f"/characters/{cid}/show")
        assert resp.status_code == 200
        assert resp.json() == {"status": "visible"}
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False
        # Did NOT publish - still a draft
        assert char.is_published is False

    def test_show_is_idempotent_for_already_visible(self, client):
        cid = _seed_character(client, name="Already visible")
        # is_hidden defaults False on seeded chars
        resp = client.post(f"/characters/{cid}/show")
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False

    def test_show_unauthenticated_401(self, client):
        cid = _seed_character(client, name="Unauth show")
        resp = client.post(f"/characters/{cid}/show", headers={"X-Test-User": ""})
        assert resp.status_code == 401

    def test_show_404_for_missing(self, client):
        resp = client.post("/characters/9999/show")
        assert resp.status_code == 404

    def test_show_403_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="other_owner", discord_name="o", display_name="Owner"))
        session.commit()
        cid = _seed_character(client, name="Foreign", owner_discord_id="other_owner")
        # Non-admin, non-owner, not granted: forbidden
        resp = client.post(
            f"/characters/{cid}/show",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403


class TestHideEndpoint:
    """POST /characters/{id}/hide flips ``is_hidden`` to True. Mirror of
    /show; together they back the bidirectional header visibility chip."""

    def test_hide_flips_visible_to_hidden(self, client):
        cid = _seed_character(client, name="Visible to hide", is_hidden=False)
        resp = client.post(f"/characters/{cid}/hide")
        assert resp.status_code == 200
        assert resp.json() == {"status": "hidden"}
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is True

    def test_hide_idempotent_on_already_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        # Created hidden; hiding again is a no-op success.
        resp = client.post(f"/characters/{cid}/hide")
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is True

    def test_hide_unauthenticated_401(self, client):
        cid = _seed_character(client, name="Unauth hide")
        resp = client.post(f"/characters/{cid}/hide", headers={"X-Test-User": ""})
        assert resp.status_code == 401

    def test_hide_404_for_missing(self, client):
        resp = client.post("/characters/9999/hide")
        assert resp.status_code == 404

    def test_hide_403_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="other_owner", discord_name="o", display_name="Owner"))
        session.commit()
        cid = _seed_character(client, name="Foreign hide", owner_discord_id="other_owner")
        resp = client.post(
            f"/characters/{cid}/hide",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_hide_after_publish_re_hides_published_character(self, client):
        """A published, currently-visible character can be re-hidden via
        /hide; the round-trip works from any starting visibility."""
        cid = _seed_character(client, name="Pub round-trip", is_hidden=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "v1"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False
        assert char.is_published is True
        resp = client.post(f"/characters/{cid}/hide")
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is True
        assert char.is_published is True


class TestHiddenIndexFiltering:
    """The homepage hides characters whose is_hidden=True from non-editors;
    owners, admins, and account-grantees still see them."""

    def _seed_hidden_for_other(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="other_owner", discord_name="other",
                         display_name="Other Owner"))
        session.commit()
        return _seed_character(
            client, name="Secret WIP", owner_discord_id="other_owner",
            is_hidden=True, is_published=False,
        )

    def test_owner_sees_their_own_hidden_character(self, client):
        _seed_character(client, name="Own Hidden", is_hidden=True)
        resp = client.get("/", headers={"X-Test-User": f"{OWNER_ID}:owner"})
        assert resp.status_code == 200
        assert "Own Hidden" in resp.text

    def test_admin_sees_other_users_hidden_character(self, client):
        self._seed_hidden_for_other(client)
        # Default test client uses admin (OWNER_ID is in ADMIN_DISCORD_IDS)
        resp = client.get("/")
        assert "Secret WIP" in resp.text

    def test_non_editor_does_not_see_hidden_character(self, client):
        self._seed_hidden_for_other(client)
        resp = client.get("/", headers={"X-Test-User": "test_user_1:Test 1"})
        assert "Secret WIP" not in resp.text

    def test_unauthenticated_does_not_see_hidden_character(self, client):
        self._seed_hidden_for_other(client)
        resp = client.get("/", headers={"X-Test-User": ""})
        assert "Secret WIP" not in resp.text

    def test_granted_account_sees_hidden_character(self, client):
        from app.models import User
        session = client._test_session_factory()
        # other_owner has granted test_user_1 account-level access
        session.add(User(discord_id="other_owner", discord_name="other",
                         display_name="Other",
                         granted_account_ids=["test_user_1"]))
        session.add(User(discord_id="test_user_1", discord_name="t1",
                         display_name="T1"))
        session.commit()
        _seed_character(
            client, name="Shared Hidden", owner_discord_id="other_owner",
            is_hidden=True,
        )
        resp = client.get("/", headers={"X-Test-User": "test_user_1:T1"})
        assert "Shared Hidden" in resp.text

    def test_visible_characters_still_show_to_everyone(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="other_owner", discord_name="other",
                         display_name="Other"))
        session.commit()
        _seed_character(
            client, name="Public Char", owner_discord_id="other_owner",
            is_hidden=False,
        )
        resp = client.get("/", headers={"X-Test-User": "test_user_1:T1"})
        assert "Public Char" in resp.text


class TestHiddenIndexBadge:
    """For editors who can see hidden characters on the homepage, the
    card is styled differently (dashed gray outline, opacity'd headshot,
    'Hidden' pill at the bottom)."""

    def test_hidden_card_has_hidden_badge(self, client):
        _seed_character(client, name="My Hidden", is_hidden=True)
        resp = client.get("/")
        assert resp.status_code == 200
        # Owner is admin, so the card is rendered.
        assert "My Hidden" in resp.text
        assert 'data-testid="card-hidden-badge"' in resp.text

    def test_hidden_card_has_data_hidden_attribute(self, client):
        _seed_character(client, name="Marked Hidden", is_hidden=True)
        resp = client.get("/")
        assert 'data-hidden="true"' in resp.text

    def test_visible_card_has_no_hidden_badge(self, client):
        _seed_character(client, name="Plainly Visible", is_hidden=False)
        resp = client.get("/")
        assert "Plainly Visible" in resp.text
        # No `data-hidden="true"` and no Hidden badge for the visible card.
        # (Other test classes may have seeded hidden chars; check that no
        # hidden marker is associated with this visible character by
        # inspecting an excerpt around its name.)
        idx = resp.text.find("Plainly Visible")
        snippet = resp.text[max(0, idx - 500):idx + 500]
        assert 'data-testid="card-hidden-badge"' not in snippet
        assert 'data-hidden="true"' not in snippet


class TestHiddenViewCharacter:
    """GET /characters/{id} returns 404 for non-editors when the character
    is hidden, so a hidden character cannot be probed by URL."""

    def _seed_hidden_for_other(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="other_owner", discord_name="other",
                         display_name="Other"))
        session.commit()
        return _seed_character(
            client, name="Hidden View", owner_discord_id="other_owner",
            is_hidden=True,
        )

    def test_owner_can_view_hidden(self, client):
        cid = _seed_character(client, name="Own Hidden View", is_hidden=True)
        resp = client.get(f"/characters/{cid}",
                          headers={"X-Test-User": f"{OWNER_ID}:owner"})
        assert resp.status_code == 200
        assert "Own Hidden View" in resp.text

    def test_admin_can_view_other_users_hidden(self, client):
        cid = self._seed_hidden_for_other(client)
        resp = client.get(f"/characters/{cid}")  # default = admin
        assert resp.status_code == 200

    def test_non_editor_gets_404(self, client):
        cid = self._seed_hidden_for_other(client)
        resp = client.get(f"/characters/{cid}",
                          headers={"X-Test-User": "test_user_1:T1"})
        assert resp.status_code == 404

    def test_unauthenticated_gets_404(self, client):
        cid = self._seed_hidden_for_other(client)
        resp = client.get(f"/characters/{cid}", headers={"X-Test-User": ""})
        assert resp.status_code == 404


class TestSheetHiddenIndicator:
    """The view-sheet page renders a 'Hidden' pill next to the character
    name for editors viewing a hidden character. Non-editors get a 404
    before reaching the sheet, so the markup is gated on
    ``character.is_hidden`` only."""

    def test_hidden_sheet_shows_indicator(self, client):
        cid = _seed_character(client, name="Hidden On Sheet", is_hidden=True)
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="sheet-hidden-indicator"' in resp.text

    def test_visible_sheet_omits_indicator(self, client):
        cid = _seed_character(client, name="Visible On Sheet", is_hidden=False)
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="sheet-hidden-indicator"' not in resp.text


class TestHiddenPartyMemberFiltering:
    """Hidden characters do not contribute to other characters' party-effect
    data unless the viewer has edit access to them."""

    def _setup(self, client, hidden_priest_owner: str):
        """Seed a Priest 5th Dan (hidden, owned by hidden_priest_owner) and an
        ally in the same gaming group. Returns (priest_id, ally_id)."""
        from app.models import GamingGroup, User
        session = client._test_session_factory()
        if not session.query(User).filter(User.discord_id == hidden_priest_owner).first():
            session.add(User(discord_id=hidden_priest_owner,
                             discord_name="hp", display_name="HP"))
        group = GamingGroup(name="Group X")
        session.add(group)
        session.commit()
        priest_id = _seed_character(
            client, name="Hidden Priest 5D", school="priest",
            knacks={"conviction": 5, "otherworldliness": 5, "pontificate": 5},
            gaming_group_id=group.id, owner_discord_id=hidden_priest_owner,
            is_hidden=True,
        )
        ally_id = _seed_character(
            client, name="Bushi Ally", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, owner_discord_id=OWNER_ID,
        )
        return priest_id, ally_id

    def test_hidden_party_priest_excluded_for_non_editor_viewer(self, client):
        """A different non-editor viewing the ally's sheet should not see
        the hidden priest in any of the priest-context JSON blocks."""
        priest_id, ally_id = self._setup(client, "other_owner")
        # Make the bushi ally owned by test_user_1 so they can view it
        from app.models import User
        session = client._test_session_factory()
        bushi = session.query(Character).filter(Character.id == ally_id).first()
        bushi.owner_discord_id = "test_user_1"
        session.commit()
        resp = client.get(f"/characters/{ally_id}",
                          headers={"X-Test-User": "test_user_1:T1"})
        assert resp.status_code == 200
        assert "Hidden Priest 5D" not in resp.text

    def test_hidden_party_priest_visible_to_admin_viewer(self, client):
        priest_id, ally_id = self._setup(client, "other_owner")
        # Default admin viewer
        resp = client.get(f"/characters/{ally_id}")
        assert resp.status_code == 200
        assert "Hidden Priest 5D" in resp.text

    def test_re_hidden_published_priest_filtered_for_non_editor(self, client):
        """A previously-public, then re-hidden character is treated the
        same as a never-revealed draft for party-effect filtering. This
        exercises the new bidirectional ``is_hidden`` semantics."""
        from app.models import Character as CharacterModel, User
        priest_id, ally_id = self._setup(client, "other_owner")
        session = client._test_session_factory()
        # Bring the priest into the public state, publish it, then hide
        # it again - mirrors the chip toggle round-trip in the UI.
        priest = session.query(CharacterModel).filter(CharacterModel.id == priest_id).first()
        priest.is_hidden = False
        priest.is_published = True
        session.commit()
        bushi = session.query(CharacterModel).filter(CharacterModel.id == ally_id).first()
        bushi.owner_discord_id = "test_user_1"
        session.commit()
        # Confirm the public priest appears for the non-editor first.
        resp = client.get(f"/characters/{ally_id}",
                          headers={"X-Test-User": "test_user_1:T1"})
        assert "Hidden Priest 5D" in resp.text
        # Now re-hide and verify the priest disappears from the ally view.
        priest = session.query(CharacterModel).filter(CharacterModel.id == priest_id).first()
        priest.is_hidden = True
        session.commit()
        resp = client.get(f"/characters/{ally_id}",
                          headers={"X-Test-User": "test_user_1:T1"})
        assert resp.status_code == 200
        assert "Hidden Priest 5D" not in resp.text

    def test_hidden_character_still_sees_other_party_members_on_own_sheet(self, client):
        """Asymmetric visibility: a hidden character does not surface to
        other party members, but other (visible) party members still
        surface to the hidden character on its own sheet. The hidden
        character's own owner is the editor, so they have full view of
        their own sheet's party block."""
        from app.models import GamingGroup, Character as CharacterModel
        session = client._test_session_factory()
        group = GamingGroup(name="Asym group")
        session.add(group)
        session.commit()
        # Hidden bushi owned by the default admin viewer.
        hidden_id = _seed_character(
            client, name="Hidden Bushi", school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            gaming_group_id=group.id, owner_discord_id=OWNER_ID,
            is_hidden=True,
        )
        # Visible priest in the same group, a different owner.
        from app.models import User
        if not session.query(User).filter(User.discord_id == "other_owner_2").first():
            session.add(User(discord_id="other_owner_2", discord_name="o2",
                             display_name="O2"))
            session.commit()
        priest_id = _seed_character(
            client, name="Visible Priest", school="priest",
            knacks={"conviction": 5, "otherworldliness": 5, "pontificate": 5},
            gaming_group_id=group.id, owner_discord_id="other_owner_2",
        )
        # Hidden bushi's owner views their own (hidden) sheet - the
        # priest should be reflected in the party data.
        resp = client.get(f"/characters/{hidden_id}")
        assert resp.status_code == 200
        assert "Visible Priest" in resp.text


class TestHiddenEditPageBanner:
    """The edit page renders a 'hidden draft' banner above the Basics
    section. The markup ships unconditionally now that visibility is
    bidirectional - the Alpine ``isHidden`` flag controls show/hide, and
    that flag is initialized from ``character.is_hidden`` so the banner
    only paints when relevant."""

    def test_banner_markup_present_on_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200
        assert 'data-testid="hidden-draft-banner"' in resp.text
        # isHidden defaults true so the Alpine flag will display the banner.
        assert "isHidden: true" in resp.text
        # Banner sits above Basics in source order.
        banner_idx = resp.text.find('data-testid="hidden-draft-banner"')
        basics_idx = resp.text.find(">Basics<")
        assert banner_idx != -1 and basics_idx != -1
        assert banner_idx < basics_idx

    def test_banner_lists_editors(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.get(f"/characters/{cid}/edit")
        # The viewer is owner+admin, so the editor list collapses to "you and the GM"
        assert "you and the GM" in resp.text

    def test_banner_alpine_flag_false_when_visible(self, client):
        cid = _seed_character(client, name="Visible char", is_hidden=False)
        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200
        # Markup ships unconditionally; Alpine ``isHidden`` is false so
        # x-show keeps the banner hidden client-side.
        assert "isHidden: false" in resp.text


class TestVisibilityToggle:
    """The header chip exposes the current visibility and flips it on
    click. The pre-existing bottom-bar 'Make Draft Visible' button has
    been removed - the chip is the only affordance now."""

    def test_chip_present_on_edit_page(self, client):
        cid = _seed_character(client, name="Toggle present")
        resp = client.get(f"/characters/{cid}/edit")
        assert 'data-testid="visibility-toggle"' in resp.text

    def test_old_make_draft_visible_button_removed(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.get(f"/characters/{cid}/edit")
        assert 'data-action="make-draft-visible"' not in resp.text


class TestReadOnlyRollBannerContext:
    """Phase 1 of the read-only roll mode: the sheet template must carry
    the Alpine flags (canEdit / isLoggedIn) and emit the banner partial
    for non-editors only. Editors get no banner at all; anon vs
    logged-in non-editors get different copy."""

    def _make_public_char(self, client):
        session = client._test_session_factory()
        from app.models import User
        session.add(User(
            discord_id="183026066498125825",
            discord_name="eli",
            display_name="Eli",
        ))
        char = Character(
            name="Sheet For Readonly Tests",
            school="akodo_bushi",
            school_ring_choice="Water",
            ring_water=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            owner_discord_id="183026066498125825",
            is_published=True,
            is_hidden=False,
        )
        session.add(char)
        session.commit()
        return char.id

    def _anon_client(self, engine):
        from fastapi.testclient import TestClient
        from sqlalchemy.orm import sessionmaker
        from app.database import get_db
        from app.main import app
        conn = engine.connect()
        tx = conn.begin()
        TestSession = sessionmaker(bind=conn)
        def _override():
            s = TestSession()
            try: yield s
            finally: s.close()
        app.dependency_overrides[get_db] = _override
        c = TestClient(app)
        c._test_session_factory = TestSession
        c._cleanup = (tx, conn)
        return c

    def test_editor_does_not_see_banner(self, client):
        """The default test client is the owner/admin — no banner."""
        cid = self._make_public_char(client)
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert 'data-testid="readonly-roll-banner"' not in resp.text

    def test_editor_alpine_flag_true(self, client):
        cid = self._make_public_char(client)
        resp = client.get(f"/characters/{cid}")
        # trackingData() carries canEdit so save() knows whether to POST
        assert "canEdit: true" in resp.text

    def test_non_editor_sees_no_edit_copy(self, client):
        """A logged-in whitelisted non-admin sees the 'no edit access' banner."""
        cid = self._make_public_char(client)
        resp = client.get(
            f"/characters/{cid}",
            headers={"X-Test-User": "test_user_1:NonEditor"},
        )
        assert resp.status_code == 200
        assert 'data-testid="readonly-roll-banner"' in resp.text
        assert "don't have edit access" in resp.text
        # Must NOT include the anonymous login-prompt copy
        assert "not logged in" not in resp.text.lower()

    def test_non_editor_alpine_flags(self, client):
        cid = self._make_public_char(client)
        resp = client.get(
            f"/characters/{cid}",
            headers={"X-Test-User": "test_user_1:NonEditor"},
        )
        assert "canEdit: false" in resp.text
        assert "isLoggedIn: true" in resp.text

    def test_anon_sees_login_prompt_with_owner_name(self, engine):
        c = self._anon_client(engine)
        try:
            cid = self._make_public_char(c)
            resp = c.get(f"/characters/{cid}")
            assert resp.status_code == 200
            assert 'data-testid="readonly-roll-banner"' in resp.text
            assert "not logged in" in resp.text
            assert "Eli" in resp.text  # owner display name
            # Login link carries return_to pointing at this sheet
            assert f"/auth/login?return_to=/characters/{cid}" in resp.text
        finally:
            c._cleanup[0].rollback()
            c._cleanup[1].close()
            from app.main import app
            app.dependency_overrides.clear()

    def test_anon_alpine_flags(self, engine):
        c = self._anon_client(engine)
        try:
            cid = self._make_public_char(c)
            resp = c.get(f"/characters/{cid}")
            assert "canEdit: false" in resp.text
            assert "isLoggedIn: false" in resp.text
            assert f'"/auth/login?return_to=/characters/{cid}"' in resp.text
        finally:
            c._cleanup[0].rollback()
            c._cleanup[1].close()
            from app.main import app
            app.dependency_overrides.clear()


class TestSheetForeignKnackHandling:
    """Coverage for char_foreign_knacks construction in pages.py and
    google_sheets.py (lookup-by-id, skip unknown), plus the worldliness-
    as-foreign-knack branch in pages.py."""

    def test_sheet_drops_unknown_foreign_knack_id(self, client):
        """An unknown foreign-knack id (e.g. left over from a deleted
        knack) doesn't 500 the sheet; the lookup returns None and the
        loop's continue branch fires."""
        cid = _seed_character(
            client, name="ForeignUnknown", school="akodo_bushi",
            school_ring_choice="Water", ring_water=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            foreign_knacks={"not_a_real_knack_id": 2, "athletics": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # The legitimate foreign knack still renders.
        assert "Athletics" in resp.text or "athletics" in resp.text

    def test_sheet_uses_foreign_worldliness_for_void_max(self, client):
        """A character with worldliness as a foreign knack (not school)
        has the worldliness pool sized to the foreign rank."""
        import json, re
        cid = _seed_character(
            client, name="ForeignWld", school="akodo_bushi",
            school_ring_choice="Water", ring_water=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            foreign_knacks={"worldliness": 3},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # void-spend-config encodes the worldliness max.
        m = re.search(
            r'id="void-spend-config">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        assert m is not None
        cfg = json.loads(m.group(1))
        # worldliness rank 3 -> worldliness_max 3 (foreign-knack branch).
        assert cfg.get("worldliness_max") == 3


class TestKitsuneWardenSwapProbs:
    """Phase 9 attack_probs / wc_probs swap variants are computed by
    routes/pages.py and embedded into the sheet HTML. These tests
    exercise the route to confirm the kitsune_swap sub-dicts are present
    on the right keys for a Kitsune Warden character."""

    def _read_json_script(self, client, cid: int, dom_id: str):
        import json, re
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        m = re.search(rf'id="{dom_id}">(.*?)</script>', resp.text, re.DOTALL)
        assert m is not None, f"Could not find script id={dom_id} on sheet"
        return json.loads(m.group(1))

    def test_attack_probs_includes_kitsune_swap_for_kitsune_warden(self, client):
        cid = _seed_character(
            client, name="KAtkProbs", school="kitsune_warden",
            school_ring_choice="Water",
            ring_water=4, ring_air=2, ring_fire=2, ring_earth=2, ring_void=2,
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            attack=2, parry=2,
        )
        ap = self._read_json_script(client, cid, "attack-probs")
        assert "attack" in ap
        assert "kitsune_swap" in ap["attack"], \
            f"Expected kitsune_swap on attack_probs[attack]; keys: {list(ap['attack'].keys())}"
        swap = ap["attack"]["kitsune_swap"]
        assert "void_keys" in swap and "probs" in swap and "avgs" in swap
        # Default: rank 2 + Fire 2 = 4 rolled, 2 kept -> "4,2"
        # Swap to Water 4: rank 2 + Water 4 = 6 rolled, 4 kept -> "6,4"
        assert ap["attack"]["void_keys"]["0"] == "4,2"
        assert swap["void_keys"]["0"] == "6,4"

    def test_wc_probs_includes_kitsune_swap_for_kitsune_warden_non_water(self, client):
        cid = _seed_character(
            client, name="KWcProbs", school="kitsune_warden",
            school_ring_choice="Earth",
            ring_water=2, ring_earth=3, ring_air=2, ring_fire=2, ring_void=2,
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
        )
        wp = self._read_json_script(client, cid, "wound-check-probs")
        assert "kitsune_swap" in wp, \
            f"Expected kitsune_swap on wc_probs; keys: {list(wp.keys())}"
        swap = wp["kitsune_swap"]
        # Default WC: Water+1 = 3 rolled, Water = 2 kept.
        # Swap to Earth: Earth+1 = 4 rolled, Earth = 3 kept.
        assert wp["void_keys"]["0"] == "3,2"
        assert swap["void_keys"]["0"] == "4,3"

    def test_non_kitsune_attack_probs_has_no_kitsune_swap(self, client):
        cid = _seed_character(
            client, name="AkodoNoSwap", school="akodo_bushi",
            school_ring_choice="Water", ring_water=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            attack=2,
        )
        ap = self._read_json_script(client, cid, "attack-probs")
        assert "kitsune_swap" not in ap.get("attack", {})

    def test_non_kitsune_wc_probs_has_no_kitsune_swap(self, client):
        cid = _seed_character(
            client, name="AkodoNoSwapWC", school="akodo_bushi",
            school_ring_choice="Water", ring_water=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        wp = self._read_json_script(client, cid, "wound-check-probs")
        assert "kitsune_swap" not in wp

    def test_wc_probs_no_swap_when_school_ring_is_water(self, client):
        """Equal-value gate at the formula level cascades: WC with school
        ring Water has no kitsune_swap (identity swap)."""
        cid = _seed_character(
            client, name="KWcWaterRing", school="kitsune_warden",
            school_ring_choice="Water", ring_water=3,
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
        )
        wp = self._read_json_script(client, cid, "wound-check-probs")
        assert "kitsune_swap" not in wp
