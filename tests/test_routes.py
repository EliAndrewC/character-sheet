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

    def test_index_lists_characters(self, client):
        _seed_character(client, name="Akodo Toturi")

        resp = client.get("/")
        assert resp.status_code == 200
        assert "Akodo Toturi" in resp.text


class TestCreatePage:
    def test_create_page_loads(self, client):
        resp = client.get("/characters/new")
        assert resp.status_code == 200
        assert "Create Character" in resp.text

    def test_create_page_has_schools(self, client):
        resp = client.get("/characters/new")
        assert "Akodo Bushi" in resp.text
        assert "Bayushi Bushi" in resp.text

    def test_create_page_has_skills(self, client):
        resp = client.get("/characters/new")
        assert "Bragging" in resp.text
        assert "Precepts" in resp.text


class TestCreateCharacter:
    def test_create_redirects(self, client):
        form = make_character_form(name="New Character")
        resp = client.post("/characters", data=form, follow_redirects=False)
        assert resp.status_code == 303
        assert "/characters/" in resp.headers["location"]

    def test_create_persists(self, client):
        form = make_character_form(name="Persisted Samurai")
        client.post("/characters", data=form)

        char = query_db(client).filter(Character.name == "Persisted Samurai").first()
        assert char is not None
        assert char.school == "akodo_bushi"
        assert char.school_ring_choice == "Water"

    def test_create_stores_rings(self, client):
        form = make_character_form(ring_fire="4", ring_water="3")
        client.post("/characters", data=form)

        char = query_db(client).first()
        assert char.ring_fire == 4
        assert char.ring_water == 3
        assert char.ring_air == 2

    def test_create_stores_skills(self, client):
        form = make_character_form(skill_precepts="3", skill_bragging="1")
        client.post("/characters", data=form)

        char = query_db(client).first()
        assert char.skills["precepts"] == 3
        assert char.skills["bragging"] == 1

    def test_create_stores_advantages(self, client):
        form = make_character_form(adv_lucky="on", adv_fierce="on")
        client.post("/characters", data=form)

        char = query_db(client).first()
        assert "lucky" in char.advantages
        assert "fierce" in char.advantages

    def test_create_stores_disadvantages(self, client):
        form = make_character_form(dis_proud="on")
        client.post("/characters", data=form)

        char = query_db(client).first()
        assert "proud" in char.disadvantages


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
        assert "Bayushi Bushi" in resp.text

    def test_view_shows_xp(self, client):
        cid = _seed_character(
            client,
            name="XP Test",
            ring_fire=3,
        )

        resp = client.get(f"/characters/{cid}")
        assert "Total Spent" in resp.text
        assert "Remaining" in resp.text

    def test_view_nonexistent_404(self, client):
        resp = client.get("/characters/999")
        assert resp.status_code == 404


class TestEditCharacter:
    def test_edit_page_loads(self, client):
        cid = _seed_character(client, name="Edit Test")

        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200
        assert "Edit: Edit Test" in resp.text

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


class TestXPCalcPartial:
    def test_xp_calc_returns_breakdown(self, client):
        form = make_character_form(ring_fire="3", skill_precepts="3")
        resp = client.post("/characters/api/xp-calc", data=form)
        assert resp.status_code == 200
        assert "Remaining" in resp.text

    def test_xp_calc_shows_overspend(self, client):
        form = make_character_form(
            ring_air="5", ring_fire="5", ring_earth="5",
            ring_water="5", ring_void="5", starting_xp="10",
        )
        resp = client.post("/characters/api/xp-calc", data=form)
        assert resp.status_code == 200
        assert "text-red-600" in resp.text  # negative remaining gets red styling


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
