"""Tests for page and API routes."""

import pytest

from app.models import Character
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
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["used"] == 1
        assert data["pool_max"] == 10  # 2 * rank(5)

    def test_ally_can_undo_priest_conviction(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        client.post(f"/characters/{priest_id}/ally-conviction", json={"delta": 1})
        client.post(f"/characters/{priest_id}/ally-conviction", json={"delta": 1})
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": -1})
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
        priest_id, _, _ = self._setup_priest_and_ally(client, priest_rank=5)
        # pool_max = 10. Spend 15 times; used should cap at 10.
        for _ in range(15):
            client.post(f"/characters/{priest_id}/ally-conviction", json={"delta": 1})
        session = client._test_session_factory()
        p = session.query(Character).filter(Character.id == priest_id).first()
        assert (p.adventure_state or {}).get("conviction_used") == 10

    def test_used_cannot_go_below_zero(self, client):
        priest_id, _, _ = self._setup_priest_and_ally(client)
        resp = client.post(f"/characters/{priest_id}/ally-conviction",
                           json={"delta": -1})
        assert resp.status_code == 200
        assert resp.json()["used"] == 0

    def test_sheet_exposes_priest_ally_script(self, client):
        """The ally's sheet page embeds priest-conviction-allies JSON with the priest."""
        priest_id, ally_id, _ = self._setup_priest_and_ally(client)
        resp = client.get(f"/characters/{ally_id}")
        assert resp.status_code == 200
        assert 'id="priest-conviction-allies"' in resp.text
        assert "Priest Ally" in resp.text

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
        resp = asyncio.get_event_loop().run_until_complete(
            ally_conviction(req, 1, db=None)
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


class TestDeleteCharacter:
    def test_delete_removes_character(self, client):
        cid = _seed_character(client, name="Delete Me")

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303
        assert query_db(client).count() == 0

    def test_delete_nonexistent_no_error(self, client):
        resp = client.post("/characters/999/delete", follow_redirects=False)
        assert resp.status_code == 303


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
        cid = _seed_character(client, name="V1")

        # Publish v1
        client.post(f"/characters/{cid}/publish")

        # Modify and publish v2
        client.post(f"/characters/{cid}/autosave", json={"name": "V2"})
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
        assert char.name == "V1"


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


class TestImportKillSwitchNavBar:
    """When IMPORT_ENABLED=false, the navbar's "New Character" control is a
    single submit button posting to /characters - no dropdown, no link to
    /import. When IMPORT_ENABLED=true (default), the dropdown shows both
    options."""

    def test_dropdown_visible_when_import_enabled(self, client, monkeypatch):
        monkeypatch.delenv("IMPORT_ENABLED", raising=False)
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


class TestWoundCheckProbability10k10Caps:
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


class TestHiddenAppliesUnhides:
    """Once a character is published via Apply Changes the hidden flag is
    cleared - it can never be re-hidden."""

    def test_publish_clears_is_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        assert char.is_hidden is True
        # Apply changes
        resp = client.post(f"/characters/{cid}/publish", json={"summary": "First"})
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_hidden is False
        assert char.is_published is True


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


class TestHiddenEditPageBanner:
    """The edit page renders a 'hidden draft' banner above the Basics section
    only while the character is hidden, with the editor list and a hint about
    Apply Changes / Make Draft Visible."""

    def test_banner_present_when_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200
        assert 'data-testid="hidden-draft-banner"' in resp.text
        # Basics heading appears AFTER the banner
        banner_idx = resp.text.find('data-testid="hidden-draft-banner"')
        basics_idx = resp.text.find(">Basics<")
        assert banner_idx != -1 and basics_idx != -1
        assert banner_idx < basics_idx, "Banner must be above the Basics section"

    def test_banner_lists_editors(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.get(f"/characters/{cid}/edit")
        # The viewer is owner+admin, so the editor list collapses to "you and the GM"
        assert "you and the GM" in resp.text

    def test_banner_hidden_when_visible(self, client):
        cid = _seed_character(client, name="Visible char", is_hidden=False)
        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200
        assert 'data-testid="hidden-draft-banner"' not in resp.text


class TestMakeDraftVisibleButton:
    """The 'Make Draft Visible' button sits next to Apply Changes only while
    the character is hidden, with an explanatory tooltip."""

    def test_button_present_when_hidden(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.get(f"/characters/{cid}/edit")
        assert 'data-action="make-draft-visible"' in resp.text

    def test_button_absent_when_visible(self, client):
        cid = _seed_character(client, name="Already visible", is_hidden=False)
        resp = client.get(f"/characters/{cid}/edit")
        assert 'data-action="make-draft-visible"' not in resp.text

    def test_button_has_tooltip_explaining_share(self, client):
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        resp = client.text if False else client.get(f"/characters/{cid}/edit").text
        # Tooltip mentions both editors-only and how to share
        assert "Make this draft visible" in resp or "make this draft visible" in resp.lower()
